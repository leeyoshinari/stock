#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import time
import math
import queue
import random
import traceback
import requests
from typing import List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.exc import NoResultFound
from sqlalchemy import desc, asc
from settings import BATCH_SIZE, MAX_PRICE, THREAD_POOL_SIZE, BATCH_INTERVAL
from utils.model import StockModelDo
from utils.scheduler import scheduler
from utils.database import Stock, Detail, Volumn, Recommend
from utils.logging import logger


queryTask = queue.Queue()   # FIFO queue
executor = ThreadPoolExecutor(THREAD_POOL_SIZE)
running_job_id = None
is_trade_day = False
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


def getStockType(code: str) -> str:
    if code.startswith("60"):
        return "沪市主板"
    elif code.startswith("00"):
        return "深市主板"
    elif code.startswith("68"):
        return "科创板"
    elif code.startswith("30"):
        return "创业板"
    elif code.startswith("8"):
        return "北交所"
    else:
        return ""


def normalizeHourAndMinute() -> str:
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


def linear_least_squares(x: List, y: List) -> float:
    n = len(x)
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    sum_x2 = sum(xi ** 2 for xi in x)
    numerator = n * sum_xy - sum_x * sum_y
    denominator = n * sum_x2 - sum_x ** 2
    k = numerator / denominator
    angle_deg = math.degrees(math.atan(k))
    return angle_deg


def getStockFromTencent():
    while True:
        try:
            datas = queryTask.get()
            logger.info(datas)
            if datas == 'end': break
            error_list = []
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
                        stockDo.open_price = float(stockInfo[5])
                        stockDo.volumn = int(stockInfo[6])
                        stockDo.max_price = float(stockInfo[33])
                        stockDo.min_price = float(stockInfo[34])
                        stockDo.day = stockInfo[30][:8]
                        logger.info(f"Tencent: {stockDo}")
                        try:
                            stockInfo = Detail.get_one((stockDo.code, stockDo.day))
                            Detail.update(stockInfo, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        except NoResultFound:
                            Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        now = datetime.now().time()
                        stop_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
                        if now < stop_time:
                            date = normalizeHourAndMinute()
                            Volumn.create(code=stockDo.code, date=date, volumn=stockDo.volumn)
                        set_time = datetime.strptime("16:00:00", "%H:%M:%S").time()
                        if now > set_time:
                            Volumn.create(code=stockDo.code, date="2021", volumn=stockDo.volumn)
                            if stockDo.current_price > MAX_PRICE:
                                try:
                                    stockBase = Stock.get_one(stockDo.code)
                                    Stock.update(stockBase, running=0)
                                    logger.info(f"股票 {stockBase.name} - {stockBase.code} 当前价格 {stockDo.current_price} 大于 {MAX_PRICE}, 忽略掉...")
                                except:
                                    logger.error(traceback.format_exc())
                    except:
                        logger.error(f"Tencent - 数据解析保存失败, {stockDo.code} - {stockDo.name}")
                        logger.error(traceback.format_exc())
                        error_list.append({stockDo.code: stockDo.name})
                if len(error_list) > 0:
                    queryTask.put(error_list)
            else:
                logger.error("Tencent - 请求未正常返回...")
                queryTask.put(datas)
            error_list = []
        except:
            logger.error("Tencent - 出现异常......")
            logger.error(traceback.format_exc())
            queryTask.put(datas)
        finally:
            queryTask.task_done()
        time.sleep(BATCH_INTERVAL)


def getStockFromXueQiu():
    while True:
        try:
            datas = queryTask.get()
            logger.info(datas)
            if datas == 'end': break
            error_list = []
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
                        stockDo.max_price = s['high']
                        stockDo.min_price = s['low']
                        stockDo.volumn = int(s['volume'] / 100)
                        stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                        logger.info(f"XueQiu: {stockDo}")
                        try:
                            stockInfo = Detail.get_one((stockDo.code, stockDo.day))
                            Detail.update(stockInfo, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        except NoResultFound:
                            Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        now = datetime.now().time()
                        stop_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
                        if now < stop_time:
                            date = normalizeHourAndMinute()
                            Volumn.create(code=stockDo.code, date=date, volumn=stockDo.volumn)
                        set_time = datetime.strptime("16:00:00", "%H:%M:%S").time()
                        if now > set_time:
                            Volumn.create(code=stockDo.code, date="2021", volumn=stockDo.volumn)
                            if stockDo.current_price > MAX_PRICE:
                                try:
                                    stockBase = Stock.get_one(stockDo.code)
                                    Stock.update(stockBase, running=0)
                                    logger.info(f"股票 {stockBase.name} - {stockBase.code} 当前价格 {stockDo.current_price} 大于 {MAX_PRICE}, 忽略掉...")
                                except:
                                    logger.error(traceback.format_exc())
                    except:
                        logger.error(f"XueQiu - 数据解析保存失败, {stockDo.code} - {stockDo.name}")
                        logger.error(traceback.format_exc())
                        error_list.append({stockDo.code: stockDo.name})
                if len(error_list) > 0:
                    queryTask.put(error_list)
            else:
                logger.error("XueQiu - 请求未正常返回...")
                queryTask.put(datas)
            error_list = []
        except:
            logger.error("XueQiu - 出现异常......")
            logger.error(traceback.format_exc())
            queryTask.put(datas)
        finally:
            queryTask.task_done()
        time.sleep(BATCH_INTERVAL)


def getStockFromSina():
    while True:
        try:
            datas = queryTask.get()
            logger.info(datas)
            if datas == 'end': break
            error_list = []
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
                        stockDo.volumn = int(int(stockInfo[8]) / 100)
                        stockDo.max_price = float(stockInfo[4])
                        stockDo.min_price = float(stockInfo[5])
                        stockDo.day = stockInfo[30].replace('-', '')
                        logger.info(f"Sina: {stockDo}")
                        try:
                            stockInfo = Detail.get_one((stockDo.code, stockDo.day))
                            Detail.update(stockInfo, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        except NoResultFound:
                            Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                                          max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn)
                        now = datetime.now().time()
                        stop_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
                        if now < stop_time:
                            date = normalizeHourAndMinute()
                            Volumn.create(code=stockDo.code, date=date, volumn=stockDo.volumn)
                        set_time = datetime.strptime("16:00:00", "%H:%M:%S").time()
                        if now > set_time:
                            Volumn.create(code=stockDo.code, date="2021", volumn=stockDo.volumn)
                            if stockDo.current_price > MAX_PRICE:
                                try:
                                    stockBase = Stock.get_one(stockDo.code)
                                    Stock.update(stockBase, running=0)
                                    logger.info(f"股票 {stockBase.name} - {stockBase.code} 当前价格 {stockDo.current_price} 大于 {MAX_PRICE}, 忽略掉...")
                                except:
                                    logger.error(traceback.format_exc())
                    except:
                        logger.error(f"Sina - 数据解析保存失败, {stockDo.code} - {stockDo.name}")
                        logger.error(traceback.format_exc())
                        error_list.append({stockDo.code: stockDo.name})
                if len(error_list) > 0:
                    queryTask.put(error_list)
            else:
                logger.error("Sina - 请求未正常返回...")
                queryTask.put(datas)
            error_list = []
        except:
            logger.error("Sina - 出现异常......")
            logger.error(traceback.format_exc())
            queryTask.put(datas)
        finally:
            queryTask.task_done()
        time.sleep(BATCH_INTERVAL)


def getStockFromSina():
    while True:
        try:
            res = requests.get(f"https://q.stock.sohu.com/hisHq?code={}&start={}&end={}", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)


async def setAllStock():
    today = datetime.today()
    if today.weekday() < 5:
        try:
            res = requests.get("https://api.mairui.club/hslt/list/b997d4403688d5e66a", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                for r in res_json:
                    code = r['dm'].split('.')[0]
                    name = r['mc']
                    try:
                        s = Stock.get_one(code)
                        if 'ST' in name.upper():
                            Stock.update(s, running=0)
                            logger.info(f"股票 {s.name} - {s.code} 处于退市状态, 忽略掉...")
                        if 'ST' in s.name.upper() and 'ST' not in name.upper():
                            Stock.update(s, running=1)
                            logger.info(f"股票 {s.name} - {s.code} 重新上市, 继续处理...")
                    except NoResultFound:
                        if 'ST' in name.upper():
                            is_running = 0
                        else:
                            is_running = 1
                        Stock.create(code=code, name=name, kind=getStockType(code), running=is_running)
                        logger.info(f"股票 {name} - {code} 添加成功, 状态是 {is_running} ...")
                    except:
                        logger.error(traceback.format_exc())
            else:
                logger.error('数据更新异常')
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


async def setAvailableStock():
    global is_trade_day
    now = datetime.now().time()
    start_time = datetime.strptime("11:30:00", "%H:%M:%S").time()
    end_time = datetime.strptime("13:00:00", "%H:%M:%S").time()
    if start_time <= now <= end_time:
        logger.info("中午休市, 暂不执行...")
    elif not is_trade_day:
        logger.info("不在交易时间...")
    else:
        try:
            stockList = []
            stockInfo = Stock.query(running=1).all()
            for s in stockInfo:
                stockList.append({s.code: s.name})
            random.shuffle(stockList)
            for i in range(0, len(stockList), BATCH_SIZE):
                d = stockList[i: i + BATCH_SIZE]
                queryTask.put(d)
            logger.info("开始实时数据查询......")
            now = datetime.now().time()
            stop_time = datetime.strptime("16:30:00", "%H:%M:%S").time()
            if now > stop_time:
                is_trade_day = False
        except:
            logger.error(traceback.format_exc())


def checkTradeDay():
    global running_job_id
    global is_trade_day
    while True:
        today = datetime.today()
        if today.weekday() >= 5:
            logger.info("周末未开市，跳过...")
            break
        try:
            current_day = time.strftime("%Y%m%d")
            res = requests.get("https://qt.gtimg.cn/q=sh600519", headers=headers)
            if res.status_code == 200:
                if current_day in res.text:
                    is_trade_day = True
                    job = scheduler.add_job(setAvailableStock, "interval", minutes=20, next_run_time=datetime.now() + timedelta(minutes=3))
                    running_job_id = job.id
                    logger.info(f"查询任务已启动, 任务id: {running_job_id}")
                    break
                else:
                    is_trade_day = False
                    logger.info("未开市，跳过...")
                    break
            else:
                logger.error(f"获取 SH600519 数据异常，状态码: {res.status_code}")
        except:
            logger.error(traceback.format_exc())
        time.sleep(3)


def stopTask():
    global running_job_id
    global is_trade_day
    if is_trade_day and running_job_id and scheduler.get_job(running_job_id):
        scheduler.remove_job(running_job_id)
        running_job_id = None
        logger.info("查询任务已停止...")
    else:
        logger.info("查询任务不存在或已结束...")


async def calcRecommendStock():
    try:
        stocks = Stock.query(running=1).all()
        for stock in stocks:
            stockInfo = Detail.query(code=stock.code).order_by(asc(Detail.create_time)).all()
    except:
        logger.error(traceback.format_exc())


executor.submit(getStockFromTencent)
executor.submit(getStockFromXueQiu)
executor.submit(getStockFromSina)
scheduler.add_job(checkTradeDay, 'cron', hour=9, minute=31, second=20)  # 启动任务
scheduler.add_job(stopTask, 'cron', hour=15, minute=0, second=20)   # 停止任务
scheduler.add_job(setAvailableStock, 'cron', hour=18, minute=0, second=20)  # 必须在 16点后启动
scheduler.add_job(setAllStock, 'cron', hour=22, minute=10, second=20)    # 更新股票信息
