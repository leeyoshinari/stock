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
    turnover_rate: float = None
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
    turnover_rate: float = None
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
                   dea=obj.dea, k=obj.kdjk, d=obj.kdjd, j=obj.kdjj, trix=obj.trix, trma=obj.trma, turnover_rate=obj.turnover_rate)


class AiModelStockList(BaseModel):
    code: str = None
    name: str = None
    day: str = None
    current_price: float = None
    last_price: float = None
    open_price: float = None
    max_price: float = None
    min_price: float = None
    volume: int = None
    turnover_rate: float = None
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
                   open_price=obj.open_price, max_price=obj.max_price, min_price=obj.min_price, volume=obj.volumn, turnover_rate=obj.turnover_rate,
                   ma_five=obj.ma_five, ma_ten=obj.ma_ten, ma_twenty=obj.ma_twenty, qrr=obj.qrr, diff=round(obj.emas - obj.emal, 4),
                   dea=round(obj.dea, 4), k=round(obj.kdjk, 4), d=round(obj.kdjd, 4), j=round(obj.kdjj, 4), trix=round(obj.trix, 4), trma=round(obj.trma, 4))


class RecommendStockDataList(BaseModel):
    code: str = None
    name: str = None
    source: int = None
    price: float = None
    last_one_price: Optional[float] = None
    last_one_high: Optional[float] = None
    last_one_low: Optional[float] = None
    last_two_price: Optional[float] = None
    last_two_high: Optional[float] = None
    last_two_low: Optional[float] = None
    last_three_price: Optional[float] = None
    last_three_high: Optional[float] = None
    last_three_low: Optional[float] = None
    last_four_price: Optional[float] = None
    last_four_high: Optional[float] = None
    last_four_low: Optional[float] = None
    last_five_price: Optional[float] = None
    last_five_high: Optional[float] = None
    last_five_low: Optional[float] = None
    create_time: str = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d")
        return cls(code=obj.code, name=obj.name, source=obj.source, price=obj.price, last_one_price=obj.last_one_price,
                   last_one_high=obj.last_one_high, last_one_low=obj.last_one_low, last_two_price=obj.last_two_price, last_two_high=obj.last_two_high,
                   last_two_low=obj.last_two_low, last_three_price=obj.last_three_price, last_three_high=obj.last_three_high, last_three_low=obj.last_three_low, last_four_price=obj.last_four_price,
                   last_four_high=obj.last_four_high, last_four_low=obj.last_four_low, last_five_price=obj.last_five_price, last_five_high=obj.last_five_high, last_five_low=obj.last_five_low, create_time=c)


class RequestData(BaseModel):
    data: List
