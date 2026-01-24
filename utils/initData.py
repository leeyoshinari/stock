#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import time
import math
import traceback
from typing import List
from datetime import datetime, timedelta
from utils.model import StockModelDo
from utils.database import Detail
from utils.http_client import http


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def calc_MA(data: List, window: int) -> float:
    return round(sum(data[-window:]) / len(data[-window:]), 2)


def calc_ema(current_price, previous_ema, period) -> float:
    alpha = 2 / (period + 1)
    return (current_price - previous_ema) * alpha + previous_ema


def calc_macd(current_price, pre_ema_12, pre_ema_26, pre_dea) -> List[float]:
    ema12 = calc_ema(current_price, pre_ema_12, 12)
    ema26 = calc_ema(current_price, pre_ema_26, 26)
    dif = ema12 - ema26
    dma = calc_ema(dif, pre_dea, 9)
    return {'dif': dif, 'dma': dma, 'ema12': ema12, 'ema26': ema26}


def getStockRegionNum(code: str) -> str:
    if code.startswith("60") or code.startswith("68"):
        return "1"
    elif code.startswith("00") or code.startswith("30"):
        return "0"
    else:
        return ""


def bollinger_bands(prices, middle, n=20, k=2):
    if len(prices) < n:
        return middle, middle
    window = prices[-n:]
    data_len = len(window)
    variance = sum((p - middle) ** 2 for p in window) / data_len
    std = math.sqrt(variance)
    up = middle + k * std
    dn = middle - k * std
    return up, dn


async def getStockFromSohu(datas: List, logger):
    ''' datas = [{'002868': '*ST绿康'}] '''
    start_time = datetime.now() - timedelta(days=360)
    start_date = start_time.strftime("%Y%m%d")
    current_day = time.strftime("%Y%m%d")
    try:
        dataDict = {k: v for d in datas for k, v in d.items()}
        s = []
        for r in list(dataDict.keys()):
            s.append(f"cn_{r}")
        s_list = ",".join(s)
        res = await http.get(f"https://q.stock.sohu.com/hisHq?code={s_list}&start={start_date}&end={current_day}", headers=headers)
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
                            _ = await Detail.get_one((stockDo.code, stockDo.day))
                            continue
                        except:
                            stockDo.current_price = float(r[2])
                            stockDo.open_price = float(r[1])
                            stockDo.volumn = int(r[7])
                            stockDo.max_price = float(r[6])
                            stockDo.min_price = float(r[5])
                            await saveStockInfo(stockDo)
                            logger.info(f"Sohu: {stockDo}")
                except:
                    logger.error(f"Sohu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {d}")
                    logger.error(traceback.format_exc())
        else:
            logger.error("Sohu - 请求未正常返回...")
    except:
        logger.error("Sohu - 出现异常......")
        logger.error(traceback.format_exc())


async def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj = await Detail.query().select('current_price').equal(code=stockDo.code).order_by(Detail.day.asc()).all()
    stock_price = [r[0] for r in stock_price_obj]
    stock_price.append(stockDo.current_price)
    up, dn = bollinger_bands(stock_price, calc_MA(stock_price, 20))
    await Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                        max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, last_price=0, boll_up=round(up, 2),
                        ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20), boll_low=round(dn, 2))
    if len(stock_price) > 4:
        stock_volumn_obj = await Detail.query().select('volumn').equal(code=stockDo.code).order_by(Detail.day.asc()).all()
        stock_volumn = [r[0] for r in stock_volumn_obj]
        average_volumn = sum(stock_volumn[-7: -2]) / 5
        await Detail.update((stockDo.code, stockDo.day), qrr=round(stockDo.volumn / average_volumn, 2))


async def getAllStockData(code, logger):
    try:
        res = await http.get(f"https://hq.stock.sohu.com/mkline/cn/{code[-3:]}/cn_{code}-10_2.html?_={int(time.time() * 1000)}", headers=headers)
        if res.status_code == 200:
            res_text = res.text[17:-1]
            res_json = json.loads(res_text)
            data_basic = res_json['dataBasic']
            alpha_trix = 2.0 / (12 + 1)
            alpha_s = 2.0 / (12 + 1)
            alpha_l = 2.0 / (26 + 1)
            alpha_sig = 2.0 / (9 + 1)
            ema_s = float(data_basic[-1][2])
            ema_l = float(data_basic[-1][2])
            dea = 0
            kdjk = 50
            kdjd = 50
            high_price = []
            low_price = []
            ema1 = float(data_basic[-1][2])
            ema2 = float(data_basic[-1][2])
            ema3 = float(data_basic[-1][2])
            pre_ema3 = ema3
            trix_list = []
            for item in data_basic[::-1][1:]:
                price = float(item[2])
                high_price.append(float(item[3]))
                low_price.append(float(item[4]))
                if len(high_price) > 9:
                    high_price.pop(0)
                    low_price.pop(0)
                ema_s = alpha_s * price + (1 - alpha_s) * ema_s
                ema_l = alpha_l * price + (1 - alpha_l) * ema_l
                diff = ema_s - ema_l
                dea = alpha_sig * diff + (1 - alpha_sig) * dea

                high_n = max(high_price)
                low_n = min(low_price)
                if high_n == low_n:
                    rsv = 50
                else:
                    rsv = (price - low_n) / (high_n - low_n) * 100
                kdjk = 2.0 * kdjk / 3 + rsv / 3
                kdjd = 2.0 * kdjd / 3 + kdjk / 3
                kdjj = 3 * kdjk - 2 * kdjd

                ema1 = price * alpha_trix + ema1 * (1 - alpha_trix)
                ema2 = ema1 * alpha_trix + ema2 * (1 - alpha_trix)
                ema3 = ema2 * alpha_trix + ema3 * (1 - alpha_trix)
                trix = (ema3 - pre_ema3) / pre_ema3 * 100
                trix_list.append(trix)
                pre_ema3 = ema3
                if len(trix_list) > 9:
                    trix_list.pop(0)
                trma = sum(trix_list) / 9
                if item[0] >= '20250901':
                    await Detail.update((code, item[0]), emas=ema_s, emal=ema_l, dea=dea, kdjk=kdjk, kdjd=kdjd, kdjj=kdjj, trix_ema_one=ema1, trix_ema_two=ema2, trix_ema_three=ema3, trix=trix, trma=trma)
                    logger.info(f"{item[0]} - diff: {diff} - dea: {dea} - K: {kdjk} - D: {kdjd} - J: {kdjj} - TRIX: {trix} - TRMA: {trma}")
        else:
            logger.error(f"Update stock MACD/KDJ/TRIX data error - {code}")

    except:
        logger.error(traceback.format_exc())


async def update_stock_turnover_rate(code, logger):
    try:
        current_day = time.strftime("%Y%m%d")
        res = await http.get(f"https://q.stock.sohu.com/hisHq?code=cn_{code}&start=20250901&end={current_day}", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text)
            if len(res_json) < 1:
                logger.error(f"turnover_rate_error: {code} no data")
            datas = res_json[0]['hq']
            if len(datas) < 1:
                logger.error(f"turnover_rate_error: {code} no data in hq")
            for k in datas:
                day = k[0].replace('-', '')
                try:
                    stock = await Detail.get_one((code, day))
                    tr = float(k[9].replace('%', ''))
                    if stock.turnover_rate is not None and stock.turnover_rate > 0:
                        continue
                    await Detail.update((code, day), turnover_rate=tr)
                    logger.info(f"turnover_rate: {day} - {code} - {tr}")
                except:
                    logger.error(f"turnover_rate_error: {code} - {day} is not in table")
        else:
            logger.error(f"turnover_rate_error: {code} request error")
    except:
        logger.error(traceback.format_exc())


async def getStockFundFlow(code, logger):
    '''从东方财富获取资金流向'''
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    try:
        url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(code)}.{code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=0&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery1123016147749948325607_{int(time.time() * 1000)}'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text.split('(')[1].split(')')[0])
        klines = res_json['data']['klines']
        for k in klines:
            datas = k.split(',')
            day = datas[0].replace('-', '')
            if day < '20250831':
                continue
            money = round(float(datas[1]) / 10000, 2)
            try:
                ss = await Detail.get_one((code, day))
                if ss.fund is not None:
                    continue
                await Detail.update((code, day), fund=money)
                logger.info(f"fund: {day} - {code} - {money}")
            except:
                logger.error(f"Error fund - {code} - {day}")
    except:
        logger.error(traceback.format_exc())


async def initStockData(code: str, name: str, logger):
    await Detail.query().equal(code=code).delete()
    await getStockFromSohu([{code: name}], logger)    # update price and volume
    await getAllStockData(code, logger)   # update MACD/KDJ
    await update_stock_turnover_rate(code, logger)    # update turnover rate
    await getStockFundFlow(code, logger)      # update fund
    await Detail.query().equal(code=code).less(day='20250901').delete()
