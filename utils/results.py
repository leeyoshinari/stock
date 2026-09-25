#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

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
