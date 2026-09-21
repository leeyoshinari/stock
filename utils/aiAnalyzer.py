import re
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any
from utils.http_client import http
from utils.logging import logger
from utils.webSearch import searchWithDuckDuckGo
from settings import ANALYSIZE_API_KEY, ANALYSIZE_API_URL, ANALYSIZE_API_MODEL


k_line_comment = '''
【字段含义说明】
day：交易日期；current_price：当日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；fund：主力资金净流入（单位：万）；turnover_rate：换手率；ma_five：5日均线；ma_ten：10日均线；ma_twenty：20日均线和布林线中轨线；qrr：量比；diff：MACD的DIFF；dea：MACD的DEA；k：KDJ的K值；d：KDJ的D值；j：KDJ的J值；boll_up：布林线上轨线；boll_low：布林线下轨线。

【K线数据】

'''


async def run_command(command: str) -> str:
    """异步执行单个 longbridge 命令"""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        logger.info(stdout.decode('utf-8').strip())
        if process.returncode == 0:
            return stdout.decode('utf-8').strip()
        else:
            return f"Error: {stderr.decode('utf-8').strip()}"
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Exception: {str(e)}"


async def run_commands(commands: List[str]) -> Dict[str, str]:
    """并发执行多个 longbridge 命令，返回 {命令: 结果} 字典"""
    tasks = [run_command(cmd) for cmd in commands]
    results = await asyncio.gather(*tasks)
    return {cmd: res for cmd, res in zip(commands, results)}


async def search_and_extract(query: str, df: str = 'w', max_results: int = 5) -> str:
    try:
        content = await searchWithDuckDuckGo(query, logger=logger, df=df, max_results=max_results)
        return json.dumps(content, ensure_ascii=False) if content else "数据缺失 (最近一周无相关信息)"
    except Exception as e:
        return f"Search Exception: {str(e)}"


async def search_longbridge_news(keyword: str, days: int = 5) -> str:
    """
    Longbridge 新闻搜索 + 过滤最近 N 天 + 并发获取正文详情
    """
    try:
        # 1. 搜索新闻列表
        cmd = f'longbridge news search "{keyword}" --format json'
        result = await run_command(cmd)
        if result.startswith("Error") or result.startswith("Exception"):
            return f"News Search Error: {result}"

        news_list = json.loads(result)
        if not isinstance(news_list, list) or not news_list:
            return "News: 未找到相关新闻"

        # 2. 过滤最近 N 天的新闻
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_news = []
        for news in news_list:
            try:
                time_str = news.get("time", "").replace("Z", "+00:00")
                news_time = datetime.fromisoformat(time_str)
                if news_time.tzinfo is not None:
                    news_time = news_time.replace(tzinfo=None)  # 转为 naive 比较

                if news_time >= cutoff_date:
                    recent_news.append(news)
            except Exception:
                continue

            if len(recent_news) >= 3:   # 最多取3条，避免请求过多导致超时
                break

        if not recent_news:
            return f"Longbridge News: 最近 {days} 天内无相关新闻"

        # 3. 并发获取详情并拼接
        async def get_detail(n):
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
            html_resp = await http.get(n["url"], headers=headers)
            content = n.get('excerpt')
            if html_resp.status_code == 200:
                logger.info(html_resp.text)
                content = html_resp.text.split("---")[1].split("##")[0]
            return (
                f"【标题】: {n.get('title')}\n"
                f"【时间】: {n.get('time')}\n"
                f"【来源】: {n.get('source_name')}\n"
                f"【摘要】: {n.get('excerpt')}\n"
                f"【正文】: {content}\n"
            )

        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        return "\n---\n".join(details)

    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Longbridge News Exception: {str(e)}"


async def chat(messages: list) -> Any:
    """调用 LLM 并强制返回 JSON 对象"""
    headers = {
        "Authorization": f"Bearer {ANALYSIZE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": ANALYSIZE_API_MODEL,
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    try:
        resp = await http.post(f"{ANALYSIZE_API_URL}/chat/completions", json_data=payload, headers=headers)
        if resp.status_code == 200:
            data = json.loads(resp.text)
            raw_content = data["choices"][0]["message"]["content"]

            # 更健壮的正则清理 Markdown 标记
            cleaned = re.sub(r'^```json\s*', '', raw_content, flags=re.MULTILINE | re.IGNORECASE)
            cleaned = re.sub(r'^```\s*', '', cleaned, flags=re.MULTILINE)
            cleaned = re.sub(r'\s*```$', '', cleaned, flags=re.MULTILINE).strip()

            return json.loads(cleaned)
        return {"error": f"LLM API Error: HTTP {resp.status_code} - {resp.text}"}
    except Exception as e:
        return {"error": f"LLM Exception: {str(e)}"}


class AsyncETFAnalyzer:
    def __init__(self, input_data: dict):
        self.data = input_data
        self.type: str = input_data.get("type", "stock")
        self.name: str = input_data.get("name", "")
        self.code: str = input_data.get("code", "")
        self.industry: str = input_data.get("industry", "未知行业")
        self.concept: str = input_data.get("concept", "无")
        self.stocks: list[dict] = input_data.get("stocks", [])
        self.kLine: str = input_data.get("k_line", "")
        self.hold: dict = input_data.get("hold", {})
        self.has_position: bool = bool(self.hold and self.hold.get("shares", 0) > 0)
        self.today: str = datetime.now().strftime("%Y-%m-%d")
        logger.debug(f"AI analyzer input data: {input_data}")

    def _get_stock_dimensions(self) -> List[Dict]:
        """股票维度的数据获取策略"""
        return [
            {"name": "政策/监管", "lb_news": f"{self.industry} 产业政策 监管 补贴", "search": f"{self.industry} 产业政策 监管 补贴 限制", "tech": False},
            {"name": "基本面", "lb_news": f"{self.name} 营收 利润 催化剂", "search": f"{self.name} 景气度 营收 利润 催化剂", "lb_fund": True, "tech": False},
            {"name": "技术面", "lb_news": "", "search": "", "tech": True},
            {"name": "资金流", "lb_news": f"{self.name} 资金流向 主力 北向", "search": f"{self.name} 北向资金 融资余额 机构调研 主力资金", "lb_capital": True, "tech": False},
            {"name": "估值+拥挤度", "lb_news": "", "search": f"{self.name} 估值 PE PB 历史分位数 拥挤度", "lb_valuation": True, "tech": False},
            {"name": "产业链高频", "lb_news": f"{self.industry} 产业链 原材料 价格", "search": f"{self.industry} 产业链 上游 原材料 价格", "tech": False},
            {"name": "国际市场", "lb_news": f"{self.industry} 美股 对标 关税", "search": f"{self.industry} 美股 对标 板块 走势 关税 汇率", "tech": False},
            {"name": "重大事件", "lb_news": f"{self.name} 财报 订单 并购 增减持", "search": f"{self.name} 近期 重大 财报 订单 并购 增减持 负面", "tech": False}
        ]

    def _get_etf_dimensions(self) -> List[Dict]:
        """ETF维度的数据获取策略"""
        return [
            {"name": "政策/监管", "lb_news": f"{self.industry} 产业政策 监管 补贴", "search": f"{self.industry} 产业政策 监管 补贴 限制", "tech": False},
            {"name": "基本面", "lb_news": f"{self.industry} 行业 景气度 营收 业绩", "search": f"{self.industry} 底层指数 行业 景气度 营收 利润", "tech": False},
            {"name": "技术面", "lb_news": "", "search": "", "tech": True},
            {"name": "产业链高频", "lb_news": f"{self.industry} 产业链 原材料", "search": f"{self.industry} 产业链 上游 原材料 价格", "tech": False},
            {"name": "国际市场", "lb_news": f"{self.industry} 海外 对标 关税", "search": f"{self.industry} 海外 对标 板块 走势 关税 汇率", "tech": False},
            {"name": "龙头事件+估值", "lb_news": "", "search": "", "tech": False, "is_etf_leaders": True}
        ]

    async def _analyze_etf_leaders_dimension(self) -> Dict[str, Any]:
        """按股票分组并发获取龙头数据，并添加清晰备注"""
        dim_name = "龙头事件+估值"

        # 按股票并发，每只股票内部获取 4 项指标并加备注
        async def get_leader_full_data(code: str) -> str:
            cmds = [
                f"longbridge calc-index {code}",
                f"longbridge valuation {code}",
                f"longbridge financial-report {code}",
                f"longbridge institution-rating {code}"
            ]
            results = await run_commands(cmds)

            lines = [f"【龙头股代码: {code}】"]
            lines.append(f"  - [实时计算指标 calc-index]: {results[cmds[0]]}")
            lines.append(f"  - [同行估值对比 valuation]: {results[cmds[1]]}")
            lines.append(f"  - [关键财报摘要 financial-report]: {results[cmds[2]]}")
            lines.append(f"  - [机构评级分布 institution-rating]: {results[cmds[3]]}")
            return "\n".join(lines)

        leader_data_list = await asyncio.gather(*[get_leader_full_data(code) for code in self.stocks])
        combined_data = f"【{self.industry}行业重仓股深度数据】:\n\n" + "\n\n".join(leader_data_list)

        prompt = f"""你是一个严谨的金融分析助手。请基于以下提供的【原始数据】，对【{dim_name}】维度进行分析。
【标的】: {self.name} ({self.code}), 类型: ETF, 行业: {self.industry}
【分析要求】:
1. 综合这几家重仓股公司的财务数据、估值水平、机构评级以及网络资讯，评估整个行业的景气度、估值分位数及潜在风险。
2. 评估结果 (sentiment) 只能是: "正面", "中性偏正", "中性", "中性偏负", "负面"。
3. 分析报告 (analysis) 必须包含具体数据支撑，详细分析，有理有据。

【原始数据】:
{combined_data}

请严格输出以下 JSON 格式：
{{
  "dimension": "{dim_name}",
  "sentiment": "...",
  "analysis": "..."
}}"""

        messages = [{"role": "system", "content": "只输出合法的 JSON。"}, {"role": "user", "content": prompt}]
        result = await chat(messages)
        logger.info(f"ETF 行业龙头名单分析结果: {result}")
        if "error" in result:
            return {"dimension": dim_name, "sentiment": "中性", "analysis": f"分析失败: {result['error']}"}
        return result

    async def _analyze_single_dimension(self, config: Dict) -> Dict[str, Any]:
        """Map 阶段：获取数据并独立分析单个维度"""
        dim_name = config["name"]

        if config.get("is_etf_leaders"):
            return await self._analyze_etf_leaders_dimension()

        # 1. 并发获取该维度的原始数据
        tasks = []
        # 构建 Longbridge 任务
        lb_tasks = []
        if config.get("lb_news"):
            lb_tasks.append(search_longbridge_news(config["lb_news"], days=5))
        if config.get("lb_fund"):
            lb_tasks.append(run_command(f"longbridge financial-report {self.code}"))
            lb_tasks.append(run_command(f"longbridge institution-rating {self.code}"))
        if config.get("lb_valuation"):
            lb_tasks.append(run_command(f"longbridge calc-index {self.code}"))
            lb_tasks.append(run_command(f"longbridge valuation {self.code}"))
        if config.get("lb_capital"):
            lb_tasks.append(run_command(f"longbridge capital {self.code} --format json"))

        if lb_tasks:
            tasks.append(asyncio.gather(*lb_tasks))
        else:
            tasks.append(asyncio.sleep(0, result=[]))
        # 网络搜索
        if config["search"]:
            tasks.append(search_and_extract(config["search"]))
        else:
            tasks.append(asyncio.sleep(0, result=""))

        # 技术指标
        if config["tech"]:
            tasks.append(self.kLine)
        else:
            tasks.append(asyncio.sleep(0, result=""))

        lb_results_list, web_data, tech_data = await asyncio.gather(*tasks)

        # 格式化 LB 数据并加上明确备注
        lb_data_str = ""
        for res in lb_results_list:
            if "capital_in" in res:
                lb_data_str += f"- 【当日实时资金流向(大单/中单/小单)】: {res}\n"
            elif "indicator" in res:
                lb_data_str += f"- 【估值水平及同行对比数据】: {res}\n"
            elif "DPS" in res:
                lb_data_str += f"- 【实时PE,PB值】: {res}\n"
            elif "strong_buy" in res:
                lb_data_str += f"- 【机构评级（买入/持有/卖出）分布】: {res}\n"
            elif "BS" in res and "CF" in res:
                lb_data_str += f"- 【关键财报数据（营收/EPS/ROE/利润表/资产负债表/现金流）】: {res}\n"
            else:
                lb_data_str += f"- {res}\n"

        # 构建该维度的专属 Prompt
        tech_data = k_line_comment + tech_data if len(tech_data) > 100 else ''
        prompt = f"""你是一个严谨的金融分析师。请仅基于以下提供的【原始数据】，对【{dim_name}】维度进行分析。
【标的】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}
【分析要求】:
1. 必须依据最近一周的最新数据。如果数据缺失或无关，评估结果设为"中性"，分析报告写"数据缺失"。严禁编造。
2. 评估结果 (sentiment) 只能是: "正面", "中性偏正", "中性", "中性偏负", "负面"。
3. 分析报告 (analysis) 必须基于提供的【原始数据】进行严谨的详细的分析，包含具体数据或事实支撑，有理有据。

【原始数据】:
{lb_data_str}
{web_data}
{tech_data}

请严格输出以下 JSON 格式，不要包含任何 Markdown 标记：
{{
  "dimension": "{dim_name}",
  "sentiment": "正面 | 中性偏正 | 中性 | 中性偏负 | 负面",
  "analysis": "详细分析报告"
}}"""

        messages = [
            {"role": "system", "content": "你是一个严谨的金融分析助手，只输出合法的 JSON，绝不输出多余字符。"},
            {"role": "user", "content": prompt}
        ]

        result = await chat(messages)
        logger.info(f"对【{dim_name}】维度分析结果: {result}")
        if "error" in result:
            return {"dimension": dim_name, "sentiment": "中性", "analysis": f"分析失败: {result['error']}"}
        return result

    async def _final_decision(self, dimension_results: List[Dict]) -> Dict[str, Any]:
        """Reduce 阶段：汇总所有维度，进行最终决策"""
        trade_info = {"名称": self.hold['name'], "代码": self.hold['code'], "持仓成本": self.hold['cost'], "持仓股数": self.hold['shares']}
        hold_info = json.dumps(trade_info, ensure_ascii=False) if self.has_position else "无持仓"
        dim_results_str = json.dumps(dimension_results, ensure_ascii=False, indent=2)
        target_desc = "底层指数/行业" if self.type == "etf" else "公司"
        prompt = f"""你是一个资深量化投研分析师。请基于以下维度的独立分析结果，结合标的信息和持仓情况，给出最终的投资决策。
【标的信息】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}, 概念: {self.concept}
【当前日期】: {self.today}
【当前持仓】: {hold_info}

【各维度分析结果】:
{dim_results_str}

【评级规则】:
- 强烈看好: ≥7个维度正面/中性偏正 + {target_desc}基本面明确改善 + 有近期催化剂 + 无重大风险
- 看好: ≥6个维度正面/中性偏正 + {target_desc}基本面无恶化 + 风险可控
- 中性: 多空相当，方向不明
- 看空: ≥4个维度中性偏负/负面，或存在重大政策/国际/基本面风险

【操作规则】:
- 买入金额(基础10000元): 强烈看好(10000-15000), 看好(5000-10000), 中性(0-5000), 看空(0)
- 持仓操作: 加仓(看好/强烈看好且未大幅偏离成本), 保持(中性偏正或盈利中趋势未破), 减仓(中性偏空或拥挤度过高), 清仓(看空或基本面恶化)

请严格输出以下 JSON 格式，不要包含任何 Markdown 标记：
{{
  "date": "{self.today}",
  "symbol": "{self.code}",
  "type": "{self.type}",
  "rating": "强烈看好 | 看好 | 中性 | 看空",
  "core_logic": "简洁精炼的2-3句话核心逻辑，综合各维度结论",
  "detailed_analysis": "综合各维度所有数据详细分析报告",
  "risk_warning": "1-2句话，最需警惕的风险",
  "action_plan": {{
    "has_position": {str(self.has_position).lower()},
    "current_position": {{"name": "{self.hold.get('name', '')}", "code": "{self.hold.get('code', '')}", "cost": {self.hold.get('cost', 0)}, "shares": {self.hold.get('shares', 0)}}},
    "estimated_pnl_ratio": "估算盈亏比例 (如: +5.2% 或 无)",
    "operation": "新买入 | 不买入 | 加仓 | 保持 | 减仓 | 清仓",
    "operation_amount": "建议操作金额 (如: 5000元，若不买入则填0元)",
    "operation_shares": "建议操作股数 (如: 1000股，若不买入则填0股)",
    "operation_reason": "简要说明操作理由",
    "stop_loss_profit": "止盈/止损参考价格或比例"
  }}
}}"""

        messages = [
            {"role": "system", "content": "你是一个严谨的金融分析助手，只输出合法的 JSON，绝不输出多余字符。"},
            {"role": "user", "content": prompt}
        ]
        return await chat(messages)

    async def analyze(self) -> Dict[str, Any]:
        """执行完整的 Map-Reduce 分析流程"""
        logger.info(f"🚀 开始 Map-Reduce 分析: {self.name} ({self.code}) | 类型: {self.type}")
        configs = self._get_stock_dimensions() if self.type == "stock" else self._get_etf_dimensions()

        logger.info(f"📡 正在并发执行 {len(configs)} 个维度的 [数据获取 + 独立分析] ...")
        for c in configs:
            logger.info(c)
        dimension_results = await asyncio.gather(*[self._analyze_single_dimension(cfg) for cfg in configs])

        logger.info("✅ 维度分析完成，正在进行最终汇总决策 (Reduce)...")
        final_result = await self._final_decision(dimension_results)
        logger.info(f"最终分析结果: {final_result}")
        if "error" in final_result:
            logger.error(f"❌ 最终决策失败: {final_result['error']}")
            return {"error": "Final Decision Failed", "raw": final_result}

        logger.info("✅ 分析完成，JSON 解析成功，可直接入库。")
        return final_result


async def main():
    user_input = {
        "type": "stock",
        "name": "格力电器",
        "code": "000651.SZ",
        "industry": "家用电器",
        "concept": "白色家电,空调,消费风格,大盘价值,红利股,储能概念,光伏概念",
        "follow": "",
        "hold": {}
    }
    # {
    #         "name": "格力电器",
    #         "code": "000651.SZ",
    #         "cost": 38.50,
    #         "shares": 1000
    #     }

    analyzer = AsyncETFAnalyzer(input_data=user_input)
    result = await analyzer.analyze()
    logger.info(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
