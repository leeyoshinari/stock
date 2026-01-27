#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import json
import time
import random
import asyncio
import traceback
from typing import List
from contextlib import suppress
from datetime import datetime, timedelta
from sqlalchemy.exc import NoResultFound
from settings import BATCH_SIZE, All_STOCK_DATA_SIZE, BATCH_INTERVAL, SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, HTTP_HOST1, HTTP_HOST2
from settings import OPENAI_URL, OPENAI_KEY, OPENAI_MODEL, API_URL, AI_MODEL, AI_MODEL25, AUTH_CODE, FILE_PATH
from utils.model import StockModelDo, StockDataList, AiModelStockList
from utils.scheduler import scheduler
from utils.writer_queue import writer_queue
from utils.http_client import http
from utils.send_email import sendEmail
from utils.initData import initStockData
from utils.ai_model import queryGemini, queryOpenAi, webSearchTopic
from utils.metric import analyze_buy_signal, analyze_buy_signal_new, bollinger_bands, real_traded_minutes
from utils.selectStock import getStockDaDanFromTencent, getStockDaDanFromSina, getStockBanKuaiFromDOngCai, normalize_topic
from utils.selectStock import getStockOrderByFundFromDongCai, getStockOrderByFundFromTencent, getBanKuaiFundFlowFromDongCai
from utils.selectStock import getStockZhuLiFundFromDongCai, getStockZhuLiFundFromTencent
from utils.database import Stock, Detail, Tools, Recommend, MinuteK, write_worker
from utils.logging_getstock import logger


queryTask = asyncio.Queue()
recommendTask = asyncio.Queue()
running_job_id = "interval_stock_data"
current_topic = []
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


def generateStockCodeForSina(data: dict) -> str:
    s = []
    for r in list(data.keys()):
        s.append(f"{getStockRegion(r)}{r}_i")
    return ",".join(s)


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[:window]) / len(data[:window]), 2)


def detail2List(data: list) -> dict:
    res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
           'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
           'd': [], 'j': [], 'trix': [], 'trma': [], 'boll_up': [], 'boll_low': []}
    for d in data:
        res['code'] = d.code
        res['day'].append(d.day)
        res['current_price'].append(d.current_price)
        res['last_price'].append(d.last_price)
        res['open_price'].append(d.open_price)
        res['max_price'].append(d.max_price)
        res['min_price'].append(d.min_price)
        res['volume'].append(d.volumn)
        res['turnover_rate'].append(f"{d.turnover_rate}%")
        res['fund'].append(d.fund)
        res['ma_five'].append(d.ma_five)
        res['ma_ten'].append(d.ma_ten)
        res['ma_twenty'].append(d.ma_twenty)
        res['qrr'].append(d.qrr)
        res['diff'].append(round(d.emas - d.emal, 4))
        res['dea'].append(round(d.dea, 4))
        res['k'].append(round(d.kdjk, 4))
        res['d'].append(round(d.kdjd, 4))
        res['j'].append(round(d.kdjj, 4))
        res['trix'].append(round(d.trix, 4))
        res['trma'].append(round(d.trma, 4))
        res['boll_up'].append(d.boll_up)
        res['boll_low'].append(d.boll_low)
    return res


async def getStockFromTencent(a):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            if a == "proxy":
                param_data = {"url": f"https://qt.gtimg.cn/q={stockCode}", "method": "GET"}
                res = await http.post(f'{HTTP_HOST2}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
            else:
                res = await http.get(f"https://qt.gtimg.cn/q={stockCode}", headers=headers)
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
                        await saveStockInfo(stockDo)
                        logger.info(f"Tencent({a}): {stockDo}")
                    except:
                        logger.error(f"Tencent({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    await queryTask.put(error_list)
                    await asyncio.sleep(3)
            else:
                logger.error(f"Tencent({a}) - 请求未正常返回... {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
            error_list = []
        except:
            logger.error(f"Tencent({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
        finally:
            if datas: queryTask.task_done()


async def getStockFromXueQiu(a):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            if a == 'proxy':
                param_data = {"url": f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", "method": "GET"}
                res = await http.post(f'{HTTP_HOST2}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
            else:
                res = await http.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
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
                            await saveStockInfo(stockDo)
                            logger.info(f"XueQiu({a}): {stockDo}")
                        except:
                            logger.error(f"XueQiu({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                            logger.error(traceback.format_exc())
                            key_stock = f"{stockDo.code}count"
                            if dataCount[key_stock] < 5:
                                error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                else:
                    logger.error(f"XueQiu({a}) - 请求未正常返回...响应值: {res_json}")
                    await queryTask.put(datas)
                    await asyncio.sleep(3)
                if len(error_list) > 0:
                    await queryTask.put(error_list)
                    await asyncio.sleep(3)
            else:
                logger.error(f"XueQiu({a}) - 请求未正常返回... {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
            error_list = []
        except:
            logger.error(f"XueQiu({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
        finally:
            if datas: queryTask.task_done()


async def getStockFromSina(a):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
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
                res = await http.post(f'{HTTP_HOST2}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
            else:
                res = await http.get(f"http://hq.sinajs.cn/list={stockCode}", headers=h)
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
                        await saveStockInfo(stockDo)
                        logger.info(f"Sina({a}): {stockDo}")
                    except:
                        logger.error(f"Sina({a}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    await queryTask.put(error_list)
                    await asyncio.sleep(3)
            else:
                logger.error(f"Sina({a}) - 请求未正常返回... {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
            error_list = []
        except:
            logger.error(f"Sina({a}) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
        finally:
            if datas: queryTask.task_done()


async def queryStockTencentFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
            if datas == 'end': break
            res = await http.post(f"{host}/stock/query/tencent", json_data={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        await queryTask.put(res_json['data']['error'])
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
                            await saveStockInfo(stockDo)
                            logger.info(f"Tencent - Http: {stockDo}")
                else:
                    logger.error(f"Tencent - Http 请求未正常返回, {res.text} - {datas}...")
                    await queryTask.put(datas)
                    await asyncio.sleep(3)
            else:
                logger.error(f"Tencent - Http 请求未正常返回 - {res.status_code} - {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
        except:
            logger.error(f"Tencent - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
        finally:
            if datas: queryTask.task_done()


async def queryStockXueQiuFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
            if datas == 'end': break
            res = await http.post(f"{host}/stock/query/xueqiu", json_data={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        await queryTask.put(res_json['data']['error'])
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
                            await saveStockInfo(stockDo)
                            logger.info(f"XueQiu - Http: {stockDo}")
                else:
                    logger.error(f"XueQiu - Http 请求未正常返回, {res.text} - {datas}...")
                    await queryTask.put(datas)
                    await asyncio.sleep(3)
            else:
                logger.error(f"XueQiu - Http 请求未正常返回 - {res.status_code} - {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
        except:
            logger.error(f"XueQiu - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
        finally:
            if datas: queryTask.task_done()


async def queryStockSinaFromHttp(host: str):
    while True:
        try:
            datas = None
            datas = await queryTask.get()
            if datas == 'end': break
            res = await http.post(f"{host}/stock/query/sina", json_data={"data": datas}, headers={"content-type": "application/json"})
            if res.status_code == 200 or res.status_code == 201:
                res_json = json.loads(res.text)
                if res_json['success']:
                    if res_json['data']['error']:
                        await queryTask.put(res_json['data']['error'])
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
                            await saveStockInfo(stockDo)
                            logger.info(f"Sina - Http: {stockDo}")
                else:
                    logger.error(f"Sina - Http 请求未正常返回, {res.text} - {datas}...")
                    await queryTask.put(datas)
                    await asyncio.sleep(3)
            else:
                logger.error(f"Sina - Http 请求未正常返回 - {res.status_code} - {datas}")
                await queryTask.put(datas)
                await asyncio.sleep(3)
        except:
            logger.error(f"Sina - Http 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await queryTask.put(datas)
            await asyncio.sleep(3)
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


async def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = await Detail.query().equal(code=stockDo.code).order_by(Detail.day.desc()).limit(21).all()
    stock_price = [r.current_price for r in stock_price_obj]
    high_price = [r.max_price for r in stock_price_obj]
    low_price = [r.min_price for r in stock_price_obj]
    trix_list = [r.trix for r in stock_price_obj]
    real_trade_time = real_traded_minutes()
    try:
        _ = await Detail.get_one((stockDo.code, stockDo.day))
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
        average_volumn = (sum(volume_list) / volume_len) * (real_trade_time / 240)
        average_volumn = average_volumn if average_volumn > 0 else stockDo.volumn
        ma_twenty = calc_MA(stock_price, 20)
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        boll_up, boll_low = bollinger_bands(stock_price[:20], ma_twenty)
        await Detail.update((stockDo.code, stockDo.day), current_price=stockDo.current_price, open_price=stockDo.open_price, last_price=stockDo.last_price,
                            max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, ma_five=calc_MA(stock_price, 5),
                            ma_ten=calc_MA(stock_price, 10), ma_twenty=ma_twenty, qrr=round(stockDo.volumn / average_volumn, 2), emas=macd['emas'],
                            emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'], fund=0.0,
                            trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'], turnover_rate=stockDo.turnover_rate,
                            boll_up=round(boll_up, 2), boll_low=round(boll_low, 2))
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
        average_volumn = (sum(volume_list) / volume_len) * (real_trade_time / 240)
        average_volumn = average_volumn if average_volumn > 0 else stockDo.volumn
        ma_twenty = calc_MA(stock_price, 20)
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        trix = calc_trix(stockDo.current_price, trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
        boll_up, boll_low = bollinger_bands(stock_price[:20], ma_twenty)
        await Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                            max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, last_price=stockDo.last_price, fund=0.0,
                            ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=ma_twenty, qrr=round(stockDo.volumn / average_volumn, 2),
                            emas=macd['emas'], emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], trix_ema_one=trix['ema1'],
                            trix_ema_two=trix['ema2'], trix_ema_three=trix['ema3'], trix=trix['trix'], trma=trix['trma'], turnover_rate=stockDo.turnover_rate,
                            boll_up=round(boll_up, 2), boll_low=round(boll_low, 2))


async def setAvailableStock():
    tool = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            total_cnt = await Stock.query().equal(running=1).count()
            total_batch = int((total_cnt + BATCH_SIZE - 1) / BATCH_SIZE)
            one_batch_size = int(BATCH_SIZE / All_STOCK_DATA_SIZE)
            page = 0
            while page < total_batch:
                offset = page * BATCH_SIZE
                stockList = []
                stockInfo = await Stock.query().equal(running=1).order_by(Stock.create_time.asc()).offset(offset).limit(BATCH_SIZE).all()
                for s in stockInfo:
                    stockList.append({s.code: s.name, f'{s.code}count': 1})
                random.shuffle(stockList)
                for i in range(0, len(stockList), one_batch_size):
                    d = stockList[i: i + one_batch_size]
                    await queryTask.put(d)
                page += 1
                logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次, 数量 {len(stockList)}...")
                await asyncio.sleep(BATCH_INTERVAL)
        except:
            logger.error(traceback.format_exc())


async def getStockFromTencentReal(a):
    while True:
        try:
            datas = None
            datas = await recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            res = await http.get(f"https://qt.gtimg.cn/q={stockCode}", headers=headers)
            if res.status_code == 200:
                res_list = res.text.split(';')
                minute = time.strftime("%H:%M")
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
                            logger.info(f"Tencent(Real) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(int(stockInfo[6]))
                        stockDo.max_price = float(stockInfo[33])
                        stockDo.min_price = float(stockInfo[34])
                        stockDo.turnover_rate = float(stockInfo[38])
                        stockDo.day = stockInfo[30][:8]
                        await MinuteK.create(code=stockDo.code, day=stockDo.day, minute=minute, volume=stockDo.volumn, price=stockDo.current_price)
                        now = datetime.now().time()
                        save_time = datetime.strptime("14:49:00", "%H:%M:%S").time()
                        if now <= save_time:
                            await saveStockInfo(stockDo)
                        logger.info(f"Tencent(Real): {stockDo}")
                    except:
                        logger.error(f"Tencent(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                if len(error_list) > 0:
                    await recommendTask.put(error_list)
                    await asyncio.sleep(2)
            else:
                logger.error(f"Tencent(Real) - 请求未正常返回... {datas}")
                await recommendTask.put(datas)
                await asyncio.sleep(2)
            error_list = []
        except:
            logger.error(f"Tencent(Real) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await recommendTask.put(datas)
            await asyncio.sleep(2)
        finally:
            if datas: recommendTask.task_done()


async def getStockFromXueQiuReal(a):
    while True:
        try:
            datas = None
            datas = await recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            res = await http.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                minute = time.strftime("%H:%M")
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
                                logger.info(f"XueQiu(Real) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.volumn = int(s['volume'] / 100)
                            stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                            await MinuteK.create(code=stockDo.code, day=stockDo.day, minute=minute, volume=stockDo.volumn, price=stockDo.current_price)
                            now = datetime.now().time()
                            save_time = datetime.strptime("14:49:00", "%H:%M:%S").time()
                            if now <= save_time:
                                await saveStockInfo(stockDo)
                            logger.info(f"XueQiu(Real): {stockDo}")
                        except:
                            logger.error(f"XueQiu(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                            logger.error(traceback.format_exc())
                            key_stock = f"{stockDo.code}count"
                            if dataCount[key_stock] < 5:
                                error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                else:
                    logger.error(f"XueQiu(Real) - 请求未正常返回...响应值: {res_json}")
                    await recommendTask.put(datas)
                    await asyncio.sleep(2)
                if len(error_list) > 0:
                    await recommendTask.put(error_list)
                    await asyncio.sleep(2)
            else:
                logger.error(f"XueQiu(Real) - 请求未正常返回... {datas}")
                await recommendTask.put(datas)
                await asyncio.sleep(2)
            error_list = []
        except:
            logger.error(f"XueQiu(Real) - 出现异常...... {res.text}")
            logger.error(traceback.format_exc())
            if datas: await recommendTask.put(datas)
            await asyncio.sleep(2)
        finally:
            if datas: recommendTask.task_done()


async def getStockFromSinaReal(a):
    while True:
        try:
            datas = None
            datas = await recommendTask.get()
            if datas == 'end': break
            error_list = []
            dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
            dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
            stockCode = generateStockCode(dataDict)
            stockCode_i = generateStockCodeForSina(dataDict)
            h = {
                'Referer': 'https://finance.sina.com.cn',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
            }
            res = await http.get(f"http://hq.sinajs.cn/list={stockCode},{stockCode_i}", headers=h)
            if res.status_code == 200:
                res_list = res.text.split(';')
                minute = time.strftime("%H:%M")
                data_dict = {}
                for line in res_list:
                    try:
                        if len(line.strip()) < 30:
                            continue
                        stockInfo = line.strip().split(',')
                        code = stockInfo[0].split('=')[0].split('_')[2][2:].strip()
                        if code in data_dict:
                            stockDo = data_dict[code]
                            if f"{code}_i" in line:
                                if float(stockInfo[8]) < 0.5:
                                    logger.info(f"Sina({a}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                    continue
                                stockDo.turnover_rate = float(stockInfo[8])
                            else:
                                stockDo.name = stockInfo[0].split('"')[-1]
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
                            data_dict.update({code: stockDo})
                        else:
                            stockDo = StockModelDo()
                            stockDo.code = code
                            if f"{code}_i" in line:
                                if float(stockInfo[8]) < 0.5:
                                    logger.info(f"Sina({a}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                    continue
                                stockDo.turnover_rate = float(stockInfo[8])
                            else:
                                stockDo.name = stockInfo[0].split('"')[-1]
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
                            data_dict.update({code: stockDo})
                    except:
                        logger.error(f"Sina(Real) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {line}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                for _, v in data_dict.items():
                    if v.volumn > 0 and v.turnover_rate > 0:
                        v.turnover_rate = round(v.volumn / v.turnover_rate, 2)
                        await MinuteK.create(code=v.code, day=v.day, minute=minute, volume=v.volumn, price=v.current_price)
                        now = datetime.now().time()
                        save_time = datetime.strptime("14:49:00", "%H:%M:%S").time()
                        if now <= save_time:
                            await saveStockInfo(v)
                        logger.info(f"Sina(Real): {v}")
                if len(error_list) > 0:
                    await recommendTask.put(error_list)
                    await asyncio.sleep(2)
            else:
                logger.error(f"Sina(Real) - 请求未正常返回... {datas}")
                await recommendTask.put(datas)
                await asyncio.sleep(2)
            error_list = []
        except:
            logger.error(f"Sina(Real) - 出现异常...... {datas}")
            logger.error(traceback.format_exc())
            if datas: await recommendTask.put(datas)
            await asyncio.sleep(2)
        finally:
            if datas: recommendTask.task_done()


async def queryRecommendStockData():
    now = datetime.now().time()
    start_time = datetime.strptime("11:30:00", "%H:%M:%S").time()
    end_time = datetime.strptime("13:00:00", "%H:%M:%S").time()
    if start_time <= now <= end_time:
        logger.info("中午休市, 暂不执行...")
    else:
        try:
            stockList = []
            hasList = []
            stockInfo = await Recommend.query().is_null('last_five_price').all()
            myStock = await Stock.query().like(filter="myself").all()
            for s in stockInfo:
                hasList.append(s.code)
                stockList.append({s.code: s.name, f'{s.code}count': 1})
            for s in myStock:
                if s.code in hasList:
                    continue
                stockList.append({s.code: s.name, f'{s.code}count': 1})
            random.shuffle(stockList)
            half_num = int(len(stockList) / 2)
            await recommendTask.put(stockList[: half_num])
            await recommendTask.put(stockList[half_num:])
        except:
            logger.error(traceback.format_exc())


async def startSelectStock():
    tool = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            try:
                stockInfos = await getStockOrderByFundFromDongCai()
            except:
                logger.error(traceback.format_exc())
                stockInfos = await getStockOrderByFundFromTencent()
            stockList = []
            for s in stockInfos:
                try:
                    s_info = await Stock.get_one(s['code'])
                    if s_info.running == 1:
                        stockList.append({s['code']: s['name'], f'{s['code']}count': 1})
                except:
                    logger.error(traceback.format_exc())
            index = 0
            one_batch_size = int(BATCH_SIZE / All_STOCK_DATA_SIZE)
            for i in range(0, len(stockList), one_batch_size):
                d = stockList[i: i + one_batch_size]
                await queryTask.put(d)
                index += 1
                if index % All_STOCK_DATA_SIZE == 0:
                    logger.info(f"正在更新选股的数据，当前是第 {index} 批，总数 {len(stockList)} 个")
                    await asyncio.sleep(8)
            current_day = time.strftime("%Y%m%d")
            try:
                _ = await Tools.get_one("openDoor2")
                await Tools.update("openDoor2", value=current_day)
            except NoResultFound:
                await Tools.create(key="openDoor2", value=current_day)
            await getStockTopic()
        except:
            logger.error(traceback.format_exc())


async def checkTradeDay():
    while True:
        today = datetime.today()
        if today.weekday() >= 5:
            logger.info("周末未开市，跳过...")
            break
        try:
            current_day = time.strftime("%Y%m%d")
            res = await http.get("https://qt.gtimg.cn/q=sh600519,sz000001", headers=headers)
            if res.status_code == 200:
                if current_day in res.text:
                    res_list = res.text.split(';')
                    v1 = res_list[0].split('~')[6]
                    v2 = res_list[1].split('~')[6]
                    if int(v1) > 2 or int(v2) > 2:
                        scheduler.add_job(queryRecommendStockData, "interval", minutes=1, next_run_time=datetime.now() + timedelta(seconds=7), id=running_job_id)
                        try:
                            _ = await Tools.get_one("openDoor")
                            await Tools.update("openDoor", value=current_day)
                        except NoResultFound:
                            await Tools.create(key="openDoor", value=current_day)
                        logger.info("查询任务已启动, 任务: queryRecommendStockData")
                        break
                    else:
                        logger.info("未开市, 跳过1...")
                        break
                else:
                    logger.info("未开市, 跳过...")
                    break
            else:
                logger.error(f"获取 SH600519 数据异常，状态码: {res.status_code}")
        except:
            logger.error(traceback.format_exc())
        await asyncio.sleep(3)


async def calcStockMetric():
    try:
        tool = await Tools.get_one("openDoor")
        current_day = tool.value
        if current_day == time.strftime("%Y%m%d"):
            stock_metric = []   # 非买入信号的策略选股
            day = ''
            stockInfos = await Stock.query().equal(running=1).all()
            for s in stockInfos:
                try:
                    stockList = await Detail.query().equal(code=s.code).order_by(Detail.day.desc()).limit(5).all()
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
                stock_data_list = await Detail.query().equal(code=stock_code_id).order_by(Detail.day.desc()).limit(6).all()
                stockData = [AiModelStockList.from_orm_format(f).model_dump() for f in stock_data_list]
                stockData.reverse()
                try:
                    fflow = await getStockZhuLiFundFromDongCai(stock_code_id)
                except:
                    logger.error(traceback.format_exc())
                    try:
                        fflow = await getStockZhuLiFundFromTencent(stock_code_id)
                    except:
                        logger.error(traceback.format_exc())
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取数据异常', f"获取 {stock_code_id} 的资金流向数据异常～")
                        fflow = 0.0
                stockData[-1]['fund'] = fflow
                # 请求大模型
                try:
                    # stock_dict = queryGemini(json.dumps(stockData), API_URL, AI_MODEL, AUTH_CODE)
                    stock_dict = await queryOpenAi(json.dumps(stockData), OPENAI_URL, OPENAI_MODEL, OPENAI_KEY)
                    logger.info(f"AI-model: {stock_dict}")
                    if stock_dict and stock_dict[0][stock_code_id]['buy']:
                        recommend_stocks = await Recommend.query().equal(code=stock_code_id).is_null('last_five_price').all()
                        if len(recommend_stocks) < 1:   # 如果已经推荐过了，就跳过，否则再次推荐
                            await Recommend.create(code=stock_code_id, name=ai_model_list[i]['name'], price=0.01)
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


async def selectStockMetric():
    global current_topic
    try:
        tool = await Tools.get_one("openDoor")
        current_day = tool.value
        if current_day == time.strftime("%Y%m%d"):
            stock_metric = []   # 非买入信号的策略选股
            day = ''
            stockInfos = await Detail.query().equal(day=current_day).all()
            for s in stockInfos:
                try:
                    stockList = await Detail.query().equal(code=s.code).order_by(Detail.day.desc()).limit(5).all()
                    if (stockList[0].qrr < 1.2 or stockList[0].qrr > 6):
                        continue
                    # s_info = await Stock.get_one(s.code)
                    # concept_res = [c for c in current_topic if c in s_info.concept or c in s_info.industry]
                    # if len(concept_res) < 1:
                    #     continue
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
            ai_model_list = stock_metric[: 500]
            has_index = 0
            for i in range(len(ai_model_list)):
                logger.info(f"Select stocks: {ai_model_list[i]}")
                stock_code_id = ai_model_list[i]['code']
                da_dan = await getStockDaDanFromTencent(stock_code_id)
                if 'msg' in da_dan:
                    logger.error(da_dan['msg'])
                    da_dan = await getStockDaDanFromSina(stock_code_id)
                    if 'msg' in da_dan:
                        logger.error(da_dan['msg'])
                        await asyncio.sleep(2)
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取买卖盘面异常', f"获取 {stock_code_id} 的买卖盘面数据异常～")
                        continue
                if 'msg' not in da_dan:
                    if da_dan['b'] > da_dan['s'] and da_dan['m'] < da_dan['s']:
                        pass
                    else:
                        logger.error(f"DaDan Stock - {stock_code_id} - no meet 60% / 30% / 10% 这样的数值, - {da_dan}")
                        await asyncio.sleep(2)
                        continue
                stock_data_list = await Detail.query().equal(code=stock_code_id).order_by(Detail.day.desc()).limit(6).all()
                stock_data_list.reverse()
                stockData = detail2List(stock_data_list)
                try:
                    fflow = await getStockZhuLiFundFromDongCai(stock_code_id)
                except:
                    logger.error(traceback.format_exc())
                    try:
                        fflow = await getStockZhuLiFundFromTencent(stock_code_id)
                    except:
                        logger.error(traceback.format_exc())
                        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '获取数据异常', f"获取 {stock_code_id} 的资金流向数据异常～")
                        fflow = 0.0
                stockData['fund'][-1] = fflow
                # 请求大模型
                try:
                    # s_info = await Stock.get_one(stock_code_id)
                    # topic_info = await Tools.get_one(current_day)
                    # stockData['hot_topic'] = topic_info.value
                    # stockData['industry'] = s_info.industry
                    # stockData['concept'] = s_info.concept
                    reason = f"主动性买盘: {da_dan['b']}%, 主动性卖盘: {da_dan['s']}%, 中性盘: {da_dan['m']}%\n\n"
                    stock_dict = await queryOpenAi(json.dumps(stockData), OPENAI_URL, OPENAI_MODEL, OPENAI_KEY)
                    logger.info(f"AI-model-OpenAI: {stock_dict}")
                    if stock_dict and stock_dict['buy']:
                        recommend_stocks = await Recommend.query().equal(code=stock_code_id).is_null('last_three_price').all()
                        if len(recommend_stocks) < 1:   # 如果已经推荐过了，就跳过，否则再次推荐
                            has_index += 1
                            reason = reason + f"ChatGPT: {stock_dict['reason']}"
                            stock_dict = await queryGemini(json.dumps(stockData), API_URL, AI_MODEL, AI_MODEL25, AUTH_CODE)
                            logger.info(f"AI-model-Gemini: {stock_dict}")
                            reason = reason + f"\n\nGemini: {stock_dict['reason']}"
                            if stock_dict and stock_dict['buy']:
                                await Recommend.create(code=stock_code_id, name=ai_model_list[i]['name'], price=0.01, content=reason)
                                send_msg.append(f"{stock_code_id} - {ai_model_list[i]['name']}, 当前价: {ai_model_list[i]['price']}")
                            if has_index > 9:
                                break
                        else:
                            logger.info(f"Has been recommended stock - {stock_code_id} - {ai_model_list[i]['name']}")
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


async def saveStockFund(day: str, code: str, fund: float):
    s = await Detail.get((code, day))
    if s:
        await Detail.update((code, day), fund=fund)
        logger.info(f"Update Stock Fund: {code} - {fund}")


async def updateStockFund(a=1):
    try:
        tool = await Tools.get_one("openDoor")
        day = tool.value
        if day == time.strftime("%Y%m%d"):
            h = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
            total_page = 100
            if a == 1:
                try:
                    logger.info("使用东方财富网更新主力资金～")
                    current_time = int(time.time() * 1000)
                    url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
                    res = await http.get(url, headers=h)
                    res_json = json.loads(res.text.split('(')[1].split(')')[0])
                    total_page = int((res_json['data']['total'] + 49) / 50)
                    for k in res_json['data']['diff']:
                        code = k['12']
                        fund = round(k['f62'] / 10000, 2)
                        await saveStockFund(day, code, fund)
                    for p in range(1, total_page):
                        if p % 5 == 0:
                            current_time = int(time.time() * 1000)
                        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn={p + 1}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
                        res = await http.get(url, headers=h)
                        res_json = json.loads(res.text.split('(')[1].split(')')[0])
                        for k in res_json['data']['diff']:
                            code = k['12']
                            fund = round(k['f62'] / 10000, 2)
                            await saveStockFund(day, code, fund)
                        await asyncio.sleep(5)
                except:
                    logger.error(traceback.format_exc())
                    await updateStockFund(2)
            else:
                try:
                    logger.info("使用腾讯财经更新主力资金～")
                    page_size = 50
                    url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset=0&count={page_size}'
                    res = await http.get(url, headers=h)
                    res_json = json.loads(res.text)
                    total_page = int((res_json['data']['total'] + 49) / 50)
                    for k in res_json['data']['rank_list']:
                        code = k['code'][2:]
                        fund = float(k['zljlr'])
                        await saveStockFund(day, code, fund)
                    for p in range(1, total_page):
                        url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset={page_size * p}&count={page_size}'
                        res = await http.get(url, headers=h)
                        res_json = json.loads(res.text)
                        for k in res_json['data']['rank_list']:
                            code = k['code'][2:]
                            fund = float(k['zljlr'])
                            await saveStockFund(day, code, fund)
                        await asyncio.sleep(5)
                except:
                    logger.error(traceback.format_exc())
                    sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, "获取所有股票的主力资金净流入数据失败")
            await asyncio.sleep(5)
            await checkUpdateStockFund()  # 更新漏网数据，如果有
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


async def checkUpdateStockFund():
    try:
        tool = await Tools.get_one("openDoor")
        day = tool.value
        stocks = await Detail.query().equal(day=day).less_equal(fund=0.01).greater_equal(fund=-0.01).all()
        for s in stocks:
            try:
                fund = await getStockZhuLiFundFromDongCai(s.code)
            except:
                fund = await getStockZhuLiFundFromTencent(s.code)
            await Detail.update((s.code, s.day), fund=fund)
            logger.info(f"ReUpdate Stock Fund: {s.code} - {fund}")
            await asyncio.sleep(5)
    except:
        logger.error(traceback.format_exc())


async def updateRecommendPrice():
    try:
        tool = await Tools.get_one("openDoor")
        new_day = tool.value
        if new_day == time.strftime("%Y%m%d"):
            # 更新最新收盘价
            try:
                new_stocks = await Recommend.query().less_equal(price=0.02).all()
                for r in new_stocks:
                    s = await Detail.get_one((r.code, new_day))
                    await Recommend.update(r.id, price=s.current_price)
            except:
                logger.error(traceback.format_exc())

            t = time.strftime("%Y-%m-%d") + " 09:00:00"
            recommend_stocks = await Recommend.query().less_equal(create_time=t).is_null('last_five_price').all()
            for r in recommend_stocks:
                try:
                    stockInfo = await Detail.get((r.code, new_day))
                    if stockInfo:
                        price_pct = round((stockInfo.current_price - r.price) / r.price * 100, 2)
                        max_price_pct = round((stockInfo.max_price - r.price) / r.price * 100, 2)
                        min_price_pct = round((stockInfo.min_price - r.price) / r.price * 100, 2)
                        if r.last_one_price is None:
                            await Recommend.update(r.id, last_one_price=price_pct, last_one_high=max_price_pct, last_one_low=min_price_pct)
                        elif r.last_two_price is None:
                            await Recommend.update(r.id, last_two_price=price_pct, last_two_high=max_price_pct, last_two_low=min_price_pct)
                        elif r.last_three_price is None:
                            await Recommend.update(r.id, last_three_price=price_pct, last_three_high=max_price_pct, last_three_low=min_price_pct)
                        elif r.last_four_price is None:
                            await Recommend.update(r.id, last_four_price=price_pct, last_four_high=max_price_pct, last_four_low=min_price_pct)
                        elif r.last_five_price is None:
                            await Recommend.update(r.id, last_five_price=price_pct, last_five_high=max_price_pct, last_five_low=min_price_pct)
                        logger.info(f"update recommend stocks {r.code} - {r.name} price success!")
                except:
                    sendEmail(SENDER_EMAIL, RECEIVER_EMAIL, EMAIL_PASSWORD, "更新推荐股票的价格报错，请抽时间核对")
                    logger.error(traceback.format_exc())
        else:
            logger.info("不在交易时间。。。")
    except:
        logger.error(traceback.format_exc())


async def updateStockBanKuai(ban=0):
    try:
        if ban == 0:
            stockInfo = await Stock.query().equal(running=1).all()
        else:
            stockInfo = await Stock.query().equal(running=1, region="").all()
        for s in stockInfo:
            res = await getStockBanKuaiFromDOngCai(s.code)
            if 'msg' in res:
                await asyncio.sleep(5)
                continue
            await Stock.update(s.code, region=res['region'], industry=res['industry'], concept=res['concept'])
            logger.info(f"Update stock BanKuai {s.code} - {s.name} - {res}")
            await asyncio.sleep(5)
    except:
        logger.error(traceback.format_exc())


async def setAllSHStock():
    tool = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            t = int(time.time() * 1000)
            page = 1
            hh = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'
            }
            res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={page}&pageHelp.pageSize=50&pageHelp.pageNo={page}&pageHelp.endPage={page}&_={t}", headers=hh)
            if res.status_code == 200:
                res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                res_json = json.loads('{' + res_text + '}')
                total_page = res_json['pageHelp']['pageCount']
                resubmit_list = []
                for p in range(total_page):
                    try:
                        t = int(time.time() * 1000)
                        res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={p + 1}&pageHelp.pageSize=50&pageHelp.pageNo={p + 1}&pageHelp.endPage={p + 1}&_={t}", headers=hh)
                        if res.status_code == 200:
                            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                            res_json = json.loads('{' + res_text + '}')
                            stock_list = res_json['pageHelp']['data']
                            for s in stock_list:
                                code = s['A_STOCK_CODE']
                                name = s['COMPANY_ABBR']
                                if code.startswith("68"):
                                    continue
                                try:
                                    s = await Stock.get_one(code)
                                    is_running = s.running
                                    if ('ST' in name.upper() or '退' in name) and s.running == 1:
                                        if s.filter and 'myself' in s.filter:
                                            continue
                                        await Stock.update(s.code, running=0, name=name)
                                        logger.info(f"股票 {s.name} - {s.code}  | {name} - {code} 处于退市状态, 忽略掉...")
                                        continue
                                    if 'ST' in s.name.upper() and 'ST' not in name.upper() and '退' not in name:
                                        is_running = min(getStockType(code), 1)
                                        await Stock.update(s.code, running=is_running, name=name)
                                        logger.info(f"股票 {s.name} - {s.code}  | {name} - {code} 重新上市, 继续处理...")
                                        resubmit_list.append(f"{name} - {code}")
                                        await initStockData(code, name, logger)
                                        continue
                                    await Stock.update(s.code, name=name)
                                except NoResultFound:
                                    is_running = getStockType(code)
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        await Stock.create(code=code, name=name, running=is_running, region="", industry="", concept="", filter="")
                                        logger.info(f"股票 {name} - {code}  | {name} - {code} 添加成功, 状态是 {is_running} ...")
                                except:
                                    logger.error(traceback.format_exc())
                        else:
                            logger.error('数据更新异常')
                    except:
                        logger.error(traceback.format_exc())
                        logger.error("请求SH数据异常...")
                    logger.info(f"正在处理SH第 {p + 1} 页...")
                    await asyncio.sleep(6)
                await updateStockBanKuai(ban=1)
                if (len(resubmit_list) > 0):
                    sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '股票重新上市', f"{','.join(resubmit_list)}，请检查数据～")
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


async def setAllSZStock():
    tool = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            t = int(time.time() * 1000)
            page = 1
            hh = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'host': 'www.szse.cn', 'referer': 'https://www.szse.cn/market/product/stock/list/index.html', 'content-type': 'application/json'
            }
            res = await http.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={page}&random=0.574{t}", headers=hh)
            if res.status_code == 200:
                res_json = json.loads(res.text)[0]
                total_page = res_json['metadata']['pagecount']
                resubmit_list = []
                for p in range(total_page):
                    try:
                        t = int(time.time() * 1000)
                        res = await http.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={p + 1}&random=0.574{t}", headers=hh)
                        if res.status_code == 200:
                            res_json = json.loads(res.text)[0]
                            stock_list = res_json['data']
                            for s in stock_list:
                                code = s['agdm']
                                name = s['agjc'].split('<u>')[-1].split('</u>')[0]
                                if code.startswith("68"):
                                    continue
                                try:
                                    s = await Stock.get_one(code)
                                    is_running = s.running
                                    if ('ST' in name.upper() or '退' in name) and s.running == 1:
                                        if s.filter and 'myself' in s.filter:
                                            continue
                                        await Stock.update(s.code, running=0, name=name)
                                        logger.info(f"股票 {s.name} - {s.code} | {name} - {code} 处于退市状态, 忽略掉...")
                                        continue
                                    if 'ST' in s.name.upper() and 'ST' not in name.upper() and '退' not in name:
                                        await Stock.update(s.code, running=1, name=name)
                                        logger.info(f"股票 {s.name} - {s.code} | {name} - {code} 重新上市, 继续处理...")
                                        resubmit_list.append(f"{name} - {code}")
                                        await initStockData(code, name, logger)
                                        continue
                                    await Stock.update(s.code, name=name)
                                except NoResultFound:
                                    is_running = getStockType(code)
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        await Stock.create(code=code, name=name, running=is_running, region="", industry="", concept="", filter="")
                                        logger.info(f"股票 {name} - {code} | {name} - {code} 添加成功, 状态是 {is_running} ...")
                                except:
                                    logger.error(traceback.format_exc())
                        else:
                            logger.error('数据更新异常')
                    except:
                        logger.error(traceback.format_exc())
                        logger.error("请求SZ数据异常...")
                    logger.info(f"正在处理SZ第 {p + 1} 页...")
                    await asyncio.sleep(6)
                await updateStockBanKuai(ban=1)
                if (len(resubmit_list) > 0):
                    sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '股票重新上市', f"{','.join(resubmit_list)}，请检查数据～")
                tool = await Tools.get_one("openDoor")
                current_day = tool.value
                if current_day == time.strftime("%Y%m%d"):
                    await getStockTopic()
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


async def getStockTopic():
    try:
        global current_topic
        tool = await Tools.get_one("openDoor")
        current_day = tool.value
        res = await webSearchTopic(API_URL, AUTH_CODE)
        file_path = os.path.join(FILE_PATH, f"{current_day}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(res)
        data = res.split("热点题材逻辑")[0].strip().split("点题材汇总")[1].strip().split("\n")[0]
        res_list = [r.replace('。', '').strip() for r in data.split(',')]
        try:
            tool = await Tools.get_one(current_day)
            await Tools.update(tool.key, value=',' .join(res_list))
        except NoResultFound:
            await Tools.create(key=current_day, value=',' .join(res_list))
        logger.info(f"Current hot topic is {res}")
        current_topic = [normalize_topic(r) for r in res_list]
        logger.info(f"Normalized topic: {current_topic}")
    except:
        logger.error(traceback.format_exc())
        logger.error("数据更新异常...")


async def stopTask():
    if scheduler.get_job(running_job_id):
        scheduler.remove_job(running_job_id)
        logger.info("查询任务已停止...")
    else:
        logger.info("查询任务不存在或已结束...")


async def clearStockData():
    t = time.strftime("%Y-%m-%d") + " 14:40:00"
    tool = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        stockInfos = await Stock.query().like(filter='myself').all()
        for s in stockInfos:
            await MinuteK.query().equal(code=s.code).less_equal(create_time=t).delete()
            logger.info(f"delete my stock data success, {s.code} - {s.name}")
        await getStockTopic()


async def main():
    scheduler.add_job(checkTradeDay, 'cron', hour=9, minute=30, second=50)    # 启动任务
    scheduler.add_job(setAllSHStock, 'cron', hour=12, minute=5, second=20)    # 中午更新股票信息
    scheduler.add_job(setAllSZStock, 'cron', hour=12, minute=0, second=20)    # 中午更新股票信息
    scheduler.add_job(startSelectStock, 'cron', hour=14, minute=49, second=1, misfire_grace_time=10)  # 开始选股
    # scheduler.add_job(calcStockMetric, 'cron', hour=14, minute=50, second=10)    # 计算推荐股票
    scheduler.add_job(selectStockMetric, 'cron', hour=14, minute=50, second=10, misfire_grace_time=10)    # 计算推荐股票
    scheduler.add_job(stopTask, 'cron', hour=15, minute=1, second=20, misfire_grace_time=10)   # 停止任务
    scheduler.add_job(setAvailableStock, 'cron', hour=15, minute=28, second=20)  # 收盘后更新数据
    scheduler.add_job(updateStockFund, 'cron', hour=15, minute=48, second=20, args=[1], misfire_grace_time=10)    # 更新主力流入数据
    scheduler.add_job(updateRecommendPrice, 'cron', hour=15, minute=52, second=50, misfire_grace_time=10)    # 更新推荐股票的价格
    scheduler.add_job(clearStockData, 'cron', hour=20, minute=20, second=20, misfire_grace_time=10)    # 删除数据
    scheduler.add_job(updateStockBanKuai, 'cron', day_of_week='sat', hour=0, minute=0, second=0)    # 更新股票行业、概念等数据
    scheduler.start()
    await asyncio.sleep(2)

    worker_task = asyncio.create_task(write_worker())
    asyncio.create_task(getStockFromTencent('base'))
    asyncio.create_task(queryStockTencentFromHttp(HTTP_HOST1))
    asyncio.create_task(queryStockXueQiuFromHttp(HTTP_HOST1))
    asyncio.create_task(getStockFromTencent('proxy'))
    asyncio.create_task(getStockFromXueQiu('proxy'))
    asyncio.create_task(getStockFromTencentReal('base'))
    asyncio.create_task(getStockFromSinaReal('base'))

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
    await writer_queue.join()
    worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await worker_task


if __name__ == '__main__':
    asyncio.run(main())
