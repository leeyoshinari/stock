#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import time
import queue
import random
import traceback
import requests
from typing import List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import desc, asc
from settings import MAX_PRICE
from utils.model import StockModelDo
from utils.scheduler import scheduler
from utils.database import Stock, Detail
from utils.logging import logger


BATCH_SIZE = 5
queryTask = queue.Queue()
executor = ThreadPoolExecutor(1)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[-window:]) / window, 2)


async def setAllStock():
    try:
        res = requests.get("https://api.mairui.club/hslt/list/b997d4403688d5e66a", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text)
            for r in res_json:
                code = r['dm'].split('.')[0]
                name = r['mc']
                try:
                    Stock.create(code=code, name=name, running=1)
                    logger.info(f"股票 {name} - {code} 添加成功 ...")
                except:
                    logger.error(traceback.format_exc())
        else:
            logger.error('数据初始化异常')
    except:
        logger.error(traceback.format_exc())
        logger.error("数据初始化异常...")


def getStockFromSohu():
    start_time = datetime.now() - timedelta(days=60)
    start_date = start_time.strftime("%Y%m%d")
    current_day = time.strftime("%Y%m%d")
    while True:
        try:
            datas = queryTask.get()
            if datas == 'end': break
            dataDict = {k: v for d in datas for k, v in d.items()}
            s = []
            for r in list(dataDict.keys()):
                s.append(f"cn_{r}")
            s_list = ",".join(s)
            res = requests.get(f"https://q.stock.sohu.com/hisHq?code={s_list}&start={start_date}&end={current_day}", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                for d in res_json:
                    try:
                        stockDo = StockModelDo()
                        if len(d["hq"]) == 0:
                            continue
                        code = d["code"].split("_")[-1]
                        stockDo.name = dataDict[code]
                        stockDo.code = code
                        history_list = d["hq"]
                        history_list_sorted = sorted(history_list, key=lambda x: datetime.strftime(x[0], "%Y-%m-%d"))
                        for r in history_list_sorted:
                            stockDo.day = r[0].replace('-', '')
                            try:
                                _ = Detail.get_one((stockDo.code, stockDo.day))
                                continue
                            except:
                                stockDo.current_price = float(r[2])
                                stockDo.open_price = float(r[1])
                                stockDo.volumn = int(r[7])
                                stockDo.max_price = float(r[6])
                                stockDo.min_price = float(r[5])
                                saveStockInfo(stockDo)
                                logger.info(f"Sohu: {stockDo}")
                    except:
                        logger.error(f"Sohu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {d}")
                        logger.error(traceback.format_exc())
                        queryTask.put([{stockDo.code: stockDo.name}])
            else:
                logger.error("Sohu - 请求未正常返回...")
                queryTask.put(datas)
        except:
            logger.error("Sohu - 出现异常......")
            logger.error(traceback.format_exc())
            queryTask.put(datas)
        finally:
            queryTask.task_done()
        time.sleep(5)


def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = Detail.query_fields(columns=['current_price'], code=stockDo.code).order_by(asc(Detail.day)).all()
    stock_price = [r[0] for r in stock_price_obj]
    stock_price.append(stockDo.current_price)
    Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                  max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_three=calc_MA(stock_price, 3),
                  ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20))
    if len(stock_price) > 4:
        stock_volumn_obj = Detail.query_fields(columns=['volumn'], code=stockDo.code).order_by(desc(Detail.day)).all()
        stock_volumn = [r[0] for r in stock_volumn_obj]
        average_volumn = sum(stock_volumn[-4: -1]) / 3
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        Detail.update(stockObj, qrr=round(stockDo.volumn / average_volumn, 2))
        if stockDo.current_price > MAX_PRICE or stockDo.current_price < 1:
            try:
                stockBase = Stock.get_one(stockDo.code)
                Stock.update(stockBase, running=0)
                logger.info(f"股票 {stockBase.name} - {stockBase.code} 当前价格为 {stockDo.current_price}, 忽略掉...")
            except:
                logger.error(traceback.format_exc())


async def setAvailableStock():
    try:
        stockList = []
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            stockList.append({s.code: s.name})
        random.shuffle(stockList)
        for i in range(0, len(stockList), BATCH_SIZE):
            d = stockList[i: i + BATCH_SIZE]
            queryTask.put(d)
            time.sleep(2)
        queryTask.put("end")
    except:
        logger.error(traceback.format_exc())


executor.submit(getStockFromSohu)
scheduler.add_job(setAllStock, 'cron', hour=22, minute=10, second=20) 
scheduler.add_job(setAvailableStock, 'cron', hour=18, minute=0, second=20)
