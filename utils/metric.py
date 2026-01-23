#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from typing import List, Dict, Any


def analyze_buy_signal(stock_data_list: List[Dict[str, Any]], params: dict = None) -> Dict[str, Any]:
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


def analyze_buy_signal_new(stock_data_list: List[Dict[str, Any]]) -> Dict[str, Any]:
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
        'min_score': 5
    }
    params = default_params

    # -------------------- 参数 --------------------
    score = 0
    reasons = []
    if not isinstance(stock_data_list, list) or len(stock_data_list) < params['min_days_for_trend']:
        return {"buy": False, "score": 0, "reason": "数据天数不足或格式错误"}

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
    macd_bar_increase = macd_bar[-1] > macd_bar[-2]

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


def bollinger_bands(prices, middle, n=20, k=2):
    # ALTER TABLE detail ADD COLUMN bollinger_upper FLOAT;
    # ALTER TABLE detail ADD COLUMN bollinger_down FLOAT;
    if len(prices) < n:
        return middle, middle
    window = prices[-n:]
    data_len = len(window)
    variance = sum((p - middle) ** 2 for p in window) / data_len
    std = math.sqrt(variance)
    up = middle + k * std
    dn = middle - k * std
    return up, dn
