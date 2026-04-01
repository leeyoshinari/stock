#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from datetime import datetime
from typing import Any


def analyze_buy_signal(stock_data_list: list[dict[str, Any]], params: dict = None) -> dict[str, Any]:
    """
    改进版买入信号分析器
    输入:
        stock_data_list: 按时间升序的行情数据列表，最后一项为最新日
    输出:
        包含买入信号、置信度、原始分数、各子信号分项及理由
    """
    default_params = {
        'min_days_for_trend': 4,  # 检查最近的最小天数，用于均线、价格趋势、MACD等持续性判断（场景2,4）
        'qrr_threshold': 1.3,     # 量比阈值，大于此值视为成交量放大（场景3，经验值：1.5表示成交量是过去5日均量的1.5倍以上）
        'min_total_rise_pct': 0.02,  # 最近几天总体涨幅最小值,5%作为强势上涨标准
        'macd_gold_cross_days': 0,   # MACD金叉持续最小天数
        'trix_upward_threshold': 0.0,      # TRIX > trma 视为金叉，>0视为向上（场景7）
        'trix_slow_increase_pct': 0.05,    # TRIX缓慢上涨的百分比阈值（<5%增长视为慢，场景7）
        'upper_shadow_ratio': 0.3,         # 上影线长度比率阈值
        'min_score': 8,
        'kdj_gold_cross_days': 1,          # KDJ金叉持续最小天数（K > D 持续天数，至少3天视为强势）
        'kdj_strong_zone': 50.0,           # K, D, J > 此值视为强势区
        'kdj_overbought_threshold': 80.0,  # J > 此值视为超买，可能涨势乏力（但初期允许，如果持续天数不多）
        'kdj_overbought_max_days': 3       # 超买持续最大天数，超过则视为弱势
    }

    if params is None:
        params = default_params
    else:
        tmp = default_params.copy()
        tmp.update(params)
        params = tmp

    # -------------------- 参数 --------------------
    eps = 1e-9
    score = 0
    reasons = []
    if not isinstance(stock_data_list, list) or len(stock_data_list) < params['min_days_for_trend']:
        return {"buy": False, "score": 0, "reason": "数据天数不足或格式错误"}

    # -------------------- 均线 --------------------
    ma5_up = True
    for i in range(1, params['min_days_for_trend']):
        if stock_data_list[i]['ma_five'] <= stock_data_list[i - 1]['ma_five']:
            ma5_up = False
            break
    ma5_up = ma5_up and stock_data_list[-1]['ma_five'] > stock_data_list[-1]['ma_ten']
    if ma5_up:
        score += 1
        reasons.append('5日均线向上并且大于10日均线')
    else:
        score -= 1
        reasons.append('5日均线未享向上')

    # -----------价格-----------------
    price_aboce_ma5 = stock_data_list[-1]['current_price'] > stock_data_list[-1]['ma_five']     # 当前价格必须站上5日均线
    total_rise = (stock_data_list[-1]['current_price'] - stock_data_list[-3]['last_price']) / stock_data_list[-3]['last_price']
    if price_aboce_ma5 and total_rise >= params['min_total_rise_pct']:
        score += 1
        reasons.append('当天上涨且最近3天总体涨幅满足条件')
    else:
        score -= 1
        reasons.append('价格上涨趋势不足')

    # -------------------- 成交量 --------------------
    qrr_up = True
    if stock_data_list[-1]['qrr'] < params['qrr_threshold']:
        qrr_up = False
    # if stock_data_list[-2]['qrr'] < 0.9:
    #     qrr_up = False
    if stock_data_list[-1]['qrr'] <= stock_data_list[-2]['qrr'] or stock_data_list[-2]['qrr'] <= stock_data_list[-3]['qrr']:
        qrr_up = False
    if qrr_up:
        score += 1
        reasons.append("成交量放大且持续递增")
    else:
        score -= 1
        reasons.append("成交量未充分放大")

    # -------------------- MACD --------------------
    macd_bar = []
    for day in stock_data_list:
        macd_bar.append(day['diff'] - day['dea'])

    # 计算金叉出现的天数
    gold_cross_count = 0
    for day in stock_data_list:
        if day['diff'] > day['dea']:
            gold_cross_count += 1
        else:
            gold_cross_count = 0
    if gold_cross_count >= params['macd_gold_cross_days']:
        score += 1
        reasons.append('MACD金叉持续足够天数')
    else:
        score -= 1
        reasons.append('MACD金叉未持续足够天数')

    # diff 必须大于0
    diff_greater_zero = stock_data_list[-1]['diff'] > 0

    # MACD柱不减小
    macd_bar_increase = macd_bar[-1] > macd_bar[-2]

    # MACD柱增大速度
    bar_increase_speed = []
    for i in range(1, len(macd_bar)):
        bar_increase_speed.append(macd_bar[i] - macd_bar[i - 1])
    macd_bar_up_speed = (bar_increase_speed[-1] - bar_increase_speed[-2]) > (bar_increase_speed[-2] - bar_increase_speed[-3])

    if diff_greater_zero and macd_bar_increase and macd_bar_up_speed:
        score += 2
        reasons.append('MACD diff大于0且加速上涨')
    else:
        score -= 2
        reasons.append('MACD 未加速上涨')

    # --------- KDJ -------------
    # 出现金叉的天数
    kdj_gold_cross_count = 0
    kdj_overbought_days = 0
    for day in stock_data_list:
        if day['k'] > day['d']:
            kdj_gold_cross_count += 1
        else:
            kdj_gold_cross_count = 0
        if day['j'] > params['kdj_overbought_threshold']:
            kdj_overbought_days += 1
    if (kdj_gold_cross_count >= params['kdj_gold_cross_days'] and kdj_overbought_days <= params['kdj_overbought_max_days'] and stock_data_list[-1]['k'] > params['kdj_strong_zone'] and stock_data_list[-1]['d'] > params['kdj_strong_zone'] and stock_data_list[-1]['j'] > params['kdj_strong_zone']):
        score += 1
        reasons.append('KDJ处于强势')
    else:
        reasons.append('KDJ趋势不足')
    if stock_data_list[-1]['j'] > 100:
        score -= 2
        reasons.append('KDJ处于严重超买')

    # ------ 上影线 -------
    candle_range = stock_data_list[-1]['max_price'] - stock_data_list[-1]['min_price']
    upper_wick_pct = (stock_data_list[-1]['max_price'] - stock_data_list[-1]['current_price']) / (candle_range + eps)
    if upper_wick_pct <= params['upper_shadow_ratio']:
        score += 1
        reasons.append('无长上影线')
    else:
        reasons.append('出现长上影线')

    buy = score >= params["min_score"]

    return {
        "code": stock_data_list[-1]["code"],
        "name": stock_data_list[-1]["name"],
        "day": stock_data_list[-1]["day"],
        "price": stock_data_list[-1]['current_price'],
        "buy": buy,
        "score": score,
        "reasons": "; ".join(reasons)
    }


def analyze_buy_signal_new(stock_data_list: list[dict[str, Any]]) -> dict[str, Any]:
    """
    改进版买入信号分析器
    输入:
        stock_data_list: 按时间升序的行情数据列表，最后一项为最新日
    输出:
        包含买入信号、置信度、原始分数、各子信号分项及理由
    """
    default_params = {
        'min_days_for_trend': 3,  # 检查最近的最小天数，用于均线、价格趋势、MACD等持续性判断
        'qrr_threshold': 1.2,     # 量比阈值，大于此值视为成交量放大（场景3，经验值：1.5表示成交量是过去5日均量的1.5倍以上）
        'upper_shadow_ratio': 0.3,         # 上影线长度比率阈值
        'open_low_ratio': -0.015,     # 低开百分比
        'min_score': 6
    }
    params = default_params

    # -------------------- 参数 --------------------
    score = 0
    reasons = []
    if not isinstance(stock_data_list, list) or len(stock_data_list) < params['min_days_for_trend']:
        return {"buy": False, "score": 0, "reason": "数据天数不足或格式错误"}

    low_open_ratio = (stock_data_list[-1]['open_price'] - stock_data_list[-1]['last_price']) / stock_data_list[-1]['last_price']
    low_open = low_open_ratio > params['open_low_ratio']
    if low_open:
        score += 1
        reasons.append('今天未低开')
    else:
        score -= 1
        reasons.append('今天大幅低开')

    # -------------------- 均线 --------------------
    ma5_up = True
    for i in range(len(stock_data_list) - params['min_days_for_trend'], len(stock_data_list)):
        print(stock_data_list[i]['day'])
        if stock_data_list[i]['ma_five'] <= stock_data_list[i - 1]['ma_five']:
            ma5_up = False
            break
    ma5_up = ma5_up and stock_data_list[-1]['ma_five'] > stock_data_list[-1]['ma_ten']
    if ma5_up:
        score += 1
        reasons.append('5日均线向上并且大于10日均线')
    else:
        score -= 1
        reasons.append('5日均线未向上')

    # -----------价格-----------------
    price_aboce_ma5 = stock_data_list[-1]['current_price'] > stock_data_list[-1]['ma_five']     # 当前价格必须站上5日均线
    if price_aboce_ma5:
        score += 1
        reasons.append('当天上涨且最近3天总体涨幅满足条件')
    else:
        score -= 1
        reasons.append('价格上涨趋势不足')

    # -------------------- 成交量 --------------------
    qrr_up = True
    if stock_data_list[-1]['qrr'] < params['qrr_threshold']:
        qrr_up = False
    if stock_data_list[-1]['volume'] <= stock_data_list[-2]['volume']:
        qrr_up = False
    if qrr_up:
        score += 1
        reasons.append("成交量放大且持续递增")
    else:
        score -= 1
        reasons.append("成交量未充分放大")

    # -------------------- MACD --------------------
    macd_bar = []
    for day in stock_data_list:
        macd_bar.append((day['diff'] - day['dea']) * 2)

    # diff 必须大于0
    diff_greater_zero = stock_data_list[-1]['diff'] > 0

    # MACD柱不减小
    macd_bar_increase = macd_bar[-1] > macd_bar[-2] > macd_bar[-3]

    macd_bar_increase123 = stock_data_list[-1]['diff'] > -0.2 and macd_bar_increase and macd_bar[-1] > 0.2

    if (diff_greater_zero and macd_bar_increase) or macd_bar_increase123:
        score += 1
        reasons.append('MACD diff大于0且加速上涨')
    else:
        score -= 1
        reasons.append('MACD 未加速上涨')

    # ------ 上影线 -------
    candle_range = stock_data_list[-1]['max_price'] - stock_data_list[-1]['min_price']
    upper_wick_pct = (stock_data_list[-1]['max_price'] - stock_data_list[-1]['current_price']) / (candle_range + 0.000001)
    if upper_wick_pct <= params['upper_shadow_ratio']:
        score += 1
        reasons.append('无长上影线')
    else:
        score -= 1
        reasons.append('出现长上影线')

    buy = score >= params["min_score"]

    return {
        "code": stock_data_list[-1]["code"],
        "name": stock_data_list[-1]["name"],
        "day": stock_data_list[-1]["day"],
        "price": stock_data_list[-1]['current_price'],
        "turnover_rate": stock_data_list[-1]['turnover_rate'],
        "buy": buy,
        "score": score,
        "reasons": "; ".join(reasons)
    }


def find_shrink_stock(day_data: dict):
    # 找缩量下跌的起点
    price = day_data['current_price']
    volume = day_data['volume']
    n = len(price)
    price_high = max(price)
    volume_high = max(volume)
    start_index = -1
    for i in range(n - 2, 1, -1):
        price_seg = price[i:]
        volume_seg = volume[i:]

        cond_price = max(price_seg) >= price_high * 0.9
        cond_volume = max(volume_seg) >= volume_high * 0.8
        if cond_price and cond_volume:
            start_index = i
    if start_index == -1:
        return {"fund": False, "reason": "未找到缩量下跌起点"}
    if n - start_index < 3 or n - start_index > 5:
        return {"fund": False, "reason": "缩量下跌不到3天或超过5天"}
    price_list = day_data['current_price'][start_index:]
    qrr_list = day_data['qrr'][start_index:]
    turnover_list = day_data['turnover_rate'][start_index:]
    # 指标必须同步下降
    is_sync_down = check_down(price_list) and check_down(qrr_list) and check_down(turnover_list, 1)
    if not is_sync_down:
        return {"fund": False, "reason": "价格、成交量、换手率没有同步下跌"}
    if qrr_list[-1] > 0.6:
        return {"fund": False, "reason": "最近一天的量比大于0.6"}
    # 跌幅不能太大
    total_drop = (price_list[-1] - price_list[0]) / price_list[0]
    if total_drop < -0.08:
        return {"fund": False, "reason": "缩量下跌阶段总跌幅大于8%"}
    # 禁止大跌、阴跌
    for i in range(1, len(price_list)):
        drop = (price_list[i] - price_list[i - 1]) / price_list[i - 1]
        if drop < -0.05:
            return {"fund": False, "reason": "某一天的跌幅过大，大于5%"}
    ma5 = day_data['ma_five']
    ma10 = day_data['ma_ten']
    ma20 = day_data['ma_twenty']
    # 10日线、20日线 向上，当前价在10日线上
    price_trend = ma10[-1] > ma10[-2] > ma10[-3] and ma20[-1] > ma20[-2] > ma20[-3] and day_data['current_price'][-1] > ma10[-1]
    ma5_trend = ma5[-3] > ma5[-4] > ma5[-5]
    if not price_trend or not ma5_trend:
        return {"fund": False, "reason": "均线趋势走差"}
    if day_data['diff'][-1] - day_data['dea'][-1] < 0.01:
        return {"fund": False, "reason": "MACD出现死叉"}
    return {"fund": True, "reason": ""}


def check_down(data: list, max_violation=0) -> bool:
    violation = 0
    for i in range(len(data) - 1):
        if data[i] < data[i + 1]:
            violation += 1
    return violation <= max_violation


def bollinger_bands(prices, middle, n=20, k=2):
    if len(prices) < n:
        return middle, middle
    window = prices[-n:]
    data_len = len(window)
    variance = sum((p - middle) ** 2 for p in window) / data_len
    std = math.sqrt(variance)
    up = middle + k * std
    dn = middle - k * std
    return up, dn


def real_traded_minutes() -> int:
    """
    实时获取当前时间，计算 A 股当日已交易分钟数
    返回范围：1 ~ 240
    """
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    current = hour * 60 + minute
    morning_start = 9 * 60 + 30     # 09:30
    morning_end = 11 * 60 + 30    # 11:30
    afternoon_start = 13 * 60       # 13:00
    afternoon_end = 15 * 60       # 15:00

    if current < morning_start:
        traded = 0
    elif morning_start <= current <= morning_end:
        traded = current - morning_start
    elif morning_end < current < afternoon_start:
        traded = 120
    elif afternoon_start <= current <= afternoon_end:
        traded = 120 + (current - afternoon_start)
    else:
        traded = 240

    if traded < 1:
        return 1
    if traded > 240:
        return 240
    return traded
