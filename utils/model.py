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
    last_price: float = None
    open_price: float = None
    max_price: float = None
    min_price: float = None
    volumn: int = None
    ma_five: float = None
    ma_ten: float = None
    ma_twenty: float = None
    qrr: float = None

    class Config:
        from_attributes = True


class StockDataList(BaseModel):
    code: str = None
    name: str = None
    day: str = None
    current_price: float = None
    last_price: float = None
    open_price: float = None
    max_price: float = None
    min_price: float = None
    volume: int = None
    ma_five: float = None
    ma_ten: float = None
    ma_twenty: float = None
    qrr: float = None
    diff: float = None
    dea: float = None
    k: float = None
    d: float = None
    j: float = None
    trix: float = None
    trma: float = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        return cls(code=obj.code, name=obj.name, day=obj.day, current_price=obj.current_price, last_price=obj.last_price,
                   open_price=obj.open_price, max_price=obj.max_price, min_price=obj.min_price, volume=obj.volumn,
                   ma_five=obj.ma_five, ma_ten=obj.ma_ten, ma_twenty=obj.ma_twenty, qrr=obj.qrr, diff=obj.emas - obj.emal,
                   dea=obj.dea, k=obj.kdjk, d=obj.kdjd, j=obj.kdjj, trix=obj.trix, trma=obj.trma)


class RequestData(BaseModel):
    data: List
