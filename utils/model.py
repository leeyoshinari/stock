#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from typing import Optional, List
from pydantic import BaseModel


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
    ma_three: float = None
    ma_five: float = None
    ma_ten: float = None
    ma_twenty: float = None
    qrr: float = None

    class Config:
        from_attributes = True


class RequestData(BaseModel):
    data: List
