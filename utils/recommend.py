#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from typing import List, Optional
# from utils.logging import logger
# from utils.results import Result


def linear_least_squares(y: List[float], period: int = 5) -> float:
    n = len(y)
    if n == 0: return 0
    t = [x * 0.03 for x in range(1, n + 1)]
    alpha = 2 / (period + 1)
    weights = [(1 - alpha) ** (n - i - 1) for i in range(n)]
    # weights = [1] * n
    w_sum = sum(weights)
    y_mean = sum(weights[i] * y[i] for i in range(n)) / w_sum
    t_mean = sum(weights[i] * t[i] for i in range(n)) / w_sum
    numerator = sum(weights[i] * (t[i] - t_mean) * (y[i] - y_mean) for i in range(n))
    denominator = sum(weights[i] * (t[i] - t_mean) ** 2 for i in range(n))
    if denominator == 0:
        return 0.0

    b = numerator / denominator
    normalized_b = b / y_mean if y_mean != 0 else 0.0
    angle = math.degrees(math.atan(normalized_b))
    return round(angle, 1)


def calc_angle(y: List[float]) -> float:
    n = len(y)
    if n == 0: return 0
    y_mean = sum(y) / n
    delta = (y[-1] - y[0]) / (n - 1) / y_mean / 0.03
    angle = math.degrees(math.atan(delta))
    return round(angle, 1)


def standard_deviation(data: List[float]) -> float:
    n = len(data)
    mean = sum(data) / n
    squared_diffs = [(x - mean) ** 2 for x in data]
    return round(math.sqrt(sum(squared_diffs) / n), 2)


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[:window]) / window, 2)


def calc_price_average(stock: List) -> dict:
    res = {}
    ma3_price_list = [s.ma_three for s in stock[-5:]]
    ma5_price_list = [s.ma_five for s in stock[-20:]]
    ma10_price_list = [s.ma_ten for s in stock[-20:]]
    ma20_price_list = [s.ma_twenty for s in stock[-20:]]

    res.update({"ma3_angle_l3d": linear_least_squares(ma3_price_list[-3:], 3)})
    res.update({"ma3_angle_l5d": linear_least_squares(ma3_price_list[-5:], 5)})

    res.update({"ma5_angle_l3d": linear_least_squares(ma5_price_list[-3:], 3)})
    res.update({"ma5_angle_l5d": linear_least_squares(ma5_price_list[-5:], 5)})
    res.update({"ma5_angle_l10d": linear_least_squares(ma5_price_list[-10:], 10)})
    res.update({"ma5_angle_l20d": linear_least_squares(ma5_price_list[-20:], 20)})

    res.update({"ma10_angle_l5d": linear_least_squares(ma10_price_list[-5:], 5)})
    res.update({"ma10_angle_l10d": linear_least_squares(ma10_price_list[-10:], 10)})
    res.update({"ma10_angle_l20d": linear_least_squares(ma10_price_list[-20:], 20)})

    res.update({"ma20_angle_l5d": linear_least_squares(ma20_price_list[-5:], 5)})
    res.update({"ma20_angle_l10d": linear_least_squares(ma20_price_list[-10:], 10)})
    res.update({"ma20_angle_l20d": linear_least_squares(ma20_price_list[-20:], 20)})
    return res


def calc_volume_average(stock: List) -> dict:
    res = {}
    qrr_list = [s.qrr for s in stock[-20:]]

    res.update({"volume_angle_l3d": linear_least_squares(qrr_list[-3:], 3)})
    res.update({"volume_angle_l5d": linear_least_squares(qrr_list[-5:], 5)})
    res.update({"volume_angle_l10d": linear_least_squares(qrr_list[-10:], 10)})
    res.update({"volume_angle_l20d": linear_least_squares(qrr_list[-20:], 20)})
    res.update({"qrr_deviation_l1d": standard_deviation(qrr_list[-5:])})
    res.update({"qrr_deviation_l2d": standard_deviation(qrr_list[-6: -1])})
    res.update({"qrr_deviation_l3d": standard_deviation(qrr_list[-7: -2])})
    res.update({"qrr_deviation_l4d": standard_deviation(qrr_list[-8: -3])})
    return res


def calc_volume_realtime_average(stock: List) -> dict:
    res = {}
    volumn_list = [s.volumn for s in stock[-10:]]
    res.update({"volumn_angle_l3d": calc_angle(volumn_list[-3:])})
    res.update({"volumn_angle_l5d": calc_angle(volumn_list[-5:])})
    return res


if __name__ == '__main__':
    a = [159.68, 176.86, 193.1, 210, 201]
    b = [6.6, 6.7, 7.31]
    print(linear_least_squares(a, 5))
    print(calc_angle(a))
