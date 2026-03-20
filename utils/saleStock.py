#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import asyncio
import json
import math
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

decidePrompt = '''
# Role
你是一个冷静、犀利的 A 股顶级短线职业交易员。你不仅看数值，更擅长透过量价看到背后的主力意图。

# 复核逻辑（严格按序执行）
1. **资金面检查**：结合 `fund` 数据。股价回撤但资金净流入（>0）通常是洗盘；股价下跌且资金大幅流出，确认为主力出货。
2. **多指标共振**：你需要结合多个指标公共分析，如果技术指标趋势出现明显走弱，必须卖出。
3. **分时支撑**：查看分钟级数据，如果 `price` 长期无法站上 `price_avg`，代表日内抛压极大，反弹无望。
4. **形态博弈**：若当日的天级别数据出现长上影线，代表多头反击失败，抛压剧增。

# 约束条件
- **买入锚点**：所有判断必须基于 买入日期 之后的交易数据，严禁将买入前的历史波动作为卖出理由。
- **最大回撤基准**：当前价相对于股票最高价的回撤幅度。最高价的定义：买入日期之后的所有交易日的最高价，包含当日股票的最高价。

#  输入的数据
- 当前精确时间。
- 买入日期和持仓成本。
- 最近10日天级数据（含当日实时数据）。每个dict的字段解释: day：交易日期；current_price：当日收盘价；last_price：前一日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；fund：主力资金净流入（单位：万）；turnover_rate：换手率；ma_five：5日均线；ma_ten：10日均线；ma_twenty：20日均线和布林线中轨线；qrr：量比；diff：MACD的DIFF；dea：MACD的DEA；k：KDJ的K值；d：KDJ的D值；j：KDJ的J值；trix：TRIX指标值；trma：TRIX均线；boll_up：布林线上轨线；boll_low：布林线下轨线。
- 当天分钟实时分时数据。每个dict的字段解释: time：时间，几点几分；price：当日价格；price_avg：当日分时均线价，volume：当日分钟的成交量。

# 标准输出格式（严格 JSON）
{
  "code": "代码",
  "sell": true/false,
  "reason": "决策:[卖出/持有] | 触发核心:[如:资金流出+J值下拐] | 盘面逻辑:[详细分析资金、均线、回撤的博弈关系] | 止损参考:[若持有，下一步死守的点位]"
}

【用户输入】
当前时间是: {}。
股票的买入日期是: {}。
持仓成本是: {}。
最近10日天级数据（含当日实时数据）是: {}。
当天分钟级实时数据是: {}
'''


def getStockLimitUp(code: str, name: str) -> int:
    if 'st' in name.lower():
        return 5
    if code.startswith("60") or code.startswith("00"):
        return 10
    if code.startswith("68") or code.startswith("30"):
        return 20
    return 10


async def sellAI(api_host: str, model: str, auth_code: str, current_time: str, buyPrice: str, buyDate: str, k_line: str, day_line: str, promptType: str, logger: Logger) -> dict:
    url = f"{api_host}/api/chat"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    if promptType == 'decidePrompt':
        prompt = decidePrompt
    else:
        prompt = sellPrompt
    data = {"model": model, "messages": [{"role": "user", "content": prompt.format(current_time, buyDate, buyPrice, k_line, day_line)}]}
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


def evaluate_sell_strategy(current_time, buy_date, cost_price, daily_data, minute_data, limit_up):
    """
    :param current_time: str, "%Y-%m-%d %H:%M:%S"
    :param buy_date: str, "%Y%m%d"
    :param cost_price: float, 买入成本
    :param daily_data: dict, 键为字段名，值为列表
    :param minute_data: dict, 键为字段名，值为列表
    :param limit_up: float, 股票最大涨跌幅，0.2、0.1
    """
    # ------- 参数设置 --------
    low_open_ratio = -0.06
    # ------------------------
    today = {k: daily_data[k][-1] for k in daily_data if isinstance(daily_data[k], list)}
    prev = {k: daily_data[k][-2] for k in daily_data if isinstance(daily_data[k], list)}

    curr_price = today['current_price']
    pnl = (curr_price - cost_price) / cost_price

    # ---------- 计算买入后最高价 ----------
    max_price_since_buy = cost_price
    for i, day in enumerate(daily_data['day']):
        if day > buy_date:
            max_price_since_buy = max(max_price_since_buy, daily_data['max_price'][i])

    today_high = today['max_price']

    # ---------- 涨停保护 ----------
    if curr_price >= math.floor(today['last_price'] * (1 + limit_up)):
        return {"action": "HOLD", "reason": "触及涨停，锁定持有"}

    # ---------- 硬止损 ----------
    if pnl <= -1 * limit_up:
        return {"action": "SELL", "reason": f"硬止损触发: 亏损{pnl}"}
    if pnl <= -1 * (limit_up - 0.015):
        return {"action": "AI_CHECK", "reason": f"硬止损触发: 亏损{pnl}"}

    # ---------- MA死叉 ----------
    ma_dead = (prev['ma_five'] >= prev['ma_ten'] and today['ma_five'] < today['ma_ten'])

    # ---------- MACD死叉 ----------
    macd_dead = (prev['diff'] >= prev['dea'] and today['diff'] < today['dea'])

    # ---------- 布林破位 ----------
    boll_break = curr_price < today['boll_low']

    if ma_dead or macd_dead or boll_break:
        return {"action": "SELL", "reason": "MA+MACD双死叉或破布林下轨"}

    # ---------- 跳空低开 ----------
    gap = (today['open_price'] - today['last_price']) / today['last_price']
    if gap < low_open_ratio:
        return {"action": "SELL", "reason": f"大幅跳空低开 - {gap}"}

    # ---------- 分时状态 ----------
    intraday = analyze_intraday_structure(minute_data)
    is_weak = intraday['is_weak']
    is_dump = intraday['is_dump']

    qrr = today['qrr']
    h = int(current_time[11:13])
    m = int(current_time[14:16])
    minutes = h * 60 + m

    # ---------- 放量止损 ----------
    if minutes <= 600:
        if qrr > 8 and is_weak and pnl < -0.05:
            return {"action": "SELL", "reason": "早盘高量比破均线且亏损>5%"}

    elif minutes <= 660:
        if qrr > 3 and is_weak and pnl < -0.05:
            return {"action": "SELL", "reason": "盘中量比>3破均线且亏损>5%"}

    else:
        if qrr > 1.5 and is_weak and pnl < -0.06:
            return {"action": "SELL", "reason": "午后量比>1.5破均线且亏损>6%"}

    # ---------- 分钟跳水 ----------
    if pnl > 0.05 and is_dump:
        return {"action": "SELL", "reason": "分钟级数据跳水"}

    # ---------- 均线向下，当天弱势 ----------
    ma_falling = today['ma_five'] < prev['ma_five']
    if is_weak and ma_falling:
        return {"action": "SELL", "reason": "整体趋势向下且当天弱势"}

    # ---------- 盈利回撤 ----------
    ref_high = max(today_high, max_price_since_buy)
    drawdown = (ref_high - curr_price) / ref_high

    if pnl > 0.005:
        if qrr < 1 and drawdown > 0.01:
            return {"action": "SELL", "reason": "慢涨/缩量上涨回撤>1%"}
        if drawdown > 0.03:
            return {"action": "SELL", "reason": "盈利状态最高点回撤>3%"}

    # ---------- 缩量洗盘 ----------
    if len(daily_data['volume']) >= 3:
        vol = daily_data['volume'][-3:]
        price = daily_data['current_price'][-3:]
        vol_down = vol[0] > vol[1] > vol[2]
        price_down = price[0] > price[1] > price[2]
        if vol_down and price_down and today['qrr'] < 0.7:
            return {"action": "HOLD", "reason": "识别为缩量洗盘，暂不操作"}

    # ---------- AI判断 ----------
    return {"action": "AI_CHECK", "reason": "未触发预设过滤逻辑"}


def analyze_intraday_structure(minute_data):
    prices = minute_data['price']
    avgs = minute_data['price_avg']
    n = len(prices)
    if n < 5:
        return {
            "below_avg_ratio": 0,
            "below_avg_duration": 0,
            "is_weak": False,
            "is_dump": False
        }

    # ---------- 1. 均线下方占比 ----------
    below_count = 0
    for i in range(n):
        if prices[i] < avgs[i]:
            below_count += 1

    below_ratio = below_count / n

    # ---------- 2. 连续压制时间 ----------
    max_streak = 0
    current_streak = 0

    for i in range(n):
        if prices[i] < avgs[i]:
            current_streak += 1
            if current_streak > max_streak:
                max_streak = current_streak
        else:
            current_streak = 0

    # ---------- 3. 尾盘跳水 ----------
    last_price = prices[-1]
    last5 = prices[-5:]
    max5 = max(last5)

    drop = (max5 - last_price) / max5

    is_dump = drop > 0.02   # 2%跳水

    # ---------- 4. 综合弱势判断 ----------
    is_weak = False

    if below_ratio > 0.6 or max_streak > n * 0.3:
        is_weak = True

    return {
        "below_avg_ratio": below_ratio,
        "below_avg_duration": max_streak,
        "is_weak": is_weak,
        "is_dump": is_dump
    }
