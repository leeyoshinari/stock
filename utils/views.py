#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import time
import json
import asyncio
import traceback
from datetime import datetime, timedelta
from sqlalchemy.exc import NoResultFound
from utils.model import SearchStockParam, StockModelDo, StockDataList, StockMinuteDo
from utils.model import StockInfoList, RecommendStockDataList, ToolsInfoList, SetStockParam
from utils.selectStock import getStockZhuLiFundFromTencent
from utils.ai_model import queryAI, webSearchTopicBak
from utils.saleStock import sellAI, evaluate_sell_strategy
from utils.logging import logger
from utils.results import Result
from utils.scheduler import scheduler
from utils.initData import initStockData
from utils.queryStockHq import getStockHqFromTencent, getStockHqFromSina, getStockHqFromXueQiu
from utils.queryStockHq import getMinuteKFromTongHuaShun, getMinuteKFromDongcai, getMinuteKFromSina
from utils.metric import real_traded_minutes, bollinger_bands
from utils.database import Recommend, Stock, Detail, Tools, DBExecutor
from settings import OPENAI_URL, OPENAI_KEY, OPENAI_MODEL, API_URL, AI_MODEL, AI_MODEL25, AUTH_CODE, FILE_PATH


alpha_trix = 2.0 / (12 + 1)
alpha_s = 2.0 / (12 + 1)
alpha_l = 2.0 / (26 + 1)
alpha_sig = 2.0 / (9 + 1)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}
AI_DECIDE = {}


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


def getStockLimitUp(code: str, name: str) -> float:
    if 'st' in name.lower():
        return 0.05
    if code.startswith("30") or code.startswith("68"):
        return 0.2
    return 0.1


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
        recommends: list[Recommend] = await Recommend.query().equal(code=code).order_by(Recommend.id.asc()).all()
        coords = []
        for r in recommends:
            if r.source == 0:
                coords.append(['R', r.create_time.strftime("%Y%m%d"), r.create_time.strftime("%Y-%m-%d %H:%M:%S"), r.price])
            if r.source == 1:
                coords.append(['B', r.create_time.strftime("%Y%m%d"), r.create_time.strftime("%Y-%m-%d %H:%M:%S"), r.price])
            if r.sale_price and r.sale_time:
                if r.sale_price < 0.1: continue
                if r.source == 1:
                    coords.append(['S', r.sale_time.strftime("%Y%m%d"), r.sale_time.strftime("%Y-%m-%d %H:%M:%S"), r.sale_price])
                else:
                    coords.append(['A', r.sale_time.strftime("%Y%m%d"), r.sale_time.strftime("%Y-%m-%d %H:%M:%S"), r.sale_price])
        if x[-1] != day:
            logger.info(f"No real data, start query read data - code: {code}")
            stockDo: dict = await calc_stock_real_data(code, site)
            if stockDo:
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
                macd.append(round((stockDo['diff'] - stockDo['dea']) * 2, 3))
                fund.append(stockDo['fund'])
                kdjk.append(round(stockDo['k'], 3))
                kdjd.append(round(stockDo['d'], 3))
                kdjj.append(round(stockDo['j'], 3))
                trix.append(round(stockDo['trix'], 3))
                trma.append(round(stockDo['trma'], 3))
                boll_up.append(stockDo['boll_up'])
                boll_low.append(stockDo['boll_low'])
        else:
            fund[-1] = await getStockZhuLiFundFromTencent(code)
        result.data = {
            'x': x, 'code': code, 'name': st.name, 'region': st.region, 'industry': st.industry, 'coord': coords,
            'price': data, 'volume': volume, 'qrr': qrr, 'turnover_rate': turnover_rate,
            'ma_five': ma_five, 'ma_ten': ma_ten, 'ma_twenty': ma_twenty, 'boll_up': boll_up,
            'diff': diff, 'dea': dea, 'macd': macd, 'fund': fund, 'concept': st.concept,
            'k': kdjk, 'd': kdjd, 'j': kdjj, 'trix': trix, 'trma': trma, 'boll_low': boll_low
        }
        result.total = len(result.data)
        logger.info(f"Query stock k-line success - code: {code}")
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
        logger.info(f"Query Stock Real Data List Success, params: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def queryRecommendStockList(source: int = 0, page: int = 1) -> Result:
    result = Result()
    pageSize = 20
    try:
        offset = (page - 1) * pageSize
        if source == 1:
            total_num: int = await Recommend.query().equal(source=source).count()
            stockInfo: list[Recommend] = await Recommend.query().equal(source=source).order_by(Recommend.create_time.desc()).offset(offset).limit(pageSize).all()
            stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo]
        elif source == 99:
            count_sql = """
                    select count(1) as total_num from (select code, sale_price, substr(create_time,1,10) as day from recommend where source=1) mm
                    left join (select code, sale_price, substr(create_time,1,10) as day from recommend where source!=1) aa on
                    mm.code=aa.code and mm.day=aa.day where aa.day is not null and aa.sale_price is not null and mm.sale_price is not null;
                """
            res_sql = """
                    select * from (
                    select aa.id, aa.code, aa.name, aa.create_time, aa.price, aa.sale_price as a_sale_price, aa.sale_time as a_sale_time, mm.sale_price as m_sale_price, mm.sale_time as m_sale_time, aa.content
                    from (select code, name, price, create_time, sale_price, sale_time, substr(create_time,1,10) as day from recommend where source=1) mm
                    left join (select id, code, name, price, create_time, sale_price, sale_time, content, substr(create_time,1,10) as day from recommend where source!=1) aa on
                    mm.code=aa.code and mm.day=aa.day where aa.day is not null and aa.sale_price is not null and mm.sale_price is not null) order by create_time desc limit :limit offset :offset;
                """
            res = await DBExecutor.execute_sql(count_sql)
            total_num: int = res[0].total_num
            res = await DBExecutor.execute_sql(res_sql, {"offset": offset, "limit": pageSize})
            stockList = [dict(r._mapping) for r in res]
        else:
            total_num: int = await Recommend.query().not_equal(source=1).count()
            stockInfo: list[Recommend] = await Recommend.query().not_equal(source=1).order_by(Recommend.create_time.desc()).offset(offset).limit(pageSize).all()
            if offset == 0:
                current_day = time.strftime("%Y-%m-%d") + " 09:20:20"
                stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo if f.sale_time and f.sale_time.strftime("%Y-%m-%d %H:%M:%S") > current_day] + \
                            [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo if not f.sale_time or f.sale_time.strftime("%Y-%m-%d %H:%M:%S") < current_day]
            else:
                stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo]
        result.total = total_num
        result.data = stockList
        logger.info("Query Recommend Stock List Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def deleteRecommendStock(rId: int) -> Result:
    result = Result()
    try:
        _ = await Recommend.query().equal(id=rId).delete()
        logger.info(f"Delete Recommend Stock {rId} Success ~")
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
        stocks: list[Recommend] = await Recommend.query().not_equal(source=1).order_by(Recommend.id.asc()).all()
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
            fflow = await getStockZhuLiFundFromTencent(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List_bak(stock_data)
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:30:00"
        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}，最新日期的所有数据都是截至当前时间实时计算出来的，不一定是一整天的数据，不能和其他日期的数据弄混了'
        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await queryAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, None, None, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"query AI suggestion successfully, code: {code}, result: {stock_dict}")
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
            fflow = await getStockZhuLiFundFromTencent(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List_bak(stock_data)
        if price and t:
            pass
        else:
            r: Recommend = await Recommend.query().equal(code=code).order_by(Recommend.id.desc()).first()
            price = r.price
            t = r.create_time.strftime("%Y-%m-%d")
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:00:00"
        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}，最新日期的所有数据都是截至当前时间实时计算出来的，不一定是一整天的数据，不能和其他日期的数据弄混了'
        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await queryAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, price, t, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"query AI suggestion successfully, code: {code}, result: {stock_dict}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def ai_sell(code: str, site: str = None) -> Result:
    '''Recommend list only'''
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
            fflow = await getStockZhuLiFundFromTencent(code)
            stock_data[0]['fund'] = fflow
        stock_data.reverse()
        post_data = detail2List_bak(stock_data)
        r: Recommend = await Recommend.query().equal(code=code).order_by(Recommend.id.desc()).first()
        price = r.price
        t = r.create_time.strftime("%Y-%m-%d %H:%M:%S")
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 15:30:00"
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        if current_time > open_date:
            current_time = open_date
        day_line: list[StockMinuteDo] = await getMinuteKFromTongHuaShun('', code, logger)
        stock_dict = await sellAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, price, t, json.dumps(post_data, ensure_ascii=False), json.dumps(minute2List(day_line), ensure_ascii=False), 'sellPrompt', logger)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"sell stock AI suggestion successfully, code: {code}, result: {stock_dict}")
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
        price_avg = []
        volume = []
        if site == 'sina':
            res: list[StockMinuteDo] = await getMinuteKFromSina('', code, logger)
        else:
            res: list[StockMinuteDo] = await getMinuteKFromTongHuaShun('', code, logger)
        for r in res:
            x.append(r.time)
            price.append(r.price)
            price_avg.append(r.price_avg)
            volume.append(r.volume)
        st = await Stock.get_one(code)
        result.data = {'x': x, 'price': price, 'price_avg': price_avg, 'volume': volume, 'code': code, 'name': st.name, 'region': st.region, 'industry': st.industry, 'concept': st.concept}
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
        logger.info(f"Query Stock List Success, params: {query}")
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
        logger.info(f"Query Hot Topic List Success, params: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_current_topic() -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        current_day = tool.value
        current_date = tool.update_time.strftime("%Y年%m月%d日")
        res = await webSearchTopicBak(API_URL, AUTH_CODE, current_date)
        print(res)
        file_path = os.path.join(FILE_PATH, f"{current_day}.txt")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(res)
        data = res.split("热点题材逻辑")[0].strip().split("点题材汇总")[1].replace(':', '').replace('：', '').strip().split("\n")[0]
        res_list = [r.replace('。', '').strip() for r in data.split(',')]
        try:
            tool: Tools = await Tools.get_one(current_day)
            await Tools.update(tool.key, value=',' .join(res_list))
        except NoResultFound:
            await Tools.create(key=current_day, value=',' .join(res_list))
        result.data = res
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


async def set_stock(data: SetStockParam) -> Result:
    result = Result()
    try:
        stock: Stock = await Stock.get_one(data.code)
        if data.operate_type == "setBuy":
            if not data.buy_time or not data.buy_price:
                raise
            date_obj = datetime.strptime(data.buy_time.replace("T", " ") + ":58", "%Y-%m-%d %H:%M:%S")
            await Recommend.create(code=stock.code, name=stock.name, price=float(data.buy_price), create_time=date_obj, source=1)
            logger.info(f"Set Stock Buy Success - {stock.code} - {stock.name} - {data.operate_type}")
        if data.operate_type == "setSale":
            if not data.buy_time or not data.buy_price:
                raise
            date_obj = datetime.strptime(data.buy_time.replace("T", " ") + ":58", "%Y-%m-%d %H:%M:%S")
            r: list[Recommend] = await Recommend.query().equal(code=stock.code, source=1).is_null('sale_price', 'sale_time').order_by(Recommend.id.desc()).all()
            await Recommend.update(r[0].id, sale_price=float(data.buy_price), sale_time=date_obj)
            if data.sell_empty == '1':
                for i in range(1, len(r)):
                    await Recommend.update(r[i].id, sale_price=0.0, sale_time=date_obj)
            logger.info(f"Set Stock Sale Success - {stock.code} - {stock.name} - {data.operate_type}")
        if data.operate_type == "addFilter":
            if not data.tag:
                raise
            await Stock.update(stock.code, filter=f"{stock.filter},{data.tag}")
            logger.info(f"Add Stock Label Success - {stock.code} - {stock.name} - {data.tag}")
        if data.operate_type == "delFilter":
            if not data.tag:
                raise
            filter_list = stock.filter.split(',')
            res_list = [r for r in filter_list if r != data.tag]
            await Stock.update(stock.code, filter=",".join(res_list))
            logger.info(f"Remove Stock Label Success - {stock.code} - {stock.name} - {data.tag}")
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
        logger.info(f"Query stock info success - {code}")
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
    if not res_stock['data']:
        return None
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
    stockDo.update({'fund': await getStockZhuLiFundFromTencent(code)})
    up, dn = bollinger_bands(stock_price[:20], calc_MA(stock_price, 20))
    stockDo.update({'boll_up': round(up, 2)})
    stockDo.update({'boll_low': round(dn, 2)})
    logger.info(stockDo)
    return stockDo


async def get_data_by_day(code: str, day: str) -> Result:
    result = Result()
    try:
        stock: list[Detail] = await Detail.query().equal(code=code).less_equal(day=day).order_by(Detail.day.desc()).limit(6).all()
        stock.reverse()
        result.data = detail2List(stock)
        logger.info(result.data)
    except:
        logger.error(traceback.format_exc())
    return result


async def test(code: str, day: str) -> Result:
    result = Result()
    try:
        s: list[Recommend] = await Recommend.query().is_null('last_one_price').all()
        result.data = [r.code for r in s]
        logger.info(result.data)
    except:
        logger.error(traceback.format_exc())
    return result


def detail2List_bak(data: list) -> dict:
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


def detail2List(data: list[Detail]) -> dict:
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
        res['volume'].append(d.volume)
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


def minute2List(data: list[StockMinuteDo]) -> dict:
    res = {'code': data[0].code, 'time': [], 'price': [], 'price_avg': [], 'volume': []}
    for d in data:
        res['time'].append(d.time)
        res['price'].append(d.price)
        res['price_avg'].append(d.price_avg)
        res['volume'].append(d.volume)
    return res


async def auto_sell_stock():
    try:
        now = datetime.now().time()
        start_time = datetime.strptime("11:30:00", "%H:%M:%S").time()
        end_time = datetime.strptime("13:00:00", "%H:%M:%S").time()
        if start_time <= now <= end_time:
            logger.info("Evaluate Sell Strategy - 中午休市, 暂不执行...")
        else:
            stock: list[Recommend] = await Recommend.query().not_equal(source=1).is_null('sale_price', 'sale_time').all()
            total_source = 3
            index = 0
            dealed_stock = []
            for s in stock:
                try:
                    if s.code in dealed_stock:
                        continue
                    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                    limit_up = getStockLimitUp(s.code, s.name)
                    stock_detail: list[Detail] = await Detail.query().equal(code=s.code).order_by(Detail.day.desc()).limit(10).all()
                    stock_detail.reverse()
                    selected = index % total_source
                    if selected == 0:
                        minute_detail: list[StockMinuteDo] = await getMinuteKFromSina("", s.code, logger)
                    elif selected == 1:
                        minute_detail: list[StockMinuteDo] = await getMinuteKFromDongcai("", s.code, logger)
                    else:
                        minute_detail: list[StockMinuteDo] = await getMinuteKFromTongHuaShun("", s.code, logger)
                    if len(minute_detail) < 3:
                        continue
                    minute_data = minute2List(minute_detail)
                    day_data = detail2List(stock_detail)
                    buy_time = s.create_time.strftime("%Y%m%d")
                    res = evaluate_sell_strategy(current_time, buy_time, s.price, day_data, minute_data, limit_up)
                    logger.info(f"Calc strategy - {s.code} - {s.name} - calc: {res}")
                    dealed_stock.append(s.code)
                    if res['action'] != 'HOLD':
                        if s.code in AI_DECIDE and time.time() - AI_DECIDE[s.code] < 1200:
                            continue
                        ai_res = await sellAI(API_URL, AI_MODEL25, AUTH_CODE, current_time, s.price, buy_time, json.dumps(day_data, ensure_ascii=False), json.dumps(minute_data, ensure_ascii=False), 'decidePrompt', logger)
                        if ai_res['sell']:
                            content = f"{s.content}LEE{res['reason']}/n/n{ai_res['reason']}"
                            await Recommend.update(s.id, sale_price=minute_detail[-1].price, sale_time=datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S"), content=content)
                            logger.info(f"Auto sell stock strategy - {s.code} - {s.name} - calc: {res} - AI: {ai_res}")
                            if s.code in AI_DECIDE:
                                del AI_DECIDE[s.code]
                        else:
                            AI_DECIDE.update({s.code: time.time()})
                            logger.info(f"Hold stock AI strategy - {s.code} - {s.name} - calc: {res} - AI: {ai_res}")
                except:
                    logger.error(f"Auto sell stock - {s.code} - {s.name}")
                    logger.error(traceback.format_exc())
                finally:
                    index += 1
                    asyncio.sleep(6)
    except:
        logger.error(traceback.format_exc())


async def start_auto_sell_stock():
    tool: Tools = await Tools.get_one("openDoor")
    current_day = tool.value
    if current_day == time.strftime("%Y%m%d"):
        scheduler.add_job(auto_sell_stock, "interval", minutes=5, next_run_time=datetime.now() + timedelta(seconds=9), id='auto_sell_stock')
        logger.info("start sell stock task ...")


async def stop_auto_sell_stock():
    if scheduler.get_job('auto_sell_stock'):
        scheduler.remove_job('auto_sell_stock')
        logger.info("stop sell stock task ...")
    else:
        logger.info("sell stock task is not exist or stopped ...")
