#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from typing import Optional
from pydantic import BaseModel


class SearchStockParam(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    region: Optional[str] = None
    industry: Optional[str] = None
    concept: Optional[str] = None
    filter: Optional[str] = None
    day: Optional[str] = None
    userId: Optional[int] = None
    pageSize: int = 20
    page: int = 1
    sortField: str = 'qrr'


class SetStockParam(BaseModel):
    code: str
    operate_type: str
    buy_time: Optional[str] = None
    buy_price: Optional[str] = None
    sell_empty: Optional[str] = None
    tag: Optional[str] = None


class StockModelDo(BaseModel):
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
    fund: float = None
    ma_five: float = None
    ma_ten: float = None
    ma_twenty: float = None
    qrr: float = None
    shares: Optional[float] = None
    premium: Optional[float] = None

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
    fund: Optional[float] = None
    ma_five: float = None
    ma_ten: float = None
    ma_twenty: float = None
    qrr: float = None
    diff: float = None
    dea: float = None
    k: float = None
    d: float = None
    j: float = None
    shares: Optional[float] = None
    premium: Optional[float] = None
    boll_up: float = None
    boll_low: float = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        return cls(code=obj.code, name=obj.name, day=obj.day, current_price=obj.current_price, last_price=obj.last_price, turnover_rate=obj.turnover_rate,
                   open_price=obj.open_price, max_price=obj.max_price, min_price=obj.min_price, volume=obj.volume, fund=obj.fund,
                   ma_five=obj.ma_five, ma_ten=obj.ma_ten, ma_twenty=obj.ma_twenty, qrr=obj.qrr, diff=round(obj.emas - obj.emal, 3),
                   dea=round(obj.dea, 3), k=round(obj.kdjk, 3), d=round(obj.kdjd, 3), j=round(obj.kdjj, 3), boll_up=obj.boll_up, boll_low=obj.boll_low,
                   shares=round(obj.shares, 2) if obj.shares is not None else 0, premium=obj.premium)


class StockInfoList(BaseModel):
    code: str
    name: str
    running: int
    filter: str = None
    region: str = None
    industry: str = None
    concept: str = None
    create_time: str
    update_time: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d %H:%M:%S")
        m = obj.update_time.strftime("%Y-%m-%d %H:%M:%S")
        filter = obj.filter if obj.filter is not None else ""
        return cls(code=obj.code, name=obj.name, running=obj.running, region=obj.region, industry=obj.industry, concept=obj.concept,
                   create_time=c, update_time=m, filter=filter)


class StockMinuteDo(BaseModel):
    code: str = None
    time: str = None
    price: float = None
    price_avg: float = None
    volume: int = None

    class Config:
        from_attributes = True


class ToolsInfoList(BaseModel):
    key: str
    value: str
    update_time: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        return cls(key=obj.key, value=obj.value, update_time=obj.update_time.strftime("%Y-%m-%d %H:%M:%S"))


class updateFundDo(BaseModel):
    code: str
    cookie: str


class SetStockHold(BaseModel):
    code: str
    status: int
    time: str
    price: float
    number: int
    userId: int


class TradeStockList(BaseModel):
    id: int = None
    code: str = None
    name: str = None
    price: float = None
    shares: int = None
    status: str = None
    fee: float = None
    flag: int = None
    user_id: int = None
    content: Optional[str] = None
    create_time: str = None
    update_time: str = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d")
        u = obj.update_time.strftime("%Y-%m-%d")
        return cls(id=obj.id, code=obj.code, name=obj.name, price=round(obj.price, 3), shares=obj.shares, status=obj.status.name,
                   fee=obj.fee, user_id=obj.user_id, create_time=c, update_time=u, flag=obj.flag, content=obj.content)


class TradeRecordList(BaseModel):
    price: float = None
    shares: int = None
    operation: str = None
    operate_time: str = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d")
        operation = "buy" if obj.status.name == "RECD" else "sell"
        return cls(price=round(obj.price, 3), shares=obj.shares, operation=operation, operate_time=c)


class AnalysisResultList(BaseModel):
    id: int = None
    code: str = None
    day: str = None
    content: Optional[str] = None
    create_time: str = None

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d")
        return cls(id=obj.id, code=obj.code, day=obj.day, create_time=c, content=obj.content)


class EtfInfoList(BaseModel):
    code: str
    name: str
    running: int
    capital: float = None
    fee: float = None
    industry: str = None
    stocks: Optional[list[dict]] = None
    create_time: str
    update_time: str

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_format(cls, obj):
        c = obj.create_time.strftime("%Y-%m-%d")
        m = obj.update_time.strftime("%Y-%m-%d %H:%M:%S")
        return cls(code=obj.code, name=obj.name, running=obj.running, capital=obj.capital, industry=obj.industry, fee=obj.fee,
                   create_time=c, update_time=m, stocks=obj.stocks)
