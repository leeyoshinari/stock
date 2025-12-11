#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import json
import time
import queue
import random
import traceback
import requests
from typing import List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, wait
from sqlalchemy.exc import NoResultFound
from sqlalchemy import desc, asc
from settings import BATCH_SIZE, THREAD_POOL_SIZE, BATCH_INTERVAL, SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, HTTP_HOST1, HTTP_HOST2
from settings import OPENAI_URL, OPENAI_KEY, OPENAI_MODEL, API_URL, AI_MODEL, AUTH_CODE
from utils.model import StockModelDo, StockDataList, AiModelStockList
from utils.database import Database
from utils.scheduler import scheduler
from utils.send_email import sendEmail
from utils.ai_model import queryGemini, queryOpenAi
from utils.metric import analyze_buy_signal, analyze_buy_signal_new
from utils.selectStock import getStockDaDanFromTencent, getStockDaDanFromSina
from utils.selectStock import getStockOrderByFundFromDongCai, getStockOrderByFundFromTencent
from utils.selectStock import getStockZhuLiFundFromDongCai, getStockZhuLiFundFromTencent
from utils.database import Stock, Detail, Tools, Recommend, MinuteK
from utils.logging_getstock import logger


Database.init_db()
queryTask = queue.Queue()   # FIFO queue
recommendTask = queue.Queue()   # FIFO queue
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
    return round(sum(data[:window]) / len(data[:window]), 2)


def getStockFromTencent(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            if a == "proxy":
                param_data = {"url": f"https://qt.gtimg.cn/q={stockCode}", "method": "GET"}
                res = requests.post(f'{HTTP_HOST2}/api/proxy', json=param_data, headers={'Content-Type': 'application/json'})
            else:
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
                            logger.info(f"Tencent({a}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[6]))
                        stockDo.max_price = float(stockInfo[33])
                        stockDo.min_price = float(stockInfo[34])
                        stockDo.turnover_rate = float(stockInfo[38])
                        stockDo.day = stockInfo[30][:8]
                        saveStockInfo(stockDo)
                        logger.info(f"Tencent({a}): {stockDo}")
                    except:
                        logger.error(f"Tencent({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    queryTask.put(error_list)
                    time.sleep(3)
            else:
                logger.error(f"Tencent({a}) - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(3)
            error_list = []
        except:
            logger.error(f"Tencent({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
        finally:
            if datas: queryTask.task_done()


def getStockFromXueQiu(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            if a == 'proxy':
                param_data = {"url": f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", "method": "GET"}
                res = requests.post(f'{HTTP_HOST2}/api/proxy', json=param_data, headers={'Content-Type': 'application/json'})
            else:
                res = requests.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                if len(res_json['data']) > 0:
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
                            stockDo.turnover_rate = s['turnover_rate']
                            if not s['volume'] or s['volume'] < 2:
                                logger.info(f"XueQiu({a}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.volumn = int(s['volume'] / 100)
                            stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                            saveStockInfo(stockDo)
                            logger.info(f"XueQiu({a}): {stockDo}")
                        except:
                            logger.error(f"XueQiu({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                            logger.error(traceback.format_exc())
                            key_stock = f"{stockDo.code}count"
                            if dataCount[key_stock] < 5:
                                error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                else:
                    logger.error(f"XueQiu({a}) - 请求未正常返回...响应值: {res_json}")
                    queryTask.put(datas)
                    time.sleep(3)
                if len(error_list) > 0:
                    queryTask.put(error_list)
                    time.sleep(3)
            else:
                logger.error(f"XueQiu({a}) - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(3)
            error_list = []
        except:
            logger.error(f"XueQiu({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
        finally:
            if datas: queryTask.task_done()


def getStockFromSina(a):
    while True:
        try:
            datas = None
            datas = queryTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            h = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
            }
            if a == 'proxy':
                param_data = {"url": f"http://hq.sinajs.cn/list={stockCode}", "method": "GET", "headers": h}
                res = requests.post(f'{HTTP_HOST2}/api/proxy', json=param_data, headers={'Content-Type': 'application/json'})
            else:
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
                            logger.info(f"Sina({a}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[8]) / 100)
                        stockDo.last_price = float(stockInfo[2])
                        stockDo.max_price = float(stockInfo[4])
                        stockDo.min_price = float(stockInfo[5])
                        stockDo.day = stockInfo[30].replace('-', '')
                        saveStockInfo(stockDo)
                        logger.info(f"Sina({a}): {stockDo}")
                    except:
                        logger.error(f"Sina({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    queryTask.put(error_list)
                    time.sleep(3)
            else:
                logger.error(f"Sina({a}) - 请求未正常返回... {datas}")
                queryTask.put(datas)
                time.sleep(3)
            error_list = []
        except:
            logger.error(f"Sina({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
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
                            stockDo.turnover_rate = stockInfo['turnover_rate']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"Tencent - Http: {stockDo}")
                else:
                    logger.error(f"Tencent - Http 请求未正常返回, {res.text} - {datas}...")
                    queryTask.put(datas)
                    time.sleep(3)
            else:
                logger.error(f"Tencent - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(3)
        except:
            logger.error(f"Tencent - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
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
                            stockDo.turnover_rate = stockInfo['turnover_rate']
                            stockDo.day = stockInfo['day']
                            saveStockInfo(stockDo)
                            logger.info(f"XueQiu - Http: {stockDo}")
                else:
                    logger.error(f"XueQiu - Http 请求未正常返回, {res.text} - {datas}...")
                    queryTask.put(datas)
                    time.sleep(3)
            else:
                logger.error(f"XueQiu - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(3)
        except:
            logger.error(f"XueQiu - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
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
                    time.sleep(3)
            else:
                logger.error(f"Sina - Http 请求未正常返回 - {res.status_code} - {datas}")
                queryTask.put(datas)
                time.sleep(3)
        except:
            logger.error(f"Sina - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: queryTask.put(datas)
            time.sleep(3)
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
    try:
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        stock_price[0] = stockDo.current_price
        high_price[0] = stockDo.max_price
        low_price[0] = stockDo.min_price
        trix_list[0] = 0
        volume_list = [r.volumn for r in stock_price_obj[1: 6]]
        volume_len = min(max(len(volume_list), 1), 5)
        if len(stock_price_obj) > 1:
            emas = stock_price_obj[1].emas
            emal = stock_price_obj[1].emal
            dea = stock_price_obj[1].dea
            kdjk = stock_price_obj[1].kdjk
            kdjd = stock_price_obj[1].kdjd
            trix_ema_one = stock_price_obj[1].trix_ema_one
            trix_ema_two = stock_price_obj[1].trix_ema_two
            trix_ema_three = stock_price_obj[1].trix_ema_three
        else:
            emas = stockDo.current_price
            emal = stockDo.current_price
            dea = 0
            kdjk = 50
            kdjd = 50
            trix_ema_one = stockDo.current_price
            trix_ema_two = stockDo.current_price
            trix_ema_three = stockDo.current_price
        average_volumn = sum(volume_list) / volume_len
        average_volumn = average_volumn if average_volumn > 0 else stockDo.volumn
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        Detail.update(stockObj, current_price=stockDo.current_price, open_price=stockDo.open_price, last_price=stockDo.last_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_five=calc_MA(stock_price, 5),
                      ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2), emas=macd['emas'],
                      emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'], fund=0.0,
                      trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'], turnover_rate=stockDo.turnover_rate)
    except NoResultFound:
        stock_price.insert(0, stockDo.current_price)
        high_price.insert(0, stockDo.max_price)
        low_price.insert(0, stockDo.min_price)
        trix_list.insert(0, 0)
        volume_list = [r.volumn for r in stock_price_obj[: 5]]
        volume_len = min(max(len(volume_list), 1), 5)
        emas = stock_price_obj[0].emas if len(stock_price_obj) > 0 else stockDo.current_price
        emal = stock_price_obj[0].emal if len(stock_price_obj) > 0 else stockDo.current_price
        dea = stock_price_obj[0].dea if len(stock_price_obj) > 0 else 0
        kdjk = stock_price_obj[0].kdjk if len(stock_price_obj) > 0 else 50
        kdjd = stock_price_obj[0].kdjd if len(stock_price_obj) > 0 else 50
        trix_ema_one = stock_price_obj[0].trix_ema_one if len(stock_price_obj) > 0 else stockDo.current_price
        trix_ema_two = stock_price_obj[0].trix_ema_two if len(stock_price_obj) > 0 else stockDo.current_price
        trix_ema_three = stock_price_obj[0].trix_ema_three if len(stock_price_obj) > 0 else stockDo.current_price
        average_volumn = sum(volume_list) / volume_len
        average_volumn = average_volumn if average_volumn > 0 else stockDo.volumn
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                      max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, last_price=stockDo.last_price, fund=0.0,
                      ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), qrr=round(stockDo.volumn / average_volumn, 2),
                      emas=macd['emas'], emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'],
                      trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'], turnover_rate=stockDo.turnover_rate)


def setAvailableStock():
    global is_trade_day
    if not is_trade_day:
        logger.info("不在交易时间...")
    else:
        try:
            total_cnt = Stock.query(running=1).count()
            total_batch = int((total_cnt + BATCH_SIZE - 1) / BATCH_SIZE)
            one_batch_size = int(BATCH_SIZE / THREAD_POOL_SIZE - 2)
            page = 0
            while page < total_batch:
                offset = page * BATCH_SIZE
                stockList = []
                stockInfo = Stock.query(running=1).order_by(asc(Stock.create_time)).offset(offset).limit(BATCH_SIZE).all()
                for s in stockInfo:
                    stockList.append({s.code: s.name, f'{s.code}count': 1})
                random.shuffle(stockList)
                for i in range(0, len(stockList), one_batch_size):
                    d = stockList[i: i + one_batch_size]
                    queryTask.put(d)
                page += 1
                logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次, 数量 {len(stockList)}...")
                time.sleep(BATCH_INTERVAL)
        except:
            logger.error(traceback.format_exc())


def getStockFromTencentReal(a):
    while True:
        try:
            minute = time.strftime("%H:%M")
            datas = None
            datas = recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
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
                        if int(stockInfo[6]) < 2:
                            logger.info(f"Tencent(Real) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[6]))
                        # stockDo.turnover_rate = float(stockInfo[38])
                        stockDo.day = stockInfo[30][:8]
                        MinuteK.create(code=stockDo.code, day=stockDo.day, minute=minute, volume=stockDo.volumn, price=stockDo.current_price)
                        logger.info(f"Tencent(Real): {stockDo}")
                    except:
                        logger.error(f"Tencent(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    recommendTask.put(error_list)
                    time.sleep(2)
            else:
                logger.error(f"Tencent(Real) - 请求未正常返回... {datas}")
                recommendTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"Tencent(Real) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: recommendTask.put(datas)
            time.sleep(2)
        finally:
            if datas: recommendTask.task_done()


def getStockFromXueQiuReal(a):
    while True:
        try:
            minute = time.strftime("%H:%M")
            datas = None
            datas = recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            res = requests.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                if len(res_json['data']) > 0:
                    for s in res_json['data']:
                        try:
                            stockDo = StockModelDo()
                            code = s['symbol'][2:]
                            stockDo.name = dataDict[code]
                            stockDo.code = code
                            stockDo.current_price = s['current']
                            # stockDo.turnover_rate = s['turnover_rate']
                            if not s['volume'] or s['volume'] < 2:
                                logger.info(f"XueQiu(Real) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.volumn = int(s['volume'] / 100)
                            stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                            MinuteK.create(code=stockDo.code, day=stockDo.day, minute=minute, volume=stockDo.volumn, price=stockDo.current_price)
                            logger.info(f"XueQiu(Real): {stockDo}")
                        except:
                            logger.error(f"XueQiu(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                            logger.error(traceback.format_exc())
                            key_stock = f"{stockDo.code}count"
                            if dataCount[key_stock] < 5:
                                error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                else:
                    logger.error(f"XueQiu(Real) - 请求未正常返回...响应值: {res_json}")
                    recommendTask.put(datas)
                    time.sleep(2)
                if len(error_list) > 0:
                    recommendTask.put(error_list)
                    time.sleep(2)
            else:
                logger.error(f"XueQiu(Real) - 请求未正常返回... {datas}")
                recommendTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"XueQiu(Real) - 出现异常...... {res.text}")
            logger.error(traceback.format_exc())
            if datas: recommendTask.put(datas)
            time.sleep(2)
        finally:
            if datas: recommendTask.task_done()


def getStockFromSinaReal(a):
    while True:
        try:
            minute = time.strftime("%H:%M")
            datas = None
            datas = recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
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
                        if int(stockInfo[8]) < 2:
                            logger.info(f"Sina(Real) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[8]) / 100)
                        stockDo.day = stockInfo[30].replace('-', '')
                        MinuteK.create(code=stockDo.code, day=stockDo.day, minute=minute, volume=stockDo.volumn, price=stockDo.current_price)
                        logger.info(f"Sina(Real): {stockDo}")
                    except:
                        logger.error(f"Sina(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    recommendTask.put(error_list)
                    time.sleep(2)
            else:
                logger.error(f"Sina(Real) - 请求未正常返回... {datas}")
                recommendTask.put(datas)
                time.sleep(2)
            error_list = []
        except:
            logger.error(f"Sina(Real) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: recommendTask.put(datas)
            time.sleep(2)
        finally:
            if datas: recommendTask.task_done()


def queryRecommendStockData():
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
            stockInfo = Recommend.filter_condition(is_null_condition=['last_five_price']).all()
            for s in stockInfo:
                stockList.append({s.code: s.name, f'{s.code}count': 1})
            random.shuffle(stockList)
            half_num = int(len(stockList) / 2)
            recommendTask.put(stockList[: half_num])
            recommendTask.put(stockList[half_num:])
        except:
            logger.error(traceback.format_exc())


def startSelectStock():
    global is_trade_day
    if not is_trade_day:
        logger.info("不在交易时间...")
    else:
        try:
            try:
                stockInfos = getStockOrderByFundFromDongCai()
            except:
                logger.error(traceback.format_exc())
                stockInfos = getStockOrderByFundFromTencent()
            stockList = []
            for s in stockInfos:
                try:
                    s_info = Stock.get_one(s['code'])
                    if s_info.running == 1:
                        stockList.append({s['code']: s['name'], f'{s['code']}count': 1})
                except:
                    logger.error(traceback.format_exc())
            index = 0
            one_batch_size = int(BATCH_SIZE / THREAD_POOL_SIZE - 2)
            for i in range(0, len(stockList), one_batch_size):
                d = stockList[i: i + one_batch_size]
                queryTask.put(d)
                index += 1
                if index % (THREAD_POOL_SIZE - 2) == 0:
                    logger.info(f"正在更新选股的数据，当前是第 {index} 批，总数 {len(stockList)} 个")
                    time.sleep(10)
            current_day = time.strftime("%Y%m%d")
            try:
                tool = Tools.get_one("openDoor2")
                Tools.update(tool, value=current_day)
            except NoResultFound:
                Tools.create(key="openDoor2", value=current_day)
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
                        job = scheduler.add_job(queryRecommendStockData, "interval", minutes=1, next_run_time=datetime.now() + timedelta(seconds=8))
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


def calcStockMetric():
    global is_trade_day
    try:
        if is_trade_day:
            stock_metric = []   # 非买入信号的策略选股
            day = ''
            stockInfos = Stock.query(running=1).all()
            for s in stockInfos:
                try:
                    stockList = Detail.query(code=s.code).order_by(desc(Detail.day)).limit(5).all()
                    up_percent = (stockList[0].current_price - stockList[0].last_price) / stockList[0].last_price * 100
                    if (up_percent > 9 or up_percent < 1 or stockList[0].qrr < 1.2):
                        continue
                    stockData = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
                    stockData.reverse()
                    stockMetric = analyze_buy_signal(stockData, None)
                    day = stockMetric['day']
                    logger.info(f"Auto Select Stock - {s.code} - {s.name} : - : {stockMetric}")
                    if stockMetric['score'] > 5:
                        stock_metric.append(stockMetric)
                except:
                    logger.error(f"{s.code} - {s.name}")
                    logger.error(traceback.format_exc())

            send_msg = []
            stock_metric.sort(key=lambda x: -x['score'])
            logger.info(f"select stocks: {stock_metric}")
            ai_model_list = stock_metric[: 10]
            for i in range(len(ai_model_list)):
                logger.info(f"Select stocks: {ai_model_list[i]}")
                stock_code_id = ai_model_list[i]['code']
                stock_data_list = Detail.query(code=stock_code_id).order_by(desc(Detail.day)).limit(6).all()
                stockData = [AiModelStockList.from_orm_format(f).model_dump() for f in stock_data_list]
                stockData.reverse()
                try:
                    fflow = getStockZhuLiFundFromDongCai(stock_code_id)
                except:
                    logger.error(traceback.format_exc())
                    try:
                        fflow = getStockZhuLiFundFromTencent(stock_code_id)
                    except:
                        logger.error(traceback.format_exc())
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取数据异常', f"获取 {stock_code_id} 的资金流向数据异常～")
                        fflow = 0.0
                stockData[-1]['fund'] = fflow
                # 请求大模型
                try:
                    # stock_dict = queryGemini(json.dumps(stockData), API_URL, AI_MODEL, AUTH_CODE)
                    stock_dict = queryOpenAi(json.dumps(stockData), OPENAI_URL, OPENAI_MODEL, OPENAI_KEY)
                    logger.info(f"AI-model: {stock_dict}")
                    if stock_dict and stock_dict[0][stock_code_id]['buy']:
                        recommend_stocks = Recommend.filter_condition(equal_condition={"code": stock_code_id}, is_null_condition=['last_five_price']).all()
                        if len(recommend_stocks) < 1:   # 如果已经推荐过了，就跳过，否则再次推荐
                            Recommend.create(code=stock_code_id, name=ai_model_list[i]['name'], price=0.01)
                            send_msg.append(f"{stock_code_id} - {ai_model_list[i]['name']}, 当前价: {ai_model_list[i]['price']}, 信号: {stock_dict[0][stock_code_id]['reason']}")
                    else:
                        logger.error(f"大模型返回结果为空 - {stock_dict}")
                except:
                    logger.error(traceback.format_exc())
                    stock_dict = {}

            if len(send_msg) > 0:
                msg = '\n'.join(send_msg)
                sendEmail(SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, f'{day} 股票推荐', msg)
                logger.info('Email send success ~')
            else:
                logger.info('No stock recommended.')
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


def selectStockMetric():
    global is_trade_day
    try:
        if is_trade_day:
            stock_metric = []   # 非买入信号的策略选股
            day = ''
            tool = Tools.get_one("openDoor")
            current_day = tool.value
            stockInfos = Detail.query(day=current_day).all()
            for s in stockInfos:
                try:
                    stockList = Detail.query(code=s.code).order_by(desc(Detail.day)).limit(5).all()
                    if (stockList[0].qrr < 1.2 or stockList[0].qrr > 6):
                        continue
                    stockData = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
                    stockData.reverse()
                    stockMetric = analyze_buy_signal_new(stockData)
                    day = stockMetric['day']
                    logger.info(f"Auto Select Stock - {s.code} - {s.name} : - : {stockMetric}")
                    if stockMetric['buy']:
                        stock_metric.append(stockMetric)
                except:
                    logger.error(f"{s.code} - {s.name}")
                    logger.error(traceback.format_exc())

            send_msg = []
            # stock_metric.sort(key=lambda x: -x['turnover_rate'])
            logger.info(f"select stocks: {stock_metric}")
            ai_model_list = stock_metric[: 500]
            has_index = 0
            for i in range(len(ai_model_list)):
                logger.info(f"Select stocks: {ai_model_list[i]}")
                stock_code_id = ai_model_list[i]['code']
                da_dan = getStockDaDanFromTencent(stock_code_id)
                if 'msg' in da_dan:
                    logger.error(da_dan['msg'])
                    da_dan = getStockDaDanFromSina(stock_code_id)
                    if 'msg' in da_dan:
                        logger.error(da_dan['msg'])
                        time.sleep(2)
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取买卖盘面异常', f"获取 {stock_code_id} 的买卖盘面数据异常～")
                        continue
                if 'msg' not in da_dan:
                    if da_dan['b'] > 59 and da_dan['s'] < 30 and da_dan['m'] < 10:
                        pass
                    else:
                        logger.error(f"DaDan Stock - {stock_code_id} - no meet 60% / 30% / 10% 这样的数值, - {da_dan}")
                        time.sleep(2)
                        continue
                stock_data_list = Detail.query(code=stock_code_id).order_by(desc(Detail.day)).limit(6).all()
                stockData = [AiModelStockList.from_orm_format(f).model_dump() for f in stock_data_list]
                stockData.reverse()
                try:
                    fflow = getStockZhuLiFundFromDongCai(stock_code_id)
                except:
                    logger.error(traceback.format_exc())
                    try:
                        fflow = getStockZhuLiFundFromTencent(stock_code_id)
                    except:
                        logger.error(traceback.format_exc())
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取数据异常', f"获取 {stock_code_id} 的资金流向数据异常～")
                        fflow = 0.0
                stockData[-1]['fund'] = fflow
                # 请求大模型
                try:
                    reason = f"主动性买盘: {da_dan['b']}%, 主动性卖盘: {da_dan['s']}%, 中性盘: {da_dan['m']}%\n\n"
                    stock_dict = queryOpenAi(json.dumps(stockData), OPENAI_URL, OPENAI_MODEL, OPENAI_KEY)
                    logger.info(f"AI-model-OpenAI: {stock_dict}")
                    if stock_dict and stock_dict['buy']:
                        recommend_stocks = Recommend.filter_condition(equal_condition={"code": stock_code_id}, is_null_condition=['last_five_price']).all()
                        if len(recommend_stocks) < 1:   # 如果已经推荐过了，就跳过，否则再次推荐
                            has_index += 1
                            reason = reason + f"ChatGPT: {stock_dict['reason']}"
                            stock_dict = queryGemini(json.dumps(stockData), API_URL, AI_MODEL, AUTH_CODE)
                            logger.info(f"AI-model-Gemini: {stock_dict}")
                            reason = reason + f"\n\nGemini: {stock_dict['reason']}"
                            if stock_dict and stock_dict['buy']:
                                Recommend.create(code=stock_code_id, name=ai_model_list[i]['name'], price=0.01, content=reason)
                                send_msg.append(f"{stock_code_id} - {ai_model_list[i]['name']}, 当前价: {ai_model_list[i]['price']}")
                            if has_index > 9:
                                break
                    else:
                        logger.error(f"大模型返回结果为空 - {stock_dict}")
                except:
                    logger.error(traceback.format_exc())
                    stock_dict = {}

                if has_index > 9:
                    break

            if len(send_msg) > 0:
                msg = '\n'.join(send_msg)
                sendEmail(SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, f'{day} 股票推荐', msg)
                logger.info('Email send success ~')
            else:
                logger.info('No stock recommended.')
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


def saveStockFund(day: str, code: str, fund: float):
    s = Detail.get((code, day))
    if s:
        Detail.update(s, fund=fund)
        logger.info(f"Update Stock Fund: {code} - {fund}")


def updateStockFund(a=1):
    global is_trade_day
    try:
        h = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
        if is_trade_day:
            total_page = 100
            tool = Tools.get_one("openDoor")
            day = tool.value
            if a == 1:
                try:
                    current_time = int(time.time() * 1000)
                    url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
                    res = requests.get(url, headers=h)
                    res_json = json.loads(res.text.split('(')[1].split(')')[0])
                    total_page = int((res_json['data']['total'] + 49) / 50)
                    for k in res_json['data']['diff']:
                        code = k['12']
                        fund = round(k['f62'] / 10000, 2)
                        saveStockFund(day, code, fund)
                    for p in range(1, total_page):
                        if p % 5 == 0:
                            current_time = int(time.time() * 1000)
                        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn={p + 1}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
                        res = requests.get(url, headers=h)
                        res_json = json.loads(res.text.split('(')[1].split(')')[0])
                        for k in res_json['data']['diff']:
                            code = k['12']
                            fund = round(k['f62'] / 10000, 2)
                            saveStockFund(day, code, fund)
                        time.sleep(5)
                except:
                    logger.error(traceback.format_exc())
                    updateStockFund(2)
            else:
                try:
                    page_size = 50
                    url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset=0&count={page_size}'
                    res = requests.get(url, headers=h)
                    res_json = json.loads(res.text)
                    total_page = int((res_json['data']['total'] + 49) / 50)
                    for k in res_json['data']['rank_list']:
                        code = k['code'][2:]
                        fund = float(k['zljlr'])
                        saveStockFund(day, code, fund)
                    for p in range(1, total_page):
                        url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset={page_size * p}&count={page_size}'
                        res = requests.get(url, headers=h)
                        res_json = json.loads(res.text)
                        for k in res_json['data']['rank_list']:
                            code = k['code'][2:]
                            fund = float(k['zljlr'])
                            saveStockFund(day, code, fund)
                        time.sleep(5)
                except:
                    logger.error(traceback.format_exc())
                    sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, "获取所有股票的主力资金净流入数据失败")
            time.sleep(5)
            checkUpdateStockFund()  # 更新漏网数据，如果有
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


def checkUpdateStockFund():
    try:
        tool = Tools.get_one("openDoor")
        day = tool.value
        stocks = Detail.filter_condition(equal_condition={'day': day}, less_equal_condition={'fund': 0.01}, greater_equal_condition={'fund': -0.01}).all()
        for s in stocks:
            try:
                fund = getStockZhuLiFundFromDongCai(s.code)
            except:
                fund = getStockZhuLiFundFromTencent(s.code)
            Detail.update(s, fund)
            logger.info(f"ReUpdate Stock Fund: {s.code} - {fund}")
            time.sleep(5)
    except:
        logger.error(traceback.format_exc())


def updateRecommendPrice():
    global is_trade_day
    try:
        if is_trade_day:
            # 更新最新收盘价
            try:
                tool = Tools.get_one("openDoor")
                new_day = tool.value
                new_stocks = Recommend.filter_condition(less_equal_condition={'price': 0.02}).all()
                for r in new_stocks:
                    s = Detail.get_one((r.code, new_day))
                    Recommend.update(r, price=s.current_price)
            except:
                logger.error(traceback.format_exc())

            t = time.strftime("%Y-%m-%d") + " 09:00:00"
            recommend_stocks = Recommend.filter_condition(less_equal_condition={'create_time': t}, is_null_condition=['last_five_price']).all()
            for r in recommend_stocks:
                try:
                    stockInfo = Detail.get((r.code, new_day))
                    if stockInfo:
                        price_pct = round((stockInfo.current_price - r.price) / r.price * 100, 2)
                        max_price_pct = round((stockInfo.max_price - r.price) / r.price * 100, 2)
                        min_price_pct = round((stockInfo.min_price - r.price) / r.price * 100, 2)
                        if r.last_one_price is None:
                            Recommend.update(r, last_one_price=price_pct, last_one_high=max_price_pct, last_one_low=min_price_pct)
                        elif r.last_two_price is None:
                            Recommend.update(r, last_two_price=price_pct, last_two_high=max_price_pct, last_two_low=min_price_pct)
                        elif r.last_three_price is None:
                            Recommend.update(r, last_three_price=price_pct, last_three_high=max_price_pct, last_three_low=min_price_pct)
                        elif r.last_four_price is None:
                            Recommend.update(r, last_four_price=price_pct, last_four_high=max_price_pct, last_four_low=min_price_pct)
                        elif r.last_five_price is None:
                            Recommend.update(r, last_five_price=price_pct, last_five_high=max_price_pct, last_five_low=min_price_pct)
                        logger.info(f"update recommend stocks {r.code} - {r.name} price success!")
                except:
                    sendEmail(SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, "更新推荐股票的价格报错，请抽时间核对")
                    logger.error(traceback.format_exc())

            # 更新交易标识
            now = datetime.now().time()
            stop_time = datetime.strptime("15:30:00", "%H:%M:%S").time()
            if now > stop_time:
                is_trade_day = False
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


def setAllSHStock():
    today = datetime.today()
    if today.weekday() < 5:
        try:
            t = int(time.time() * 1000)
            page = 1
            hh = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'
            }
            res = requests.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={page}&pageHelp.pageSize=50&pageHelp.pageNo={page}&pageHelp.endPage={page}&_={t}", headers=hh)
            if res.status_code == 200:
                res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                res_json = json.loads('{' + res_text + '}')
                total_page = res_json['pageHelp']['pageCount']
                for p in range(total_page):
                    try:
                        t = int(time.time() * 1000)
                        res = requests.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={p + 1}&pageHelp.pageSize=50&pageHelp.pageNo={p + 1}&pageHelp.endPage={p + 1}&_={t}", headers=hh)
                        if res.status_code == 200:
                            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                            res_json = json.loads('{' + res_text + '}')
                            stock_list = res_json['pageHelp']['data']
                            for s in stock_list:
                                code = s['A_STOCK_CODE']
                                name = s['COMPANY_ABBR']
                                try:
                                    s = Stock.get_one(code)
                                    is_running = s.running
                                    if ('ST' in name.upper() or '退' in name) and s.running == 1:
                                        Stock.update(s, running=0, name=name)
                                        logger.info(f"股票 {s.name} - {s.code}  | {name} - {code} 处于退市状态, 忽略掉...")
                                        continue
                                    if 'ST' in s.name.upper() and 'ST' not in name.upper():
                                        is_running = min(getStockType(code), 1)
                                        Stock.update(s, running=is_running, name=name)
                                        logger.info(f"股票 {s.name} - {s.code}  | {name} - {code} 重新上市, 继续处理...")
                                        continue
                                    Stock.update(s, name=name)
                                except NoResultFound:
                                    is_running = getStockType(code)
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        Stock.create(code=code, name=name, running=is_running)
                                        logger.info(f"股票 {name} - {code}  | {name} - {code} 添加成功, 状态是 {is_running} ...")
                                except:
                                    logger.error(traceback.format_exc())
                        else:
                            logger.error('数据更新异常')
                    except:
                        logger.error(traceback.format_exc())
                        logger.error("请求SH数据异常...")
                    logger.info(f"正在处理SH第 {p + 1} 页...")
                    time.sleep(6)
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


def setAllSZStock():
    today = datetime.today()
    if today.weekday() < 5:
        try:
            t = int(time.time() * 1000)
            page = 1
            hh = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'host': 'www.szse.cn', 'referer': 'https://www.szse.cn/market/product/stock/list/index.html', 'content-type': 'application/json'
            }
            res = requests.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={page}&random=0.574{t}", headers=hh)
            if res.status_code == 200:
                res_json = json.loads(res.text)[0]
                total_page = res_json['metadata']['pagecount']
                for p in range(total_page):
                    try:
                        t = int(time.time() * 1000)
                        res = requests.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={p + 1}&random=0.574{t}", headers=hh)
                        if res.status_code == 200:
                            res_json = json.loads(res.text)[0]
                            stock_list = res_json['data']
                            for s in stock_list:
                                code = s['agdm']
                                name = s['agjc'].split('<u>')[-1].split('</u>')[0]
                                try:
                                    s = Stock.get_one(code)
                                    is_running = s.running
                                    if ('ST' in name.upper() or '退' in name) and s.running == 1:
                                        Stock.update(s, running=0, name=name)
                                        logger.info(f"股票 {s.name} - {s.code} | {name} - {code} 处于退市状态, 忽略掉...")
                                        continue
                                    if 'ST' in s.name.upper() and 'ST' not in name.upper():
                                        Stock.update(s, running=1, name=name)
                                        logger.info(f"股票 {s.name} - {s.code} | {name} - {code} 重新上市, 继续处理...")
                                        continue
                                    Stock.update(s, name=name)
                                except NoResultFound:
                                    is_running = getStockType(code)
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        Stock.create(code=code, name=name, running=is_running)
                                        logger.info(f"股票 {name} - {code} | {name} - {code} 添加成功, 状态是 {is_running} ...")
                                except:
                                    logger.error(traceback.format_exc())
                        else:
                            logger.error('数据更新异常')
                    except:
                        logger.error(traceback.format_exc())
                        logger.error("请求SZ数据异常...")
                    logger.info(f"正在处理SZ第 {p + 1} 页...")
                    time.sleep(6)
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


def stopTask():
    global running_job_id
    global is_trade_day
    if is_trade_day and running_job_id and scheduler.get_job(running_job_id):
        scheduler.remove_job(running_job_id)
        running_job_id = None
        logger.info("查询任务已停止...")
    else:
        logger.info("查询任务不存在或已结束...")


# def clearStockData():
#     # 清理 volumn 表数据
#     stockInfos = Stock.query().all()
#     for s in stockInfos:
#         s_v = Volumn.query(code=s.code).order_by(asc(Volumn.create_time)).all()
#         if len(s_v) > 125:
#             for i in range(25):
#                 Volumn.delete(s_v[i])
#             logger.info(f"delete stock volume data success,  {s.code} - {s.name}")


if __name__ == '__main__':
    scheduler.add_job(checkTradeDay, 'cron', hour=9, minute=30, second=50)  # 启动任务
    scheduler.add_job(setAllSHStock, 'cron', hour=12, minute=5, second=20)    # 中午更新股票信息
    scheduler.add_job(setAllSZStock, 'cron', hour=12, minute=0, second=20)    # 中午更新股票信息
    scheduler.add_job(startSelectStock, 'cron', hour=14, minute=49, second=1)  # 开始选股
    # scheduler.add_job(calcStockMetric, 'cron', hour=14, minute=50, second=10)    # 计算推荐股票
    scheduler.add_job(selectStockMetric, 'cron', hour=14, minute=50, second=10)    # 计算推荐股票
    scheduler.add_job(stopTask, 'cron', hour=15, minute=0, second=20)   # 停止任务
    scheduler.add_job(setAvailableStock, 'cron', hour=15, minute=28, second=20)  # 收盘后更新数据
    scheduler.add_job(updateStockFund, 'cron', hour=15, minute=48, second=20, args=[1])    # 更新主力流入数据
    scheduler.add_job(updateRecommendPrice, 'cron', hour=15, minute=52, second=50)    # 更新推荐股票的价格
    # scheduler.add_job(clearStockData, 'cron', hour=15, minute=58, second=50)    # 删除交易时间的数据
    scheduler.start()
    time.sleep(2)
    PID = os.getpid()
    with open('pid', 'w', encoding='utf-8') as f:
        f.write(str(PID))
    funcList = [getStockFromTencent, queryStockTencentFromHttp, queryStockXueQiuFromHttp, getStockFromTencent, getStockFromXueQiu, getStockFromTencentReal, getStockFromSinaReal]
    paramList = ['base', HTTP_HOST1, HTTP_HOST1, 'proxy', 'proxy', 'base', 'base']
    with ThreadPoolExecutor(max_workers=THREAD_POOL_SIZE) as executor:
        futures = [executor.submit(func, param) for func, param in zip(funcList, paramList)]
        wait(futures)
