#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

from typing import List, Dict, Any


def analyze_buy_signal(stock_data_list: List[Dict[str, Any]], params: dict = None) -> Dict[str, Any]:
    """
    改进版买入信号分析器
    输入:
        stock_data_list: 按时间升序的行情数据列表，最后一项为最新日
    输出:
        包含买入信号、置信度、原始分数、各子信号分项及理由
    """

    # -------------------- 参数 --------------------
    eps = 1e-9
    if not isinstance(stock_data_list, list) or len(stock_data_list) < 5:
        return {"buy": False, "score": 0, "reason": "数据天数不足或格式错误"}

    # -------------------- 最新数据 --------------------
    d0, d1, d2, d3 = stock_data_list[-1], stock_data_list[-2], stock_data_list[-3], stock_data_list[-4]

    # -------------------- MACD --------------------
    diff0, diff1, diff2, diff3 = d0["diff"], d1["diff"], d2["diff"], d3["diff"]
    dea0, dea1, dea2 = d0["dea"], d1["dea"], d2["dea"]
    hist0, hist1, hist2 = diff0 - dea0, diff1 - dea1, diff2 - dea2
    slope_diff1, slope_diff2 = diff0 - diff1, diff1 - diff2
    slope_delta = slope_diff1 - slope_diff2

    # (3) 近3日、5日平均成交量
    vol3 = sum([x["volume"] for x in stock_data_list[-3:]]) / 3.0
    vol5 = sum([x["volume"] for x in stock_data_list[-5:]]) / 5.0

    # -------------------- 均线 --------------------
    ma5_0, ma5_1, ma5_2 = d0["ma_five"], d1["ma_five"], d2["ma_five"]
    ma10_0 = d0["ma_ten"]

    # -------------------- 价格 --------------------
    price0, price1, price2 = d0["current_price"], d1["current_price"], d2["current_price"]
    last0, high0, low0 = d0["last_price"], d0["max_price"], d0["min_price"]

    # -------------------- 其他指标 --------------------
    qrr0, qrr1 = d0["qrr"], d1["qrr"]
    j0, j1, j2 = d0["j"], d1["j"], d2["j"]
    k0, k1, _ = d0["k"], d1["k"], d2["k"]
    trix0, trix1, trix2 = d0["trix"], d1["trix"], d2["trix"]
    trma0, trma2 = d0["trma"], d2["trma"]

    # -------------------- 构造子信号 --------------------
    subs = {}
    contribs = {}
    score = 0

    # ===== 均线趋势 =====
    subs["ma5_up"] = (ma5_0 >= ma5_1) and (ma5_1 >= ma5_2)
    subs["price_above_ma5"] = price0 > ma5_0
    subs["price_vs_ma10_pct"] = (price0 - ma10_0) / (abs(ma10_0) + eps) > -0.01
    if subs["ma5_up"] and subs["price_above_ma5"] and subs["price_vs_ma10_pct"]:
        score += 2.0
        contribs["ma5_up"] = 2.0
    else:
        score -= 2.0
        contribs["ma5_up"] = -2.0

    # ===== 成交量强度 =====
    subs["vol3_vs_vol5_ratio"] = (vol3 / (vol5 + eps)) if vol5 > 0 else 1.0
    subs["qrr_strong"] = (qrr0 >= params["qrr_strong"] and qrr0 <= 3.0) and (qrr1 >= 0.9)
    # if subs["vol3_vs_vol5_ratio"] > params["qrr_strong"]:
    #     score += 1.0
    #     contribs["vol3_vs_vol5_ratio"] = 1.0
    # else:
    #     score -= 1.5
    #     contribs["vol3_vs_vol5_ratio"] = -1.5
    if subs["qrr_strong"]:
        score += 1.0
        contribs["qrr_strong"] = 1.0
    else:
        score -= 1.5
        contribs["qrr_strong"] = -1.5

    # ===== MACD =====
    subs["hist_converging"] = (hist0 > hist1) and (hist1 > hist2)
    subs["diff_up"] = (diff0 > diff1) and (diff1 > diff2)
    subs["macd_cross_fresh"] = (diff1 <= dea1 + eps) and (diff0 >= dea0 - eps)  # 已经出现金叉
    subs["macd_bullish_pre_cross"] = subs["hist_converging"] and subs["diff_up"] and (not subs["macd_cross_fresh"])  # 金叉前
    # subs["diff_slope_delta"] = slope_delta

    if subs["diff_up"] and subs["hist_converging"] and subs["macd_cross_fresh"]:
        score += 2.0
        contribs["macd_cross_fresh"] = 2.0

    subs["diff_decreasing"] = (slope_diff1 < 0)     # 若 diff 开始向下，视为动能衰退 -> 硬拒绝买入
    base_strength = 0
    if subs["diff_up"] and subs["hist_converging"]:
        if diff1 > 0 and slope_diff1 > 0 and slope_diff2 > 0:
            base_strength = 2.0   # 正区间上升：强动能，给较高基础权重
        else:
            # 负区间上升：要求斜率正在加速才能给分，且权重较小
            if slope_delta > 0 and slope_diff1 > params["diff_delta"] and slope_diff2 > params["diff_delta"]:
                base_strength = 1.0  # 负区间回升但加速 -> 适度正分
            else:
                base_strength = 0.5   # 负区间但未加速 -> 更小的正分

        if subs["macd_cross_fresh"] or subs["macd_bullish_pre_cross"]:
            score = score + base_strength
            contribs["macd_diff"] = base_strength
        else:
            score -= 2.0
            contribs["macd_diff"] = -2.0
    else:
        score -= 2.0
        contribs["diff_up"] = -2.0

    # 连续上方天数
    macd_above_days = 0
    for i in range(1, min(5, len(stock_data_list)) + 1):
        if stock_data_list[-i]["diff"] > stock_data_list[-i]["dea"]:
            macd_above_days += 1
        else:
            break
    if macd_above_days > 2:
        score -= 2.0
        contribs["macd_above_days"] = -2.0

    # ===== KDJ =====
    subs["j_low_rebound"] = (j1 < 30) and (j0 > j1)
    subs["kdj_pre_bullish"] = (k0 > k1) and (j0 > j1) and subs["j_low_rebound"]
    subs["j_high_value"] = (j0 > 70) or (j1 > 70) or (j2 > 60)     # 如果 J 值过高，拒绝买入
    if subs["kdj_pre_bullish"]:
        score += 1.0
        contribs["kdj_pre_bullish"] = 1.0
    else:
        score -= 1.0
        contribs["kdj_pre_bullish"] = -1.0

    # ===== TRIX =====
    subs["trix_up"] = (trix0 > trix1) and (trix1 > trix2) and ((trix0 - trix1) > params["trix_delta_min"])
    subs["trix_dead"] = (trix2 >= trma2) and (trix0 <= trma0)   # 出现死叉，拒绝买入
    subs["trix_pre_bullish"] = subs["trix_up"] and (trix0 <= trma0 + eps)
    if subs["trix_pre_bullish"]:
        score += 1.0
        contribs["trix_pre_bullish"] = 1.0
    else:
        score -= 1.0
        contribs["trix_pre_bullish"] = -1.0

    # ===== 风险信号 =====
    candle_range = high0 - low0 if high0 != low0 else eps
    upper_wick_pct = (high0 - price0) / (candle_range + eps)
    subs["big_upper_wick"] = (upper_wick_pct > 0.4) and (d0["volume"] > d1["volume"])   # 上影线
    subs["bear_volume_today"] = (price0 < last0 * params["down_price_pct"]) and (qrr0 > params["qrr_strong"])    # 放量下跌, 拒绝买入
    subs["too_hot"] = ((price0 - price2) / (price2 + eps)) > params["too_hot"]         # 近2天上涨幅度, 拒绝买入
    subs["high_position_volume"] = (price0 > ma10_0 * 1.05) and (subs["vol3_vs_vol5_ratio"] > params["qrr_strong"])    # 价格处于高位, 拒绝买入
    subs["rebound_from_ma5"] = (price1 < ma5_1) and (price0 > ma5_0) and (qrr0 > 1.5)   # 超跌后回踩5日均线

    if subs["big_upper_wick"]:
        score -= 2.0
        contribs["big_upper_wick"] = -2.0
    # else:
    #     score += 1.0
    #     contribs["big_upper_wick"] = 1.0

    if subs["rebound_from_ma5"]:    # 超跌后回踩5日均线, 不易出现的信号，不计入得分门槛
        score += 3.0
        contribs["rebound_from_ma5"] = 3.0

    # 缩量下跌后的放量反弹
    price3 = d3["current_price"]
    qrr2, qrr3 = d2["qrr"], d3["qrr"]
    subs["last_3_price"] = (price1 <= price2) and (price2 < price3) and (price0 > ma5_0)    # 价格逐日下跌
    subs["last_3_diff"] = (diff0 > diff1) and (diff2 <= diff3) and (diff1 <= diff2) and (diff1 > 0) and (diff3 > 0) and (diff3 - diff1 < 0.03)  # 允许diff轻微下跌，但必须大于0 +2.0
    subs["last_3_macd"] = hist0 > 0 and hist1 > 0 and hist2 > 0     # +2.0
    subs["last_trix_delta"] = trix0 - trma0 > 0      # +1.0
    subs["last_3_qrr"] = (qrr1 <= qrr2) and (qrr2 < qrr3) and (qrr1 < 0.6) and (qrr0 > 2 * qrr1)    # 先缩量下跌，再放量上涨 +1.5
    if subs["ma5_up"] and subs["last_3_price"] and subs["last_3_diff"] and subs["last_3_macd"] and subs["last_trix_delta"] and subs["last_3_qrr"]:
        score += 12.0
        contribs["volume_decline_rise"] = 12.0

    # -------------------- 硬拒绝条件 --------------------
    hard_reject = subs["high_position_volume"] or subs["bear_volume_today"] or subs["diff_decreasing"] or subs["j_high_value"] or subs["too_hot"] or subs["trix_dead"]
    if hard_reject:
        score = -9
    buy = score >= params["min_score"]

    # -------------------- 结果输出 --------------------
    reasons = []
    for k, v in contribs.items():
        if v > 0:
            reasons.append(f"{k}+{v:.2f}")
        elif v < 0:
            reasons.append(f"{k}{v:.2f}")

    return {
        "code": d0["code"],
        "name": d0["name"],
        "day": d0["day"],
        "price": price0,
        "buy": buy,
        "score": score,
        "subsignals": subs,
        "contribs": contribs,
        "hard_reject": hard_reject,
        "reasons": "; ".join(reasons)
    }
