#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import json
import time
import queue
import traceback
import requests
from typing import List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, wait
from sqlalchemy import desc, asc
from utils.database import Database
from utils.model import StockModelDo
from utils.scheduler import scheduler
from utils.database import Stock, Detail
from utils.logging import logger


MAX_PRICE = 500
BATCH_SIZE = 5
Database.init_db()
queryTask = queue.Queue()
executor = ThreadPoolExecutor(1)
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[-window:]) / window, 2)


def getStockFromSohu():
    start_time = datetime.now() - timedelta(days=60)
    start_date = start_time.strftime("%Y%m%d")
    current_day = time.strftime("%Y%m%d")
    while True:
        datas = queryTask.get()
        try:
            if datas == 'end': break
            dataDict = {k: v for d in datas for k, v in d.items()}
            s = []
            for r in list(dataDict.keys()):
                s.append(f"cn_{r}")
            if (len(s) == 0): continue
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
                        history_list_sorted = sorted(history_list, key=lambda x: x[0])
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


def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = Detail.query_fields(columns=['current_price'], code=stockDo.code).order_by(asc(Detail.day)).all()
    stock_price = [r[0] for r in stock_price_obj]
    stock_price.append(stockDo.current_price)
    Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                  max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_three=calc_MA(stock_price, 3),
                  ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20))
    if len(stock_price) > 4:
        stock_volumn_obj = Detail.query_fields(columns=['volumn'], code=stockDo.code).order_by(asc(Detail.day)).all()
        stock_volumn = [r[0] for r in stock_volumn_obj]
        average_volumn = sum(stock_volumn[-5: -2]) / 3
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        Detail.update(stockObj, qrr=round(stockDo.volumn / average_volumn, 2))
        if stockDo.current_price > MAX_PRICE or stockDo.current_price < 1:
            try:
                stockBase = Stock.get_one(stockDo.code)
                Stock.update(stockBase, running=0)
                logger.info(f"股票 {stockBase.name} - {stockBase.code} 当前价格为 {stockDo.current_price}, 忽略掉...")
            except:
                logger.error(traceback.format_exc())


def setAvailableStock():
    try:
        total_cnt = Stock.query(running=1).count()
        total_batch = int((total_cnt + BATCH_SIZE - 1) / BATCH_SIZE)
        page = 0
        while page < total_batch:
            offset = page * BATCH_SIZE
            stockList = []
            stockInfo = Stock.query(running=1).order_by(asc(Stock.create_time)).offset(offset).limit(BATCH_SIZE).all()
            for s in stockInfo:
                stockList.append({s.code: s.name})
            if (stockList):
                queryTask.put(stockList)
            page += 1
            logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次...")
            time.sleep(15)
        queryTask.put("end")
    except:
        logger.error(traceback.format_exc())


def fixStockQrr():
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            stocks = Detail.query(code=s.code).order_by(asc(Detail.day)).all()
            volumn = [stocks[0].volumn, stocks[1].volumn, stocks[2].volumn]
            for i in range(3, len(stocks)):
                avg_v = sum(volumn) / 3
                Detail.update(stocks[i], qrr=round(stocks[i].volumn / avg_v, 2))
                volumn.append(stocks[i].volumn)
                volumn.pop(0)

            logger.info(f"正在处理第 {s.code} 个...")
    except:
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    s = executor.submit(getStockFromSohu)
    scheduler.add_job(setAvailableStock, 'cron', hour=11, minute=5, second=20)
    time.sleep(2)
    scheduler.start()
    PID = os.getpid()
    with open('pid', 'w', encoding='utf-8') as f:
        f.write(str(PID))
    wait([s])
