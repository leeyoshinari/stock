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
from utils.database import Stock, Detail, Volumn


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


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
        stockInfo = Detail.query(code=code).order_by(Detail.create_time).all()
        result.data = [[getattr(row, k) for k in ['day', 'open_price', 'current_price', 'min_price', 'max_price', 'volumn']] for row in stockInfo]
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
        now = datetime.now().time()
        start_time = datetime.strptime("09:39:00", "%H:%M:%S").time()
        if now < start_time:
            day = time.strftime("%Y%m%d", time.localtime(time.time() - 36000))
        else:
            day = time.strftime("%Y%m%d")
        if query.code:
            stockInfo = Detail.get_one((query.code, day))
            stockList = [StockModelDo.model_validate(stockInfo).model_dump()]
        elif query.name:
            stockInfo = Detail.filter_condition(equal_condition={"day": day}, like_condition={"name", query.name}).all()
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
