#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
import traceback
from typing import List
from collections import defaultdict
from datetime import datetime
import requests
from sqlalchemy import desc, asc
from utils.model import SearchStockParam, StockModelDo, RequestData
from utils.logging import logger
from utils.results import Result
from utils.database import Stock, Detail, Volumn, Tools


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def getStockRegion(code: str) -> str:
    if code.startswith("60") or code.startswith("68"):
        return "sh"
    elif code.startswith("00") or code.startswith("30"):
        return "sz"
    else:
        return ""


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


def generateStockCode(data: dict) -> str:
    s = []
    for r in list(data.keys()):
        s.append(f"{getStockRegion(r)}{r}")
    return ",".join(s)


async def queryByCode(code: str) -> Result:
    result = Result()
    try:
        stockInfo = Detail.query(code=code).order_by(asc(Detail.create_time)).all()
        data = [[getattr(row, k) for k in ['open_price', 'current_price', 'min_price', 'max_price', 'volumn', 'qrr']] for row in stockInfo]
        result.data = {
            'x': [getattr(row, 'day') for row in stockInfo],
            'price': data,
            'volumn': [[index, d[-2], 1 if d[0] > d[1] else -1] for index, d in enumerate(data)],
            'qrr': [[index, d[-1], 1 if d[0] > d[1] else -1] for index, d in enumerate(data)],
            'ma_three': [getattr(row, 'ma_three') for row in stockInfo],
            'ma_five': [getattr(row, 'ma_five') for row in stockInfo],
            'ma_ten': [getattr(row, 'ma_ten') for row in stockInfo],
            'ma_twenty': [getattr(row, 'ma_twenty') for row in stockInfo]
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
            sort_key = query.sortField.split('_')[0]
            sort_type = query.sortField.split('_')[1]
            if sort_type == 'desc':
                detail_sort = desc(getattr(Detail, sort_key))
            else:
                detail_sort = asc(getattr(Detail, sort_key))
            offset = (query.page - 1) * query.pageSize
            total_num = Detail.query(day=day).count()
            stockInfo = Detail.query(day=day).order_by(detail_sort).offset(offset).limit(query.pageSize).all()
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


async def query_tencent(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items()}
        stockCode = generateStockCode(dataDict)
        res = requests.get(f"https://qt.gtimg.cn/q={stockCode}", headers=headers)
        if res.status_code == 200:
            res_list = res.text.split(';')
            for s in res_list:
                try:
                    stockDo = StockModelDo()
                    if len(s) < 30:
                        continue
                    stockInfo = s.split('~')
                    stockDo.name = stockInfo[1]
                    stockDo.code = stockInfo[2]
                    stockDo.current_price = float(stockInfo[3])
                    stockDo.last_price = float(stockInfo[4])
                    stockDo.open_price = float(stockInfo[5])
                    if int(stockInfo[6]) < 2:
                        logger.info(f"Tencent - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volumn = int(int(stockInfo[6]))
                    stockDo.max_price = float(stockInfo[33])
                    stockDo.min_price = float(stockInfo[34])
                    stockDo.day = stockInfo[30][:8]
                    r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                    logger.info(f"Tencent: {stockDo}")
                except:
                    logger.error(f"Tencent - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    error_list.append({stockDo.code: stockDo.name})
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("Tencent - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def query_xueqiu(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items()}
        stockCode = generateStockCode(dataDict)
        res = requests.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text)
            for s in res_json['data']:
                try:
                    stockDo = StockModelDo()
                    code = s['symbol'][2:]
                    stockDo.name = dataDict[code]
                    stockDo.code = code
                    stockDo.current_price = s['current']
                    stockDo.open_price = s['open']
                    stockDo.last_price = s['last_close']
                    stockDo.max_price = s['high']
                    stockDo.min_price = s['low']
                    if not s['volume'] or s['volume'] < 2:
                        logger.info(f"XueQiu - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volumn = int(s['volume'] / 100)
                    stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                    r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                    logger.info(f"XueQiu: {stockDo}")
                except:
                    logger.error(f"XueQiu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    error_list.append({stockDo.code: stockDo.name})
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("XueQiu - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def query_sina(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items()}
        stockCode = generateStockCode(dataDict)
        h = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        res = requests.get(f"http://hq.sinajs.cn/list={stockCode}", headers=h)
        if res.status_code == 200:
            res_list = res.text.split(';')
            for s in res_list:
                try:
                    stockDo = StockModelDo()
                    if len(s) < 30:
                        continue
                    stockInfo = s.split(',')
                    stockDo.name = stockInfo[0].split('"')[-1]
                    stockDo.code = stockInfo[0].split('=')[0].split('_')[-1][2:]
                    stockDo.current_price = float(stockInfo[3])
                    stockDo.open_price = float(stockInfo[1])
                    if int(stockInfo[8]) < 2:
                        logger.info(f"Sina - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volumn = int(int(stockInfo[8]) / 100)
                    stockDo.last_price = float(stockInfo[2])
                    stockDo.max_price = float(stockInfo[4])
                    stockDo.min_price = float(stockInfo[5])
                    stockDo.day = stockInfo[30].replace('-', '')
                    r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                    logger.info(f"Sina: {stockDo}")
                except:
                    logger.error(f"Sina - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    error_list.append({stockDo.code: stockDo.name})
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("Sina - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def test() -> Result:
    result = Result()
    stock_volumn_obj = Detail.query_fields(columns=['volumn'], code='688045').order_by(desc(Detail.day)).all()
    stock_volumn = [r[0] for r in stock_volumn_obj]
    result.data = stock_volumn
    return result
