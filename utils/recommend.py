#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from typing import List, Optional
from utils.logging import logger
from utils.results import Result


def linear_least_squares(y: List[float], weights: Optional[List[float]] = None) -> float:
    n = len(y)
    t = list(range(1, n + 1))

    if weights is None:
        weights = [1.0] * n
    if len(weights) != n:
        raise ValueError("weights 长度必须和 y 相同")

    log_y = [math.log(v) for v in y]

    w_sum = sum(weights)
    t_bar = sum(w * ti for w, ti in zip(weights, t)) / w_sum
    x_bar = sum(w * xi for w, xi in zip(weights, log_y)) / w_sum

    num = sum(w * (ti - t_bar) * (xi - x_bar) for w, ti, xi in zip(weights, t, log_y))
    den = sum(w * (ti - t_bar) ** 2 for w, ti in zip(weights, t))
    beta = num / den

    angle = math.degrees(math.atan(beta))
    return round(angle, 1)


def calc_price_average(stock: List) -> dict:
    res = {}
    stock.reverse()
    ma3_price_list = [s.ma_three for s in stock[-5:]]
    print(ma3_price_list)
    ma5_price_list = [s.ma_five for s in stock[-20:]]
    ma10_price_list = [s.ma_ten for s in stock[-20:]]
    ma20_price_list = [s.ma_twenty for s in stock[-20:]]

    res.update({"ma3_angle_l3d": linear_least_squares(ma3_price_list[-3:])})
    res.update({"ma3_angle_l5d": linear_least_squares(ma3_price_list[-5:])})

    res.update({"ma5_angle_l3d": linear_least_squares(ma5_price_list[-3:])})
    res.update({"ma5_angle_l5d": linear_least_squares(ma5_price_list[-5:])})
    res.update({"ma5_angle_l10d": linear_least_squares(ma5_price_list[-10:])})
    res.update({"ma5_angle_l20d": linear_least_squares(ma5_price_list[-20:])})

    res.update({"ma10_angle_l5d": linear_least_squares(ma10_price_list[-5:])})
    res.update({"ma10_angle_l10d": linear_least_squares(ma10_price_list[-10:])})
    res.update({"ma10_angle_l20d": linear_least_squares(ma10_price_list[-20:])})

    res.update({"ma20_angle_l5d": linear_least_squares(ma20_price_list[-5:])})
    res.update({"ma20_angle_l10d": linear_least_squares(ma20_price_list[-10:])})
    res.update({"ma20_angle_l20d": linear_least_squares(ma20_price_list[-20:])})

    return res
