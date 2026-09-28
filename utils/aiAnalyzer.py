import re
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable
from functools import partial
from utils.http_client import http
from utils.logging import logger
from utils.webSearch import searchWithDuckDuckGo
from settings import ANALYSIZE_API_KEY, ANALYSIZE_API_URL, ANALYSIZE_API_MODEL
from utils.akshare import getGlobalShortInfoFromSina, getGlobalShortInfoFromThs, getStockResearchReport, getStockFinanceReportFromSina, getShortInfoMorning
from utils.tushare import getStockIncome, getStockEarnings, getStockStatistics, getStockDrivers, getStockHistoryValuation, getStockRatings, getMarketOverview, getStockEarningStatus
from utils.longbridge import getNewsDetail, getStockNews, getStockReport, getStockCalcIndex, getStockCapital, getStockValuation, getStockFinancialStatement, getStockFinancialAnalysis


k_line_comment = '''
【字段含义说明】
day：交易日期；current_price：收盘价；volume：成交量；fund：主力资金净流入(万)；turnover_rate：换手率；ma_five/ten/twenty：均线；qrr：量比；diff/dea：MACD；k/d/j：KDJ；boll_up/low：布林带{}\n
【K线数据】
'''


async def search_and_extract(query: str, max_results: int = 5) -> str:
    """DuckDuckGo 联网搜索兜底"""
    try:
        content = await searchWithDuckDuckGo(query, logger=logger, df='w', max_results=max_results)
        return json.dumps(content, ensure_ascii=False) if content else ""
    except Exception as e:
        return f"Search Exception: {str(e)}"


async def generate_search_keyword(context: str, dimension: str) -> str:
    """当 API 数据缺失时，调用 LLM 动态生成精准的搜索关键词"""
    prompt = f"你是一个金融搜索专家。为了分析【{context}】的【{dimension}】维度，请生成1个最精准、最容易搜到最新资讯的中文搜索关键词（不超过12个字）。只返回关键词本身，不要任何解释。"
    messages = [{"role": "user", "content": prompt}]
    try:
        # 使用极简配置快速生成
        headers = {"Authorization": f"Bearer {ANALYSIZE_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": ANALYSIZE_API_MODEL, "messages": messages, "temperature": 0.1, "max_tokens": 20}
        resp = await http.post(f"{ANALYSIZE_API_URL}/chat/completions", json_data=payload, headers=headers)
        if resp.status_code == 200:
            keyword = json.loads(resp.text)["choices"][0]["message"]["content"].strip()
            return keyword.replace('"', '').replace("'", "")
    except:
        pass
    return f"{context} {dimension} 最新消息"


async def chat(messages: list) -> Any:
    """调用 LLM 并强制返回 JSON 对象"""
    headers = {"Authorization": f"Bearer {ANALYSIZE_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": ANALYSIZE_API_MODEL, "messages": messages, "temperature": 0.2, "response_format": {"type": "json_object"}}
    try:
        resp = await http.post(f"{ANALYSIZE_API_URL}/chat/completions", json_data=payload, headers=headers)
        if resp.status_code == 200:
            raw_content = json.loads(resp.text)["choices"][0]["message"]["content"]
            cleaned = re.sub(r'^```json\s*', '', raw_content, flags=re.MULTILINE | re.IGNORECASE)
            cleaned = re.sub(r'```\s*$', '', cleaned, flags=re.MULTILINE).strip()
            return json.loads(cleaned)
        return {"error": f"LLM API Error: HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": f"LLM Exception: {str(e)}"}


class AsyncETFAnalyzer:
    def __init__(self, input_data: dict):
        self.today: str = datetime.now().strftime("%Y-%m-%d")
        self.data = input_data
        self.type: str = input_data.get("type", "stock")    # 类型，stock-股票，etf-ETF
        self.totalFund: float = input_data.get("totalFund", 100000)     # 总资产
        self.availableFund: float = input_data.get("availableFund", 0)  # 可用资产
        self.lastDay: str = input_data.get("lastDay", self.today)   # 前一个交易日日期
        self.name: str = input_data.get("name", "")     # 股票名称
        self.code: str = input_data.get("code", "")     # 股票code
        self.industry: str = input_data.get("industry", "未知行业")     # 行业
        self.concept: str = input_data.get("concept", "无")     # 股票概念
        raw_stocks = input_data.get("stocks", [])
        self.stocks: list[str] = [s.get("code", s) if isinstance(s, dict) else s for s in raw_stocks]   # ETF前10重仓股
        self.kLine: str = input_data.get("k_line", "")      # K线等技术数据
        self.hold: dict = input_data.get("hold", {})    # 当前持仓数据
        self.has_position: bool = bool(self.hold and self.hold.get("shares", 0) > 0)

    async def _fetch_data(self, api_chain: list[Callable], context: str, dimension: str, aggregate: bool = False) -> str:
        """
        数据获取引擎，支持两种模式：\n
        :params aggregate: False (短路模式): 依次尝试，成功一个立即返回；True  (聚合模式): 并发执行所有API，拼接所有成功结果
        """
        if not aggregate:
            # ===== 短路模式：依次尝试 =====
            for api_func in api_chain:
                try:
                    res = await api_func()
                    if self._is_valid_data(res):
                        return res
                except Exception as e:
                    logger.warning(f"[{dimension}] API 调用失败: {e}")
                    logger.error(traceback.format_exc())
        else:
            results = await asyncio.gather(*[api_func() for api_func in api_chain], return_exceptions=True)
            valid_parts = []
            for api_func, res in zip(api_chain, results):
                func_name = getattr(api_func, 'func', api_func).__name__  # 获取函数名用于标注
                if isinstance(res, Exception):
                    logger.warning(f"[{dimension}] {func_name} 调用异常: {res}")
                if self._is_valid_data(res):
                    valid_parts.append(f"[{func_name}]: {res}")

            if valid_parts:
                return "\n\n".join(valid_parts)

        # ===== 所有 API 均失败，触发 AI 动态搜索兜底 =====
        logger.info(f"[{dimension}] API 数据均缺失，触发 AI 动态搜索兜底...")
        keyword = await generate_search_keyword(context, dimension)
        web_data = await search_and_extract(keyword)
        return web_data if web_data else "数据缺失"

    def _is_valid_data(self, res) -> bool:
        """校验数据是否有效"""
        if not res:
            return False
        res_str = str(res).strip()
        if not res_str:
            return False
        invalid_keywords = ["未找到", "Error", "Exception", "数据缺失", "无相关"]
        return not any(kw in res_str for kw in invalid_keywords)

    def _get_dimension_configs(self) -> list[dict]:
        """构建维度配置：包含 API 降级链 和 定制化 Prompt"""
        # 股票与 ETF 的差异化 API 链
        if self.type == "etf":
            configs = [
                {
                    "name": "金融财经新闻",
                    "aggregate": True,
                    "api_chain": [
                        partial(getGlobalShortInfoFromSina, self.lastDay, logger),
                        partial(getNewsDetail, f"{self.industry} 产业政策 监管", logger),
                        partial(getNewsDetail, f"{self.industry} 行业景气度 营收", logger),
                        partial(getGlobalShortInfoFromThs, self.lastDay, logger),
                        partial(getShortInfoMorning, logger)
                    ],
                    "prompt": "你是宏观政策分析师。请基于数据，分析该行业近期的政策导向、监管态度、补贴变化及行业准入限制。重点评估政策是利好还是利空，是否有突发性监管风险。分析行业整体景气度、产能利用率及上下游需求变化。"
                },
                {
                    "name": "技术面与资金流向",
                    "aggregate": True,
                    "api_chain": [
                        partial(getStockCapital, self.code, logger),
                        lambda: self.kLine if self.kLine else ""
                    ],
                    "prompt": "你是技术面分析师。这是ETF的K线数据，充分利用所有指标，特别是价格、份额、溢价率之间的共振，详细分析股票在技术面的表现。"
                }, {
                    "name": "重大事件与市场情绪",
                    "aggregate": True,
                    "api_chain": [
                        partial(searchWithDuckDuckGo, f"{self.industry} 美股 对标 海外", logger),
                        partial(searchWithDuckDuckGo, f"{self.industry} 产业链 上游 原材料 价格", logger),
                        partial(getNewsDetail, f"{self.industry} 行业", logger)
                    ],
                    "prompt": "你是事件驱动分析师。评估这些事件对行业的催化剂作用。"
                }, {
                    "name": "重仓股深度共振",
                    "api_chain": [],
                    "prompt": "你是 ETF 微观结构分析师。请基于前几大重仓股的财务、估值和评级数据，评估它们对整个 ETF 的支撑力度。如果龙头股基本面恶化或估值过高，即使行业利好，也要提示风险。",
                    "is_etf_leaders": True
                }
            ]
        else:
            configs = [
                {
                    "name": "宏观政策与监管环境",
                    "aggregate": True,
                    "api_chain": [
                        partial(getNewsDetail, f"{self.industry} 产业政策 监管", logger),
                        partial(getStockNews, self.code, logger)
                    ],
                    "prompt": "你是宏观政策分析师。请基于数据，分析该行业近期的政策导向、监管态度、补贴变化及行业准入限制。重点评估政策是利好还是利空，是否有突发性监管风险。"
                }, {
                    "name": "基本面与业绩预期",
                    "aggregate": False,
                    "api_chain": [
                        partial(getStockFinancialAnalysis, self.code, logger),
                        partial(getStockFinanceReportFromSina, self.code, logger),
                    ],
                    "prompt": "你是基本面分析师。必须基于数据详细客观的分析股票。"
                }, {
                    "name": "技术面与资金流向",
                    "aggregate": True,
                    "api_chain": [
                        partial(getStockCapital, self.code, logger),
                        partial(getStockValuation, self.code, logger),
                        lambda: self.kLine if self.kLine else ""
                    ],
                    "prompt": "你是技术面与资金面分析师。你需要全面仔细地分析各个指标，你必须识别并规避的假信号：高开低走、长上影线、单日暴涨但量能异常、高换手率+小阳线或上影线（疑似出货）、高位派发、主力资金异常、假金叉、指标高位钝化、上涨动能明显减弱、均线系统未修复、价格远离均线导致短线情绪透支等异常情况。重点分析 PE/PB 的历史分位数（是否低估/高估），与同行对比的溢价/折价情况。"
                }, {
                    "name": "产业链高频与海外映射",
                    "aggregate": True,
                    "api_chain": [
                        partial(searchWithDuckDuckGo, f"{self.industry} 产业链 上游 原材料 价格", logger),
                        partial(searchWithDuckDuckGo, f"{self.industry} 美股 对标 海外", logger),
                    ],
                    "prompt": "你是产业链与全球宏观分析师。分析上游原材料成本变化对利润的挤压或释放。分析海外对标公司（如美股）的走势映射，以及关税、汇率、地缘政治对该行业的潜在影响。"
                }
            ]
        return configs

    async def _analyze_etf_leaders_dimension(self, prompt_template: str) -> dict[str, Any]:
        """ETF专属：并发获取前5大重仓股数据"""
        dim_name = "龙头重仓股深度共振"
        target_stocks = self.stocks[:5]

        async def get_leader_data(code: str) -> str:
            api_chain = [
                partial(getStockCalcIndex, code, logger),
                partial(getStockStatistics, code, logger),
                partial(getStockReport, code, logger)
            ]
            results = await asyncio.gather(*[api() for api in api_chain], return_exceptions=True)
            lines = [f"【龙头股: {code}】"]
            for res in results:
                if isinstance(res, Exception) or not res:
                    lines.append("  - 获取失败")
                else:
                    lines.append(f"  - {res}")
            return "\n".join(lines)

        leader_data_list = await asyncio.gather(*[get_leader_data(code) for code in target_stocks if code])
        combined_data = "\n\n".join(leader_data_list)

        prompt = f"""{prompt_template}
【标的】: {self.name} ({self.code}), 行业: {self.industry}
【重仓股数据】:
{combined_data}

【要求】:
1. 必须基于提供的【原始数据】进行严谨客观的分析，严禁编造。
2. 详细的分析报告 (analysis) 必须包含具体数据支撑，逻辑严密。
请严格输出 JSON：{{"dimension": "{dim_name}", "analysis": "详细分析"}}"""

        messages = [{"role": "system", "content": "只输出合法的 JSON。"}, {"role": "user", "content": prompt}]
        return await chat(messages)

    async def _analyze_single_dimension(self, config: dict) -> dict[str, Any]:
        """Map 阶段：获取数据并独立分析单个维度"""
        dim_name = config["name"]
        if config.get("is_etf_leaders"):
            return await self._analyze_etf_leaders_dimension(config["prompt"])

        # 1. 执行 Fallback 数据获取
        context = f"{self.name}({self.code}) {self.industry}"
        raw_data = await self._fetch_data(config["api_chain"], context, dim_name, config.get("aggregate", False))

        # 2. 追加技术面 K 线数据（如果是技术面维度）
        if dim_name == "技术面与资金流向" and self.kLine:
            raw_data += f"\n{k_line_comment.format("；shares：ETF份额；premium：溢价率" if self.type == "etf" else "")}\n{self.kLine}"

        # 3. 构建定制化 Prompt
        prompt = f"""{config["prompt"]}
【标的】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}
【当前日期】: {self.today}
【原始数据】:
{raw_data}

【要求】:
1. 必须基于提供的【原始数据】进行严谨客观的分析，严禁编造。
2. 详细的分析报告 (analysis) 必须包含具体数据支撑，逻辑严密。
请严格输出 JSON：{{"dimension": "{dim_name}", "analysis": "详细分析"}}"""

        messages = [{"role": "system", "content": "只输出合法的 JSON。"}, {"role": "user", "content": prompt}]
        result = await chat(messages)
        logger.info(f"{self.code} - {self.name} - {dim_name} 维度分析结果如下: {result}")
        if "error" in result:
            return {"dimension": dim_name, "sentiment": "中性", "analysis": f"分析失败: {result}"}
        return result

    async def _final_decision(self, dimension_results: list[dict]) -> dict[str, Any]:
        """Reduce 阶段：汇总所有维度，进行最终决策"""
        trade_info = {"名称": self.hold.get('name'), "代码": self.hold.get('code'), "持仓成本": self.hold.get('cost'), "持仓股数": self.hold.get('shares')}
        hold_info = json.dumps(trade_info, ensure_ascii=False) if self.has_position else "无持仓"
        dim_results_str = json.dumps(dimension_results, ensure_ascii=False, indent=2)

        prompt = f"""你是一个在中国A股市场有着丰富经验的资深量化投研交易员。请基于以下维度的独立分析结果，结合标的信息和持仓情况，给出最终的投资决策。
【标的信息】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}
【当前持仓】: {hold_info}
【各维度分析结果】: {dim_results_str}

【核心交易规则】:
1. 你必须根据提供的【各维度分析结果】，全面综合分析评估标的，特别是各维度和各指标共振。
2. 评级规则: 强烈看好(4个维度全部正面+逻辑顺畅), 看好(≥3个维度正面), 中性(多空交织), 看空(存在排雷信号或重大风险)。

【交易金额规则】
当前账户总资产{self.totalFund}元，可用资产{self.availableFund}元。如果需要【建仓|加仓】买入股票，那么买入金额绝对不能超过可用资产；如果可用资产不够，那么必须综合决策卖出多少已有的持仓，再新买入多少股票。

具体操作规则如下：
| 评级 | 建议买入金额 |
|------|------------|
| 强烈看好 | 10000-15000元 |
| 看好 | 5000-10000元 |
| 中性 | 0-5000元（观望为主） |
| 看空 | 0元（不买入） |

【输出格式规则】:
请严格输出 JSON：
{{
 "date": "{self.today}", "symbol": "{self.code}", "type": "{self.type}",
 "rating": "强烈看好|看好|中性|看空",
 "core_logic": "2-3句话核心逻辑",
 "detailed_analysis": "综合各维度详细报告",
 "risk_warning": "2-3句话最需警惕的风险",
 "action_plan": {{
   "current_position": {json.dumps(trade_info, ensure_ascii=False) if self.has_position else "{}"},
   "operation": "建仓|加仓|不操作|减仓|清仓",
   "operation_amount": "建议金额(数字)",
   "operation_shares": "建议股数(数字)",
   "operation_reason": "简要理由",
   "stop_loss_profit": "硬性止损/止盈位"
 }}
}}"""

        messages = [{"role": "system", "content": "只输出合法的 JSON。"}, {"role": "user", "content": prompt}]
        return await chat(messages)

    async def analyze(self) -> dict[str, Any]:
        """执行完整的 Map-Reduce 分析流程"""
        logger.info(f"🚀 开始 Map-Reduce 分析: {self.name} ({self.code}) | 类型: {self.type}")
        configs = self._get_dimension_configs()

        logger.info(f"📡 正在并发执行 {len(configs)} 个维度的 [API降级获取 + 定制化分析] ...")
        dimension_results = await asyncio.gather(*[self._analyze_single_dimension(cfg) for cfg in configs])

        logger.info("✅ 维度分析完成，正在进行最终汇总决策 (Reduce)...")
        final_result = await self._final_decision(dimension_results)

        if "error" in final_result:
            logger.error(f"❌ 最终决策失败: {final_result['error']}")
            return {"error": "Final Decision Failed", "raw": final_result}

        logger.info("✅ 分析完成，JSON 解析成功。")
        return final_result
