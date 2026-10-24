#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import json
import time
import random
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
from sqlalchemy.exc import NoResultFound
from settings import BATCH_SIZE, BATCH_INTERVAL, SENDER_EMAIL, EMAIL_PASSWORD, HTTP_HOST_CLOUD, HTTP_HOST_VERCEL, HTTP_HOST_NETLIFY
from utils.model import StockModelDo
from utils.dispatcher import AsyncRoundRobinDispatcher
from utils.scheduler import scheduler
from utils.http_client import http
from utils.send_email import sendEmail
from utils.initData import initStockData
from utils.queryStockHq import getStockHqFromTencent, getStockHqFromSina, getStockHqFromXueQiu
from utils.metric import bollinger_bands, real_traded_minutes
from utils.selectStock import getStockOrderByFundFromSina, getStockOrderByFundFromTencent
from utils.selectStock import getStockZhuLiFundFromTencent, getStockZhuLiFundFromSina, getStockBanKuaiFromDOngCai
from utils.etfData import getEtfInfoFromSH, getEtfInfoFromSZ, getEtfDetailFromDongCai, getHoldStockOfEtfFromTencent
from utils.etfData import getEtfShareFromSH, getEtfShareFromSZ
from utils.database import Stock, Detail, Tools, Capital, ETF, Transaction, TradeType


logger = logging.getLogger(__name__)
All_STOCK_DATA_SIZE = 3
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


alpha_s = 2.0 / (12 + 1)
alpha_l = 2.0 / (26 + 1)
alpha_sig = 2.0 / (9 + 1)


def calc_MA(data: list, window: int, digit: int = 2) -> float:
    return round(sum(data[:window]) / len(data[:window]), digit)


def get_past_date(days_diff: int) -> str:
    """
    根据当前日期和相差天数，计算之前的日期
    :param days_diff: 相差天数
    :return: 之前的日期字符串
    """
    date_format = "%Y%m%d"
    current_date = datetime.now()
    past_date = current_date - timedelta(days=days_diff)
    return past_date.strftime(date_format)


async def getStockFromTencent(host: str, datas: list[dict]) -> list[dict]:
    try:
        result: dict = await getStockHqFromTencent(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorList: list[dict] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorList
    except:
        logger.error(f"Tencent({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        error_list = [{k: (v + 1 if k.endswith('count') else v) for k, v in d.items()} for d in datas]
        return error_list


async def getStockFromXueQiu(host: str, datas: list[dict]) -> list[dict]:
    try:
        result: dict = await getStockHqFromXueQiu(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorList: list[dict] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorList
    except:
        logger.error(f"XueQiu({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        error_list = [{k: (v + 1 if k.endswith('count') else v) for k, v in d.items()} for d in datas]
        return error_list


async def getStockFromSina(host: str, datas: list[dict]) -> list[dict]:
    try:
        result: dict = await getStockHqFromSina(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorList: list[dict] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorList
    except:
        logger.error(f"Sina({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        error_list = [{k: (v + 1 if k.endswith('count') else v) for k, v in d.items()} for d in datas]
        return error_list


async def getEtfFromTencent(host: str, datas: list[dict]) -> list[dict]:
    await asyncio.sleep(random.random())
    try:
        result: dict = await getStockHqFromTencent(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorList: list[dict] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorList
    except:
        logger.error(f"Tencent({host}) - ETF 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        error_list = [{k: (v + 1 if k.endswith('count') else v) for k, v in d.items()} for d in datas]
        return error_list


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


async def saveStockInfo(stockDo: StockModelDo):
    stock_price_obj: list[Detail] = await Detail.query().equal(code=stockDo.code).order_by(Detail.day.desc()).limit(21).all()
    stock_price = [r.current_price for r in stock_price_obj]
    high_price = [r.max_price for r in stock_price_obj]
    low_price = [r.min_price for r in stock_price_obj]
    real_trade_time = real_traded_minutes()
    digit = 2
    if stockDo.code.startswith('1') or stockDo.code.startswith('5'):
        digit = 3
    try:
        _ = await Detail.get_one((stockDo.code, stockDo.day))
        stock_price[0] = stockDo.current_price
        high_price[0] = stockDo.max_price
        low_price[0] = stockDo.min_price
        volume_list = [r.volume for r in stock_price_obj[1: 6]]
        volume_len = min(max(len(volume_list), 1), 5)
        if len(stock_price_obj) > 1:
            emas = stock_price_obj[1].emas
            emal = stock_price_obj[1].emal
            dea = stock_price_obj[1].dea
            kdjk = stock_price_obj[1].kdjk
            kdjd = stock_price_obj[1].kdjd
        else:
            emas = stockDo.current_price
            emal = stockDo.current_price
            dea = 0
            kdjk = 50
            kdjd = 50
        average_volume = (sum(volume_list) / volume_len) * (real_trade_time / 240)
        average_volume = average_volume if average_volume > 0 else stockDo.volume
        ma_twenty = calc_MA(stock_price, 20, digit)
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        boll_up, boll_low = bollinger_bands(stock_price[:20], ma_twenty)
        await Detail.update((stockDo.code, stockDo.day), current_price=stockDo.current_price, open_price=stockDo.open_price, last_price=stockDo.last_price,
                            max_price=stockDo.max_price, min_price=stockDo.min_price, volume=stockDo.volume, ma_five=calc_MA(stock_price, 5, digit),
                            ma_ten=calc_MA(stock_price, 10, digit), ma_twenty=ma_twenty, qrr=round(stockDo.volume / average_volume, 2), emas=macd['emas'],
                            emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], fund=0.0, shares=stockDo.shares, premium=stockDo.premium,
                            turnover_rate=stockDo.turnover_rate, boll_up=round(boll_up, digit), boll_low=round(boll_low, digit))
    except NoResultFound:
        stock_price.insert(0, stockDo.current_price)
        high_price.insert(0, stockDo.max_price)
        low_price.insert(0, stockDo.min_price)
        volume_list = [r.volume for r in stock_price_obj[: 5]]
        volume_len = min(max(len(volume_list), 1), 5)
        emas = stock_price_obj[0].emas if len(stock_price_obj) > 0 else stockDo.current_price
        emal = stock_price_obj[0].emal if len(stock_price_obj) > 0 else stockDo.current_price
        dea = stock_price_obj[0].dea if len(stock_price_obj) > 0 else 0
        kdjk = stock_price_obj[0].kdjk if len(stock_price_obj) > 0 else 50
        kdjd = stock_price_obj[0].kdjd if len(stock_price_obj) > 0 else 50
        average_volume = (sum(volume_list) / volume_len) * (real_trade_time / 240)
        average_volume = average_volume if average_volume > 0 else stockDo.volume
        ma_twenty = calc_MA(stock_price, 20, digit)
        macd = calc_macd(stockDo.current_price, emas, emal, dea)
        kdj = calc_kdj(stockDo.current_price, high_price, low_price, kdjk, kdjd)
        boll_up, boll_low = bollinger_bands(stock_price[:20], ma_twenty)
        await Detail.create(code=stockDo.code, day=stockDo.day, name=stockDo.name, current_price=stockDo.current_price, open_price=stockDo.open_price,
                            max_price=stockDo.max_price, min_price=stockDo.min_price, volume=stockDo.volume, last_price=stockDo.last_price, fund=0.0,
                            ma_five=calc_MA(stock_price, 5, digit), ma_ten=calc_MA(stock_price, 10, digit), ma_twenty=ma_twenty, qrr=round(stockDo.volume / average_volume, 2),
                            emas=macd['emas'], emal=macd['emal'], dea=macd['dea'], kdjk=kdj['k'], kdjd=kdj['d'], kdjj=kdj['j'], shares=stockDo.shares, premium=stockDo.premium,
                            turnover_rate=stockDo.turnover_rate, boll_up=round(boll_up, digit), boll_low=round(boll_low, digit))


async def getStockFromTencentLocal(datas: list[dict]) -> list[dict]:
    return await getStockFromTencent('', datas)


async def getStockFromTencentCloud(datas: list[dict]) -> list[dict]:
    return await getStockFromTencent(HTTP_HOST_CLOUD, datas)


async def getStockFromTencentVercel(datas: list[dict]) -> list[dict]:
    return await getStockFromTencent(HTTP_HOST_VERCEL, datas)


async def getStockFromTencentNetlify(datas: list[dict]) -> list[dict]:
    return await getStockFromTencent(HTTP_HOST_NETLIFY, datas)


async def getStockFromXueQiuLocal(datas: list[dict]) -> list[dict]:
    return await getStockFromXueQiu('', datas)


async def getStockFromXueQiuCloud(datas: list[dict]) -> list[dict]:
    return await getStockFromXueQiu(HTTP_HOST_CLOUD, datas)


async def getStockFromXueQiuVercel(datas: list[dict]) -> list[dict]:
    return await getStockFromXueQiu(HTTP_HOST_VERCEL, datas)


async def getStockFromXueQiuNetlify(datas: list[dict]) -> list[dict]:
    return await getStockFromXueQiu(HTTP_HOST_NETLIFY, datas)


async def getStockFromSinaLocal(datas: list[dict]) -> list[dict]:
    return await getStockFromSina('', datas)


async def getStockFromSinaCloud(datas: list[dict]) -> list[dict]:
    return await getStockFromSina(HTTP_HOST_CLOUD, datas)


async def getStockFromSinaVercel(datas: list[dict]) -> list[dict]:
    return await getStockFromSina(HTTP_HOST_VERCEL, datas)


async def getStockFromSinaNetlify(datas: list[dict]) -> list[dict]:
    return await getStockFromSina(HTTP_HOST_NETLIFY, datas)


async def getEtfFromTencentLocal(datas: list[dict]) -> list[dict]:
    return await getEtfFromTencent('', datas)


async def getEtfFromTencentCloud(datas: list[dict]) -> list[dict]:
    return await getEtfFromTencent(HTTP_HOST_CLOUD, datas)


method_list = [getStockFromTencentLocal, getStockFromTencentCloud, getStockFromTencentVercel, getStockFromTencentNetlify,
               getStockFromXueQiuLocal, getStockFromXueQiuCloud, getStockFromXueQiuVercel, getStockFromXueQiuNetlify,
               getStockFromSinaLocal, getStockFromSinaCloud, getStockFromSinaVercel, getStockFromSinaNetlify]
etf_method = [getEtfFromTencentLocal, getEtfFromTencentCloud]
All_STOCK_DATA_SIZE = len(method_list)
random.shuffle(method_list)
stock_dispatcher = AsyncRoundRobinDispatcher(methods=method_list, max_retries=5, timeout=10, cooldown=100, name="Stock Dispatcher")
etf_dispatcher = AsyncRoundRobinDispatcher(methods=etf_method, max_retries=5, timeout=10, cooldown=100, name="ETF Dispatcher")


async def getStockFrom(*args, **kwargs):
    return await stock_dispatcher.call(*args, **kwargs)


async def getEtfFrom(*args, **kwargs):
    return await etf_dispatcher.call(*args, **kwargs)


async def updateStockDetail():
    tool: Tools = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            total_cnt: int = await Stock.query().equal(running=1).count()
            total_batch_size = BATCH_SIZE * All_STOCK_DATA_SIZE
            total_batch = int((total_cnt + total_batch_size - 1) / total_batch_size)
            page = 0
            while page < total_batch:
                offset = page * total_batch_size
                stockList = []
                stockInfo: list[Stock] = await Stock.query().equal(running=1).order_by(Stock.create_time.asc()).offset(offset).limit(total_batch_size).all()
                for s in stockInfo:
                    stockList.append({s.code: s.name, f'{s.code}count': 1})
                random.shuffle(stockList)
                start_time = time.time()
                for i in range(0, len(stockList), BATCH_SIZE):
                    result = await getStockFrom(stockList[i: i + BATCH_SIZE])
                    if result:
                        result = await getStockFrom(result)
                        if result:
                            _ = await getStockFrom(result)
                page += 1
                logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次, 数量 {len(stockList)}...")
                delta = time.time() - start_time
                if delta < BATCH_INTERVAL:
                    await asyncio.sleep(BATCH_INTERVAL - delta)

            etfList = []
            etfInfo: list[ETF] = await ETF.query().equal(running=1).all()
            for s in etfInfo:
                etfList.append({s.code: s.name, f'{s.code}count': 1})
            index = int(len(etfList) / 2)
            results = await asyncio.gather(*[getEtfFrom(d) for d in [etfList[:index], etfList[index:]]], return_exceptions=True)
            results = await asyncio.gather(*[getEtfFrom(d) for d in results if d], return_exceptions=True)
            if results:
                pass
            logger.info(f"总共 {len(etfList)} 个 ETF ...")
        except:
            logger.error(traceback.format_exc())


async def checkTradeDay():
    """ 检查今天是否开市 """
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
                        try:
                            _ = await Tools.get_one("openDoor")
                            await Tools.update("openDoor", value=current_day)
                        except NoResultFound:
                            await Tools.create(key="openDoor", value=current_day)
                        try:
                            _ = await Capital.get_one(current_day)
                        except NoResultFound:
                            capital: Capital = await Capital.query().order_by(Capital.day.desc()).first()
                            await Capital.create(day=current_day, total=capital.total, available=capital.available, hold=capital.hold, campare=capital.campare)
                        logger.info(f"{current_day} 今天开市")
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


async def updateStockFund(a=1):
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        if day == time.strftime("%Y%m%d"):
            page_size = 20
            p = 0
            if a == 1:
                try:
                    logger.info("使用腾讯财经更新主力资金～")
                    while True:
                        res = await getStockOrderByFundFromTencent(page_size, p, is_price=False)
                        for r in res:
                            await Detail.query().equal(code=r['code'], day=day).update(fund=r['fund'])
                            logger.info(f"Update Stock Fund: {r['code']} - {r['fund']}")
                        if len(res) == 0 or int((res[-1]['total'] + page_size - 1) / page_size) <= p:
                            break
                        p += 1
                        await asyncio.sleep(6)
                except:
                    logger.error(traceback.format_exc())
                    await updateStockFund(2)
            else:
                try:
                    logger.info("使用新浪财经更新主力资金～")
                    while True:
                        res = await getStockOrderByFundFromSina(page_size, p, is_price=False)
                        for r in res:
                            await Detail.query().equal(code=r['code'], day=day).update(fund=r['fund'])
                            logger.info(f"Update Stock Fund: {r['code']} - {r['fund']}")
                        if len(res) == 0 or int((res[-1]['total'] + page_size - 1) / page_size) <= p:
                            break
                        p += 1
                        await asyncio.sleep(6)
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
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stocks: list[Detail] = await Detail.query().equal(day=day).less_equal(fund=0.01).greater_equal(fund=-0.01).all()
        for s in stocks:
            try:
                fund = await getStockZhuLiFundFromTencent(s.code)
            except:
                fund = await getStockZhuLiFundFromSina(s.code)
            await Detail.update((s.code, s.day), fund=fund)
            logger.info(f"ReUpdate Stock Fund: {s.name} - {s.code} - {fund}")
            await asyncio.sleep(8)
    except:
        logger.error(traceback.format_exc())


async def updateStockBanKuai(ban=0):
    try:
        if ban == 0:
            stockInfo: list[Stock] = await Stock.query().equal(running=1).all()
        else:
            stockInfo: list[Stock] = await Stock.query().equal(running=1, region="").all()
        for s in stockInfo:
            res = await getStockBanKuaiFromDOngCai(s.code)
            if 'msg' in res:
                await asyncio.sleep(5)
                continue
            region = res['region'] if res['region'] else s.region
            await Stock.update(s.code, region=region, industry=res['industry'], concept=res['concept'])
            logger.info(f"Update stock BanKuai {s.code} - {s.name} - {res}")
            await asyncio.sleep(5)
    except:
        logger.error(traceback.format_exc())


async def setAllSHStock(stock_type: str = "1"):
    tool: Tools = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        try:
            t = int(time.time() * 1000)
            page = 1
            hh = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
                'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'
            }
            if stock_type == '8':
                res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback93570008&STOCK_TYPE=8&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={page}&pageHelp.pageSize=50&pageHelp.pageNo={page}&pageHelp.endPage={page}&_={t}", headers=hh)
            else:
                res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={page}&pageHelp.pageSize=50&pageHelp.pageNo={page}&pageHelp.endPage={page}&_={t}", headers=hh)
            if res.status_code == 200:
                res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                res_json = json.loads('{' + res_text + '}')
                total_page = res_json['pageHelp']['pageCount']
                resubmit_list = []
                for p in range(total_page):
                    try:
                        t = int(time.time() * 1000)
                        if stock_type == '8':
                            res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback93570008&STOCK_TYPE=8&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={p + 1}&pageHelp.pageSize=50&pageHelp.pageNo={p + 1}&pageHelp.endPage={p + 1}&_={t}", headers=hh)
                        else:
                            res = await http.get(f"https://query.sse.com.cn/sseQuery/commonQuery.do?jsonCallBack=jsonpCallback48155236&STOCK_TYPE=1&REG_PROVINCE=&CSRC_CODE=&STOCK_CODE=&sqlId=COMMON_SSE_CP_GPJCTPZ_GPLB_GP_L&COMPANY_STATUS=2%2C4%2C5%2C7%2C8&type=inParams&isPagination=true&pageHelp.cacheSize=1&pageHelp.beginPage={p + 1}&pageHelp.pageSize=50&pageHelp.pageNo={p + 1}&pageHelp.endPage={p + 1}&_={t}", headers=hh)
                        if res.status_code == 200:
                            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                            res_json = json.loads('{' + res_text + '}')
                            stock_list = res_json['pageHelp']['data']
                            for s in stock_list:
                                code = s['A_STOCK_CODE']
                                name = s['COMPANY_ABBR'].replace(' ', '')
                                try:
                                    s: Stock = await Stock.get_one(code)
                                    is_running = s.running
                                    if ('ST' in name.upper() or '退' in name) and s.running == 1:
                                        if s.filter and 'myself' in s.filter:
                                            continue
                                        await Stock.update(s.code, running=0, name=name)
                                        logger.info(f"股票 {s.name} - {s.code}  | {name} - {code} 处于退市状态, 忽略掉...")
                                        continue
                                    if 'ST' in s.name.upper() and 'ST' not in name.upper() and '退' not in name:
                                        await Stock.update(s.code, running=1, name=name)
                                        logger.info(f"股票 {s.name} - {s.code} | {name} - {code} 重新上市, 继续处理...")
                                        resubmit_list.append(f"{name} - {code}")
                                        await initStockData(code, name)
                                        continue
                                    await Stock.update(s.code, name=name)
                                except NoResultFound:
                                    is_running = 1
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
            if stock_type == '8':
                scheduler.add_job(setAllSHStock, 'date', run_date=datetime.now() + timedelta(seconds=30), args=["1"])
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


async def setAllSZStock():
    tool: Tools = await Tools.get_one("openDoor")
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
                                name = s['agjc'].split('<u>')[-1].split('</u>')[0].replace(' ', '')
                                try:
                                    s: Stock = await Stock.get_one(code)
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
                                        await initStockData(code, name)
                                        continue
                                    await Stock.update(s.code, name=name)
                                except NoResultFound:
                                    is_running = 1
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
                tool: Tools = await Tools.get_one("openDoor")
                current_day = tool.value
        except:
            logger.error(traceback.format_exc())
            logger.error("数据更新异常...")


async def setAllSHEtf():
    try:
        page = 1
        total_page = 20
        while page <= total_page:
            res = await getEtfInfoFromSH(page)
            if res:
                total_page = res['pageCount']
                data_list = res['data']
                for d in data_list:
                    code = d['fundCode']
                    await writeEtfDatabase(code)
                    await asyncio.sleep(30)
            page += 1
    except:
        logger.error(traceback.format_exc())


async def setAllSZEtf():
    try:
        page = 1
        total_page = 70
        while page <= total_page:
            res = await getEtfInfoFromSZ(page)
            if res:
                total_page = res['metadata']['pagecount']
                data_list = res['data']
                for d in data_list:
                    result = re.findall(r'<u>(\d+)</u>', d['sys_key'])
                    code = result[0].strip()
                    await writeEtfDatabase(code)
                    await asyncio.sleep(30)
            page += 1
    except:
        logger.error(traceback.format_exc())


# async def updateEtfHoldStock(host: str = ''):
#     '''
#     获取ETF的重仓前10的股票
#     '''
#     try:
#         etfInfo: list[ETF] = await ETF.query().equal(running=1).all()
#         for r in etfInfo:
#             if r.code == '159934':      # 黄金ETF过滤掉
#                 continue
#             res = await getHoldStockOfEtfFromTencent(host, r.code)
#             await ETF.update(r.code, stocks=res)
#             logger.info(f"{r.name} - {r.code} 的前10大重仓股是 {res}")
#             await asyncio.sleep(8)
#     except:
#         logger.error(traceback.format_exc())


async def writeEtfDatabase(code: str):
    try:
        etf: ETF = await ETF.get_one(code)
        etf_info = await getEtfDetailFromDongCai(code)
        res = await getHoldStockOfEtfFromTencent('', code)
        if etf_info and etf_info['code'] == code:
            name = etf_info['name'] if etf_info['name'] else etf.name
            capital = etf_info['capital'] if etf_info['capital'] > 0 else etf.capital
            fee = etf_info['fee'] if etf_info['fee'] > 0 else etf.fee
            await ETF.update(code, name=name, capital=capital, fee=fee, stocks=res)
            logger.info(f"ETF {code} 更新成功, {etf.name} -> {name}, {etf.capital} -> {capital}, {etf.fee} -> {fee}")
        else:
            logger.error(f"获取ETF信息失败: {code} - {etf_info}")
    except NoResultFound:
        etf_info = await getEtfDetailFromDongCai(code)
        res = await getHoldStockOfEtfFromTencent('', code)
        if etf_info and etf_info['code'] == code:
            await ETF.create(code=code, name=etf_info['name'], capital=etf_info['capital'], fee=etf_info['fee'], stocks=res,
                             industry=etf_info['tracking'], create_time=datetime.strptime(etf_info['date'], "%Y-%m-%d"))
            logger.info(f"ETF {code} 添加成功, {etf_info['name']} - {etf_info['capital']} - {etf_info['fee']} -> {etf_info['tracking']}")
        else:
            logger.error(f"获取ETF信息失败: {code} - {etf_info}")
    except:
        logger.error(traceback.format_exc())


async def updateEtfShares():
    try:
        tool: Tools = await Tools.get_one("openDoor")
        d = tool.value
        pre_day = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        d1 = datetime.strptime(pre_day, "%Y-%m-%d").date()
        diff_days = (datetime.today().date() - d1).days
        if diff_days == 1:
            res = await getEtfShareFromSZ('159915', pre_day)    # 查询深交所数据是否已更新
            if len(res) < 1:
                # 10 分钟后再次查询
                scheduler.add_job(updateEtfShares, "date", run_date=datetime.now() + timedelta(minutes=10), id="updateEtfShares_retry", replace_existing=True, misfire_grace_time=10)
                logger.warning("深交所数据未更新, 10分钟后再次查询 ~")
                return
            logger.info("开始深交所获取 ETF 份额 ~")
            stocks: list[ETF] = await ETF.query().equal(running=1).all()
            for s in stocks:
                if s.code.startswith('1'):
                    res = await getEtfShareFromSZ(s.code, pre_day)
                    shares = float(res[0]['current_size'].replace(',', '')) / 10000
                    await Detail.update((s.code, d), shares=round(shares, 5))
                    logger.info(f"day: {d}, code: {s.code}, shares: {shares}")
                    await asyncio.sleep(5)

            logger.info("开始从上交所获取 ETF 份额 ~")
            res = await getEtfShareFromSH(pre_day)
            for k, v in res.items():
                await Detail.update((k, d), shares=round(v, 5))
                logger.info(f"day: {d}, code: {k}, shares: {v}")
        else:
            logger.info(f"No need update ETF shares, because {time.strftime("%Y-%m-%d")} - {pre_day} ≠ 1")
    except:
        sendEmail(SENDER_EMAIL, SENDER_EMAIL, EMAIL_PASSWORD, '更新 ETF 份额异常')
        logger.error(traceback.format_exc())


async def clearStockData():
    try:
        stock: list[Stock] = await Stock.query().all()
        etf: list[ETF] = await ETF.query().equal(running=1).all()
        code = [f.code for f in stock] + [f.code for f in etf]
        past_day = get_past_date(383)    # 383天大概是一年多的数据，大概共256个交易日
        for c in code:
            trans: list[Transaction] = await Transaction.query().equal(code=c).order_by(Transaction.id.desc()).limit(3).all()
            if len(trans) == 0 or trans[0].status == TradeType.MAN:
                _ = await Detail.query().equal(code=c).less_equal(day=past_day).delete()
                logger.info(f"Delete detail data success, {c} - {past_day}")
            else:
                logger.info(f"Delete detail data fail because not sold, {c} - {past_day}")
    except:
        logger.error(traceback.format_exc())
