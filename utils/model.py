#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from typing import Optional
from pydantic import BaseModel, Field


class SearchStockParam(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    pageSize: int = 20
    page: int = 1
    sortField: str = 'qrr'


class StockModelDo(BaseModel):
    code: str = None
    name: str = None
    day: str = None
    current_price: float = None
    open_price: float = None
    max_price: float = None
    min_price: float = None
    volumn: int = None
    qrr: float = None


class StockDetailData(BaseModel):   # 日期、开盘、收盘、最低、最高、成交量
    code: str
    day: str
