#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import re
import json
import time
import random
import logging
import asyncio
import traceback
import aiofiles
from datetime import datetime, timedelta
from sqlalchemy.exc import NoResultFound
from settings import BATCH_SIZE, BATCH_INTERVAL, HTTP_HOST_CLOUD, HTTP_HOST_VERCEL, HTTP_HOST_NETLIFY
from settings import BASE_PATH, BACKUP_PATH, EMAIL_TEMPLATE, DEFAULT_USER_ID
from settings import stock_fee_ratio, etf_fee_ratio, stamp_duty
from utils.model import StockModelDo
from utils.dispatcher import AsyncRoundRobinDispatcher
from utils.scheduler import scheduler
from utils.http_client import http
from utils.backup import zip_file
from utils.send_email import sendEmail
from utils.initData import initStockData
from utils.common import calc_MA, calc_macd, calc_kdj, get_past_date, real_traded_minutes
from utils.common import queryByCodeForAI, get_holding, get_today_hold
from utils.queryStockHq import getStockHqFromTencent, getStockHqFromSina, getStockHqFromXueQiu, getStockHq
from utils.metric import bollinger_bands, check_confirmation, detect_buy, detect_sell
from utils.selectStock import getStockOrderByFundFromSina, getStockOrderByFundFromTencent, getStockDivideData
from utils.selectStock import getStockZhuLiFund, getStockZhuLiFundFromSina, getStockBanKuaiFromDOngCai
from utils.etfData import getEtfInfoFromSH, getEtfInfoFromSZ, getEtfDetailFromDongCai, getHoldStockOfEtfFromTencent
from utils.etfData import getEtfShareFromSH, getEtfShareFromSZ
from utils.database import Stock, Detail, Tools, Capital, ETF, Transaction, TradeType, Analysis


logger = logging.getLogger(__name__)
All_STOCK_DATA_SIZE = 3
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


async def getStockFromTencent(host: str, datas: dict[str, str]) -> dict[str, str]:
    if not datas:
        return None
    try:
        result: dict = await getStockHqFromTencent(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorDict: dict[str, str] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorDict
    except:
        logger.error(f"Tencent({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        return datas


async def getStockFromXueQiu(host: str, datas: dict[str, str]) -> dict[str, str]:
    if not datas:
        return None
    try:
        result: dict = await getStockHqFromXueQiu(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorDict: dict[str, str] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorDict
    except:
        logger.error(f"XueQiu({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        return datas


async def getStockFromSina(host: str, datas: dict[str, str]) -> dict[str, str]:
    if not datas:
        return None
    try:
        result: dict = await getStockHqFromSina(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorDict: dict[str, str] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorDict
    except:
        logger.error(f"Sina({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        return datas


async def getEtfFromTencent(host: str, datas: dict[str, str]) -> dict[str, str]:
    if not datas:
        return None
    await asyncio.sleep(random.random())
    try:
        result: dict = await getStockHqFromTencent(host, datas)
        dataList: list[StockModelDo] = result['data']
        errorDict: dict[str, str] = result['error']
        for d in dataList:
            await saveStockInfo(d)
        return errorDict
    except:
        logger.error(f"Tencent({host}) - ETF 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        return datas


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


async def getStockFromTencentLocal(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromTencent('', datas)


async def getStockFromTencentCloud(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromTencent(HTTP_HOST_CLOUD, datas)


async def getStockFromTencentVercel(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromTencent(HTTP_HOST_VERCEL, datas)


async def getStockFromTencentNetlify(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromTencent(HTTP_HOST_NETLIFY, datas)


async def getStockFromXueQiuLocal(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromXueQiu('', datas)


async def getStockFromXueQiuCloud(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromXueQiu(HTTP_HOST_CLOUD, datas)


async def getStockFromXueQiuVercel(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromXueQiu(HTTP_HOST_VERCEL, datas)


async def getStockFromXueQiuNetlify(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromXueQiu(HTTP_HOST_NETLIFY, datas)


async def getStockFromSinaLocal(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromSina('', datas)


async def getStockFromSinaCloud(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromSina(HTTP_HOST_CLOUD, datas)


async def getStockFromSinaVercel(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromSina(HTTP_HOST_VERCEL, datas)


async def getStockFromSinaNetlify(datas: dict[str, str]) -> dict[str, str]:
    return await getStockFromSina(HTTP_HOST_NETLIFY, datas)


async def getEtfFromTencentLocal(datas: dict[str, str]) -> dict[str, str]:
    return await getEtfFromTencent('', datas)


async def getEtfFromTencentCloud(datas: dict[str, str]) -> dict[str, str]:
    return await getEtfFromTencent(HTTP_HOST_CLOUD, datas)


method_list = [getStockFromTencentLocal, getStockFromTencentCloud, getStockFromTencentVercel, getStockFromTencentNetlify,
               getStockFromXueQiuLocal, getStockFromXueQiuCloud, getStockFromXueQiuVercel, getStockFromXueQiuNetlify,
               getStockFromSinaLocal, getStockFromSinaCloud, getStockFromSinaVercel, getStockFromSinaNetlify]
etf_method = [getEtfFromTencentLocal, getEtfFromTencentCloud]
All_STOCK_DATA_SIZE = len(method_list)
random.shuffle(method_list)
stock_dispatcher = AsyncRoundRobinDispatcher(methods=method_list, max_retries=5, timeout=10, cooldown=100, name="Stock Dispatcher")
etf_dispatcher = AsyncRoundRobinDispatcher(methods=etf_method, max_retries=5, timeout=10, cooldown=100, name="ETF Dispatcher")


async def getStockFrom(*args, **kwargs) -> dict[str, str]:
    return await stock_dispatcher.call(*args, **kwargs)


async def getEtfFrom(*args, **kwargs) -> dict[str, str]:
    return await etf_dispatcher.call(*args, **kwargs)


async def updateStockDetail(flag: int = 1):
    tool: Tools = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day != time.strftime("%Y%m%d"):
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
                    stockList.append({s.code: s.name})
                random.shuffle(stockList)
                for i in range(0, len(stockList), BATCH_SIZE):
                    stockSlice = stockList[i: i + BATCH_SIZE]
                    stockDict = {k: v for d in stockSlice for k, v in d.items()}
                    result = await getStockFrom(stockDict)
                    if result:
                        result = await getStockFrom(result)
                        if result:
                            _ = await getStockFrom(result)
                page += 1
                logger.info(f"总共 {total_batch} 批次, 当前是第 {page} 批次, 数量 {len(stockList)}...")

            if flag != 123:
                etfList = []
                etfInfo: list[ETF] = await ETF.query().equal(running=1).all()
                for s in etfInfo:
                    etfList.append({s.code: s.name})
                for i in range(0, len(etfList), BATCH_SIZE):
                    etfSlice = etfList[i: i + BATCH_SIZE]
                    etfDict = {k: v for d in etfSlice for k, v in d.items()}
                    result = await getEtfFrom(etfDict)
                    if result:
                        _ = await getEtfFrom(result)
                logger.info(f"总共 {len(etfList)} 个 ETF ...")

                # 更新主力流入数据
                scheduler.add_job(updateStockFund, "date", run_date=datetime.now() + timedelta(seconds=10), args=[1], misfire_grace_time=10)
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

                        # 根据除权、分红数据更新 K 线图
                        scheduler.add_job(updateStockDivideData, "date", run_date=datetime.now() + timedelta(minutes=30), misfire_grace_time=10)
                        # 中午更新股票信息
                        scheduler.add_job(setAllSHStock, "date", run_date=datetime.now() + timedelta(hours=2), args=["8"], misfire_grace_time=10)
                        scheduler.add_job(setAllSZStock, "date", run_date=datetime.now() + timedelta(hours=2), misfire_grace_time=10)
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
                except Exception as e:
                    logger.error(traceback.format_exc())
                    sendEmail("Warning", f"获取所有股票的主力资金净流入数据失败 - {e}")
            await asyncio.sleep(5)
            await checkUpdateStockFund()  # 更新漏网数据，如果有

            # 备份数据库
            db_path = os.path.join(BASE_PATH, 'sqlite3.db')
            zip_path = os.path.join(BACKUP_PATH, f'db.{day}.zip')
            scheduler.add_job(zip_file, "date", run_date=datetime.now() + timedelta(seconds=60), args=[[db_path], zip_path], misfire_grace_time=10)
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
                fund = await getStockZhuLiFund(s.code)
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
                                    logger.info(f"{s.code} 股票名称从 {s.name} -> {name}")
                                except NoResultFound:
                                    is_running = 1
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        await Stock.create(code=code, name=name, running=is_running, region="", industry="", concept="", filter="")
                                        logger.info(f"股票 {name} - {code} 添加成功, 状态是 {is_running} ...")
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
                    sendEmail('股票重新上市', f"{','.join(resubmit_list)}，请检查数据～")
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
                                    logger.info(f"{s.code} 股票名称从 {s.name} -> {name}")
                                except NoResultFound:
                                    is_running = 1
                                    if 'ST' in name.upper() or '退' in name:
                                        is_running = 0
                                    if is_running == 1:
                                        await Stock.create(code=code, name=name, running=is_running, region="", industry="", concept="", filter="")
                                        logger.info(f"股票 {name} - {code} 添加成功, 状态是 {is_running} ...")
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
                    sendEmail('股票重新上市', f"{','.join(resubmit_list)}，请检查数据～")
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

        # 更新ETF份额
        if diff_days == 1:
            etfs: list[ETF] = await ETF.query().equal(running=1).all()
            for r in etfs:
                detail: Detail = await Detail.get_one((r.code, d))
                await ETF.update(r.code, capital=round(detail.current_price * detail.shares, 2))
                logger.info(f"update ETF total shares success, {r.code} - {r.name} - {r.capital}")
    except Exception as e:
        sendEmail('Warning', f'更新 ETF 份额异常 - {e}')
        logger.error(traceback.format_exc())


async def clearStockData():
    try:
        stock: list[Stock] = await Stock.query().all()
        etf: list[ETF] = await ETF.query().equal(running=1).all()
        code = [f.code for f in stock] + [f.code for f in etf]
        past_day = get_past_date()
        for c in code:
            _ = await Detail.query().equal(code=c).less_equal(day=past_day).delete()
            logger.info(f"Delete detail data success, {c} - {past_day}")

        # 更新股票行业、概念等数据
        scheduler.add_job(updateStockBanKuai, "date", run_date=datetime.now() + timedelta(seconds=10), misfire_grace_time=10)
    except:
        logger.error(traceback.format_exc())


async def updateStockDivideData():
    '''获取派息除权信息，更新股票K线数据'''
    try:
        tool: Tools = await Tools.get_one("openDoor")
        if tool.value != time.strftime("%Y%m%d"):
            logger.info("今天未开市，跳过...")
            return
        day = f"{tool.value[:4]}-{tool.value[4:6]}-{tool.value[6:]}"
        res = await getStockDivideData(day)
        for r in res:
            await initStockData(r['code'], r['name'])
            await asyncio.sleep(30)
    except:
        logger.error(traceback.format_exc())


async def auto_trade():
    """自动交易"""
    try:
        tool: Tools = await Tools.get_one("openDoor")
        if tool.value != time.strftime("%Y%m%d"):
            logger.info("今天未开市，跳过...")
            return

        # 更是K线数据
        await updateStockDetail(flag=123)

        # 先卖
        await auto_sell()

        # 再买
        await buy_confirm()

        # 再新筛选数据
        await auto_buy()

        # 删除已经产出信号的数据，days_diff 是 T+1 or T+2
        days_diff = 2
        past_day = get_past_date(days_diff=days_diff, date_format="%Y-%m-%d") + " 23:59:59"
        await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).less_equal(create_time=past_day).delete()
    except:
        logger.error(traceback.format_exc())


async def auto_buy():
    try:
        # 第一次从全市场筛选数据，初筛，不使用主力资金
        stocks: list[Stock] = await Stock.query().equal(running=1).all()
        temp_res = []
        for s in stocks:
            k_line = await queryByCodeForAI(s.code, limit=40, flag=False)
            res = detect_buy(k_line, isFund=False)
            if res:
                res.update({'code': s.code})
                temp_res.append(res)

        # 第二次筛选，使用主力资金
        for s in temp_res:
            k_line = await queryByCodeForAI(s['code'], limit=40)
            res = detect_buy(k_line)
            if res:
                stock = await Stock.get_one(s['code'])
                await Transaction.create(code=stock.code, name=stock.name, status=TradeType.TEMB, price=res['price'],
                                         shares=res['shares'], fee=0, flag=0, user_id=DEFAULT_USER_ID)
                await Analysis.create(code=stock.code, day=res['day'], content=json.dumps(res, ensure_ascii=False))
                logger.info(f"detect buy signal - {stock.code} - {stock.name} - {res}")
            await asyncio.sleep(2)
        logger.info("detect buy signal task completed ~")
    except:
        logger.error(traceback.format_exc())


async def buy_confirm():
    try:
        tool: Tools = await Tools.get_one("openDoor")
        capital: Capital = await Capital.get_one(tool.value)
        available = capital.available
        logger.info(f"buy stock task: current day {capital.day} available fund is {available}.")

        trans_temp: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, status=TradeType.TEMB, flag=0).all()
        for r in trans_temp:
            if r.code.startswith("1") or r.code.startswith("5"):
                continue
            k_line = await queryByCodeForAI(r.code, limit=40)
            confirmed, buy_price = check_confirmation(k_line)
            if confirmed and buy_price is not None:
                fee = max(buy_price * r.shares * stock_fee_ratio, 5)
                await Transaction.update(r.id, price=buy_price, status=TradeType.RECD, fee=fee)
                available = available - (buy_price * r.shares + fee)
                logger.info(f"buy stock {r.code} - {r.name} success, price: {buy_price}, shares: {r.shares}")
            await asyncio.sleep(2)
        await Capital.update(tool.value, available=round(available, 2))
        logger.info(f"buy stock task completed. after buy stock, current available fund is {available}")
    except:
        logger.error(traceback.format_exc())


async def auto_sell():
    try:
        tool: Tools = await Tools.get_one("openDoor")
        capital: Capital = await Capital.get_one(tool.value)
        available = capital.available
        logger.info(f"sell stock task: current day {capital.day} available fund is {available}.")

        trans_temp: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, status=TradeType.RECD, flag=0).all()
        for r in trans_temp:
            if r.code.startswith("1") or r.code.startswith("5"):
                continue
            k_line = await queryByCodeForAI(r.code, limit=40)
            position = {'day': r.create_time.strftime("%Y%m%d"), 'code': r.code, 'name': r.name, 'price': r.price, 'shares': r.shares}
            res = detect_sell(k_line, position)
            if res:
                fee = max(res['price'] * r.shares * stock_fee_ratio, 5) + res['price'] * r.shares * stamp_duty
                await Transaction.create(code=r.code, name=r.name, status=TradeType.AIS, price=res['price'], shares=r.shares,
                                         fee=fee, flag=0, user_id=r.user_id)
                available = available + (res['price'] * r.shares - fee)
                logger.info(f"sell stock {r.code} - {r.name} success, price: {res['price']}, shares: {r.shares}")
            await asyncio.sleep(2)
        await Capital.update(tool.value, available=round(available, 2))
        logger.info(f"sell stock task completed. after sell stock, current available fund is {available}")
    except:
        logger.error(traceback.format_exc())


async def clear_auto_temp():
    try:
        days_diff = 2
        past_day = get_past_date(days_diff=days_diff, date_format="%Y-%m-%d") + " 23:59:59"
        await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).less_equal(create_time=past_day).delete()
    except:
        logger.error(traceback.format_exc())


async def update_holding_capital():
    """处理交易记录，更新清仓数据"""
    try:
        tool: Tools = await Tools.get_one("openDoor")
        current_day = tool.value
        if current_day == time.strftime("%Y%m%d"):
            _ = await get_holding()
            holdList = await get_holding(user_id=DEFAULT_USER_ID)
            hold_fund = 0
            etfDict = {}
            stockDict = {}
            for h in holdList:
                code = h['code']
                isEtf = code.startswith('1') or code.startswith('5')
                if isEtf:
                    etfDict.update({h['code']: h['name']})
                else:
                    stockDict.update({h['code']: h['name']})

            _ = await getStockFrom(stockDict)
            _ = await getEtfFrom(etfDict)

            for h in holdList:
                detail: Detail = await Detail.query().equal(code=h['code']).order_by(Detail.day.desc()).first()
                hold_fund += round(detail.current_price * h['shares'], 2)

            # 更新当天沪深300指数价格
            res: dict = await getStockHqFromTencent(HTTP_HOST_CLOUD, {"sh000300": "沪深300"})
            stockDo: StockModelDo = res['data'][0]
            capital: Capital = await Capital.get_one(current_day)
            await Capital.update(current_day, total=round(capital.available + hold_fund, 2), hold=round(hold_fund, 2), campare=stockDo.current_price)
    except:
        logger.error(traceback.format_exc())


async def auto_select_email():
    try:
        tradeStatus = {"TEMB": "买入", "TEMS": "卖出", "RECD": "买入", "AIS": "卖出"}
        res = await get_today_hold()
        today_str = ''
        hold_str = ''
        for r in res['todayList']:
            if r['status'] not in tradeStatus:
                continue
            today_str += f'''<tr><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['name']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['code']}</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['create_time']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{tradeStatus[r['status']]}(待确认)</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['price']}(预估)</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['shares']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;"></td></tr>'''
        for r in res['holdList']:
            hold_str += f'''<tr><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['name']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['code']}</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['create_time']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['price']}</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['shares']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['profit']}</td></tr>'''
        async with aiofiles.open(EMAIL_TEMPLATE, 'r', encoding='utf-8') as f:
            template = await f.read()
        template = template.replace("today_filter_stock", today_str).replace("has_hold_stock", hold_str)
        sendEmail("今日数据", template)
        logger.info("send email success ~")
    except:
        logger.error(traceback.format_exc())
