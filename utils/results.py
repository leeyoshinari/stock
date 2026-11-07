#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from datetime import datetime, timedelta
from pydantic import BaseModel
from typing import Any


class Result(BaseModel):
    success: bool = True
    msg: str = 'Success!'
    data: Any = None
    total: int = 0


def getStockRegion(code: str) -> str:
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return "sh"
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return "sz"
    else:
        return ""


def getStockRegionNum(code: str) -> str:
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return "1"
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return "0"
    else:
        return ""


def getMarketCode(code: str) -> int:
    """同花顺-股票所属市场判断"""
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return 17
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return 33
    else:
        return 0


def get_past_date(days_diff: int = 373, date_format: str = "%Y%m%d") -> str:
    """根据当前日期和相差天数，计算之前的日期\n
    :param days_diff: 相差天数, 默认373, 373天大概是一年多的数据, 大概共250个交易日
    :param date_format: 默认"%Y%m%d"
    :return: 之前的日期字符串
    """
    current_date = datetime.now()
    past_date = current_date - timedelta(days=days_diff)
    return past_date.strftime(date_format)
