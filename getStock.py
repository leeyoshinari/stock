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
from sqlalchemy.exc import NoResultFound
from sqlalchemy import desc, asc
from settings import BATCH_SIZE, THREAD_POOL_SIZE, BATCH_INTERVAL
from utils.model import StockModelDo
from utils.database import Database
from utils.scheduler import scheduler
from utils.database import Stock, Detail, Volumn, Tools
from utils.logging_getstock import logger


Database.init_db()
queryTask = queue.Queue()   # FIFO queue
running_job_id = None
is_trade_day = False
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


alpha_trix = 2.0 / (12 + 1)
alpha_s = 2.0 / (12 + 1)
alpha_l = 2.0 / (26 + 1)
alpha_sig = 2.0 / (9 + 1)


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
                        stockDo.last_price = float(stockInfo[4])
                        stockDo.open_price = float(stockInfo[5])
                        if int(stockInfo[6]) < 2:
                            logger.info(f"Tencent - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[6]))
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
                logger.error(f"Tencent - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"Tencent - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
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
                logger.info(f"XueQiu - {res.text}")
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
                        saveStockInfo(stockDo)
                        logger.info(f"XueQiu: {stockDo}")
                    except:
                        logger.error(f"XueQiu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        error_list.append({stockDo.code: stockDo.name})
                if len(error_list) > 0:
                    queryTask.put(error_list)
            else:
                logger.error(f"XueQiu - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"XueQiu - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
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
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
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
                        saveStockInfo(stockDo)
                        logger.info(f"Sina: {stockDo}")
                    except:
                        logger.error(f"Sina - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        error_list.append({stockDo.code: stockDo.name})
                if len(error_list) > 0:
                    queryTask.put(error_list)
            else:
                logger.error(f"Sina - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"Sina - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
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
                            stockDo.last_price = stockInfo['last_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"Tencent - Http: {stockDo}")
                else:
                    logger.error(f"Tencent - Http 请求未正常返回, {res.text} - {datas}...")
                    queryTask.put(datas)
                    time.sleep(2)
            else:
                logger.error(f"Tencent - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(2)
        except:
            logger.error(f"Tencent - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
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
                            stockDo.last_price = stockInfo['last_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"XueQiu - Http: {stockDo}")
                else:
                    logger.error(f"XueQiu - Http 请求未正常返回, {res.text} - {datas}...")
                    queryTask.put(datas)
                    time.sleep(2)
            else:
                logger.error(f"XueQiu - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(2)
        except:
            logger.error(f"XueQiu - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
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
                            stockDo.last_price = stockInfo['last_price']
                            stockDo.volumn = stockInfo['volumn']
                            stockDo.max_price = stockInfo['max_price']
                            stockDo.min_price = stockInfo['min_price']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"Sina - Http: {stockDo}")
                else:
                    logger.error(f"Sina - Http 请求未正常返回, {res.text} - {datas}...")
                    queryTask.put(datas)
                    time.sleep(2)
            else:
                logger.error(f"Sina - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(2)
        except:
            logger.error(f"Sina - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(2)
        finally:
            if datas: queryTask.task_done()


def calc_macd(price: float, ema_s: float, ema_l: float, dea: float) -> dict:
    ema_s = alpha_s * price + (1 - alpha_s) * ema_s
    ema_l = alpha_l * price + (1 - alpha_l) * ema_l
    diff = ema_s - ema_l
    dea = alpha_sig * diff + (1 - alpha_sig) * dea
    return {'emas': ema_s, 'emal': ema_l, 'diff': diff, 'dea': dea}


def calc_kdj(price: float, high_price: list, low_price: list, kdjk: float, kdjd: float) -> dict:
    high_n = max(high_price[: 9])
    low_n = min(low_price[: 9])
    if high_n == low_n:
        rsv = 50
    else:
        rsv = (price - low_n) / (high_n - low_n) * 100
    kdjk = 2.0 * kdjk / 3 + rsv / 3
    kdjd = 2.0 * kdjd / 3 + kdjk / 3
    kdjj = 3 * kdjk - 2 * kdjd
    return {'k': kdjk, 'd': kdjd, 'j': kdjj}


def calc_trix(price: float, trix_list: list, ema1: float, ema2: float, ema3: float) -> dict:
    ema1 = price * alpha_trix + ema1 * (1 - alpha_trix)
    ema2 = ema1 * alpha_trix + ema2 * (1 - alpha_trix)
    ema_three = ema2 * alpha_trix + ema3 * (1 - alpha_trix)
    trix = (ema_three - ema3) / ema3 * 100
    trix_list[0] = trix
    trma = sum(trix_list[: 9]) / 9
    return {'ema1': ema1, 'ema2': ema2, 'ema3': ema_three, 'trix': trix, 'trma': trma}


def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = Detail.query(code=stockDo.code).order_by(desc(Detail.day)).limit(21).all()
    stock_price = [r.current_price for r in stock_price_obj]
    high_price = [r.max_price for r in stock_price_obj]
    low_price = [r.min_price for r in stock_price_obj]
    trix_list = [r.trix for r in stock_price_obj]
    emas = stock_price_obj[1].emas
    emal = stock_price_obj[1].emal
    dea = stock_price_obj[1].dea
    kdjk = stock_price_obj[1].kdjk
    kdjd = stock_price_obj[1].kdjd
    trix_ema_one = stock_price_obj[1].trix_ema_one
    trix_ema_two = stock_price_obj[1].trix_ema_two
    trix_ema_three = stock_price_obj[1].trix_ema_three
    now = datetime.now().time()
    stop_time = datetime.strptime("15:00:20", "%H:%M:%S").time()
    if now < stop_time:
        current_date = normalizeHourAndMinute()
    else:
        current_date = "2021"
    volume_obj = Volumn.query_fields(columns=['volumn'], code=stockDo.code, date=current_date).order_by(desc(Volumn.create_time)).limit(3).all()
    stock_volume = [r[0] for r in volume_obj]
    volume_len = len(stock_volume) if len(stock_volume) > 0 else 1
    average_volumn = sum(stock_volume) / volume_len
    average_volumn = average_volumn if average_volumn > 0 else stockDo.volumn
    try:
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        stock_price[0] = stockDo.current_price
        high_price[0] = stockDo.max_price
        low_price[0] = stockDo.min_price
        trix_list[0] = 0
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        Detail.update(stockObj, current_price=stockDo.current_price, open_price=stockDo.open_price, last_price=stockDo.last_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_five=calc_MA(stock_price, 5),
                      ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2), emas=macd['emas'],
                      emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'],
                      trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'])
    except NoResultFound:
        stock_price.insert(0, stockDo.current_price)
        high_price.insert(0, stockDo.max_price)
        low_price.insert(0, stockDo.min_price)
        trix_list.index(0, 0)
        emas = stock_price_obj[0].emas
        emal = stock_price_obj[0].emal
        dea = stock_price_obj[0].dea
        kdjk = stock_price_obj[0].kdjk
        kdjd = stock_price_obj[0].kdjd
        trix_ema_one = stock_price_obj[0].trix_ema_one
        trix_ema_two = stock_price_obj[0].trix_ema_two
        trix_ema_three = stock_price_obj[0].trix_ema_three
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, last_price=stockDo.last_price,
                      ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2),
                      emas=macd['emas'], emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'],
                      trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'])
    Volumn.create(code=stockDo.code, date=current_date, volumn=stockDo.volumn, price=stockDo.current_price)


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
                        Stock.create(code=code, name=name, running=is_running, checking=0)
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
            stop_time = datetime.strptime("15:30:00", "%H:%M:%S").time()
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
                        job = scheduler.add_job(setAvailableStock, "interval", minutes=10, next_run_time=datetime.now() + timedelta(minutes=2))
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


if __name__ == '__main__':
    http1_host = "https://usc.ihuster.top"
    scheduler.add_job(checkTradeDay, 'cron', hour=9, minute=31, second=20)  # 启动任务
    scheduler.add_job(stopTask, 'cron', hour=15, minute=0, second=20)   # 停止任务
    scheduler.add_job(setAvailableStock, 'cron', hour=15, minute=30, second=20)  # 必须在15点后启动
    scheduler.add_job(setAllStock, 'cron', hour=22, minute=54, second=20)    # 更新股票信息
    scheduler.start()
    time.sleep(2)
    PID = os.getpid()
    with open('pid', 'w', encoding='utf-8') as f:
        f.write(str(PID))
    funcList = [getStockFromTencent, getStockFromSina, queryStockTencentFromHttp, queryStockXueQiuFromHttp, queryStockSinaFromHttp]
    paramList = ['', '', http1_host, http1_host, http1_host]
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        futures = [executor.submit(func, param) for func, param in zip(funcList, paramList)]
        wait(futures)
