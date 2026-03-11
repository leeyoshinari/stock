#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import asyncio
import json
import traceback
from logging import Logger
from utils.http_client import http


max_retry = 1

sellPrompt = '''
# Role
你是精通 A 股的量化交易专家，性格冷静、果断。你负责对买入后的持仓进行实时监控，根据量价、技术指标与时间锚点，给出唯一的交易执行指令。
# 核心判定规则 (优先级由高到低)
## 强制锁定 (封板/硬止损)
- 涨停保护: 若股价触及涨停（10% 或 20%），无论其他指标如何，必须继续持有。
- 硬性死线: 当前价较持仓成本亏损大于9.5%时，必须立即卖出。
- 技术死刑: 无论盈亏，若出现死叉（MA5/MA10、MACD全部死叉）或价格破布林下轨，立即卖出。
## 量价异动 (关键盘感)
- 放量止损:
 - 09:30 - 10:00  若量比大于8，且股价位于分时均线下方且亏损大于5%，立即卖出。
 - 10:00 - 11:00  若量比大于3，且股价位于分时均线下方且亏损大于5%，立即卖出。
 - 11:00 以后，若量比大于1.5，且股价跌破分时均线且亏损大于6%，立即卖出。
- 高位放量止盈: 在盈利大于5%的状态下，若当天分钟级数据出现放量跳水（量比大于1.5且盈利回撤大于5%），立即卖出。
- 跳空截断: 今日开盘价较前日收盘价跌幅大于6%（尤其是前日上涨后），立即卖出。
## 动态止盈与洗盘识别
- 缩量洗盘保护: 若连续 4-5 个交易日价格下跌但成交量萎缩（量比持续下行），视为洗盘，继续持有，直至触及9.5%硬止损。
- 移动止盈: 盈利状态下，当天分钟级数据从最高点回撤大于3%触发止盈（回撤后也必须是盈利状态）。若属于“缓慢上涨/缩量上涨”，回撤大于1%且处于盈利状态时，立即卖出；若回撤时处于亏损，则继续持有。
# 执行约束 (防误判指令)
- 回撤定义：使用“当日最高价”计算的回撤，和使用“买入后最高价”计算的回撤，两者取最大回撤值作为判断依据。
- 时间锚点: 你的所有判断必须基于 买入日期 之后的交易数据，严禁将买入前的历史波动作为卖出理由。
- 天级别的数据中，最新日期的所有数据都是截至当前时间实时计算出来的，不一定是一整天的数据。
#  输入的数据
- 当前精确时间。
- 买入日期和持仓成本。
- 最近10日天级数据（含当日实时数据）。每个dict的字段解释: current_price：当日收盘价；last_price：前一日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；fund：主力资金净流入（单位：万）；turnover_rate：换手率；ma_five：5日均线；ma_ten：10日均线；ma_twenty：20日均线和布林线中轨线；qrr：量比；diff：MACD的DIFF；dea：MACD的DEA；k：KDJ的K值；d：KDJ的D值；j：KDJ的J值；trix：TRIX指标值；trma：TRIX均线；boll_up：布林线上轨线；boll_low：布林线下轨线。
- 当天分钟实时分时数据。每个dict的字段解释: time：时间，几点几分；price：当前价格；price_avg：当前分时均线价，volume：当前分钟的成交量。
# 标准输出格式
- 返回单个JSON对象，格式是：{{"code":"603128","sell":true,"reason":"分析过程和最终判断结果"}}。如果卖出，sell为true，如果继续持有，sell为false，分析过程和最终判断结果必须包括：交易决策: 卖出/继续持有；核心决策理由；风险预警: (若继续持有，下一个关键压力位或止损位在哪)

【用户输入】
当前时间是: {}，
股票的买入日期是: {}，
持仓成本是: {}，
最近10日天级数据（含当日实时数据）是: {}，
当天分钟级实时数据是: {}
'''


async def sellAI(api_host: str, model: str, auth_code: str, current_time: str, buyPrice: str, buyDate: str, k_line: str, day_line: str, logger: Logger) -> dict:
    url = f"{api_host}/api/chat"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    data = {"model": model, "messages": [{"role": "user", "content": sellPrompt.format(current_time, buyDate, buyPrice, k_line, day_line)}]}
    for attempt in range(max_retry):
        try:
            res = await http.post(url=url, json_data=data, headers=header)
            try:
                gemini_res = json.loads(res.text)
                result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
                res_json = json.loads(result_text.replace('```', '').replace('json', '').replace('\n', ''))
                return res_json
            except:
                logger.error(res.text)
                logger.error(traceback.format_exc())
        except:
            logger.error(traceback.format_exc())
            sleep_time = 2 ** attempt
            await asyncio.sleep(sleep_time)
    raise RuntimeError("Gemini 服务持续繁忙")


def evaluate_sell_strategy(current_time, buy_date, cost_price, daily_data, minute_data):
    """
    A股量化卖出决策引擎
    :param current_time: str, "HH:MM" 格式
    :param buy_date: str, 买入时间
    :param cost_price: float, 买入成本价
    :param daily_data: List[dict], 10日数据，最后一项为当日实时
    :param minute_data: List[dict], 当日分钟数据
    """
    # 只保留买入日期当天及之后的数据
    valid_daily = [d for d in daily_data if d['date'] >= buy_date]
    if not valid_daily:
        return {"action": "HOLD", "reason": "未获取到买入后的有效数据"}

    # 1. 提取基础变量
    today = daily_data[-1]
    prev_day = daily_data[-2]
    curr_price = today['current_price']

    # 计算盈亏比 (当前价 vs 成本)
    pnl_ratio = (curr_price - cost_price) / cost_price

    # 计算买入以来的最高价 (含今日)
    max_price_since_buy = max([d['max_price'] for d in valid_daily])
    today_max = today['max_price']

    # --- 1. 强制锁定 (优先级最高) ---
    # 涨停保护: A股主板10%，创业板/科创板20% (统一按9.5%触发阈值)
    if curr_price >= prev_day['current_price'] * 1.095:
        return {"action": "HOLD", "reason": "涨停保护中"}

    # 硬性死线止损
    if pnl_ratio <= -0.095:
        return {"action": "SELL", "reason": f"触及-9.5%硬止损线 (当前:{pnl_ratio:.2%})"}

    # 技术死刑 (MA & MACD & BOLL)
    is_ma_dead = today['ma_five'] < today['ma_ten']
    is_macd_dead = today['diff'] < today['dea']
    is_boll_break = curr_price < today['boll_low']
    if (is_ma_dead and is_macd_dead) or is_boll_break:
        return {"action": "SELL", "reason": "MA/MACD双死叉或跌破布林下轨"}

    # --- 2. 量价异动 (盘感逻辑) ---
    qrr = today['qrr']  # 量比
    curr_min_node = minute_data[-1]
    on_avg_line = curr_min_node['price'] >= curr_min_node['price_avg']

    # 时间锚点判断 (将 HH:MM 转为整数分钟方便比较)
    h, m = map(int, current_time.split(':'))
    minutes_now = h * 60 + m

    # 分时量比止损逻辑
    if minutes_now <= 600:  # 10:00 之前
        if qrr > 8 and not on_avg_line and pnl_ratio < -0.05:
            return {"action": "SELL", "reason": "早盘高量比且均线下亏损>5%"}
    elif minutes_now <= 660:    # 11:00 之前
        if qrr > 3 and not on_avg_line and pnl_ratio < -0.05:
            return {"action": "SELL", "reason": "盘中量比>3且均线下亏损>5%"}
    elif minutes_now >= 660:    # 11:00 之后
        if qrr > 1.5 and not on_avg_line and pnl_ratio < -0.06:
            return {"action": "SELL", "reason": "午后破位且量比>1.5"}

    # 高位放量止盈 (盈利>5%时)
    if pnl_ratio > 0.05:
        # 盈利回撤定义：从买入后最高点回撤
        max_drawdown = (max_price_since_buy - curr_price) / max_price_since_buy
        if qrr > 1.5 and max_drawdown > 0.05:
            return {"action": "SELL", "reason": "盈利5%以上出现放量跳水"}

    # 跳空截断
    if (today['open_price'] / prev_day['current_price'] - 1) < -0.06:
        return {"action": "SELL", "reason": "大幅低开(>-6%)截断"}

    # --- 3. 动态止盈与洗盘识别 ---
    # 缩量洗盘保护 (判断最近4日是否缩量下跌)
    if len(daily_data) >= 5:
        recent_4 = daily_data[-4:]
        is_vol_down = all(recent_4[i]['volume'] > recent_4[i + 1]['volume'] for i in range(len(recent_4) - 1))
        is_price_down = all(recent_4[i]['current_price'] > recent_4[i + 1]['current_price'] for i in range(len(recent_4) - 1))

        if is_vol_down and is_price_down:
            return {"action": "HOLD", "reason": "识别为缩量洗盘，观察硬止损线"}

    # 移动止盈 (使用当日最高与买入后最高的最大回撤)
    reference_max = max(today_max, max_price_since_buy)
    current_dd = (reference_max - curr_price) / reference_max
    if pnl_ratio > 0:
        # 缓慢/缩量上涨识别 (量比 < 1.0)
        if qrr < 1.0 and current_dd > 0.01:
            return {"action": "SELL", "reason": "慢涨/缩量上涨回撤>1%止盈"}
        # 通用回撤止盈
        if current_dd > 0.03:
            return {"action": "SELL", "reason": "盈利状态从最高点回撤>3%"}
    return {"action": "HOLD", "reason": "未触及过滤规则"}
