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


def getStocks():
    try:
        t = int(time.time() * 1000)
        page = 1
        headers.update({'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'})
        res = requests.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={page}&pageHelp.pageSize=50&pageHelp.pageNo={page}&pageHelp.endPage={page}&_={t}", headers=headers)
        if res.status_code == 200:
            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
            res_json = json.loads('{' + res_text + '}')
            total_page = res_json['pageHelp']['pageCount']
            for p in range(total_page):
                t = int(time.time() * 1000)
                res = requests.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={p + 1}&pageHelp.pageSize=50&pageHelp.pageNo={p + 1}&pageHelp.endPage={p + 1}&_={t}", headers=headers)
                if res.status_code == 200:
                    res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                    res_json = json.loads('{' + res_text + '}')
                    stock_list = res_json['pageHelp']['data']
                    for s in stock_list:
                        logger.info(f"{s['A_STOCK_CODE']} - {s['COMPANY_ABBR']}")
                time.sleep(5)

        headers.update({'host': 'www.szse.cn', 'referer': 'https://www.szse.cn/market/product/stock/list/index.html', 'content-type': 'application/json'})
        res = requests.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={page}&random=0.574{t}", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text)[0]
            total_page = res_json['metadata']['pagecount']
            for p in range(total_page):
                t = int(time.time() * 1000)
                res = requests.get(f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1110&TABKEY=tab1&PAGENO={p + 1}&random=0.574{t}", headers=headers)
                if res.status_code == 200:
                    res_json = json.loads(res.text)[0]
                    stock_list = res_json['data']
                    for s in stock_list:
                        logger.info(f"{s['agdm']} - {s['agjc'].split('<u>')[-1].split('</u>')[0]}")
                time.sleep(5)
    except:
        logger.error(traceback.format_exc())


if __name__ == '__main__':
    s_list = [{'002316': '亚联发展'}]
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
