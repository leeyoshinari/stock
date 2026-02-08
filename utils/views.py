#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import time
import json
import traceback
from datetime import datetime
from utils.model import SearchStockParam, StockModelDo, StockDataList, StockMinuteDo
from utils.model import StockInfoList, RecommendStockDataList, ToolsInfoList
from utils.selectStock import getStockZhuLiFundFromDongCai
from utils.ai_model import queryAI, webSearchTopic
from utils.saleStock import sellAI
from utils.logging import logger
from utils.results import Result
from utils.initData import initStockData
from utils.queryStockHq import getStockHqFromTencent, getStockHqFromSina, getStockHqFromXueQiu
from utils.queryStockHq import getMinuteKFromTongHuaShun, getMinuteKFromTencent, getMinuteKFromSina
from utils.metric import real_traded_minutes, bollinger_bands
from utils.database import Recommend, Stock, Detail, Tools
from settings import OPENAI_URL, OPENAI_KEY, OPENAI_MODEL, API_URL, AI_MODEL, AI_MODEL25, AUTH_CODE, FILE_PATH


alpha_trix = 2.0 / (12 + 1)
alpha_s = 2.0 / (12 + 1)
alpha_l = 2.0 / (26 + 1)
alpha_sig = 2.0 / (9 + 1)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


def calc_MA(data: list, window: int) -> float:
    return round(sum(data[:window]) / len(data[:window]), 2)


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


async def queryByCode(code: str, site: str = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockInfo: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.asc()).all()
        data = [[getattr(row, k) for k in ['open_price', 'current_price', 'min_price', 'max_price', 'volume', 'qrr', 'emas', 'emal', 'dea', 'turnover_rate', 'fund']] for row in stockInfo]
        bollinger = []
        x = []
        volume = []
        qrr = []
        ma_five = []
        ma_ten = []
        ma_twenty = []
        turnover_rate = []
        fund = []
        diff = []
        dea = []
        macd = []
        kdjk = []
        kdjd = []
        kdjj = []
        trix = []
        trma = []
        boll_up = []
        boll_low = []
        for index, d in enumerate(data):
            bollinger.append(d[1])
            x.append(stockInfo[index].day)
            volume.append(d[4])
            qrr.append(d[5])
            ma_five.append(stockInfo[index].ma_five)
            ma_ten.append(stockInfo[index].ma_ten)
            ma_twenty.append(stockInfo[index].ma_twenty)
            turnover_rate.append(d[9])
            fund.append(d[10])
            diff_x = d[6] - d[7]
            macd_x = (diff_x - d[8]) * 2
            diff.append(round(diff_x, 3))
            dea.append(round(d[8], 3))
            macd.append(round(macd_x, 3))
            kdjk.append(round(stockInfo[index].kdjk, 3))
            kdjd.append(round(stockInfo[index].kdjd, 3))
            kdjj.append(round(stockInfo[index].kdjj, 3))
            trix.append(round(stockInfo[index].trix, 3))
            trma.append(round(stockInfo[index].trma, 3))
            boll_up.append(stockInfo[index].boll_up)
            boll_low.append(stockInfo[index].boll_low)
        st: Stock = await Stock.get_one(code)
        recommends: list[Recommend] = await Recommend.query().select('create_time', 'price').equal(code=code).order_by(Recommend.create_time.asc()).all()
        coords = [['R', r[0].strftime("%Y%m%d"), r[0].strftime("%Y-%m-%d %H:%M:%S"), r[1]] for r in recommends]
        if x[-1] != day:
            stockDo: dict = await calc_stock_real_data(code, site)
            x.append(day)
            data.append([stockDo['open_price'], stockDo['current_price'], stockDo['min_price'], stockDo['max_price'], stockDo['volume'], stockDo['qrr'], 0, 0, stockDo['dea'], stockDo['turnover_rate'], stockDo['fund']])
            volume.append(stockDo['volume'])
            qrr.append(stockDo['qrr'])
            turnover_rate.append(stockDo['turnover_rate'])
            ma_five.append(stockDo['ma_five'])
            ma_ten.append(stockDo['ma_ten'])
            ma_twenty.append(stockDo['ma_twenty'])
            diff.append(round(stockDo['diff'], 3))
            dea.append(round(stockDo['dea'], 3))
            macd.append(round(stockDo['diff'] - stockDo['dea'], 3))
            fund.append(stockDo['fund'])
            kdjk.append(round(stockDo['k'], 3))
            kdjd.append(round(stockDo['d'], 3))
            kdjj.append(round(stockDo['j'], 3))
            trix.append(round(stockDo['trix'], 3))
            trma.append(round(stockDo['trma'], 3))
            boll_up.append(stockDo['boll_up'])
            boll_low.append(stockDo['boll_low'])
        result.data = {
            'x': x, 'code': code, 'name': st.name, 'region': st.region, 'industry': st.industry, 'coord': coords,
            'price': data, 'volume': volume, 'qrr': qrr, 'turnover_rate': turnover_rate,
            'ma_five': ma_five, 'ma_ten': ma_ten, 'ma_twenty': ma_twenty, 'boll_up': boll_up,
            'diff': diff, 'dea': dea, 'macd': macd, 'fund': fund, 'concept': st.concept,
            'k': kdjk, 'd': kdjd, 'j': kdjj, 'trix': trix, 'trma': trma, 'boll_low': boll_low
        }
        result.total = len(result.data)
        logger.info(f"查询信息成功, 代码: {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def queryStockList(query: SearchStockParam) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        tool: Tools = await Tools.get_one("openDoor2")
        day2 = tool.value
        if query.code:
            stockInfo: Detail = await Detail.get((query.code, day))
            if not stockInfo:
                stockInfo = await Detail.get((query.code, day2))
            stockList = [StockModelDo.model_validate(stockInfo).model_dump()] if stockInfo else []
        elif query.name:
            stockInfo: list[Detail] = await Detail.query().equal(day=day).like(name=query.name).all()
            if len(stockInfo) < 1:
                stockInfo: list[Detail] = await Detail.query().equal(day=day2).like(name=query.name).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
        else:
            logger.info(query)
            offset = (query.page - 1) * query.pageSize
            total_num: int = await Detail.query().equal(day=day).count()
            if total_num < 1:
                total_num: int = await Detail.query().equal(day=day2).count()
                stockInfo: list[Detail] = await Detail.query().equal(day=day2).order_by_key(Detail, query.sortField).offset(offset).limit(query.pageSize).all()
            else:
                stockInfo: list[Detail] = await Detail.query().equal(day=day).order_by_key(Detail, query.sortField).offset(offset).limit(query.pageSize).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
            result.total = total_num
        result.data = stockList
        logger.info(f"查询列表成功, 查询参数: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def queryRecommendStockList(page: int = 1) -> Result:
    result = Result()
    pageSize = 20
    try:
        offset = (page - 1) * pageSize
        total_num: int = await Recommend.query().count()
        stockInfo: list[Recommend] = await Recommend.query().order_by(Recommend.create_time.desc()).offset(offset).limit(pageSize).all()
        stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo]
        result.total = total_num
        result.data = stockList
        logger.info("查询推荐股票列表成功～")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def calc_stock_return(fee) -> Result:
    result = Result()
    try:
        init_fund = 5000
        coupon = 13
        if fee > 0:
            coupon = 0
        r1, r1h, r1l, r2, r2h, r2l, r3, r3h, r3l, r4, r4h, r4l, r5, r5h, r5l = 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        x = []
        y1, y1h, y1l, y2, y2h, y2l, y3, y3h, y3l, y4, y4h, y4l, y5, y5h, y5l = [], [], [], [], [], [], [], [], [], [], [], [], [], [], []
        stocks: list[Recommend] = await Recommend.query().order_by(Recommend.id.asc()).all()
        for s in stocks:
            s_time = s.create_time.strftime("%Y-%m-%d")
            if s_time in x:
                index = x.index(s_time)
                y1[index] = y1[index] + round(init_fund * (s.last_one_price or 0) / 100 - coupon, 2)
                y1h[index] = y1h[index] + round(init_fund * (s.last_one_high or 0) / 100 - coupon, 2)
                y1l[index] = y1l[index] + round(init_fund * (s.last_one_low or 0) / 100 - coupon, 2)
                y2[index] = y2[index] + round(init_fund * (s.last_two_price or 0) / 100 - coupon, 2)
                y2h[index] = y2h[index] + round(init_fund * (s.last_two_high or 0) / 100 - coupon, 2)
                y2l[index] = y2l[index] + round(init_fund * (s.last_two_low or 0) / 100 - coupon, 2)
                y3[index] = y3[index] + round(init_fund * (s.last_three_price or 0) / 100 - coupon, 2)
                y3h[index] = y3h[index] + round(init_fund * (s.last_three_high or 0) / 100 - coupon, 2)
                y3l[index] = y3l[index] + round(init_fund * (s.last_three_low or 0) / 100 - coupon, 2)
                y4[index] = y4[index] + round(init_fund * (s.last_four_price or 0) / 100 - coupon, 2)
                y4h[index] = y4h[index] + round(init_fund * (s.last_four_high or 0) / 100 - coupon, 2)
                y4l[index] = y4l[index] + round(init_fund * (s.last_four_low or 0) / 100 - coupon, 2)
                y5[index] = y5[index] + round(init_fund * (s.last_five_price or 0) / 100 - coupon, 2)
                y5h[index] = y5h[index] + round(init_fund * (s.last_five_high or 0) / 100 - coupon, 2)
                y5l[index] = y5l[index] + round(init_fund * (s.last_five_low or 0) / 100 - coupon, 2)
            else:
                x.append(s_time)
                y1.append(round(init_fund * (s.last_one_price or 0) / 100 - coupon, 2))
                y1h.append(round(init_fund * (s.last_one_high or 0) / 100 - coupon, 2))
                y1l.append(round(init_fund * (s.last_one_low or 0) / 100 - coupon, 2))
                y2.append(round(init_fund * (s.last_two_price or 0) / 100 - coupon, 2))
                y2h.append(round(init_fund * (s.last_two_high or 0) / 100 - coupon, 2))
                y2l.append(round(init_fund * (s.last_two_low or 0) / 100 - coupon, 2))
                y3.append(round(init_fund * (s.last_three_price or 0) / 100 - coupon, 2))
                y3h.append(round(init_fund * (s.last_three_high or 0) / 100 - coupon, 2))
                y3l.append(round(init_fund * (s.last_three_low or 0) / 100 - coupon, 2))
                y4.append(round(init_fund * (s.last_four_price or 0) / 100 - coupon, 2))
                y4h.append(round(init_fund * (s.last_four_high or 0) / 100 - coupon, 2))
                y4l.append(round(init_fund * (s.last_four_low or 0) / 100 - coupon, 2))
                y5.append(round(init_fund * (s.last_five_price or 0) / 100 - coupon, 2))
                y5h.append(round(init_fund * (s.last_five_high or 0) / 100 - coupon, 2))
                y5l.append(round(init_fund * (s.last_five_low or 0) / 100 - coupon, 2))
            r1 += round(init_fund * (s.last_one_price or 0) / 100 - coupon, 2)
            r1h += round(init_fund * (s.last_one_high or 0) / 100 - coupon, 2)
            r1l += round(init_fund * (s.last_one_low or 0) / 100 - coupon, 2)
            r2 += round(init_fund * (s.last_two_price or 0) / 100 - coupon, 2)
            r2h += round(init_fund * (s.last_two_high or 0) / 100 - coupon, 2)
            r2l += round(init_fund * (s.last_two_low or 0) / 100 - coupon, 2)
            r3 += round(init_fund * (s.last_three_price or 0) / 100 - coupon, 2)
            r3h += round(init_fund * (s.last_three_high or 0) / 100 - coupon, 2)
            r3l += round(init_fund * (s.last_three_low or 0) / 100 - coupon, 2)
            r4 += round(init_fund * (s.last_four_price or 0) / 100 - coupon, 2)
            r4h += round(init_fund * (s.last_four_high or 0) / 100 - coupon, 2)
            r4l += round(init_fund * (s.last_four_low or 0) / 100 - coupon, 2)
            r5 += round(init_fund * (s.last_five_price or 0) / 100 - coupon, 2)
            r5h += round(init_fund * (s.last_five_high or 0) / 100 - coupon, 2)
            r5l += round(init_fund * (s.last_five_low or 0) / 100 - coupon, 2)

        result.data = {'r1': r1, 'r1h': r1h, 'r1l': r1l, 'r2': r2, 'r2h': r2h, 'r2l': r2l, 'r3': r3, 'r3h': r3h,
                       'r3l': r3l, 'r4': r4, 'r4h': r4h, 'r4l': r4l, 'r5': r5, 'r5h': r5h, 'r5l': r5l, 'x': x,
                       'y1': y1, 'y1h': y1h, 'y1l': y1l, 'y2': y2, 'y2h': y2h, 'y2l': y2l, 'y3': y3, 'y3h': y3h,
                       'y3l': y3l, 'y4': y4, 'y4h': y4h, 'y4l': y4l, 'y5': y5, 'y5h': y5h, 'y5l': y5l}
    except:
        logger.error(traceback.format_exc())
        result.success = False
    return result


async def query_ai_stock(code: str, site: str = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockList: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(10).all()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
        is_stock = [item for item in stock_data if item['day'] == day]
        if not is_stock:
            logger.info(f"query newest data - {code}")
            stockDo: dict = await calc_stock_real_data(code, site)
            stock_data.insert(0, stockDo)
        else:
            fflow = await getStockZhuLiFundFromDongCai(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List(stock_data)
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:30:00"
        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}，最新日期的所有数据都是截至当前时间实时计算出来的，不一定是一整天的数据，不能和其他日期的数据弄混了'
        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await queryAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, None, None, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"query AI suggestion successfully, code: {code}, result: {result.data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def sell_stock(code: str, price: str = None, t: str = None, site: str = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockList: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(10).all()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
        is_stock = [item for item in stock_data if item['day'] == day]
        if not is_stock:
            logger.info(f"query newest data - {code}")
            stockDo: dict = await calc_stock_real_data(code, site)
            stock_data.insert(0, stockDo)
        else:
            fflow = await getStockZhuLiFundFromDongCai(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List(stock_data)
        if price and t:
            pass
        else:
            r: Recommend = await Recommend.query().equal(code=code).order_by(Recommend.id.desc()).first()
            price = r.price
            t = r.create_time.strftime("%Y%m%d")
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:30:00"
        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}，最新日期的所有数据都是截至当前时间实时计算出来的，不一定是一整天的数据，不能和其他日期的数据弄混了'
        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await queryAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, price, t, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"query AI suggestion successfully, code: {code}, result: {result.data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def ai_sell(code: str, site: str = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockList: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(10).all()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
        is_stock = [item for item in stock_data if item['day'] == day]
        if not is_stock:
            logger.info(f"query newest data - {code}")
            stockDo: dict = await calc_stock_real_data(code, site)
            stock_data.insert(0, stockDo)
        else:
            fflow = await getStockZhuLiFundFromDongCai(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List(stock_data)
        r: Recommend = await Recommend.query().equal(code=code).order_by(Recommend.id.desc()).first()
        price = r.price
        t = r.create_time.strftime("%Y-%m-%d %H:%M:%S")
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:30:00"
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        if current_time > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await sellAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, price, t, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"sell stock AI suggestion successfully, code: {code}, result: {result.data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def calc_stock_real(code: str, site: str = None) -> Result:
    result = Result()
    try:
        x = []
        price = []
        volume = []
        if site == 'sina':
            res: list[StockMinuteDo] = await getMinuteKFromSina('', code, logger)
        else:
            res: list[StockMinuteDo] = await getMinuteKFromTongHuaShun('', code, logger)
        for r in res:
            x.append(r.time)
            price.append(r.price)
            volume.append(r.volume)
        st = await Stock.get_one(code)
        result.data = {'x': x, 'price': price, 'volume': volume, 'code': code, 'name': st.name, 'region': st.region, 'industry': st.industry, 'concept': st.concept}
        logger.info(f"query Recommend stock minute real data success - {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def all_stock_info(query: SearchStockParam) -> Result:
    result = Result()
    try:
        if query.code:
            stockInfo: Stock = await Stock.get(query.code)
            stockList = [StockInfoList.from_orm_format(stockInfo).model_dump()]
        elif query.name or query.region or query.industry or query.concept or query.filter:
            stockInfo: list[Stock] = await Stock.query().like(name=query.name, region=query.region, industry=query.industry, concept=query.concept, filter=query.filter).all()
            stockList = [StockInfoList.from_orm_format(f).model_dump() for f in stockInfo]
            result.total = len(stockList)
        else:
            logger.info(query)
            offset = (query.page - 1) * query.pageSize
            total_num: int = await Stock.query().equal(running=1).count()
            stockInfo: list[Stock] = await Stock.query().equal(running=1).order_by(Stock.create_time.desc()).offset(offset).limit(query.pageSize).all()
            stockList = [StockInfoList.from_orm_format(f).model_dump() for f in stockInfo]
            result.total = total_num
        result.data = stockList
        logger.info(f"查询股票列表成功, 查询参数: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def all_topic_info(query: SearchStockParam) -> Result:
    result = Result()
    try:
        offset = (query.page - 1) * query.pageSize
        total_num: int = await Tools.query().count()
        topicInfo: list[Tools] = await Tools.query().order_by(Tools.update_time.desc()).offset(offset).limit(query.pageSize).all()
        topicList = [ToolsInfoList.from_orm_format(f).model_dump() for f in topicInfo if not f.key.startswith('openDoor')]
        result.total = total_num
        result.data = topicList
        logger.info(f"查询股票列表成功, 查询参数: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_current_topic() -> Result:
    result = Result()
    try:
        result.data = await webSearchTopic(API_URL, AUTH_CODE)
        logger.info(f"Current Topic is: {result.data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_topic_file(code: str) -> Result:
    result = Result()
    try:
        file_path = os.path.join(FILE_PATH, f"{code}.txt")
        if not os.path.exists(file_path):
            return result
        with open(file_path, 'r', encoding='utf-8') as f:
            result.data = f.read()
        logger.info(f"{code} Topic is: {result.data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def set_stock_filter(code: str, filter: str, operate: int) -> Result:
    result = Result()
    try:
        stock: Stock = await Stock.get_one(code)
        if operate == 1:
            await Stock.update(stock.code, filter=f"{stock.filter},{filter}")
            logger.info(f"设置股票标签成功 - {code} - {filter}")
        else:
            filter_list = stock.filter.split(',')
            res_list = [r for r in filter_list if r != filter]
            await Stock.update(stock.code, filter=",".join(res_list))
            logger.info(f"删除股票标签成功 - {code} - {filter}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_stock_info(code: str) -> Result:
    result = Result()
    try:
        code_list = code.split(',')
        if len(code_list) == 1:
            stock: Stock = await Stock.get_one(code_list[0])
            stockList = [StockInfoList.from_orm_format(stock).model_dump()]
        else:
            stocks: list[Stock] = await Stock.query().isin(code=code_list).all()
            stockList = [StockInfoList.from_orm_format(f).model_dump() for f in stocks]
        result.data = stockList
        result.total = len(stockList)
        logger.info(f"查询股票信息成功 - {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def init_stock_data(code: str) -> Result:
    result = Result()
    try:
        stock: Stock = await Stock.get_one(code)
        await initStockData(code, stock.name, logger)
        logger.info(f"初始化股票数据成功 - {code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def calc_stock_real_data(code: str, site: str = None) -> dict:
    if site == 'sina':
        res_stock: dict = await getStockHqFromSina('', [{code: "-"}], logger)
    elif site == 'xueqiu':
        res_stock: dict = await getStockHqFromXueQiu('', [{code: "-"}], logger)
    else:
        res_stock: dict = await getStockHqFromTencent('', [{code: "-"}], logger)
    stockDo = StockModelDo.model_validate(res_stock['data'][0]).model_dump()
    stock_price_obj: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(21).all()
    stock_price = [r.current_price for r in stock_price_obj]
    high_price = [r.max_price for r in stock_price_obj]
    low_price = [r.min_price for r in stock_price_obj]
    trix_list = [r.trix for r in stock_price_obj]
    stock_price.insert(0, stockDo['current_price'])
    high_price.insert(0, stockDo['max_price'])
    low_price.insert(0, stockDo['min_price'])
    trix_list.insert(0, 0)
    real_trade_time = real_traded_minutes()
    volume_list = [r.volume for r in stock_price_obj[: 5]]
    volume_len = min(max(len(volume_list), 1), 5)
    emas = stock_price_obj[0].emas
    emal = stock_price_obj[0].emal
    dea = stock_price_obj[0].dea
    kdjk = stock_price_obj[0].kdjk
    kdjd = stock_price_obj[0].kdjd
    trix_ema_one = stock_price_obj[0].trix_ema_one
    trix_ema_two = stock_price_obj[0].trix_ema_two
    trix_ema_three = stock_price_obj[0].trix_ema_three
    average_volume = (sum(volume_list) / volume_len) * (real_trade_time / 240)
    average_volume = average_volume if average_volume > 0 else stockDo['volume']
    macd = calc_macd(stockDo['current_price'], emas, emal, dea)
    kdj = calc_kdj(stockDo['current_price'], high_price, low_price, kdjk, kdjd)
    trix = calc_trix(stockDo['current_price'], trix_list, trix_ema_one, trix_ema_two, trix_ema_three)
    stockDo.update({'ma_five': calc_MA(stock_price, 5)})
    stockDo.update({'ma_ten': calc_MA(stock_price, 10)})
    stockDo.update({'ma_twenty': calc_MA(stock_price, 20)})
    stockDo.update({'qrr': round(stockDo['volume'] / average_volume, 2)})
    stockDo.update({'diff': macd['emas'] - macd['emal']})
    stockDo.update({'dea': macd['dea']})
    stockDo.update({'k': kdj['k']})
    stockDo.update({'d': kdj['d']})
    stockDo.update({'j': kdj['j']})
    stockDo.update({'trix': trix['trix']})
    stockDo.update({'trma': trix['trma']})
    stockDo.update({'volume': stockDo['volume']})
    stockDo.update({'fund': await getStockZhuLiFundFromDongCai(code)})
    up, dn = bollinger_bands(stock_price[:20], calc_MA(stock_price, 20))
    stockDo.update({'boll_up': round(up, 2)})
    stockDo.update({'boll_low': round(dn, 2)})
    logger.info(stockDo)
    return stockDo


async def test(code) -> Result:
    result = Result()
    try:
        stock_volume_obj: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(6).all()
        stock_volume_obj.reverse()
        stock_volume = detail2List(stock_volume_obj)
        s_info = await Stock.get_one(code)
        tool = await Tools.get_one("openDoor")
        topic_info = await Tools.get_one(tool.value)
        stock_volume['hot_topic'] = topic_info.value
        stock_volume['industry'] = s_info.industry
        stock_volume['concept'] = s_info.concept
        result.data = stock_volume
    except:
        logger.error(traceback.format_exc())
    return result


def detail2List(data: list) -> dict:
    res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
           'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
           'd': [], 'j': [], 'trix': [], 'trma': [], 'boll_up': [], 'boll_low': []}
    for d in data:
        res['code'] = d['code']
        res['day'].append(d['day'])
        res['current_price'].append(d['current_price'])
        res['last_price'].append(d['last_price'])
        res['open_price'].append(d['open_price'])
        res['max_price'].append(d['max_price'])
        res['min_price'].append(d['min_price'])
        res['volume'].append(d['volume'])
        res['turnover_rate'].append(f"{d['turnover_rate']}%")
        res['fund'].append(d['fund'])
        res['ma_five'].append(d['ma_five'])
        res['ma_ten'].append(d['ma_ten'])
        res['ma_twenty'].append(d['ma_twenty'])
        res['qrr'].append(d['qrr'])
        res['diff'].append(round(d['diff'], 4))
        res['dea'].append(round(d['dea'], 4))
        res['k'].append(round(d['k'], 4))
        res['d'].append(round(d['d'], 4))
        res['j'].append(round(d['j'], 4))
        res['trix'].append(round(d['trix'], 4))
        res['trma'].append(round(d['trma'], 4))
        res['boll_up'].append(d['boll_up'])
        res['boll_low'].append(d['boll_low'])
    return res


def minute2List(data: list[StockMinuteDo]) -> dict:
    res = {'code': data[0].code, 'time': [], 'price': [], 'price_avg': [], 'volume': []}
    for d in data:
        res['time'].append(d.time)
        res['price'].append(d.price)
        res['price_avg'].append(d.price_avg)
        res['volume'].append(d.volume)
    return res
