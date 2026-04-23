#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from datetime import datetime
from typing import Any


def getStockLimitUp(code: str, name: str) -> float:
    if 'st' in name.lower():
        return 0.05
    if code.startswith("30") or code.startswith("68"):
        return 0.2
    return 0.1


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


def evaluate_sell_strategy(current_time: str, buy_date: str, cost_price: float, daily_data: dict, minute_data: dict, limit_up: float) -> dict:
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

    curr_price = minute_data['price'][-1]    # today['current_price']
    pnl = (curr_price - cost_price) / cost_price

    # ---------- 计算买入后最高价 ----------
    max_price_since_buy = cost_price
    for i, day in enumerate(daily_data['day']):
        if day > buy_date:
            max_price_since_buy = max(max_price_since_buy, daily_data['max_price'][i])

    today_high = today['max_price']

    # ---------- 涨停保护 ----------
    if curr_price >= round(math.floor(today['last_price'] * (1 + limit_up) * 100) / 100, 2):
        return {"action": "HOLD", "reason": "触及涨停，锁定持有"}

    # ---------- 硬止损 ----------
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
    return {"action": "HOLD", "reason": "未触发预设过滤逻辑"}


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
    is_dump = False
    if len(prices) > 10:
        last_price = prices[-1]
        last5 = prices[-10:]
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


def find_shrink_stock(day_data: dict, start_index: int = None) -> dict[str, Any]:
    price = day_data['current_price']
    volume = day_data['volume']
    turnover = [float(r.replace('%', '')) for r in day_data['turnover_rate']]
    qrr = day_data['qrr']
    ma5 = day_data['ma_five']
    ma10 = day_data['ma_ten']
    n = len(price)

    max_price = max(price)
    min_price = min(price)
    up_gain = (max_price - min_price) / min_price
    if start_index is None:
        start_index = price.index(max_price)
    else:
        # 第一天最高点，可能第二天微跌，然后才开始下跌
        start_index = price.index(max_price) + 1
        if (start_index) >= len(price):
            return {"fund": False, "start": start_index, "reason": "缩量下跌不到3天"}
        down_drop = (price[start_index] - max_price) / max_price
        if down_drop < -0.02:
            return {"fund": False, "start": start_index, "reason": "第二天跌幅大于2%"}
    end = n - 1
    length = end - start_index + 1
    if length < 3 or length > 5:
        return {"fund": False, "start": start_index, "reason": "缩量下跌不到3天或超过5天"}
    if up_gain < 0.15:
        return {"fund": False, "start": start_index, "reason": "前期涨幅太低，不在上涨趋势中"}
    for i in range(start_index + 1, n):
        price_down = price[i] < price[i - 1]
        volume_down = volume[i] < volume[i - 1]
        turnover_down = turnover[i] < turnover[i - 1] * 1.05
        if not (price_down and volume_down and turnover_down):
            return {"fund": False, "start": start_index, "reason": "价格、成交量、换手率没有同步下跌"}
        amplitude = (day_data['max_price'][i] - day_data['min_price'][i]) / price[i]
        if amplitude < 0.015:
            return {"fund": False, "start": start_index, "reason": "振幅过小，疑似阴跌"}
    if day_data['open_price'][start_index + 1] > price[start_index]:
        return {"fund": False, "start": start_index, "reason": "第二天高开"}
    if qrr[-1] > 0.6 or qrr[start_index] < 1.2:
        return {"fund": False, "start": start_index, "reason": "最近一天的量比大于0.6"}
    total_drop = (price[end] - price[start_index]) / price[start_index]
    if total_drop < -0.08:
        return {"fund": False, "start": start_index, "reason": "缩量下跌阶段总跌幅大于8%"}
    if total_drop > -0.03:
        return {"fund": False, "start": start_index, "reason": "缩量下跌阶段总跌幅小于3%，回撤跌幅不够"}
    for i in range(start_index + 1, end + 1):
        drop = (price[i] - price[i - 1]) / price[i - 1]
        if drop < -0.05:
            return {"fund": False, "start": start_index, "reason": "某一天的跌幅过大，大于5%"}
    price_trend = ma10[-1] > ma10[-2] > ma10[-3] and price[-1] > ma10[-1] and ma5[-1] > ma10[-1]
    ma5_trend = ma5[-3] > ma5[-4] > ma5[-5]
    if not price_trend:
        return {"fund": False, "start": start_index, "reason": "10日线未向上，或者当前价在10日线下，或者5日线在10日线下"}
    if not ma5_trend:
        return {"fund": False, "start": start_index, "reason": "5日均线趋势太差"}
    if (price[-1] - ma5[-1]) / ma5[-1] > -0.01:
        return {"fund": False, "start": start_index, "reason": "价格不在5日均线下方附近之上"}
    if day_data['min_price'][-1] >= price[-1] * 0.99:
        return {"fund": False, "start": start_index, "reason": "无下影线，缺乏承接"}
    if day_data['diff'][-1] - day_data['dea'][-1] < 0.01:
        return {"fund": False, "start": start_index, "reason": "MACD出现死叉"}
    p_slope, p_r2 = linear_check(price[start_index:])
    v_slope, v_r2 = linear_check(volume[start_index:])
    if p_slope >= 0 or p_r2 < 0.95:
        return {"fund": False, "start": start_index, "reason": "价格下跌没有线性特征"}
    if v_slope >= 0 or v_r2 < 0.9:
        return {"fund": False, "start": start_index, "reason": "成交量下跌没有线性特征"}
    return {"fund": True, "reason": "", "start": start_index, "start_date": day_data['day'][start_index]}


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


def linear_check(arr):
    """
    输入: arr - list，表示一段价格/成交量/换手率数据
    输出: slope - 斜率
          r2    - 决定系数 R²
    """
    n = len(arr)
    if n < 2:
        return 0, 0  # 数据太少无法拟合

    x_sum = 0
    y_sum = 0
    xy_sum = 0
    x2_sum = 0
    y_mean = sum(arr) / n

    for i, y in enumerate(arr):
        x = i
        x_sum += x
        y_sum += y
        xy_sum += x * y
        x2_sum += x * x

    # 计算斜率 a 和截距 b
    denominator = n * x2_sum - x_sum * x_sum
    if denominator == 0:
        slope = 0
        intercept = y_mean
    else:
        slope = (n * xy_sum - x_sum * y_sum) / denominator
        intercept = (y_sum - slope * x_sum) / n

    # 计算 R²
    ss_tot = sum((y - y_mean) ** 2 for y in arr)
    ss_res = sum((y - (slope * i + intercept)) ** 2 for i, y in enumerate(arr))
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else 0

    return slope, r2
