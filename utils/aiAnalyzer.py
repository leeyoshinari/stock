#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import logging
import asyncio
import traceback
import aiofiles
from datetime import datetime, timedelta
from typing import Any, Callable
from functools import partial
from utils.AI import chat
from utils.webSearch import getNews, searchWithSerper
from utils.akshare import getGlobalShortInfoFromSina, getGlobalShortInfoFromThs, getStockFinanceReportFromSina, getShortInfoMorning
from utils.longbridge import getStockNews, getStockValuation, getStockFinancialAnalysis
from settings import ETF_ANALYZE_NEWS, ETF_ANALYZE_TECH, ETF_ANALYZE_FINALLY, AUTO_DECISION_MAKING
from settings import STOCK_ANALYZE_NEWS, STOCK_ANALYZE_TECH, STOCK_ANALYZE_BASIC, STOCK_ANALYZE_FINALLY

logger = logging.getLogger(__name__)
etf_k_line_comment = '''
【字段含义说明】
day：交易日期；current_price：当日收盘价；last_price：前一日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；turnover_rate：换手率；ma_five：5日均线；ma_ten：10日均线；ma_twenty：20日均线和布林线中轨线；qrr：量比；boll_up：布林线上轨线；boll_low：布林线下轨线；shares：ETF份额(亿份)；premium：ETF溢价率\n
【K线数据】
'''
stock_k_line_comment = '''
【字段含义说明】
day：交易日期；current_price：当日收盘价；last_price：前一日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；fund：主力资金净流入（单位：万）；turnover_rate：换手率；ma_five：5日均线；ma_ten：10日均线；ma_twenty：20日均线和布林线中轨线；qrr：量比；diff：MACD的DIFF；dea：MACD的DEA；k：KDJ的K值；d：KDJ的D值；j：KDJ的J值；boll_up：布林线上轨线；boll_low：布林线下轨线\n
【K线数据】
'''


async def read_prompt(filePath: str) -> str:
    async with aiofiles.open(filePath, 'r', encoding='utf-8') as f:
        res = await f.read()
    return res


class AsyncETFAnalyzer:
    def __init__(self, input_data: dict):
        self.today: str = input_data.get("toDay", datetime.now().strftime("%Y-%m-%d"))
        self.type: str = input_data.get("type", "stock")    # 类型，stock-股票，etf-ETF
        self.totalFund: float = input_data.get("totalFund", 0)          # 总资产
        self.availableFund: float = input_data.get("availableFund", 0)  # 可用资产
        self.name: str = input_data.get("name", "")     # 股票名称
        self.code: str = input_data.get("code", "")     # 股票code
        self.current_price = input_data.get("current_price", None)  # 当前价格
        self.industry: str = input_data.get("industry", self.name)     # 行业
        self.concept: str = input_data.get("concept", self.code)     # 股票概念
        # raw_stocks = input_data.get("stocks", [])
        # self.stocks: list[str] = [s.get("code", s) if isinstance(s, dict) else s for s in raw_stocks]   # ETF前10重仓股
        self.kLine: str = input_data.get("k_line", "")          # K线等技术数据
        self.trade: list[dict] = input_data.get("trade", None)        # 交易记录
        self.analysis: list[dict] = input_data.get("analysis", None)      # AI分析记录
        self.hold: dict = input_data.get("hold", None)        # 当前持仓数据
        logger.debug(f"input_data is - {json.dumps(input_data, ensure_ascii=False)}")

    async def _fetch_data(self, api_chain: list[Callable], context: str, dimension: str, aggregate: bool = False) -> str:
        """
        数据获取引擎，支持两种模式：\n
        :params aggregate: False (短路模式): 依次尝试，成功一个立即返回；True  (聚合模式): 并发执行所有API，拼接所有成功结果
        """
        if not aggregate:
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
                func_name = getattr(api_func, 'func', api_func).__name__
                if isinstance(res, Exception):
                    logger.warning(f"[{dimension}] {func_name} 调用异常: {res}")
                if self._is_valid_data(res):
                    valid_parts.append(f"[{func_name}]: {res}")

            if valid_parts:
                return "\n\n".join(valid_parts)

        # ===== 所有 API 均失败，触发 AI 动态搜索兜底 =====
        logger.info(f"[{dimension}] API 数据均缺失, 触发 serper 搜索兜底 - {context}")
        # keyword = await generate_search_keyword(context, dimension)
        web_data = await searchWithSerper(context, df='d')
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

    async def _safe_call(self, api_func) -> Any:
        """
        安全调用包装器：兼容异步 API 和同步本地数据（如 lambda 返回的字符串）
        """
        result = api_func()
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            return await result
        return result

    def _get_dimension_configs(self) -> list[dict]:
        """构建维度配置：包含 API 降级链 和 定制化 Prompt"""
        if self.type == "etf":
            configs = [
                {
                    "name": "金融财经新闻",
                    "aggregate": False,
                    "api_chain": [
                        partial(getNews, f"{self.industry}产业 政策 监管", self.today),
                        partial(getNews, f"{self.industry}行业", self.today),
                    ],
                    "prompt": ETF_ANALYZE_NEWS
                },
                {
                    "name": "技术面",
                    "aggregate": True,
                    "api_chain": [],
                    "prompt": ETF_ANALYZE_TECH
                }
            ]
        else:
            configs = [
                {
                    "name": "金融财经新闻",
                    "aggregate": False,
                    "api_chain": [
                        partial(getNews, f"{self.industry}产业 政策 监管", self.today),
                        partial(getStockNews, self.code, self.today),
                        partial(getNews, f"{self.industry} 美股 海外", self.today)
                    ],
                    "prompt": STOCK_ANALYZE_NEWS
                }, {
                    "name": "基本面",
                    "aggregate": False,
                    "api_chain": [
                        partial(getStockFinancialAnalysis, self.code),
                        partial(getStockFinanceReportFromSina, self.code),
                    ],
                    "prompt": STOCK_ANALYZE_BASIC
                }, {
                    "name": "技术面",
                    "aggregate": True,
                    "api_chain": [
                        partial(getStockValuation, self.code),
                    ],
                    "prompt": STOCK_ANALYZE_TECH
                }
            ]
        return configs

#     async def _analyze_etf_leaders_dimension(self, prompt_template: str) -> dict[str, Any]:
#         """ETF专属：并发获取前5大重仓股数据"""
#         dim_name = "龙头重仓股深度共振"
#         target_stocks = self.stocks[:5]

#         async def get_leader_data(code: str) -> str:
#             api_chain = [
#                 partial(getStockFinancialAnalysis, code, logger),
#             ]
#             results = await asyncio.gather(*[api() for api in api_chain], return_exceptions=True)
#             lines = [f"【重仓股: {code}】"]
#             for res in results:
#                 if isinstance(res, Exception) or not res:
#                     lines.append("  - 获取失败")
#                 else:
#                     lines.append(f"  - {res}")
#             return "\n".join(lines)

#         leader_data_list = await asyncio.gather(*[get_leader_data(code) for code in target_stocks if code])
#         combined_data = "\n\n".join(leader_data_list)

#         prompt = f"""{prompt_template}
# 【标的】: {self.name} ({self.code}), 跟踪行业/主题: {self.industry}
# 【重仓股数据】:
# {combined_data}

# 【分析框架与约束条件】（请在思考时严格遵循，并在输出中体现）：
# 1. 权重决定论：前几大重仓股通常占据 ETF 30%-60% 以上的权重，它们的走势对 ETF 具有决定性影响。分析时必须考虑核心龙头的“代表性”。
# 2. 盈利与景气度验证：提取重仓股的营收增速、净利润增速、ROE 等核心财务指标，判断行业基本面是处于“扩张期”、“稳健期”还是“衰退期”。
# 3. 估值安全边际：重点分析重仓股的 PE/PB 绝对值及其历史分位数。如果行业有利好，但龙头股估值已处于历史 90% 以上高分位，必须明确提示“估值透支”或“利好出尽”的回调风险。
# 4. 机构共识与目标价：综合重仓股的分析师评级（如买入/增持比例）和目标价上行空间，评估资金面的潜在共识。
# 5. 风险一票否决：若数据中显示核心龙头股存在业绩大幅下滑、盈利预警、或估值极端泡沫，即使行业宏观逻辑再好，也必须在分析中给予高风险提示，并下调 ETF 的上涨预期。
# 6. 严格数据边界：绝对忠实于提供的【重仓股数据】，严禁编造任何财务数据、估值指标或评级结论。若数据缺失，请明确说明“数据不足”，不可臆测。

# 【输出格式要求】：
# 必须且仅输出严格合法的 JSON 对象。不要包含任何 Markdown 标记（如 ```json），不要包含任何额外的解释文本。格式如下：
# {{"dimension": "{dim_name}", "analysis": "详细分析该ETF近期是否具备上涨条件，核心逻辑或最大阻碍是什么"}}"""

#         messages = [{"role": "system", "content": "只输出合法的 JSON。"}, {"role": "user", "content": prompt}]
#         return await chat(messages)

    async def _analyze_single_dimension(self, config: dict) -> dict[str, Any]:
        """Map 阶段：获取数据并独立分析单个维度"""
        dim_name = config["name"]
        # if config.get("is_etf_leaders"):
        #     return await self._analyze_etf_leaders_dimension(config["prompt"])

        context = f"{self.name}({self.code}) {self.industry}"
        if config["api_chain"]:
            raw_data = await self._fetch_data(config["api_chain"], context, dim_name, config.get("aggregate", False))
        else:
            raw_data = ''
        # 2. 追加技术面 K 线数据（如果是技术面维度）
        if dim_name == "技术面" and self.kLine:
            raw_data += self.kLine

        # 3. 构建定制化 Prompt
        system_prompt = await read_prompt(config['prompt'])
        system_prompt = system_prompt.replace('dimension_name', dim_name).replace('real_industry', self.industry)
        user_message = f"""用户输入的数据如下：
【标的】: {self.name} ({self.code}), 行业: {self.industry}
【当前日期】: {self.today}
【原始数据】:{raw_data}"""
        result = await chat(system_prompt, user_message)
        logger.info(f"{self.code} - {self.name} - {dim_name} 维度分析结果如下: {result}")
        if "error" in result:
            return {"dimension": dim_name, "score": 0, "analysis": f"分析失败: {result}"}
        return json.loads(result)

    async def _final_decision(self, dimension_results: list[dict]) -> dict[str, Any]:
        """Reduce 阶段：汇总所有维度，进行最终决策"""
        my_hold = None
        if self.hold:
            my_hold = {"成本": self.hold['price'], "数量": f"{self.hold['shares']}股", "市值": self.hold['amount'], "当前仓位": f"{self.hold['current_position']}%", "当前盈亏比": f"{self.hold['profit']}%"}
        if self.type == 'etf':
            system_prompt = await read_prompt(ETF_ANALYZE_FINALLY)
        else:
            system_prompt = await read_prompt(STOCK_ANALYZE_FINALLY)
        system_prompt = system_prompt.replace('replace_date', self.today).replace('replace_code', self.code).replace('replace_name', self.name)
        system_prompt = system_prompt.replace('replace_current_price', str(self.current_price))
        system_prompt = system_prompt.replace('current_position_json', json.dumps(self.hold, ensure_ascii=False))

        if self.type == 'etf':
            user_message = f"""用户输入的数据是：
【ETF信息】: {self.name} ({self.code}), 跟踪标的: {self.concept}, 行业: {self.industry}
【账户资金】: 总资产: {self.totalFund}元, 可用资金: {self.availableFund}元
【当前持仓】: {json.dumps(my_hold, ensure_ascii=False) if self.hold else "无持仓"}
【交易记录】: {json.dumps(self.trade, ensure_ascii=False) if self.trade else "暂无交易记录"}
【历史分析结果】: {json.dumps(self.analysis, ensure_ascii=False) if self.analysis else "暂无历史分析结果"}
【各维度分析结果】: {json.dumps(dimension_results, ensure_ascii=False, indent=2)}"""
        else:
            user_message = f"""用户输入的数据是：
【股票信息】: {self.name} ({self.code}), 行业: {self.industry}
【账户资金】: 总资产: {self.totalFund}元, 可用资金: {self.availableFund}元
【当前持仓】: {json.dumps(my_hold, ensure_ascii=False) if self.hold else "无持仓"}
【交易记录】: {json.dumps(self.trade, ensure_ascii=False) if self.trade else "暂无交易记录"}
【各维度分析结果】: {json.dumps(dimension_results, ensure_ascii=False, indent=2)}"""

        res = await chat(system_prompt, user_message)
        logger.info(f"{self.code} - {self.name} - 最终分析结果如下: {res}")
        return json.loads(res)

    async def analyze(self) -> dict[str, Any]:
        """执行完整的 Map-Reduce 分析流程"""
        logger.info(f"🚀 开始分析: {self.name} ({self.code}) | 类型: {self.type}")
        configs = self._get_dimension_configs()

        logger.info(f"📡 正在并发执行 {len(configs)} 个维度的数据 ...")
        dimension_results = await asyncio.gather(*[self._analyze_single_dimension(cfg) for cfg in configs])

        logger.info("✅ 维度分析完成，正在进行最终汇总决策 (Reduce)...")
        final_result = await self._final_decision(dimension_results)
        if "error" in final_result:
            logger.error(f"❌ 最终决策失败: {final_result['error']}")
            return {"error": "Final Decision Failed", "raw": final_result}

        logger.info(f"✅ 分析完成, JSON 解析成功 - {self.code} - {self.name}")
        return final_result


async def analyze_etf_from_news(etfList: list[dict], lastDay: str) -> list[dict]:
    """ETF专属：从新闻中选取ETF"""
    try:
        api_chain = [
            partial(getGlobalShortInfoFromSina, lastDay),
            partial(getGlobalShortInfoFromThs, lastDay),
            partial(getShortInfoMorning)
        ]
        results = await asyncio.gather(*[api() for api in api_chain], return_exceptions=True)
        lines = []
        for res in results:
            if isinstance(res, Exception) or not res:
                lines.append("  - 获取失败")
            else:
                lines.append(f"{res}")

        combined_data = "\\n".join(lines)

        system_prompt = """你是一位拥有10年以上经验的资深全球宏观与ETF策略分析师，擅长事件驱动策略、跨市场联动分析、产业链逻辑推演及市场情绪甄别。
你的任务：根据用户提供的最新【财经新闻】，从给定的【ETF列表】中，精准筛选出在短期内（1-5个交易日）具备明确受益逻辑、且与中长期宏观趋势共振、具备较高上涨概率的ETF。

【分析框架与约束条件】：
宏观周期与全局校验（防局部陷阱）：严禁孤立看待单一新闻。必须将局部政策或事件放入宏观大周期（如产业生命周期、全国整体政策导向、人口/债务周期）中交叉验证。若局部利好（如某省市房地产微调）与宏观大趋势（如行业整体去杠杆/需求下行）严重背离，应视为“噪音”或“弱反弹”，坚决降权或排除。
全球宏观与跨市场联动（补国际视野）：必须主动提取新闻中的国际宏观变量（如美联储加息/降息预期、美债收益率走势、美元指数、地缘政治、美股特定板块映射、大宗商品全球定价等），并分析其对国内相关资产（如贵金属、有色金属、创新药、出海链、港股等）的流动性或估值传导机制。
事实与情绪剥离：严格区分“实质性催化”（如央行降准降息、中央财政真金白银补贴、产业技术重大突破、海外超预期数据）与“噪音”（如口号式政策、无资金支持的局部文件、市场小作文、已被充分定价的旧闻）。优先选择有官方背书、资金规模明确或产业趋势反转的实质性新闻。
逻辑链条完整性：推演必须包含：新闻核心事件 → 全球/国内宏观背景校验 → 受益行业/细分主题 → 业绩或估值改善传导机制 → 对应ETF。
警惕“利好出尽”与“伪催化”：若该新闻在市场前期已被充分炒作（预期已兑现），或属于长期逻辑但短期无资金/事件催化剂，请谨慎排除，避免追涨杀跌。
严格数据边界：绝对忠实于提供的【财经新闻】和【ETF列表】，严禁编造任何新闻细节、行业关联或ETF代码。若没有符合条件的ETF，请返回空数组 []。

【输出格式要求】：
必须且仅输出严格合法的 JSON 数组格式。不要包含任何 Markdown 标记（如 ```json），不要包含任何额外的解释文本。格式示例如下：
[
  {
    "name": "ETF名称",
    "code": "ETF代码",
    "reason": "1. 新闻核心：[一句话概括]；2. 宏观校验：[说明该事件是否符合宏观大趋势，或如何受国际宏观变量(如美联储/美债/美股映射)影响，排除局部噪音]；3. 受益逻辑：[说明新闻如何直接利好该ETF底层资产的业绩或估值]；4. 短期催化剂：[说明为何短期会涨，如资金流入预期、政策落地窗口、海外映射发酵等]"
  }
]"""
        user_message = f"""用户输入的数据如下：
【财经新闻】
{combined_data}

【ETF列表】
{etfList}"""
        res = await chat(system_prompt, user_message)
        try:
            return json.loads(res)
        except:
            logger.error(res)
            logger.error(traceback.format_exc)
            return []
    except:
        logger.error(traceback.format_exc())
        return []


async def analyze_buy_etf(totalFund: float, availableFund: float, etfList: list[dict]) -> list[dict]:
    """可用金额不够，综合分析进行取舍"""
    try:
        system_prompt = await read_prompt(AUTO_DECISION_MAKING)
        user_message = f"""用户输入的数据是：
        【账户资金】: 总资产: {totalFund}元, 可用资金: {availableFund}元
        【所有候选ETF的分析结果】: {json.dumps(etfList, ensure_ascii=False)}"""
        res = await chat(system_prompt, user_message)
        try:
            return json.loads(res)
        except:
            logger.error(res)
            logger.error(traceback.format_exc())
    except:
        logger.error(traceback.format_exc())
