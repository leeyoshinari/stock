#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

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


BATCH_SIZE = 30
Database.init_db()
queryTask = queue.Queue()
executor = ThreadPoolExecutor(1)
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


def getStockFromSohu():
    start_time = datetime.now() - timedelta(days=360)
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
                  max_price=stockDo.max_price, min_price=stockDo.min_price, volumn=stockDo.volumn, last_price=0,
                  ma_five=calc_MA(stock_price, 5), ma_ten=calc_MA(stock_price, 10), ma_twenty=calc_MA(stock_price, 20))
    if len(stock_price) > 4:
        stock_volumn_obj = Detail.query_fields(columns=['volumn'], code=stockDo.code).order_by(asc(Detail.day)).all()
        stock_volumn = [r[0] for r in stock_volumn_obj]
        average_volumn = sum(stock_volumn[-7: -2]) / 5
        stockObj = Detail.get_one((stockDo.code, stockDo.day))
        Detail.update(stockObj, qrr=round(stockDo.volumn / average_volumn, 2))


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
            time.sleep(10)
        queryTask.put("end")
    except:
        logger.error(traceback.format_exc())


def fixStockQrr():
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            stocks = Detail.query(code=s.code).order_by(asc(Detail.day)).all()
            if len(stocks) < 6:
                continue
            volumn = [stocks[0].volumn, stocks[1].volumn, stocks[2].volumn, stocks[3].volumn, stocks[4].volumn]
            for i in range(5, len(stocks)):
                avg_v = sum(volumn) / 5.0
                Detail.update(stocks[i], qrr=round(stocks[i].volumn / avg_v, 2))
                volumn.append(stocks[i].volumn)
                volumn.pop(0)

            logger.info(f"正在处理第 {s.code} 个...")
    except:
        logger.error(traceback.format_exc())


def fixQrrLastDay():
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            stocks = Detail.query(code=s.code).order_by(desc(Detail.day)).limit(4).all()
            volumn = [stocks[3].volumn, stocks[1].volumn, stocks[2].volumn, stocks[5].volumn, stocks[4].volumn]
            avg_v = sum(volumn) / 5
            Detail.update(stocks[0], qrr=round(stocks[0].volumn / avg_v, 2))
            logger.info(f"正在处理第 {s.code} 个...")
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def fixTencentVolume():
    try:
        stockInfo = Detail.query(day='20250825').order_by(asc(Detail.qrr)).limit(1470).all()
        for s in stockInfo:
            if s.qrr <= 0.06 and s.code not in ['600246', '605255']:
                stocks = Detail.query(code=s.code).order_by(desc(Detail.day)).limit(6).all()
                volumn = [stocks[3].volumn, stocks[1].volumn, stocks[2].volumn, stocks[5].volumn, stocks[4].volumn]
                avg_v = sum(volumn) / 5
                Detail.update(stocks[0], volumn=s.volumn * 100, qrr=round(s.volumn * 100 / avg_v, 2))
            logger.info(f"正在处理第 {s.code} 个...")
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def getAllStockData(code):
    try:
        res = requests.get(f"https://hq.stock.sohu.com/mkline/cn/{code[-3:]}/cn_{code}-10_2.html?_={int(time.time() * 1000)}", headers=headers)
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
                    stock = Detail.get_one((code, item[0]))
                    Detail.update(stock, emas=ema_s, emal=ema_l, dea=dea, kdjk=kdjk, kdjd=kdjd, kdjj=kdjj, trix_ema_one=ema1, trix_ema_two=ema2, trix_ema_three=ema3, trix=trix, trma=trma)
                    logger.info(f"{item[0]} - diff: {diff} - dea: {dea} - K: {kdjk} - D: {kdjd} - J: {kdjj} - TRIX: {trix} - TRMA: {trma}")

    except:
        logger.error(traceback.format_exc())


def initMetricsData():
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            getAllStockData(s.code)
            time.sleep(10)
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def update_turnover_rate():
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            res = requests.get(f"https://q.stock.sohu.com/hisHq?code=cn_{s.code}&start=20250901&end=20251205", headers=headers)
            if res.status_code == 200:
                res_json = json.loads(res.text)
                if len(res_json) < 1:
                    logger.error(f"turnover_rate_error: {s.code} no data")
                    continue
                datas = res_json[0]['hq']
                if len(datas) < 1:
                    logger.error(f"turnover_rate_error: {s.code} no data in hq")
                    continue
                for k in datas:
                    day = k[0].replace('-', '')
                    try:
                        stock = Detail.get_one((s.code, day))
                        tr = float(k[9].replace('%', ''))
                        Detail.update(stock, turnover_rate=tr)
                    except:
                        logger.error(f"turnover_rate_error: {s.code} - {day} is not in table")
                logger.info(f"turnover_rate: {s.code}")
            else:
                logger.error(f"turnover_rate_error: {s.code} request error")
            time.sleep(8)
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def update_stock_turnover_rate(code):
    try:
        res = requests.get(f"https://q.stock.sohu.com/hisHq?code=cn_{code}&start=20250901&end=20251205", headers=headers)
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
                    stock = Detail.get_one((code, day))
                    tr = float(k[9].replace('%', ''))
                    Detail.update(stock, turnover_rate=tr)
                except:
                    logger.error(f"turnover_rate_error: {code} - {day} is not in table")
            logger.info(f"turnover_rate: {code}")
        else:
            logger.error(f"turnover_rate_error: {code} request error")
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def getStockFundFlowFromDongCai():
    '''从东方财富获取资金流向，最近10日'''
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    try:
        stockInfo = Stock.query(running=1).all()
        for s in stockInfo:
            try:
                url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(s.code)}.{s.code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=0&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery1123016147749948325607_{int(time.time() * 1000)}'
                res = requests.get(url, headers=header)
                res_json = json.loads(res.text.split('(')[1].split(')')[0])
                klines = res_json['data']['klines']
                for k in klines:
                    datas = k.split(',')
                    day = datas[0].replace('-', '')
                    if day < '20250831':
                        continue
                    money = round(float(datas[1]) / 10000, 2)
                    try:
                        ss = Detail.get_one((s.code, day))
                        Detail.update(ss, fund=money)
                    except:
                        logger.error(f"Error fund - {s.code}")
                time.sleep(8)
            except:
                logger.error(f"error - {s.code}")
        logger.info("completed!!!!")
    except:
        logger.error(traceback.format_exc())


def getStockFundFlow(code):
    '''从东方财富获取资金流向，最近10日'''
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    try:
        url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(code)}.{code}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=0&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery1123016147749948325607_{int(time.time() * 1000)}'
        res = requests.get(url, headers=header)
        res_json = json.loads(res.text.split('(')[1].split(')')[0])
        klines = res_json['data']['klines']
        for k in klines:
            datas = k.split(',')
            day = datas[0].replace('-', '')
            if day < '20250831':
                continue
            money = round(float(datas[1]) / 10000, 2)
            try:
                ss = Detail.get_one((code, day))
                Detail.update(ss, fund=money)
            except:
                logger.error(f"Error fund - {code}")
    except:
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    s_list = [{'600831': '广电网络'}, {'600603': '广汇物流'}, {'301584': '建发致新'}, {'301656': '联合动力'}]
    # executor.submit(getStockFromSohu)
    # queryTask.put(s_list)
    # queryTask.put("end")
    # s = executor.submit(fixQrrLastDay)
    # scheduler.add_job(setAvailableStock, 'cron', hour=11, minute=5, second=20)
    # time.sleep(2)
    # scheduler.start()
    # PID = os.getpid()
    # with open('pid', 'w', encoding='utf-8') as f:
    #     f.write(str(PID))
    # wait([s])
    # fixMacdData()
    # fixMacdEma()
    # getStocks()
    # getAllStockData('002316')
    # update_stock_turnover_rate('600831')
    # update_turnover_rate()
    # getStockFundFlowFromDongCai()
    getStockFundFlow('002602')
