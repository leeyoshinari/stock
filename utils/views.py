#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari
import time
import traceback
from typing import List
from collections import defaultdict
from datetime import datetime
from sqlalchemy import desc, asc
from utils.model import SearchStockParam, StockModelDo
from utils.logging import logger
from utils.results import Result
from utils.database import Stock, Detail, Volumn, Tools


def normalizeHourAndMinute():
    local_time = time.localtime(time.time())
    hour = local_time.tm_hour
    minute = local_time.tm_min
    remainder = minute % 10
    if remainder != 0:
        minute += (10 - remainder)
        if minute >= 60:
            minute -= 60
            hour += 1
    return f"{hour:02d}{minute:02d}"


async def queryByCode(code: str) -> Result:
    result = Result()
    try:
        stockInfo = Detail.query(code=code).order_by(asc(Detail.create_time)).all()
        data = [[getattr(row, k) for k in ['open_price', 'current_price', 'min_price', 'max_price', 'volumn']] for row in stockInfo[20:]]
        result.data = {
            'x': [getattr(row, 'day') for row in stockInfo[20:]],
            'price': data,
            'volumn': [[index, d[-1], 1 if d[0] > d[1] else -1] for index, d in enumerate(data)],
            'ma_three': [getattr(row, 'ma_three') for row in stockInfo[20:]],
            'ma_five': [getattr(row, 'ma_five') for row in stockInfo[20:]],
            'ma_ten': [getattr(row, 'ma_ten') for row in stockInfo[20:]],
            'ma_twenty': [getattr(row, 'ma_twenty') for row in stockInfo[20:]]
        }
        result.total = len(result.data)
        logger.info(f"查询信息成功, 代码: {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def queryStockList(query: SearchStockParam) -> Result:
    result = Result()
    try:
        tool = Tools.get_one("openDoor")
        day = tool.value
        if query.code:
            stockInfo = Detail.get_one((query.code, day))
            stockList = [StockModelDo.model_validate(stockInfo).model_dump()]
        elif query.name:
            stockInfo = Detail.filter_condition(equal_condition={"day": day}, like_condition={"name": query.name}).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
        else:
            logger.info(query)
            offset = (query.page - 1) * query.pageSize
            total_num = Detail.query(day=day).count()
            stockInfo = Detail.query(day=day).order_by(desc(getattr(Detail, query.sortField))).offset(offset).limit(query.pageSize).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
            result.total = total_num
        result.data = stockList
        logger.info(f"查询列表成功, 查询参数: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def queryStockRetailQrr(codeList: List) -> Result:
    result = Result()
    try:
        now = datetime.now().time()
        start_time = datetime.strptime("11:30:00", "%H:%M:%S").time()
        end_time = datetime.strptime("13:00:00", "%H:%M:%S").time()
        if start_time < now < end_time:
            date = "1130"
        else:
            date = normalizeHourAndMinute()
        stockVolumn = Volumn.queryByCodeAndDate(codeList, date).all()
        dataDict = defaultdict(list)
        for s in stockVolumn:
            dataDict[s.code].append(s.volumn)
        result.data = dict(dataDict)
        logger.info(f"查询量比成功, code: {codeList}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def test() -> Result:
    result = Result()
    stock_volumn_obj = Detail.query_fields(columns=['volumn'], code='688045').order_by(desc(Detail.day)).all()
    stock_volumn = [r[0] for r in stock_volumn_obj]
    result.data = stock_volumn
    return result
