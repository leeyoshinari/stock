#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import json
import time
import math
import queue
import traceback
import requests
from typing import List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, wait
from sqlalchemy.exc import NoResultFound
from sqlalchemy import desc, asc
from settings import BATCH_SIZE, THREAD_POOL_SIZE, BATCH_INTERVAL
from utils.model import StockModelDo
from utils.scheduler import scheduler
from utils.database import Stock, Detail, Volumn, Recommend, Tools
from utils.logging import logger


queryTask = queue.Queue()   # FIFO queue
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


def getStockType(code: str) -> int:
    if code.startswith("60"):
        return 1
    elif code.startswith("00"):
        return 1
    elif code.startswith("68"):
        return 0
    elif code.startswith("30"):
        return 1
    else:
        return 0


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


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[:window]) / window, 2)


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


def getStockFromTencent(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
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
                        if int(stockInfo[6]) < 2:
                            logger.info(f"Tencent - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[6]) / 100)
                        stockDo.max_price = float(stockInfo[33])
                        stockDo.min_price = float(stockInfo[34])
                        stockDo.day = stockInfo[30][:8]
                        saveStockInfo(stockDo)
                        logger.info(f"Tencent: {stockDo}")
                    except:
                        logger.error(f"Tencent - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
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
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def getStockFromXueQiu(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
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
                        if not s['volume'] or s['volume'] < 2:
                            logger.info(f"XueQiu - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(s['volume'] / 100)
                        stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                        saveStockInfo(stockDo)
                        logger.info(f"XueQiu: {stockDo}")
                    except:
                        logger.error(f"XueQiu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
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
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def getStockFromSina(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
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
                        if int(stockInfo[8]) < 2:
                            logger.info(f"Sina - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[8]) / 100)
                        stockDo.max_price = float(stockInfo[4])
                        stockDo.min_price = float(stockInfo[5])
                        stockDo.day = stockInfo[30].replace('-', '')
                        saveStockInfo(stockDo)
                        logger.info(f"Sina: {stockDo}")
                    except:
                        logger.error(f"Sina - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
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
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def queryStockTencentFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            res = requests.post(f"{host}/stock/query/tencent", json={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        queryTask.put(res_json['data']['error'])
                    if res_json['data']['data']:
                        stock_list = res_json['data']['data']
                        for stockInfo in stock_list:
                            stockDo = StockModelDo()
                            stockDo.name = stockInfo['name']
                            stockDo.code = stockInfo['code']
                            stockDo.current_price = stockInfo['current_price']
                            stockDo.open_price = stockInfo['open_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"Tencent - Http: {stockDo}")
                else:
                    logger.error(f"Tencent - Http 请求未正常返回, {res.text}...")
                    queryTask.put(datas)
            else:
                logger.error(f"Tencent - Http 请求未正常返回 - {res.status_code}")
                queryTask.put(datas)
        except:
            logger.error("Tencent - Http 出现异常......")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def queryStockXueQiuFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            res = requests.post(f"{host}/stock/query/xueqiu", json={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        queryTask.put(res_json['data']['error'])
                    if res_json['data']['data']:
                        stock_list = res_json['data']['data']
                        for stockInfo in stock_list:
                            stockDo = StockModelDo()
                            stockDo.name = stockInfo['name']
                            stockDo.code = stockInfo['code']
                            stockDo.current_price = stockInfo['current_price']
                            stockDo.open_price = stockInfo['open_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"XueQiu - Http: {stockDo}")
                else:
                    logger.error(f"XueQiu - Http 请求未正常返回, {res.text}...")
                    queryTask.put(datas)
            else:
                logger.error(f"XueQiu - Http 请求未正常返回 - {res.status_code}")
                queryTask.put(datas)
        except:
            logger.error("XueQiu - Http 出现异常......")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def queryStockSinaFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            res = requests.post(f"{host}/stock/query/sina", json={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        queryTask.put(res_json['data']['error'])
                    if res_json['data']['data']:
                        stock_list = res_json['data']['data']
                        for stockInfo in stock_list:
                            stockDo = StockModelDo()
                            stockDo.name = stockInfo['name']
                            stockDo.code = stockInfo['code']
                            stockDo.current_price = stockInfo['current_price']
                            stockDo.open_price = stockInfo['open_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"Sina - Http: {stockDo}")
                else:
                    logger.error(f"Sina - Http 请求未正常返回, {res.text}...")
                    queryTask.put(datas)
            else:
                logger.error(f"Sina - Http 请求未正常返回 - {res.status_code}")
                queryTask.put(datas)
        except:
            logger.error("Sina - Http 出现异常......")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
        finally:
            if datas: queryTask.task_done()


def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = Detail.query_fields(columns=['current_price'], code=stockDo.code).order_by(desc(Detail.day)).limit(21).all()
    stock_price = [r[0] for r in stock_price_obj]
    now = datetime.now().time()
    stop_time = datetime.strptime("15:00:00", "%H:%M:%S").time()
    if now < stop_time:
        current_date = normalizeHourAndMinute()
    else:
        current_date = "2021"
    volume_obj = Volumn.query_fields(columns=['volumn'], code=stockDo.code, date=current_date).order_by(desc(Volumn.create_time)).limit(3).all()
    stock_volume = [r[0] for r in volume_obj]
    average_volumn = sum(stock_volume) / 3
    average_volumn = average_volumn if average_volumn > 0 else 1
    try:
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        stock_price[0] = stockDo.current_price
        Detail.update(stockObj, current_price=stockDo.current_price, open_price=stockDo.open_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn,
                      ma_three=calc_MA(stock_price, 3), ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10),
                      ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2))
    except NoResultFound:
        stock_price.insert(0, stockDo.current_price)
        Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_three=calc_MA(stock_price, 3),
                      ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2))
    Volumn.create(code=stockDo.code, date=current_date, volumn=stockDo.volumn)


def setAllStock():
    today = datetime.today()
    if today.weekday() < 5:
        try:
            res = requests.get("https://api.mairui.club/hslt/list/b997d4403688d5e66a", headers=headers, timeout=30)
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
                        is_running = getStockType(code)
                        if 'ST' in name.upper():
                            is_running = 0
                        Stock.create(code=code, name=name, running=is_running)
                        logger.info(f"股票 {name} - {code} 添加成功, 状态是 {is_running} ...")
                    except:
                        logger.error(traceback.format_exc())
            else:
                logger.error('数据更新异常')
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


def setAvailableStock():
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
            total_cnt = Stock.query(running=1).count()
            total_batch = int((total_cnt + BATCH_SIZE - 1) / BATCH_SIZE)
            one_batch_size = int(BATCH_SIZE / THREAD_POOL_SIZE)
            page = 0
            while page < total_batch:
                offset = page * BATCH_SIZE
                stockList = []
                stockInfo = Stock.query(running=1).order_by(asc(Stock.create_time)).offset(offset).limit(BATCH_SIZE).all()
                for s in stockInfo:
                    stockList.append({s.code: s.name})
                for i in range(0, len(stockList), one_batch_size):
                    d = stockList[i: i + one_batch_size]
                    queryTask.put(d)
                page += 1
                logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次, 数量 {len(stockList)}...")
                time.sleep(BATCH_INTERVAL)
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
            res = requests.get("https://qt.gtimg.cn/q=sh600519,sz000001", headers=headers)
            if res.status_code == 200:
                if current_day in res.text:
                    res_list = res.text.split(';')
                    v1 = res_list[0].split('~')[6]
                    v2 = res_list[1].split('~')[6]
                    if int(v1) > 2 or int(v2) > 2:
                        is_trade_day = True
                        job = scheduler.add_job(setAvailableStock, "interval", minutes=20, next_run_time=datetime.now() + timedelta(minutes=3))
                        running_job_id = job.id
                        try:
                            tool = Tools.get_one("openDoor")
                            Tools.update(tool, value=current_day)
                        except NoResultFound:
                            Tools.create(key="openDoor", value=current_day)
                        logger.info(f"查询任务已启动, 任务id: {running_job_id}")
                        break
                    else:
                        is_trade_day = False
                        logger.info("未开市, 跳过1...")
                        break
                else:
                    is_trade_day = False
                    logger.info("未开市, 跳过...")
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


# async def calcRecommendStock():
#     try:
#         stocks = Stock.query(running=1).all()
#         for stock in stocks:
#             stockInfo = Detail.query(code=stock.code).order_by(asc(Detail.create_time)).all()
#     except:
#         logger.error(traceback.format_exc())

is_trade_day = True
if __name__ == '__main__':
    http1_host = "https://usc.ihuster.top"
    scheduler.add_job(checkTradeDay, 'cron', hour=9, minute=31, second=20)  # 启动任务
    scheduler.add_job(stopTask, 'cron', hour=15, minute=0, second=20)   # 停止任务
    scheduler.add_job(setAvailableStock, 'cron', hour=18, minute=0, second=20)  # 必须在 16点后启动
    scheduler.add_job(setAllStock, 'cron', hour=7, minute=54, second=20)    # 更新股票信息
    scheduler.start()
    time.sleep(2)
    PID = os.getpid()
    with open('pid', 'w', encoding='utf-8') as f:
        f.write(str(PID))
    funcList = [getStockFromTencent, getStockFromXueQiu, getStockFromSina, queryStockTencentFromHttp, queryStockXueQiuFromHttp, queryStockSinaFromHttp]
    paramList = ['', '', '', http1_host, http1_host, http1_host]
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        futures = [executor.submit(func, param) for func, param in zip(funcList, paramList)]
        wait(futures)
