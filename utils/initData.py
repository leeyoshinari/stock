#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import time
import math
import random
import traceback
from typing import List
from logging import Logger
from utils.model import StockModelDo
from utils.database import Detail
from utils.http_client import http
from utils.results import getStockRegion, getStockRegionNum
from settings import TUSHARE_API_KEY


headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def calc_MA(data: List, window: int, digit: int = 2) -> float:
    return round(sum(data[-window:]) / len(data[-window:]), digit)


def calc_ema(current_price, previous_ema, period) -> float:
    alpha = 2 / (period + 1)
    return (current_price - previous_ema) * alpha + previous_ema


def calc_macd(current_price, pre_ema_12, pre_ema_26, pre_dea) -> List[float]:
    ema12 = calc_ema(current_price, pre_ema_12, 12)
    ema26 = calc_ema(current_price, pre_ema_26, 26)
    dif = ema12 - ema26
    dma = calc_ema(dif, pre_dea, 9)
    return {'dif': dif, 'dma': dma, 'ema12': ema12, 'ema26': ema26}


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


async def getQfqFactorFromSina(code: str, logger: Logger) -> list[dict]:
    try:
        h = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        res = await http.get(f"https://finance.sina.com.cn/realstock/company/{getStockRegion(code)}{code}/qfq.js", headers=h)
        if res.status_code == 200:
            res_text = res.text.replace('[{', 'q1a2z3').replace('}]', 'q1a2z3').split('q1a2z3')[1]
            datas = json.loads('[{' + res_text + '}]')
            logger.info(f"{code} - 前复权因子: {datas}")
            return datas
    except:
        logger.error(traceback.format_exc())


async def getStockFromSohu(datas: List, factor_list: list[dict], logger: Logger):
    ''' datas = [{'002868': '*ST绿康'}] '''
    start_date = "20250801"
    current_day = time.strftime("%Y%m%d")
    try:
        dataDict = {k: v for d in datas for k, v in d.items()}
        s = []
        for r in list(dataDict.keys()):
            s.append(f"cn_{r}")
        s_list = ",".join(s)
        pre_price = 0
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
                        factor = float(next((d['f'] for d in factor_list if r[0] >= d['d']), 1.0))
                        stockDo.current_price = float(r[2]) / factor
                        stockDo.open_price = float(r[1]) / factor
                        stockDo.volume = int(r[7])
                        stockDo.last_price = pre_price
                        stockDo.max_price = float(r[6]) / factor
                        stockDo.min_price = float(r[5]) / factor
                        try:
                            _ = await Detail.get_one((stockDo.code, stockDo.day))
                            await saveStockInfo(stockDo, flag='update')
                        except:
                            await saveStockInfo(stockDo, flag='create')
                            logger.info(f"Sohu: factor: {factor}, {stockDo}")
                        pre_price = stockDo.current_price
                except:
                    logger.error(f"Sohu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {d}")
                    logger.error(traceback.format_exc())
        else:
            logger.error("Sohu - 请求未正常返回...")
    except:
        logger.error("Sohu - 出现异常......")
        logger.error(traceback.format_exc())


async def saveStockInfo(stockDo: StockModelDo, flag: str = 'create'):
    stock_price_obj = await Detail.query().select('current_price').equal(code=stockDo.code).order_by(Detail.day.asc()).all()
    stock_price = [r[0] for r in stock_price_obj]
    stock_price.append(stockDo.current_price)
    digit = 2
    if stockDo.code.startswith('1') or stockDo.code.startswith('5'):
        digit = 3
    up, dn = bollinger_bands(stock_price, calc_MA(stock_price, 20, digit))
    if flag == 'create':
        await Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=round(stockDo.current_price, digit), open_price=round(stockDo.open_price, digit),
                            max_price=round(stockDo.max_price, digit), min_price=round(stockDo.min_price, digit), volume=stockDo.volume, last_price=round(stockDo.last_price, digit), boll_up=round(up, digit),
                            ma_five=calc_MA(stock_price, 5, digit), ma_ten=calc_MA(stock_price, 10, digit), ma_twenty=calc_MA(stock_price, 20, digit), boll_low=round(dn, digit))
    else:
        await Detail.update((stockDo.code, stockDo.day), name=stockDo.name, current_price=round(stockDo.current_price, digit), open_price=round(stockDo.open_price, digit),
                            max_price=round(stockDo.max_price, digit), min_price=round(stockDo.min_price, digit), volume=stockDo.volume, last_price=round(stockDo.last_price, digit), boll_up=round(up, digit),
                            ma_five=calc_MA(stock_price, 5, digit), ma_ten=calc_MA(stock_price, 10, digit), ma_twenty=calc_MA(stock_price, 20, digit), boll_low=round(dn, digit))
    if len(stock_price) > 4:
        stock_volume_obj = await Detail.query().select('volume').equal(code=stockDo.code).order_by(Detail.day.asc()).all()
        stock_volume = [r[0] for r in stock_volume_obj]
        average_volume = sum(stock_volume[-7: -2]) / 5
        await Detail.update((stockDo.code, stockDo.day), qrr=round(stockDo.volume / average_volume, 2))


async def getAllStockData(code: str, factor_list: list[dict], logger: Logger):
    try:
        res = await http.get(f"https://hq.stock.sohu.com/mkline/cn/{code[-3:]}/cn_{code}-10_2.html?_={int(time.time() * 1000)}", headers=headers)
        if res.status_code == 200:
            res_text = res.text[17:-1]
            res_json = json.loads(res_text)
            data_basic = res_json['dataBasic']
            alpha_s = 2.0 / (12 + 1)
            alpha_l = 2.0 / (26 + 1)
            alpha_sig = 2.0 / (9 + 1)
            factor = float(next((d['f'] for d in factor_list if data_basic[-1][0] >= d['d'].replace('-', '')), 1.0))
            ema_s = float(data_basic[-1][2]) / factor
            ema_l = float(data_basic[-1][2]) / factor
            dea = 0
            kdjk = 50
            kdjd = 50
            high_price = []
            low_price = []
            ema1 = float(data_basic[-1][2]) / factor
            # 第一天初始化
            kdjj = 3 * (2.0 * kdjk / 3 + 50 / 3) - 2 * (2.0 * kdjd / 3 + (2.0 * kdjk / 3 + 50 / 3) / 3)
            await Detail.update((code, data_basic[-1][0]), emas=ema1, emal=ema1, dea=dea, kdjk=kdjk, kdjd=kdjd, kdjj=kdjj)
            for item in data_basic[::-1][1:]:
                date_str = item[0]
                factor = float(next((d['f'] for d in factor_list if date_str >= d['d'].replace('-', '')), 1.0))
                price = float(item[2]) / factor
                h_price = float(item[3]) / factor
                l_price = float(item[4]) / factor
                high_price.append(h_price)
                low_price.append(l_price)
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

                if date_str >= '20250901':
                    await Detail.update((code, item[0]), emas=ema_s, emal=ema_l, dea=dea, kdjk=kdjk, kdjd=kdjd, kdjj=kdjj)
                    logger.info(f"{item[0]} - factor: {factor} - diff: {diff} - dea: {dea} - K: {kdjk} - D: {kdjd} - J: {kdjj}")
        else:
            logger.error(f"Update stock MACD/KDJ/TRIX data error - {code}")

    except:
        logger.error(traceback.format_exc())


async def update_stock_turnover_rate(code, logger: Logger):
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


async def getStockFundFlow(code, cookie, logger: Logger):
    '''从东方财富获取资金流向
    https://data.eastmoney.com/zjlx/002149.html
    '''
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
              'host': 'push2his.eastmoney.com', 'origin': 'https://data.eastmoney.com', 'referer': 'https://data.eastmoney.com', 'cookie': cookie}
    try:
        rand = str(int(random.randint(10**17, 10**18 - 1) / 10))
        url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(code)}.{code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=0&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery11230{rand}_{int(time.time() * 1000)}&klt=101&_={int(time.time() * 1000)}'
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
                logger.error(f"Error fund - {code} - {day} - {money}")
                logger.error(traceback.format_exc())
    except:
        logger.error(traceback.format_exc())


async def getStockZhuLiFundFromTencentL5D(code: str, logger: Logger) -> float:
    '''获取腾讯财经当前股票的主力净流入'''
    '''https://gu.qq.com/sz300274/gp'''
    try:
        header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
        url = f'https://proxy.finance.qq.com/cgi/cgi-bin/fundflow/hsfundtab?code={getStockRegion(code)}{code}&type=fiveDayFundFlow,todayFundFlow&klineNeedDay=20'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text)
        day_list = res_json['data']['fiveDayFundFlow']['DayMainNetInList']
        for item in day_list:
            day = item['date'].replace('-', '')
            fund = round(float(item['mainNetIn']) / 10000, 2)
            await Detail.update2return((code, day), fund=fund)
            logger.info(f"{code} L5D fund - {day} - {fund}")
    except:
        logger.error(traceback.format_exc())


async def getStockFromTushare(code: str, logger: Logger):
    try:
        header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
                  "Accept": "application/json", "apiKey": TUSHARE_API_KEY}
        url = f"https://data.infoway.io/common/basic/symbols/adjustment_factors?market=CN&beginDay=20251024&endDay=20260930&symbol={code}.{getStockRegion(code).upper()}"
        res = await http.get(url, headers=header)
        if res.status_code == 200:
            logger.info(res.text)
        else:
            logger.error(f"status code is {res.status_code} - {res.text}")
    except:
        logger.error(traceback.format_exc())


async def initStockData(code: str, name: str, logger: Logger):
    factorList: list[dict] = await getQfqFactorFromSina(code, logger)
    await getStockFromSohu([{code: name}], factorList, logger)    # update price and volume
    await getAllStockData(code, factorList, logger)   # update MACD/KDJ
    await update_stock_turnover_rate(code, logger)    # update turnover rate
    await getStockZhuLiFundFromTencentL5D(code, logger)      # update fund
    await Detail.query().equal(code=code).less(day='20250901').delete()
