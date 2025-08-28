#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
from typing import List
from utils.logging import logger
from utils.results import Result


def linear_least_squares(y: List) -> float:
    x = list(range(len(y)))
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)
    numerator = n * sum_xy - sum_x * sum_y
    denominator = n * sum_x2 - sum_x ** 2
    k = numerator / denominator
    angle_deg = math.degrees(math.atan(k))
    return round(angle_deg, 1)


def calc_price_average(stock) -> dict:
    res = {}
    ma3_price_list = [s.ma_three for s in stock[:5]]
    ma5_price_list = [s.ma_five for s in stock[:20]]
    ma10_price_list = [s.ma_ten for s in stock[:20]]
    ma20_price_list = [s.ma_twenty for s in stock[:20]]

    res.update({"ma3_angle_l3d": linear_least_squares(ma3_price_list[:3])})
    res.update({"ma3_angle_l5d": linear_least_squares(ma3_price_list[:5])})

    res.update({"ma5_angle_l3d": linear_least_squares(ma5_price_list[:3])})
    res.update({"ma5_angle_l5d": linear_least_squares(ma5_price_list[:5])})
    res.update({"ma5_angle_l10d": linear_least_squares(ma5_price_list[:10])})
    res.update({"ma5_angle_l20d": linear_least_squares(ma5_price_list[:20])})

    res.update({"ma10_angle_l5d": linear_least_squares(ma10_price_list[:5])})
    res.update({"ma10_angle_l10d": linear_least_squares(ma10_price_list[:10])})
    res.update({"ma10_angle_l20d": linear_least_squares(ma10_price_list[:20])})

    res.update({"ma20_angle_l5d": linear_least_squares(ma20_price_list[:5])})
    res.update({"ma20_angle_l10d": linear_least_squares(ma20_price_list[:10])})
    res.update({"ma20_angle_l20d": linear_least_squares(ma20_price_list[:20])})

    return res
