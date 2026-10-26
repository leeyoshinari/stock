#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable
from functools import partial
from utils.AI import chat
from utils.webSearch import searchWithDuckDuckGo
from settings import read_prompt
from utils.akshare import getGlobalShortInfoFromSina, getGlobalShortInfoFromThs, getStockResearchReport, getStockFinanceReportFromSina, getShortInfoMorning, getNewsFromDongCai
from utils.longbridge import getNewsDetail, getStockNews, getStockReport, getStockCalcIndex, getStockCapital, getStockValuation, getStockFinancialStatement, getStockFinancialAnalysis


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
system_prompt_etf_analyzer_tech = read_prompt('etf_analyzer_tech.md')


async def search_and_extract(query: str, max_results: int = 5) -> str:
    """DuckDuckGo 联网搜索兜底"""
    try:
        content = await searchWithDuckDuckGo(query, df='w', max_results=max_results)
        return json.dumps(content, ensure_ascii=False) if content else ""
    except Exception as e:
        return f"Search Exception: {str(e)}"


class AsyncETFAnalyzer:
    def __init__(self, input_data: dict):
        self.today: str = input_data.get("toDay", datetime.now().strftime("%Y-%m-%d"))
        self.type: str = input_data.get("type", "stock")    # 类型，stock-股票，etf-ETF
        self.availableFund: float = input_data.get("availableFund", 0)  # 可用资产
        self.name: str = input_data.get("name", "")     # 股票名称
        self.code: str = input_data.get("code", "")     # 股票code
        self.current_price = input_data.get("current_price", None)  # 当前价格
        self.news_reason: str = input_data.get("newsRes", None)   # 从每日新闻中选出的ETF的原因
        self.industry: str = input_data.get("industry", self.name)     # 行业
        self.concept: str = input_data.get("concept", self.code)     # 股票概念
        # raw_stocks = input_data.get("stocks", [])
        # self.stocks: list[str] = [s.get("code", s) if isinstance(s, dict) else s for s in raw_stocks]   # ETF前10重仓股
        self.kLine: str = input_data.get("k_line", "")      # K线等技术数据
        self.hold: dict = input_data.get("hold", {})    # 当前持仓数据
        self.has_position: bool = bool(self.hold and self.hold.get("shares", 0) > 0)
        logger.info(f"input_data is - {json.dumps(input_data, ensure_ascii=False)}")

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
        logger.info(f"[{dimension}] API 数据均缺失，触发 AI 动态搜索兜底...")
        # keyword = await generate_search_keyword(context, dimension)
        web_data = await search_and_extract(context)
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
        # 股票与 ETF 的差异化 API 链
        if self.type == "etf":
            configs = [
                {
                    "name": "金融财经新闻",
                    "aggregate": False,
                    "api_chain": [
                        partial(getNewsDetail, f"{self.industry} 产业政策 监管", self.today),
                        # partial(getNewsDetail, f"{self.industry} 行业景气度 营收", logger),
                        partial(getNewsDetail, f"{self.industry} 行业", self.today),
                        partial(getNewsFromDongCai, self.concept, self.today)
                    ],
                    "prompt": "你是一位资深的宏观策略与产业政策分析师，擅长从政策文本、行业新闻和宏观数据中剥离噪音，精准判断行业中观景气度与政策底/市场底。\n你的任务：基于用户提供的行业政策与新闻数据，评估该行业近期的政策导向、供需格局及整体景气度，最终判定该行业对 ETF 的宏观基本面是构成实质性利好、利空还是中性，并重点提示潜在的监管或产业风险。",
                    "rule": """【分析框架与约束条件】（请在思考时严格遵循，并在输出中体现）：
                    1. 事实与噪音剥离：严格区分“国家级/部委级实质性政策落地（如具体补贴金额、准入文件）”与“市场传闻/小作文/口号式呼吁”。仅以前者作为核心判断依据。
                    2. 政策导向与监管评估：重点分析政策是鼓励发展、规范整顿还是限制扩张。关注补贴退坡、行业准入限制或突发性强监管（如环保、反垄断、数据安全）的潜在风险。
                    3. 产业景气度与供需验证：基于数据提取关键指标（如产能利用率、库存周期、上下游需求增速、产品价格拐点），判断行业处于“主动补库存”、“被动去库存”还是“产能过剩”阶段。
                    4. 风险一票否决：若数据中显示该行业面临突发性严厉监管、核心补贴取消或严重的产能过剩价格战，即使有局部利好，也必须给予“明确利空”或“高风险”评级。
                    5. 严格数据边界：绝对忠实于用户提供的行业政策与新闻数据，严禁编造任何政策文件、宏观数据或行业指标。若某维度数据缺失，请明确填写“当前数据未提及”，不可臆测。""",
                    "conclusion": f"详细分析{self.industry}行业近期是否具备支撑 ETF 上涨的条件，核心驱动力或最大阻碍是什么。"
                },
                {
                    "name": "技术面与资金流向",
                    "aggregate": True,
                    "api_chain": [],
                    "prompt": system_prompt_etf_analyzer_tech,
                    "rule": "",
                    "conclusion": "详细的深度分析报告"
                }
                # , {
                #     "name": "重仓股深度共振",
                #     "api_chain": [],
                #     "prompt": "你是一位资深的 ETF 微观结构与基本面量化分析师，擅长“自下而上”的穿透分析。你的任务是通过拆解 ETF 前几大重仓股的财务、估值和机构评级数据，评估这些核心资产对整体 ETF 净值的支撑力度，并判断该 ETF 所跟踪的行业在近期是否具备上涨潜力。",
                #     "is_etf_leaders": True
                # }
            ]
        else:
            configs = [
                {
                    "name": "宏观政策与监管环境",
                    "aggregate": False,
                    "api_chain": [
                        partial(getNewsDetail, f"{self.industry}产业政策监管", self.today),
                        partial(getStockNews, self.code, self.today),
                        # partial(searchWithDuckDuckGo, f"{self.industry} 产业链 上游 原材料 价格", logger),
                        partial(getNewsFromDongCai, f"{self.industry} 美股 海外", self.today)
                    ],
                    "prompt": "你是一位资深股票基本面与宏观行业分析师，擅长从宏观政策、产业链结构及全球宏观视角，对行业及特定标的进行深度、客观、数据驱动的基本面分析。请基于用户输入的数据，对指定标的及其所属行业进行严谨的基本面分析。",
                    "rule": """【分析框架】（请在 analysis 中综合涵盖以下相关维度，若数据缺失请明确说明“原始数据未提供相关信息”，严禁臆测）：
                    1. 政策与监管环境：近期的政策导向、监管态度、补贴变化及行业准入限制。重点评估政策整体是利好还是利空，并提示是否存在突发性监管风险。
                    2. 产业链与成本结构：上游原材料成本变化对该行业及标的利润空间的挤压或释放效应。
                    3. 全球宏观与外部映射：海外对标公司（如美股同类企业）走势的映射关系，以及关税、汇率波动、地缘政治对该行业的潜在影响。

                    【严格约束】
                    1. 绝对忠于【用户输入的数据】：所有结论必须有【用户输入的数据】中的具体事实或数值（如金额、比例、时间等）作为支撑，严禁编造、外推或引入外部未提供的知识。
                    2. 逻辑严密：分析需条理清晰，因果关系明确，避免空泛的套话。
                    3. 纯 JSON 输出：必须且只能输出合法的 JSON 字符串。严禁包含 Markdown 代码块标记（如 ```json 或 ```）、严禁包含任何前言、后记或额外解释文本。""",
                    "conclusion": "在此处输出有数据支撑的详细分析文本"
                }, {
                    "name": "基本面与业绩预期",
                    "aggregate": False,
                    "api_chain": [
                        partial(getStockFinancialAnalysis, self.code),
                        partial(getStockFinanceReportFromSina, self.code),
                    ],
                    "prompt": "你是一位资深股票基本面与财务估值分析师，擅长通过财务报表数据和估值指标对上市公司进行深度、客观、数据驱动的基本面评估。请基于用户输入的数据，对指定标的进行严谨的财务基本面分析。",
                    "rule": """【分析框架】（请在 analysis 中综合涵盖以下相关维度；若某项数据在原始数据中缺失，请明确说明"原始数据未提供该信息"，严禁臆测或编造）：
                    1. 盈利能力分析：营收规模及增速、净利润及增速、毛利率、净利率、ROE、ROA 等核心盈利指标的表现与变化趋势。
                    2. 财务健康度：资产负债率、流动比率/速动比率、经营性现金流净额等指标，评估公司的偿债能力、资金链安全性与潜在财务风险。
                    3. 成长性判断：基于营收和利润的同比/环比变化趋势，判断公司当前所处的发展阶段（高速成长/稳健增长/增速放缓/承压下行）。
                    4. 综合评价与风险提示：综合以上分析，给出该标的当前基本面的整体定性评价，明确列出主要亮点（如盈利改善、估值偏低等）与核心风险点（如负债过高、增速下滑、估值泡沫等）。

                    【严格约束】
                    1. 绝对忠于【用户输入的数据】：所有结论必须有【用户输入的数据】中的具体数值（如金额、比率、百分比、同比增速等）作为直接支撑，严禁编造、外推或引入外部未提供的知识。
                    2. 逻辑严密：分析需条理清晰，因果关系明确，数据引用与结论之间必须有清晰的推导逻辑，避免空泛套话。
                    3. 纯 JSON 输出：必须且只能输出合法的 JSON 字符串。严禁包含 Markdown 代码块标记（如 ```json 或 ```）、严禁包含任何前言、后记或额外解释文本。""",
                    "conclusion": "在此处输出有数据支撑的详细分析文本"
                }, {
                    "name": "技术面与资金流向",
                    "aggregate": True,
                    "api_chain": [
                        partial(getStockValuation, self.code),
                    ],
                    "prompt": "你是一位资深量化与技术面分析师，擅长结合量价关系、主力资金流向、技术指标以及估值安全边际，对股票进行深度、客观、数据驱动的综合研判。请基于用户输入的数据，对指定标的进行严谨的技术面与资金面分析。",
                    "rule": """【分析框架】（请在 analysis 中严格按以下维度展开；若某项数据缺失，请明确说明“原始数据未提供该信息”，严禁臆测或编造）：
                    1. 趋势与均线系统：分析当前价格与 5日/10日/20日均线 的相对位置，判断短期趋势方向。重点评估是否存在“价格远离均线导致短线情绪透支”或“均线系统未修复”的弱势特征。
                    2. 量价关系与假信号识别：结合 volume、turnover_rate、qrr，重点排查并警示以下异常/假信号：高开低走、长上影线、单日暴涨但量能异常、高换手率+小阳线或上影线（疑似主力出货）、高位派发特征。
                    3. 资金面深度解析：分析 fund (主力资金净流入) 的近期趋势与单日异常值。结合价格走势，判断资金是在持续吸筹、震荡洗盘，还是拉高出货。
                    4. 技术指标状态：综合研判 MACD（是否存在假金叉、高位钝化、顶/底背离）、KDJ（超买/超卖区域及 J 值极端情况）、布林带（价格触及上下轨、开口/收口状态）给出的共振或冲突信号。
                    5. 估值与安全边际辅助：结合提供的 PE、PB、PS 历史分位数及同行对比（溢价/折价情况），以及股息率水平，评估当前技术位置是否具备基本面支撑（例如：“技术超卖 + 估值低估”的共振买点，或“技术高位 + 估值泡沫”的强烈风险）。
                    6. 综合结论与风险提示：用简练的语言总结当前技术面与资金面的整体状态（如：多头趋势/震荡筑底/顶部背离风险等），并明确列出 1-2 个最核心的技术或资金面风险点。

                    【严格约束】
                    1. 绝对忠于【用户输入的数据】：所有结论必须有【用户输入的数据】中的具体数值（如价格、成交量、资金额、指标数值、分位数等）作为直接支撑，严禁编造、外推或引入外部未提供的知识。
                    2. 逻辑严密：分析需条理清晰，因果关系明确（例如：“因换手率达X%且收长上影，故疑似出货”），避免空泛的套话。
                    3. 纯 JSON 输出：必须且只能输出合法的 JSON 字符串。严禁包含 Markdown 代码块标记（如 ```json 或 ```）、严禁包含任何前言、后记或额外解释文本。""",
                    "conclusion": "在此处输出有数据支撑的详细分析文本"
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

        # 1. 执行 Fallback 数据获取
        context = f"{self.name}({self.code}) {self.industry}"
        raw_data = await self._fetch_data(config["api_chain"], context, dim_name, config.get("aggregate", False))

        # 2. 追加技术面 K 线数据（如果是技术面维度）
        if dim_name == "技术面与资金流向" and self.kLine:
            raw_data += f"\n{etf_k_line_comment if self.type == "etf" else stock_k_line_comment}\n{self.kLine}"

        # 3. 构建定制化 Prompt
        system_prompt = f"""{config["prompt"]}

{config["rule"]}

请严格输出 JSON：{{"dimension": "{dim_name}", "analysis": "{config['conclusion']}"}}"""
        user_message = f"""用户输入的数据如下：
【标的】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}
【当前日期】: {self.today}
【原始数据】:{raw_data}"""
        result = await chat(system_prompt, user_message)
        logger.info(f"{self.code} - {self.name} - {dim_name} 维度分析结果如下: {result}")
        if "error" in result:
            return {"dimension": dim_name, "sentiment": "中性", "analysis": f"分析失败: {result}"}
        return json.loads(result)

    async def _final_decision(self, dimension_results: list[dict]) -> dict[str, Any]:
        """Reduce 阶段：汇总所有维度，进行最终决策"""
        hold_info = json.dumps(self.hold, ensure_ascii=False) if self.has_position else "无持仓"
        dim_results_str = json.dumps(dimension_results, ensure_ascii=False, indent=2)
        news_result_prompt = f"【最新新闻事件驱动】: {self.news_reason}。特别注意：这是从最近24小时的新闻中分析出来的，仅供参考。"

        system_prompt = f"""你是一位在中国A股市场拥有丰富实战经验的资深量化投研与交易决策专家。你的任务是综合用户输入的【各维度分析结果】的独立分析结果，结合标的现状与账户头寸，进行交叉验证，并输出严谨、可执行的最终交易决策。

【分析与决策框架】
1. 交叉验证与共振分析：必须综合评估各个维度。寻找“共振点”（如：估值低估+资金持续流入+技术面突破）或“冲突点”（如：基本面良好但技术面破位/主力出逃）。
2. 异常降级处理：若某个维度的分析结果为空、报错或数据缺失，必须在分析中明确指出，并在决策时对该维度降权（视为中性或未知），严禁自行脑补缺失数据。
3. 综合评级定义：
   - 强烈看好：三个维度均为正面，逻辑高度自洽，多维指标产生强烈向上共振。
   - 看好：至少两个核心维度（如基本面+技术面）为正面，无明显排雷信号或重大技术瑕疵。
   - 中性：多空因素交织，或维度间存在明显冲突（如基本面好但资金面流出），趋势不明朗。
   - 看空：存在财务排雷信号、重大监管风险，或技术面/资金面出现严重破位、主力坚决出逃。

【交易执行与头寸管理规则】
1. 资金约束：买入金额绝对不能超过用户当前可用资金。若可用资金不足但评级为“看好/强烈看好”需建仓，必须在逻辑中说明“卖出部分现有持仓以腾出资金”的调仓计划，不能因为可用资金不足而减少买入的股数。
2. A股交易规则（极其重要）：
   - 买入股数：必须是 100 股（1手）的整数倍。
   - 卖出股数：绝对不能超过当前实际持仓股数。
3. 操作金额与评级映射（仅供参考，需结合股价折算股数）：
   - 强烈看好：建议买入 10000 - 15000元
   - 看好：建议买入 5000 - 10000元
   - 中性：建议买入 0元（建议观望/减仓）
   - 看空：建议买入 0元（若已有持仓，应执行减仓或清仓）

【严格输出约束】
必须且只能输出合法的 JSON 字符串。严禁包含 Markdown 代码块标记（如 ```json）、不要包含任何额外的解释文本。

【输出格式规则】:
请严格输出 JSON：
{{
 "date": "{self.today}", "code": "{self.code}", "name": "{self.name}",
 "rating": "强烈看好|看好|中性|看空",
 "core_logic": "2-3句话核心逻辑",
 "detailed_analysis": "对每个维度进行详细的交叉验证分析。必须引用各维度报告中的具体数据支撑，严禁编造。若某维度报错需在此说明。",
 "risk_warning": "2-3句话最需警惕的风险",
 "action_plan": {{
   "current_position": {json.dumps(self.hold, ensure_ascii=False)},
   "current_price": {self.current_price},
   "operation": "建仓|加仓|不操作|减仓|清仓",
   "operation_amount": "建议金额(数字)",
   "operation_shares": "建议股数(数字)",
   "operation_reason": "简要说明操作理由（如：因可用资金不足，需要在操作理由后加上“可用资金不足，需要卖出部分现有持仓以腾出资金。”的说明文案）",
   "stop_loss_profit": "硬性止损/止盈位"
 }}
}}"""
        user_message = f"""用户输入的数据是：
【标的信息】: {self.name} ({self.code}), 类型: {self.type}, 行业: {self.industry}
【账户可用资金】: {self.availableFund}元
【当前持仓】: {hold_info}
{news_result_prompt if self.news_reason else ""}
【各维度分析结果】: {dim_results_str}"""

        res = await chat(system_prompt, user_message)
        return json.loads(res)

    async def analyze(self) -> dict[str, Any]:
        """执行完整的 Map-Reduce 分析流程"""
        logger.info(f"🚀 开始 Map-Reduce 分析: {self.name} ({self.code}) | 类型: {self.type}")
        configs = self._get_dimension_configs()

        logger.info(f"📡 正在并发执行 {len(configs)} 个维度的 [API降级获取 + 定制化分析] ...")
        dimension_results = await asyncio.gather(*[self._analyze_single_dimension(cfg) for cfg in configs if len(cfg['api_chain']) > 0])

        logger.info("✅ 维度分析完成，正在进行最终汇总决策 (Reduce)...")
        final_result = await self._final_decision(dimension_results)

        if "error" in final_result:
            logger.error(f"❌ 最终决策失败: {final_result['error']}")
            return {"error": "Final Decision Failed", "raw": final_result}

        logger.info(f"✅ 分析完成, JSON 解析成功。{final_result}")
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


async def analyze_buy_etf(availablesFund: float, etfList: list[dict]) -> list[dict]:
    """可用金额不够，综合分析进行取舍"""
    try:
        system_prompt = """你是一位在中国A股市场拥有丰富实战经验的资深ETF交易与资金分配专家，擅长在“硬资金约束”下进行精细化的头寸管理与最优配置。
【你的任务】
用户当前可用资金有限，但AI初步分析生成的ETF交易决策结果全部为“看好”或“强烈看好”。你需要对初步决策结果进行二次综合裁剪与资金重分配。
核心目标：确保最终“买入”操作的总金额严格 ≤ 可用金额；已持仓的ETF绝对不能卖出；在资金不足时，通过“优中选优”决定哪些买入、哪些少买、哪些放弃，并给出极具说服力的对比理由。

【输入数据说明】
用户将提供一份JSON格式的初步决策结果，包含以下关键字段供你二次决策参考：
rating: 评级（“强烈看好”优先级高于“看好”）。
core_logic & detailed_analysis: 核心逻辑与详细分析（用于对比逻辑的硬度、爆发力及数据支撑强度）。
risk_warning: 风险提示（用于对比风险收益比，风险越大的优先级越低）。
action_plan.current_position: 该ETF当前的持仓情况（核心约束：若持仓>0，则绝对禁止卖出）。
action_plan.operation_amount: 初步建议的金额。
action_plan.operation_shares: 初步建议的股数。

【二次决策框架与约束条件】（请严格按此逻辑思考）：
1. 持仓保护红线（绝对不可违背）：
检查 current_position。若某ETF当前持仓数量 > 0，其最终 operation 只能是“加仓”或“不操作”，绝对禁止出现“减仓”或“清仓”。
2. 优中选优与优先级排序：
必须通过横向对比来决定资金分配优先级。排序规则如下：
第一顺位：rating 为“强烈看好”的标的。
第二顺位：对比 core_logic 的爆发力与确定性，以及 detailed_analysis 中数据支撑的扎实程度。逻辑更硬、数据更实的优先。
第三顺位：对比 risk_warning。短期风险更可控、胜率更高的优先。
3. 资金裁剪与做减法：
计算所有初步建议买入的总金额。若超出可用金额，按上述优先级顺序分配资金。一旦决策结果是买入，必须保证最低买入金额是5000元，否则不买入。
降级/放弃原则：对于优先级靠后的标的，优先降低买入股数；若资金极度紧张，优先级最低的标的买入金额低于5000元，则直接将其 operation 改为“不操作”。
已持仓标的的特殊处理：若资金紧张，已持仓标的可暂缓加仓（改为“不操作”），但绝不能卖出。
4. 交易规则与数学一致性：
所有 operation_shares 必须是100的整数倍（向下取整）。operation_amount 必须与 operation_shares 在数学上合理匹配（金额 ≈ 股数 × current_price）。
5. 构建极具说服力的操作理由（核心要求）：
operation_reason 绝不能只写“资金不足”。必须写明 “对比逻辑”。
如果是“建仓/加仓”，需说明：“在资金有限下，因该标的[引用core_logic或rating优势]，优先级高于其他标的，故优先分配资金。”
如果是“降低股数/不操作”，需说明：“因可用资金不足，且对比发现[指出优先级更高的标的名称]的[逻辑更硬/风险更小]，故削减/放弃本标的的买入，以保全核心仓位。”

【输出格式要求】：
必须且仅输出严格合法的 JSON 数组格式。不要包含任何 Markdown 标记（如 ```json），不要包含任何额外的解释文本。格式示例如下：
[{
 "date": "（保持原内容不变）", "code": "（保持原内容不变）", "name": "（保持原内容不变）",
 "rating": "（保持原内容不变）",
 "core_logic": "（保持原内容不变）",
 "detailed_analysis": "（保持原内容不变）",
 "risk_warning": "（保持原内容不变）",
 "action_plan": {
   "current_position": "（保持原内容不变）",
   "current_price": （保持原内容不变）,
   "operation": "建仓|加仓|不操作",
   "operation_amount": "建议金额(数字)",
   "operation_shares": "建议股数(数字)",
   "operation_reason": "详细说明操作理由，解释为什么要调整操作和仓位",
   "stop_loss_profit": "（保持原内容不变）"
 }
}]"""
        user_message = f"""用户输入的数据是：当前可用金额 {availablesFund}元。AI分析的交易决策结果如下：{json.dumps(etfList, ensure_ascii=False)}"""
        res = await chat(system_prompt, user_message)
        return json(res)
    except:
        logger.error(traceback.format_exc())
