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
from utils.model import SearchStockParam, StockModelDo, StockDataList, StockMinuteDo, updateFundDo, TradeStockList
from utils.model import StockInfoList, RecommendStockDataList, ToolsInfoList, SetStockParam, SetStockHold
from utils.model import EtfInfoList
from utils.selectStock import getStockZhuLiFundFromTencent
from utils.ai_model import queryGemini, webSearchTopicBak, queryOpenAi, auto_sell_prompt
from utils.logging import logger
from utils.results import Result, getStockRegion
from utils.scheduler import scheduler
from utils.aiAnalyzer import AsyncETFAnalyzer
from utils.initData import initStockData, getStockFundFlow
from utils.webSearch import searchWithDuckDuckGo
from utils.queryStockHq import getStockHqFromTencent, getStockHqFromSina, getStockHqFromXueQiu
from utils.queryStockHq import getMinuteKFromTongHuaShun, getMinuteKFromDongcai, getMinuteKFromSina
from utils.metric import real_traded_minutes, bollinger_bands, getStockLimitUp, evaluate_sell_strategy
from utils.database import Recommend, Stock, Detail, Tools, DBExecutor, ETF, Transaction, TradeType
from settings import OPENAI_URL, OPENAI_KEY, OPENAI_MODEL, API_URL, AUTH_CODE, FILE_PATH, HISTORY_PATH


stock_fee_ratio = 1 / 10000   # 股票交易佣金，默认万分之一
etf_fee_ratio = 2.5 / 10000   # ETF交易佣金，默认万分之2.5
stamp_duty = 5 / 10000   # 印花税，默认万分之5
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


def calc_holding(status: str, price: float, number: int, cost: float = 0.0, shares: int = 0, fee: float = 0.0) -> dict:
    result = {}
    try:
        profit = 0.0
        if status == TradeType.BUY or status == TradeType.RECD:    # 建仓/加仓
            total_value = cost * shares + price * number + fee
            shares += number
            cost = round(total_value / shares, 6)
        else:    # 减仓/清仓
            if number > shares:
                raise Exception(f"卖出数量大于持仓数量, {number} > {shares} ...")
            profit = (price - cost) * number - fee
            shares -= number
            if shares != 0:
                cost = cost - (profit / shares)

        result = {'cost': cost, 'shares': shares, 'profit': profit}
        logger.debug(f"计算持仓数据成功, 操作: {status}, 数量: {price} - {number}, 最新成本: {cost} - {shares}")
    except:
        logger.error(traceback.format_exc())
    return result


async def get_holding(user_id: int = None, code: str = None, status: str = None) -> list[dict]:
    '''
    status: 默认所有, "M" - 手动操作, "A" - 自动操作
    '''
    async def get_holding_call(user_id: int, code: str, status: str):
        result = []
        try:
            filter = [TradeType.BUY, TradeType.SELL]
            trade_type = TradeType.MAN
            if status == "A":
                filter = [TradeType.RECD, TradeType.AIS]
                trade_type = TradeType.AUTO
            if user_id and code:
                rows = await Transaction.query().equal(code=code, user_id=user_id, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
            elif user_id and not code:
                rows = await Transaction.query().equal(user_id=user_id, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
            elif code and not user_id:
                rows = await Transaction.query().equal(code=code, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
            else:
                rows = await Transaction.query().equal(flag=0).isin(status=filter).select("user_id", "code").distinct().all()

            for r in rows:
                stock: list[Transaction] = await Transaction.query().equal(code=r[1], user_id=r[0], flag=0).isin(status=filter).order_by(Transaction.create_time.asc()).all()
                res = {'cost': 0.0, 'shares': 0, 'profit': 0.0}
                for s in stock:
                    res = calc_holding(s.status, s.price, s.shares, res['cost'], res['shares'], s.fee)
                if res['shares'] == 0:
                    await Transaction.create(code=stock[-1].code, name=stock[-1].name, price=s.price, shares=s.shares, status=trade_type,
                                             fee=round(res['profit'], 2), user_id=stock[-1].user_id, flag=1, create_time=stock[0].create_time)
                    for s in stock:
                        await Transaction.update(s.id, flag=1)
                    logger.info(f"{stock[-1].code} - {stock[-1].name} 已清仓, 盈利: {round(res['profit'], 2)}")
                else:
                    info = {'name': stock[-1].name, 'code': stock[-1].code, 'create_time': stock[0].create_time.strftime("%Y-%m-%d"),
                            'user_id': stock[-1].user_id, 'price': res['cost'], 'shares': res['shares'], 'profit': None, 'status': trade_type}
                    result.append(info)
        except:
            logger.error(traceback.format_exc())
        return result

    if status:
        return await get_holding_call(user_id, code, status)
    else:
        return await get_holding_call(user_id, code, "M") + await get_holding_call(user_id, code, "A")    # 手动操作和自动操作


async def run_command(command: str) -> str:
    """异步执行单个 shell 命令"""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    logger.info(f"Run Cmd {command} result is {stdout.decode('utf-8').strip()}")
    if process.returncode == 0:
        return stdout.decode('utf-8').strip()
    else:
        raise Exception(f"Error: {stderr.decode('utf-8').strip()}")


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
        total_shares = []
        premium = []
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
            total_shares.append(round(stockInfo[index].shares, 2))
            premium.append(round(stockInfo[index].premium, 2))
            boll_up.append(stockInfo[index].boll_up)
            boll_low.append(stockInfo[index].boll_low)
        if code.startswith('1') or code.startswith('5'):
            st: ETF = await ETF.get_one(code)
        else:
            st: Stock = await Stock.get_one(code)
        trans: list[Transaction] = await Transaction.query().equal(code=code).order_by(Transaction.id.asc()).all()
        coords = []
        for r in trans:
            logger.info(f"{r.status} - {TradeType.MAN}")
            if r.status != TradeType.MAN and r.status != TradeType.AUTO:
                coords.append([r.status, r.create_time.strftime("%Y%m%d"), r.price, r.shares, r.fee])
        profit_res = await get_holding(code=code)
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
                total_shares.append(round(stockDo['shares'], 2))
                premium.append(round(stockDo['premium'], 2))
                boll_up.append(stockDo['boll_up'])
                boll_low.append(stockDo['boll_low'])
        else:
            fund[-1] = await getStockZhuLiFundFromTencent(code)
        profit = round((data[-1][1] - profit_res[0]['price']) * profit_res[0]['shares'], 2) if profit_res else None
        cost = round(profit_res[0]['price'], 3) if profit_res else None
        shares = profit_res[0]['shares'] if profit_res else None
        result.data = {
            'x': x, 'code': code, 'name': st.name, 'industry': st.industry, 'coord': coords, 'total_shares': total_shares,
            'price': data, 'volume': volume, 'qrr': qrr, 'turnover_rate': turnover_rate, 'cost': cost,
            'ma_five': ma_five, 'ma_ten': ma_ten, 'ma_twenty': ma_twenty, 'boll_up': boll_up,
            'diff': diff, 'dea': dea, 'macd': macd, 'fund': fund, 'profit': profit, 'shares': shares,
            'k': kdjk, 'd': kdjd, 'j': kdjj, 'boll_low': boll_low, 'premium': premium
        }
        if not (code.startswith('1') or code.startswith('5')):
            result.data.update({'region': st.region, 'concept': st.concept})
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
        if query.day:
            day = query.day
        else:
            tool: Tools = await Tools.get_one("openDoor")
            day = tool.value
        if query.code:
            stockInfo: Detail = await Detail.get((query.code, day))
            stockList = [StockModelDo.model_validate(stockInfo).model_dump()] if stockInfo else []
        elif query.name:
            stockInfo: list[Detail] = await Detail.query().equal(day=day).like(name=query.name).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
        else:
            logger.info(query)
            offset = (query.page - 1) * query.pageSize
            total_num: int = await Detail.query().equal(day=day).count()
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
                todaySellStock: list[Recommend] = await Recommend.query().not_equal(source=1).greater(sale_time=current_day).all()
                stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in todaySellStock] + \
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
        r1, r1h, r1l, r2, r2h, r2l, r3, r3h, r3l, r4, r4h, r4l, r5, r5h, r5l, sale = 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        x = []
        y1, y1h, y1l, y2, y2h, y2l, y3, y3h, y3l, y4, y4h, y4l, y5, y5h, y5l, saleList = [], [], [], [], [], [], [], [], [], [], [], [], [], [], [], []
        stocks: list[Recommend] = await Recommend.query().not_equal(source=1).greater(create_time='2026-03-27 00:00:00').order_by(Recommend.id.asc()).all()
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
                saleList[index] = round(saleList[index] + init_fund * ((s.sale_price or s.price) - s.price) / s.price - coupon, 2)
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
                saleList.append(round(init_fund * ((s.sale_price or s.price) - s.price) / s.price - coupon, 2))
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
            sale += init_fund * ((s.sale_price or s.price) - s.price) / s.price - coupon

        result.data = {'r1': r1, 'r1h': r1h, 'r1l': r1l, 'r2': r2, 'r2h': r2h, 'r2l': r2l, 'r3': r3, 'r3h': r3h,
                       'r3l': r3l, 'r4': r4, 'r4h': r4h, 'r4l': r4l, 'r5': r5, 'r5h': r5h, 'r5l': r5l, 'x': x,
                       'y1': y1, 'y1h': y1h, 'y1l': y1l, 'y2': y2, 'y2h': y2h, 'y2l': y2l, 'y3': y3, 'y3h': y3h, 'sale': round(sale, 2),
                       'y3l': y3l, 'y4': y4, 'y4h': y4h, 'y4l': y4l, 'y5': y5, 'y5h': y5h, 'y5l': y5l, 'saleList': saleList}
    except:
        logger.error(traceback.format_exc())
        result.success = False
    return result


async def buy_stock(code: str, site: str = None, source: str = None, day: str = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        current_day = tool.value
        if day:
            day = day.replace('-', '')
        else:
            day = current_day
        stockList: list[Detail] = await Detail.query().equal(code=code).less_equal(day=day).order_by(Detail.day.desc()).limit(10).all()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
        is_stock = [item for item in stock_data if item['day'] == day]
        if not is_stock:
            logger.info(f"query newest data - {code}")
            stockDo: dict = await calc_stock_real_data(code, site)
            stock_data.insert(0, stockDo)
        else:
            if stock_data[0]['day'] == current_day:
                fflow = await getStockZhuLiFundFromTencent(code)
                stock_data[0]['fund'] = fflow
        stock_data.reverse()
        if source == 'shrink':
            stock_dict = await queryGemini(json.dumps(stock_data, ensure_ascii=False), API_URL, AUTH_CODE, 1)
        else:
            # post_data = detail2List_bak(stock_data)
            date_obj = datetime.strptime(day, "%Y%m%d")
            open_date = date_obj.strftime("%Y-%m-%d") + " 14:50:00"
            current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}, 所有数据都是截至当前时间实时计算出来的, 是盘中数据, 不是一整天的数据'
            if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
                current_time = open_date
            day_line = await getMinuteKFromTongHuaShun('', code, logger)
            prompt = f"当前时间是: {current_time} \n这只股票的最近10日天级数据是: {json.dumps(stock_data, ensure_ascii=False)} \n当天分钟级数据是: {json.dumps(minute2List(day_line), ensure_ascii=False)}"
            stock_dict = await queryGemini(prompt, API_URL, AUTH_CODE, 2)
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
        # post_data = detail2List_bak(stock_data)
        if price and t:
            pass
        else:
            r: Recommend = await Recommend.query().equal(code=code).not_equal(source=1).order_by(Recommend.id.desc()).first()
            price = r.price
            t = r.create_time.strftime("%Y-%m-%d")
        date_obj = datetime.strptime(day, "%Y%m%d")
        open_date = date_obj.strftime("%Y-%m-%d") + " 14:50:00"
        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}, 所有数据都是截至当前时间实时计算出来的, 是盘中数据, 不是一整天的数据'
        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
            current_time = open_date
        day_line = await getMinuteKFromTongHuaShun('', code, logger)
        prompt = f"当前时间是: {current_time} \n股票的买入时间是: {t} \n持仓成本是: {price} \n最近10日天级数据是: {json.dumps(stock_data, ensure_ascii=False)} \n当天分钟级数据是: {json.dumps(minute2List(day_line), ensure_ascii=False)}"
        stock_dict = await queryGemini(prompt, API_URL, AUTH_CODE, 4)
        result.data = stock_dict['reason'].replace("#", "").replace("*", "")
        logger.info(f"query AI suggestion successfully, code: {code}, result: {stock_dict}")
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

        result.data = {'x': x, 'price': price, 'price_avg': price_avg, 'volume': volume, 'code': code}
        if code.startswith('1') or code.startswith('5'):
            st: ETF = await ETF.get_one(code)
            result.data.update({'name': st.name, 'industry': st.industry})
        else:
            st: Stock = await Stock.get_one(code)
            result.data.update({'name': st.name, 'region': st.region, 'industry': st.industry, 'concept': st.concept})
        logger.info(f"query Recommend stock minute real data success - {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_current_price(code: str, site: str = None) -> Result:
    result = Result()
    try:
        try:
            res: list[StockMinuteDo] = await getMinuteKFromTongHuaShun('', code, logger)
            result.data = res[-1].price
        except IndexError:
            logger.error(f"query stock real data error, {traceback.format_exc}")
            res: list[StockMinuteDo] = await getMinuteKFromSina('', code, logger)
            result.data = res[-1].price
        logger.info(f"query current stock price success - {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def all_stock_info(query: SearchStockParam) -> Result:
    result = Result()
    try:
        etfList = []
        if query.code:
            stockInfo: Stock = await Stock.get(query.code)
            stockList = [StockInfoList.from_orm_format(stockInfo).model_dump()]
        elif query.name or query.region or query.industry or query.concept or query.filter:
            if query.filter == 'buy':
                hold_id_list = await get_holding()
                hold_stock_list = [r['code'] for r in hold_id_list]
                stockInfo: list[Stock] = await Stock.query().isin(code=hold_stock_list).all()
                etfInfo: list[ETF] = await ETF.query().isin(code=hold_stock_list).all()
                for f in etfInfo:
                    r = EtfInfoList.from_orm_format(f).model_dump()
                    r.update({'filter': None, 'region': r['capital'], 'concept': r['fee']})
                    etfList.append(r)
                logger.info(etfList)
            else:
                stockInfo: list[Stock] = await Stock.query().like(name=query.name, region=query.region, industry=query.industry, concept=query.concept, filter=query.filter).all()
            stockList = [StockInfoList.from_orm_format(f).model_dump() for f in stockInfo] + etfList
            result.total = len(stockList)
        else:
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


async def all_etf_info(query: SearchStockParam) -> Result:
    result = Result()
    try:
        if query.code:
            etfInfo: ETF = await ETF.get(query.code)
            etfList = [EtfInfoList.from_orm_format(etfInfo).model_dump()]
        elif query.filter == '1':
            if query.name or query.sortField:
                if query.sortField:
                    etfInfo: list[ETF] = await ETF.query().equal(running=int(query.filter)).like(name=query.name).order_by_key(ETF, query.sortField).all()
                else:
                    etfInfo: list[ETF] = await ETF.query().equal(running=int(query.filter)).like(name=query.name).all()
                result.total = len(etfInfo)
            else:
                offset = (query.page - 1) * query.pageSize
                total_num: int = await ETF.query().equal(running=int(query.filter)).count()
                etfInfo: list[ETF] = await ETF.query().equal(running=int(query.filter)).order_by(ETF.code.asc()).offset(offset).limit(query.pageSize).all()
                result.total = total_num
            etfList = [EtfInfoList.from_orm_format(f).model_dump() for f in etfInfo]
        else:
            if query.name or query.sortField:
                if query.sortField:
                    etfInfo: list[ETF] = await ETF.query().like(name=query.name).order_by_key(ETF, query.sortField).all()
                else:
                    etfInfo: list[ETF] = await ETF.query().like(name=query.name).all()
                result.total = len(etfInfo)
            else:
                offset = (query.page - 1) * query.pageSize
                total_num: int = await ETF.query().count()
                etfInfo: list[ETF] = await ETF.query().order_by(ETF.code.asc()).offset(offset).limit(query.pageSize).all()
                result.total = total_num
            etfList = [EtfInfoList.from_orm_format(f).model_dump() for f in etfInfo]
        result.data = etfList
        logger.info(f"Query ETF List Success, params: {query}")
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
                    await Recommend.update(r[i].id, sale_price=float(data.buy_price), sale_time=date_obj)
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
        if code.startswith('1') or code.startswith('5'):
            stock: ETF = await ETF.get_one(code)
        else:
            stock: Stock = await Stock.get_one(code)
        await initStockData(code, stock.name, logger)
        logger.info(f"初始化股票数据成功 - {code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def init_stock_fund_data(query: updateFundDo) -> Result:
    result = Result()
    try:
        stock: Stock = await Stock.get_one(query.code)
        await getStockFundFlow(query.code, query.cookie, logger)
        logger.info(f"更新股票主力资金数据成功 - {query.code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def calc_stock_real_data(code: str, site: str = None) -> dict:
    res_stock: dict = await getStockHqFromTencent('', [{code: "-", f"{code}count": 5}], logger)
    if not res_stock['data']:
        return None
    stockDo = StockModelDo.model_validate(res_stock['data'][0]).model_dump()
    stock_price_obj: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(21).all()
    stock_price = [r.current_price for r in stock_price_obj]
    high_price = [r.max_price for r in stock_price_obj]
    low_price = [r.min_price for r in stock_price_obj]
    stock_price.insert(0, stockDo['current_price'])
    high_price.insert(0, stockDo['max_price'])
    low_price.insert(0, stockDo['min_price'])
    real_trade_time = real_traded_minutes()
    volume_list = [r.volume for r in stock_price_obj[: 5]]
    volume_len = min(max(len(volume_list), 1), 5)
    emas = stock_price_obj[0].emas
    emal = stock_price_obj[0].emal
    dea = stock_price_obj[0].dea
    kdjk = stock_price_obj[0].kdjk
    kdjd = stock_price_obj[0].kdjd
    average_volume = (sum(volume_list) / volume_len) * (real_trade_time / 240)
    average_volume = average_volume if average_volume > 0 else stockDo['volume']
    macd = calc_macd(stockDo['current_price'], emas, emal, dea)
    kdj = calc_kdj(stockDo['current_price'], high_price, low_price, kdjk, kdjd)
    stockDo.update({'ma_five': calc_MA(stock_price, 5)})
    stockDo.update({'ma_ten': calc_MA(stock_price, 10)})
    stockDo.update({'ma_twenty': calc_MA(stock_price, 20)})
    stockDo.update({'qrr': round(stockDo['volume'] / average_volume, 2)})
    stockDo.update({'diff': macd['emas'] - macd['emal']})
    stockDo.update({'dea': macd['dea']})
    stockDo.update({'k': kdj['k']})
    stockDo.update({'d': kdj['d']})
    stockDo.update({'j': kdj['j']})
    stockDo.update({'volume': stockDo['volume']})
    stockDo.update({'shares': stockDo['shares']})
    stockDo.update({'premium': stockDo['premium']})
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


async def get_user_hold(userId: str) -> Result:
    result = Result()
    try:
        stockList = await get_holding(user_id=userId)
        result.data = [f for f in stockList if f['code'] not in ['603167', '000651']]
        result.total = len(result.data)
        logger.info(f"查询用户{userId} 持仓：{result.data}")
    except:
        result.success = False
        logger.error(traceback.format_exc())
    return result


async def set_user_hold(data: SetStockHold) -> Result:
    result = Result()
    try:
        fee = 0
        if data.code.startswith('1') or data.code.startswith('5'):
            stock: ETF = await ETF.get_one(data.code)
            fee = max((data.price * data.number) * etf_fee_ratio, 5)
        else:
            stock: Stock = await Stock.get_one(data.code)
            fee = max((data.price * data.number) * stock_fee_ratio, 5)
            if data.status == 0:
                fee += (data.price * data.number) * stamp_duty

        date_obj = datetime.strptime(data.time.replace("T", " ") + ":00", "%Y-%m-%d %H:%M:%S")
        status = TradeType.SELL if data.status == 0 else TradeType.BUY
        await Transaction.create(code=data.code, name=stock.name, price=data.price, shares=data.number, status=status,
                                 fee=round(fee, 2), user_id=data.userId, create_time=date_obj, flag=0)
        logger.info(f"设置用户交易数据成功, 用户: {data.userId}, 股票: {data.code}, 数据: {data}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


# async def set_hold_ai_text(data: SetStockAiText) -> Result:
#     result = Result()
#     try:
#         stock = await Transaction.get_one(data.id)
#         await Transaction.update(stock.id, content=data.content)
#         logger.info(f"设置买入股票分析内容成功, 用户: {stock.user_id}, 股票: {stock.code} - {stock.name}, 内容: {data.content}")
#     except Exception as e:
#         logger.error(traceback.format_exc())
#         result.success = False
#         result.msg = str(e)
#     return result


async def queryTradeStockList(page: int = 1) -> Result:
    result = Result()
    pageSize = 20
    try:
        offset = (page - 1) * pageSize
        total_num: int = await Transaction.query().equal(status=TradeType.MAN).count()
        stockInfo: list[Transaction] = await Transaction.query().equal(status=TradeType.MAN).order_by(Transaction.create_time.desc()).offset(offset).limit(pageSize).all()
        stockList = [TradeStockList.from_orm_format(f).model_dump() for f in stockInfo]
        result.total = total_num
        result.data = stockList
        logger.info("Query Hold Stock List Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


# async def getHoldAiText(rId: int) -> Result:
#     result = Result()
#     try:
#         stock = await Transaction.get_one(rId)
#         result.data = stock.content
#         logger.info(f"get Hold Stock AI text {rId} - {stock.code} - {stock.name} Success ~")
#     except Exception as e:
#         logger.error(traceback.format_exc())
#         result.success = False
#         result.msg = str(e)
#     return result


async def deleteHoldStock(rId: int) -> Result:
    result = Result()
    try:
        _ = await Transaction.query().equal(id=rId).delete()
        logger.info(f"Delete Hold Stock {rId} Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def deleteEtf(code: str) -> Result:
    result = Result()
    try:
        _ = await ETF.query().equal(code=code).delete()
        logger.info(f"Delete ETF {code} Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def setEtf(code: str, running: int) -> Result:
    result = Result()
    try:
        _ = await ETF.get_one(code)
        await ETF.update(code, running=running)
        logger.info(f"Update ETF {code} Running Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def getEtf() -> Result:
    result = Result()
    try:
        text = ''
        index = 1
        etfInfo: list[ETF] = await ETF.query().equal(running=1).all()
        for r in etfInfo:
            text += f"{index}. 名称:{r.name}, 代码:{r.code}\n"
            index += 1
        result.data = text
        logger.info("Query ETF data Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def test(code: ToolsInfoList) -> Result:
    result = Result()
    try:
        await Recommend.update(int(code.key), content=code.value)
        logger.info(f"{code}")
    except:
        logger.error(traceback.format_exc())
    return result


def detail2List_bak(data: list) -> dict:
    res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
           'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
           'd': [], 'j': [], 'shares': [], 'premium': [], 'boll_up': [], 'boll_low': []}
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
        res['shares'].append(round(d['shares'], 2))
        res['premium'].append(round(d['premium'], 2))
        res['boll_up'].append(d['boll_up'])
        res['boll_low'].append(d['boll_low'])
    return res


def detail2List(data: list[Detail]) -> dict:
    res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
           'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
           'd': [], 'j': [], 'shares': [], 'premium': [], 'boll_up': [], 'boll_low': []}
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
        res['shares'].append(round(d.shares, 2))
        res['premium'].append(round(d.premium, 2))
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
            tool: Tools = await Tools.get_one("openDoor")
            day = tool.value
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
                    stock_detail: list[Detail] = await Detail.query().equal(code=s.code).order_by(Detail.day.desc()).limit(15).all()
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
                        date_obj = datetime.strptime(day, "%Y%m%d")
                        open_date = date_obj.strftime("%Y-%m-%d") + " 14:50:00"
                        current_time = f'{time.strftime("%Y-%m-%d %H:%M:%S")}, 所有数据都是截至当前时间实时计算出来的, 是盘中数据, 不是一整天的数据'
                        if time.strftime("%Y-%m-%d %H:%M:%S") > open_date:
                            current_time = open_date
                        prompt = f"当前时间是: {current_time} \n股票的买入时间是: {buy_time} \n持仓成本是: {s.price} \n最近10日天级数据是: {json.dumps(day_data, ensure_ascii=False)} \n当天分钟级数据是: {json.dumps(minute_data, ensure_ascii=False)}"
                        ai_res = await queryGemini(prompt, API_URL, AUTH_CODE, 3)
                        if ai_res['sell']:
                            content = f"{s.content}LEE{res['reason']}\n\n{ai_res['reason']}"
                            await Recommend.update(s.id, sale_price=minute_detail[-1].price, sale_time=datetime.now(), content=content)
                            logger.info(f"Auto sell stock strategy - {s.code} - {s.name} - calc: {res} - AI: {ai_res}")
                            if s.code in AI_DECIDE:
                                del AI_DECIDE[s.code]
                            history_file = os.path.join(HISTORY_PATH, s.code + "-sell.txt")
                            history_txt = f"#这是卖出系统提示词:\n{auto_sell_prompt} \n\n#这是股票数据:\n{prompt}\n\n#这是你识别出来的卖出决策:\n{ai_res['reason']}"
                            with open(history_file, 'w', encoding='utf-8') as f:
                                f.write(history_txt)
                        else:
                            AI_DECIDE.update({s.code: time.time()})
                            logger.info(f"Hold stock AI strategy - {s.code} - {s.name} - calc: {res} - AI: {ai_res}")
                except:
                    logger.error(f"Auto sell stock - {s.code} - {s.name}")
                    logger.error(traceback.format_exc())
                finally:
                    index += 1
                    asyncio.sleep(6)
        await get_holding()
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

    scheduler.add_job(get_holding, "date", run_date=datetime.now() + timedelta(seconds=3600))


async def queryByCodeForAI(code: str, limit: int = 20) -> Result:
    result = Result()
    try:
        if not limit:
            limit = 20
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockInfo: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(limit).all()
        stockInfo.reverse()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockInfo]

        if stockInfo[-1].day != day:
            logger.info(f"No real data, start query read data - code: {code}")
            stockDo: dict = await calc_stock_real_data(code, None)
            if stockDo:
                today = {'code': code, 'name': '', 'day': day, 'current_price': stockDo['current_price'], 'last_price': 0,
                         'open_price': stockDo['open_price'], 'max_price': stockDo['max_price'], 'min_price': stockDo['min_price'],
                         'volume': stockDo['volume'], 'fund': stockDo['fund'], 'ma_five': stockDo['ma_five'], 'ma_ten': stockDo['ma_ten'],
                         'ma_twenty': stockDo['ma_twenty'], 'qrr': stockDo['qrr'], 'diff': round(stockDo['diff'], 3), 'dea': round(stockDo['dea'], 3),
                         'k': round(stockDo['k'], 3), 'd': round(stockDo['d'], 3), 'j': round(stockDo['j'], 3), 'shares': round(stockDo['shares'], 2),
                         'premium': round(stockDo['premium'], 2), 'turnover_rate': stockDo['turnover_rate'], 'boll_up': stockDo['boll_up'],
                         'boll_low': stockDo['boll_low']}  # , 'macd': round((stockDo['diff'] - stockDo['dea']) * 2, 3)}
                stock_data.append(today)
        for s in stock_data:
            s.pop('code', None)
            s.pop('name', None)
            s.pop('last_price', None)
            s.pop('shares', None)
            s.pop('premium', None)
        result.data = stock_data
        logger.info(f"Query AI stock k-line success - code: {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def webSearch(q: str, df: str) -> Result:
    result = Result()
    try:
        result.data = await searchWithDuckDuckGo(q, logger=logger, df=df, max_results=5)
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = f"Search Exception: {str(e)}"
    return result


async def analysize(code: str, limit: int) -> Result:
    result = Result()
    try:
        isEtf = code.startswith("1") or code.startswith("5")
        if isEtf:
            stock: ETF = await ETF.get_one(code)
        else:
            stock: Stock = await Stock.get_one(code)
        res: Result = await queryByCodeForAI(code, limit)
        if not res.success:
            logger.error(f"Get K-line Error: code:{code}, {res.msg}")
            return res
        hold = await get_holding(user_id=1, code=stock.code)
        hold[0]['code'] = f"{stock.code}.{getStockRegion(stock.code).upper()}"
        user_input = {
            "type": "etf" if isEtf else "stock",
            "name": stock.name,
            "code": f"{stock.code}.{getStockRegion(stock.code).upper()}",
            "industry": stock.name.split("ETF")[0] if isEtf else stock.industry,
            "concept": "" if isEtf else stock.concept,
            "stocks": stock.stocks if isEtf else "",
            "k_line": json.dumps(res.data, ensure_ascii=False),
            "hold": hold[0]
        }
        analyzer = AsyncETFAnalyzer(input_data=user_input)
        result = await analyzer.analyze()
    except:
        logger.error(traceback.format_exc())
        result.success = False
    return result
