#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
import logging
import asyncio
import traceback
from datetime import datetime, timedelta
from utils.model import SearchStockParam, StockModelDo, StockDataList, StockMinuteDo, updateFundDo
from utils.model import StockInfoList, ToolsInfoList, SetStockParam, TradeRecordList
from utils.model import EtfInfoList, TradeStockList, SetStockHold, AnalysisResultList
from utils.selectStock import getStockZhuLiFundFromTencent, isOpenStock
from utils.results import Result
from utils.send_email import sendEmail
from utils.etfData import pre_filter_etf
from utils.scheduler import scheduler, get_schedule_time
from utils.aiAnalyzer import AsyncETFAnalyzer, analyze_etf_from_news, analyze_buy_etf
from utils.initData import initStockData, getStockFundFlow
from utils.queryStockHq import getStockHqFromTencent, getStockHq
from utils.queryStockHq import getMinuteKFromTongHuaShun, getMinuteKFromDongcai, getMinuteKFromSina
from utils.metric import real_traded_minutes, bollinger_bands
from utils.database import Stock, Detail, Tools, ETF, Transaction, TradeType, Capital, Analysis
from settings import DEFAULT_USER_ID, EMAIL_TEMPLATE, EXCLUSIVE_ETF_LIST, TOTAL_FUND
import aiofiles


logger = logging.getLogger(__name__)
stock_fee_ratio = 1 / 10000   # 股票交易佣金，默认万分之一，不免5
etf_fee_ratio = 2.5 / 10000   # ETF交易佣金，默认万分之2.5，不免5
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
    """计算持仓\n
    :params status: 方向，买入 or 卖出
    :params price: 本次交易的价格
    :params number: 本次交易的股数
    :params cost: 当前持仓成本
    :params shares: 当前持仓股数
    :params fee: 本次交易费用"""
    result = {}
    try:
        profit = 0.0
        if status == TradeType.BUY or status == TradeType.RECD:    # 建仓/加仓
            total_value = cost * shares + price * number + fee
            shares += number
            cost = round(total_value / shares, 6)
            profit = (price - cost) * shares
        else:    # 减仓/清仓
            if number > shares:
                raise Exception(f"卖出数量大于持仓数量, {number} > {shares} ...")
            profit = (price - cost) * number - fee
            shares -= number
            if shares != 0:
                cost = cost - (profit / shares)

        result = {'cost': cost, 'shares': shares, 'profit': profit}
    except:
        logger.error(traceback.format_exc())
    return result


async def get_holding(user_id: int = None, code: str = None) -> list[dict]:
    '''获取持仓的数据，更新已清仓的数据

    :params user_id: 用户id, 默认用户 99, DEFAULT_USER_ID
    :params code: 股票代码
    '''
    result = []
    try:
        filter = [TradeType.RECD, TradeType.AIS] if user_id == DEFAULT_USER_ID else [TradeType.BUY, TradeType.SELL]
        if user_id is not None and code:
            rows = await Transaction.query().equal(code=code, user_id=user_id, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
        elif user_id is not None and not code:
            rows = await Transaction.query().equal(user_id=user_id, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
        elif code and user_id is None:
            filter = [TradeType.BUY, TradeType.SELL, TradeType.RECD, TradeType.AIS]
            rows = await Transaction.query().equal(code=code, flag=0).isin(status=filter).select("user_id", "code").distinct().all()
        else:
            filter = [TradeType.BUY, TradeType.SELL, TradeType.RECD, TradeType.AIS]
            rows = await Transaction.query().equal(flag=0).isin(status=filter).select("user_id", "code").distinct().all()

        for r in rows:
            try:
                filter = [TradeType.RECD, TradeType.AIS] if r[0] == DEFAULT_USER_ID else [TradeType.BUY, TradeType.SELL]
                trade_type = TradeType.AUTO if r[0] == DEFAULT_USER_ID else TradeType.MAN
                stock: list[Transaction] = await Transaction.query().equal(code=r[1], user_id=r[0], flag=0).isin(status=filter).order_by(Transaction.create_time.asc()).all()
                res = {'cost': 0.0, 'shares': 0, 'profit': 0.0}
                for s in stock:
                    if s.status == TradeType.FAIL:
                        continue
                    res = calc_holding(s.status, s.price, s.shares, res['cost'], res['shares'], s.fee)
                if res['shares'] == 0:
                    await Transaction.create(code=stock[-1].code, name=stock[-1].name, price=s.price, shares=s.shares, status=trade_type,
                                             fee=round(res['profit'], 2), user_id=stock[-1].user_id, flag=1, create_time=stock[0].create_time)

                    await Transaction.query().equal(code=r[1], user_id=r[0], flag=0).isin(status=filter).update(flag=1)
                    logger.info(f"{stock[-1].code} - {stock[-1].name} 已清仓, 盈利: {round(res['profit'], 2)}")
                else:
                    info = {'name': stock[-1].name, 'code': stock[-1].code, 'create_time': stock[0].create_time.strftime("%Y-%m-%d"),
                            'user_id': stock[-1].user_id, 'price': res['cost'], 'shares': res['shares'], 'profit': res['profit'], 'status': trade_type}
                    result.append(info)
                    logger.info(f"{stock[-1].code} - {stock[-1].name} - {res}")
            except:
                logger.error(f"{r} - {traceback.format_exc()}")
    except:
        logger.error(f"{user_id} - {code} - {traceback.format_exc()}")
    return result


async def queryByCode(code: str, userId: int = None) -> Result:
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        isEtf = code.startswith("1") or code.startswith("5")
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
            total_shares.append(round(stockInfo[index].shares, 2) if isEtf else None)
            premium.append(round(stockInfo[index].premium, 2) if isEtf else None)
            boll_up.append(stockInfo[index].boll_up)
            boll_low.append(stockInfo[index].boll_low)
        if isEtf:
            st: ETF = await ETF.get_one(code)
        else:
            st: Stock = await Stock.get_one(code)
        trans: list[Transaction] = await Transaction.query().equal(code=code, user_id=userId).order_by(Transaction.id.asc()).all()
        coords = []
        for r in trans:
            if r.status in [TradeType.BUY, TradeType.SELL, TradeType.RECD, TradeType.AIS]:
                coords.append([r.status, r.create_time.strftime("%Y%m%d"), r.price, r.shares, r.fee])
        profit_res = await get_holding(user_id=userId, code=code)
        if x[-1] != day:
            logger.info(f"No real data, start query read data - code: {code}")
            stockDo: dict = await calc_stock_real_data(code)
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
                total_shares.append(round(stockDo['shares'], 2) if isEtf else None)
                premium.append(round(stockDo['premium'], 2) if isEtf else None)
                boll_up.append(stockDo['boll_up'])
                boll_low.append(stockDo['boll_low'])
        else:
            fund[-1] = await getStockZhuLiFundFromTencent(code)
        profit = round((data[-1][1] - profit_res[0]['price']) * profit_res[0]['shares'], 2) if profit_res else None
        cost = round(profit_res[0]['price'], 3) if profit_res else None
        shares = profit_res[0]['shares'] if profit_res else None
        result.data = {
            'x': x, 'code': code, 'name': st.name, 'industry': st.industry, 'coord': coords, 'total_shares': total_shares if isEtf else None,
            'price': data, 'volume': volume, 'qrr': qrr, 'turnover_rate': turnover_rate, 'cost': cost,
            'ma_five': ma_five, 'ma_ten': ma_ten, 'ma_twenty': ma_twenty, 'boll_up': boll_up,
            'diff': diff, 'dea': dea, 'macd': macd, 'fund': fund, 'profit': profit, 'shares': shares,
            'k': kdjk, 'd': kdjd, 'j': kdjj, 'boll_low': boll_low, 'premium': premium if isEtf else None
        }
        if not isEtf:
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


async def calc_stock_real(code: str) -> Result:
    result = Result()
    try:
        x = []
        price = []
        price_avg = []
        volume = []
        res: list[StockMinuteDo] = await getMinuteKFromSina('', code)
        if not res:
            res: list[StockMinuteDo] = await getMinuteKFromDongcai(code)
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


async def all_stock_info(query: SearchStockParam) -> Result:
    result = Result()
    try:
        etfList = []
        if query.code:
            stockInfo: Stock = await Stock.get(query.code)
            stockList = [StockInfoList.from_orm_format(stockInfo).model_dump()]
        elif query.name or query.region or query.industry or query.concept or query.filter:
            if query.filter == 'buy':
                hold_id_list = await get_holding(user_id=query.userId)
                hold_stock_list = [r['code'] for r in hold_id_list]
                stockInfo: list[Stock] = await Stock.query().isin(code=hold_stock_list).all()
                etfInfo: list[ETF] = await ETF.query().isin(code=hold_stock_list).all()
                for f in etfInfo:
                    r = EtfInfoList.from_orm_format(f).model_dump()
                    r.update({'filter': None, 'region': r['capital'], 'concept': json.dumps(r['stocks'], ensure_ascii=False)})
                    etfList.append(r)
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


async def set_stock(data: SetStockParam) -> Result:
    result = Result()
    try:
        stock: Stock = await Stock.get_one(data.code)
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


async def init_stock_data(code: str) -> Result:
    result = Result()
    try:
        if code.startswith('1') or code.startswith('5'):
            stock: ETF = await ETF.get_one(code)
        else:
            stock: Stock = await Stock.get_one(code)
        await initStockData(code, stock.name)
        logger.info(f"初始化股票数据成功 - {code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def init_stock_fund_data(query: updateFundDo) -> Result:
    result = Result()
    try:
        if query.code.startswith('1') or query.code.startswith('5'):
            stock: ETF = await ETF.get_one(query.code)
        else:
            stock: Stock = await Stock.get_one(query.code)
        await getStockFundFlow(query.code, query.cookie)
        logger.info(f"更新股票主力资金数据成功 - {query.code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def calc_stock_real_data(code: str) -> dict:
    isEtf = code.startswith('1') or code.startswith('5')
    if isEtf:
        res_stock: dict = await getStockHqFromTencent('', [{code: "-", f"{code}count": 5}])
    else:
        res_stock: dict = await getStockHq('', [{code: "-", f"{code}count": 5}])
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
    stockDo.update({'shares': stockDo['shares'] if isEtf else 0})
    stockDo.update({'premium': stockDo['premium'] if isEtf else 0})
    stockDo.update({'fund': await getStockZhuLiFundFromTencent(code)})
    up, dn = bollinger_bands(stock_price[:20], calc_MA(stock_price, 20))
    stockDo.update({'boll_up': round(up, 2)})
    stockDo.update({'boll_low': round(dn, 2)})
    logger.info(stockDo)
    return stockDo


async def get_user_hold(userId: str) -> Result:
    result = Result()
    try:
        stockList = await get_holding(user_id=userId)
        result.data = [f for f in stockList if f['code'] not in ['603167', '000651']]
        result.total = len(result.data)
        logger.info(f"查询用户{userId} 持仓：{result.data}")
    except Exception as e:
        result.success = False
        result.msg = str(e)
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


async def queryTradeStockList(userId: int = None, page: int = 1) -> Result:
    result = Result()
    pageSize = 20
    try:
        offset = (page - 1) * pageSize
        filter = TradeType.AUTO if userId == DEFAULT_USER_ID else TradeType.MAN
        total_num: int = await Transaction.query().equal(user_id=userId, status=filter).count()
        stockInfo: list[Transaction] = await Transaction.query().equal(user_id=userId, status=filter).order_by(Transaction.create_time.desc()).offset(offset).limit(pageSize).all()
        stockList = [TradeStockList.from_orm_format(f).model_dump() for f in stockInfo]
        result.total = total_num
        result.data = stockList
        logger.info("Query Hold Stock List Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


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
        exclude = ['513500', '159941', '159501', '159659']    # 排除 标普500ETF、纳指100ETF
        index = []
        etfInfo: list[ETF] = await ETF.query().equal(running=1).notin(code=exclude).order_by(ETF.capital.desc()).all()
        for r in etfInfo:
            index.append({"名称": r.name, "代码": r.code, "跟踪指数": r.industry})
        result.data = index
        logger.info("Query ETF data Success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def getTradeData() -> Result:
    result = Result()
    try:
        res = await get_today_hold()

        capital: list[Capital] = await Capital.query().order_by(Capital.day.asc()).all()
        day = []
        ratio = []
        hs = []
        pre_value = capital[0].total
        pre_value_hs = capital[0].campare
        for r in capital:
            ra = (r.total - pre_value) / pre_value * 100
            hs_ra = (r.campare - pre_value_hs) / pre_value_hs * 100
            day.append(r.day)
            ratio.append(round(ra, 2))
            hs.append(round(hs_ra, 2))
        profit = round((capital[-1].total - TOTAL_FUND) / TOTAL_FUND * 100, 2)
        result.data = {'todayList': res['todayList'], 'holdList': res['holdList'], 'day': day, 'ratio': ratio, 'hs': hs, 'profit': profit,
                       'currentDay': capital[-1].day, 'total': capital[-1].total, 'available': capital[-1].available, 'hold': capital[-1].hold}
        logger.info("query trade data success ~")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def get_today_hold() -> dict:
    tools: Tools = await Tools.get_one("openDoor")
    current_day = f"{tools.value[:4]}-{tools.value[4:6]}-{tools.value[6:]}"
    if time.strftime("%H:%M:%S") < "09:35:00" and time.strftime("%H:%M:%S") > "09:00:00":  # 已分析但未买入
        current_day = time.strftime("%Y-%m-%d")
        status = [TradeType.TEMB, TradeType.TEMS, TradeType.FAIL]
        today: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID).isin(status=status).all()
    else:
        status = [TradeType.RECD, TradeType.AIS, TradeType.FAIL]
        today: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID).isin(status=status).greater(create_time=current_day + " 08:00:00").all()
    todayList = [TradeStockList.from_orm_format(f).model_dump() for f in today]
    holdList = await get_holding(user_id=DEFAULT_USER_ID)
    for h in holdList:
        detail: Detail = await Detail.query().equal(code=h['code']).order_by(Detail.day.desc()).first()
        h['price'] = round(h['price'], 3)
        h['profit'] = round((detail.current_price - h['price']) * h['shares'], 2)
    return {'todayList': todayList, 'holdList': holdList}


async def test(code: ToolsInfoList) -> Result:
    result = Result()
    try:
        logger.info(f"{code}")
    except:
        logger.error(traceback.format_exc())
    return result


# def detail2List_bak(data: list) -> dict:
#     res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
#            'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
#            'd': [], 'j': [], 'shares': [], 'premium': [], 'boll_up': [], 'boll_low': []}
#     for d in data:
#         res['code'] = d['code']
#         res['day'].append(d['day'])
#         res['current_price'].append(d['current_price'])
#         res['last_price'].append(d['last_price'])
#         res['open_price'].append(d['open_price'])
#         res['max_price'].append(d['max_price'])
#         res['min_price'].append(d['min_price'])
#         res['volume'].append(d['volume'])
#         res['turnover_rate'].append(f"{d['turnover_rate']}%")
#         res['fund'].append(d['fund'])
#         res['ma_five'].append(d['ma_five'])
#         res['ma_ten'].append(d['ma_ten'])
#         res['ma_twenty'].append(d['ma_twenty'])
#         res['qrr'].append(d['qrr'])
#         res['diff'].append(round(d['diff'], 4))
#         res['dea'].append(round(d['dea'], 4))
#         res['k'].append(round(d['k'], 4))
#         res['d'].append(round(d['d'], 4))
#         res['j'].append(round(d['j'], 4))
#         res['shares'].append(round(d['shares'], 2))
#         res['premium'].append(round(d['premium'], 2))
#         res['boll_up'].append(d['boll_up'])
#         res['boll_low'].append(d['boll_low'])
#     return res


# def detail2List(data: list[Detail]) -> dict:
#     res = {'code': '', 'day': [], 'current_price': [], 'last_price': [], 'open_price': [], 'max_price': [], 'min_price': [], 'volume': [],
#            'turnover_rate': [], 'fund': [], 'ma_five': [], 'ma_ten': [], 'ma_twenty': [], 'qrr': [], 'diff': [], 'dea': [], 'k': [],
#            'd': [], 'j': [], 'shares': [], 'premium': [], 'boll_up': [], 'boll_low': []}
#     for d in data:
#         res['code'] = d.code
#         res['day'].append(d.day)
#         res['current_price'].append(d.current_price)
#         res['last_price'].append(d.last_price)
#         res['open_price'].append(d.open_price)
#         res['max_price'].append(d.max_price)
#         res['min_price'].append(d.min_price)
#         res['volume'].append(d.volume)
#         res['turnover_rate'].append(f"{d.turnover_rate}%")
#         res['fund'].append(d.fund)
#         res['ma_five'].append(d.ma_five)
#         res['ma_ten'].append(d.ma_ten)
#         res['ma_twenty'].append(d.ma_twenty)
#         res['qrr'].append(d.qrr)
#         res['diff'].append(round(d.emas - d.emal, 4))
#         res['dea'].append(round(d.dea, 4))
#         res['k'].append(round(d.kdjk, 4))
#         res['d'].append(round(d.kdjd, 4))
#         res['j'].append(round(d.kdjj, 4))
#         res['shares'].append(round(d.shares, 2))
#         res['premium'].append(round(d.premium, 2))
#         res['boll_up'].append(d.boll_up)
#         res['boll_low'].append(d.boll_low)
#     return res


# def minute2List(data: list[StockMinuteDo]) -> dict:
#     res = {'code': data[0].code, 'time': [], 'price': [], 'price_avg': [], 'volume': []}
#     for d in data:
#         res['time'].append(d.time)
#         res['price'].append(d.price)
#         res['price_avg'].append(d.price_avg)
#         res['volume'].append(d.volume)
#     return res


async def queryByCodeForAI(code: str, limit: int = 22) -> Result:
    """ 查询K线数据, 只用于AI分析
    :params code: 标的code
    :params limit: 查询多少天的数据
    """
    result = Result()
    try:
        if not limit:
            limit = 22
        isEtf = code.startswith("1") or code.startswith("5")
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockInfo: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(limit).all()
        stockInfo.reverse()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockInfo]

        if stockInfo[-1].day != day:
            logger.info(f"No real data, start query read data - code: {code}")
            stockDo: dict = await calc_stock_real_data(code)
            if stockDo:
                today = {'code': code, 'name': '', 'day': day, 'current_price': stockDo['current_price'], 'last_price': 0,
                         'open_price': stockDo['open_price'], 'max_price': stockDo['max_price'], 'min_price': stockDo['min_price'],
                         'volume': stockDo['volume'], 'fund': stockDo['fund'], 'ma_five': stockDo['ma_five'], 'ma_ten': stockDo['ma_ten'],
                         'ma_twenty': stockDo['ma_twenty'], 'qrr': stockDo['qrr'], 'diff': round(stockDo['diff'], 3), 'dea': round(stockDo['dea'], 3),
                         'k': round(stockDo['k'], 3), 'd': round(stockDo['d'], 3), 'j': round(stockDo['j'], 3), 'shares': round(stockDo['shares'], 2),
                         'premium': round(stockDo['premium'], 2), 'turnover_rate': stockDo['turnover_rate'], 'boll_up': stockDo['boll_up'],
                         'boll_low': stockDo['boll_low']}  # , 'macd': round((stockDo['diff'] - stockDo['dea']) * 2, 3)}
                stock_data.append(today)
        pre_shares = stock_data[0]['shares']
        for s in stock_data:
            s.pop('code', None)
            s.pop('name', None)
            if isEtf:
                # 在A股ETF单边暴涨/暴跌时，KDJ和MACD会严重钝化，主力资金净流入极具欺骗性
                curr_shares = s['shares']
                shares_delta = (curr_shares - pre_shares) / pre_shares * 100
                s.update({"shares_delta": round(shares_delta, 2)})
                pre_shares = curr_shares
                s.pop('k', None)
                s.pop('d', None)
                s.pop('j', None)
                s.pop('diff', None)
                s.pop('dea', None)
                s.pop('fund', None)
            else:
                s.pop('shares', None)
                s.pop('premium', None)
        result.data = stock_data
        logger.info(f"Query AI stock k-line success - code: {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def analysizeEtfFromNews() -> Result:
    """从财经新闻中筛选出ETF"""
    result = Result()
    try:
        res = await getEtf()
        tool = await Tools.get_one("openDoor")
        open_time = tool.value
        lastDay = f"{open_time[:4]}-{open_time[4:6]}-{open_time[6:]} 16:00:00"
        resp = await analyze_etf_from_news(res.data, lastDay)
        result.data = resp
        logger.info(f"从新闻中提取出的ETF结果 {resp}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def getAnalysizeResult(code: str, day: str = None) -> Result:
    """获取 AI 分析结, day的格式是: %Y%m%d"""
    result = Result()
    try:
        if day:
            datas: list[Analysis] = await Analysis.query().equal(code=code, day=day).all()
        else:
            trade: Transaction = await Transaction.query().equal(code=code, flag=0, user_id=DEFAULT_USER_ID).order_by(Transaction.id.asc()).first()
            pre_day = trade.create_time.strftime("%Y%m%d")
            datas: list[Analysis] = await Analysis.query().equal(code=code).greater_equal(day=pre_day).order_by(Analysis.day.desc()).all()
        result.data = [AnalysisResultList.from_orm_format(f).model_dump() for f in datas]
        result.total = len(datas)
        logger.info(f"get AI analysis result success, {code} - {day}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


async def analysize(code: str, userId: int, totalFund: float = 100000, availableFund: float = 100000, newsRes: str = None, isAuto: bool = False) -> Result:
    """分析标的，判断怎么操作 \n
    :params code: code
    :params userId: 用户Id
    :params totalFund: 用户总金额
    :params availableFund: 用户可用金额
    :params newsRes: 从新闻资讯中分析结果
    :params isAuto: 是否只程序自动调用
    :return: Result对象
    """
    result = Result()
    try:
        tool: Tools = await Tools.get_one("openDoor")
        open_time = tool.value
        isEtf = code.startswith("1") or code.startswith("5")
        if isEtf:
            stock: ETF = await ETF.get_one(code)
        else:
            stock: Stock = await Stock.get_one(code)

        # 获取 K 线数据
        res: Result = await queryByCodeForAI(code, 30)
        current_price = res.data[-1]['current_price']
        hold = await get_holding(user_id=userId, code=stock.code)
        if not res.success:
            logger.error(f"Get K-line Error: code:{code}, {res.msg}")
            return res
        if isAuto and len(hold) < 1:    # 如果是自动处理，且未持仓，则需要预过滤，已持仓则直接走AI决策
            res_flag, reason = pre_filter_etf(res.data)
            if not res_flag:
                result.success = res_flag
                result.msg = reason
                return result

        # 获取当前仓位数据
        user_hold = {}
        if hold:
            amount = round(hold[0]['price'] * hold[0]["shares"], 2)
            current_position = (amount / totalFund) * 100
            profit = (current_price - hold[0]['price']) / hold[0]['price'] * 100
            user_hold = {"name": hold[0]['name'], "code": hold[0]['code'], "price": round(hold[0]['price'], 2), "shares": hold[0]["shares"],
                         "amount": amount, "current_position": current_position + "%", "profit": profit + "%"}

        # 获取交易记录
        tradeList: list[Transaction] = await Transaction.query().equal(code=code, user_id=userId, flag=0).order_by(Transaction.id.desc()).limit(5).all()
        trade = [TradeRecordList.from_orm_format(f).model_dump() for f in tradeList]
        # analysisList: list[Analysis] = await Analysis.query().equal(code=code).order_by(Analysis.day.desc()).limit(5).all()
        user_input = {
            "type": "etf" if isEtf else "stock",
            "name": stock.name,
            "code": stock.code,
            "toDay": f"{open_time[:4]}-{open_time[4:6]}-{open_time[6:]}",
            "totalFund": totalFund,
            "availableFund": availableFund,
            "newsRes": newsRes,
            "current_price": current_price,
            "userId": userId,
            "industry": stock.name.split("ETF")[0] if isEtf else stock.industry,
            "concept": stock.industry if isEtf else stock.concept,
            "stocks": stock.stocks if isEtf else "",
            "k_line": json.dumps(res.data, ensure_ascii=False),
            "hold": user_hold,
            "trade": trade
        }
        analyzer = AsyncETFAnalyzer(input_data=user_input)
        result.data = await analyzer.analyze()
        logger.info(f"{stock.code} - {stock.name} analyze result is : {result.data['rating']} - {result.data['core_logic']}")
        await asyncio.sleep(5)
    except Exception as e:
        logger.error(traceback.format_exc())
        result.msg = str(e)
        result.success = False
    return result


''' ======================== Scheduler ========================  '''


async def write_analysize_result(data: dict):
    """将分析结果写入到数据库中"""
    operation = data['action_plan']['operation']
    amount = float(data['action_plan']['operation_amount'])
    shares = int(data['action_plan']['operation_shares'])
    if shares < 100:
        logger.error(f"分析结果异常，建议股数不正确 - {data}")
        return
    price = round(amount / shares, 3)
    code = data['code']
    name = data['name']

    if operation in ['建仓', '加仓']:
        status = TradeType.TEMB
    elif operation in ['减仓', '清仓']:
        status = TradeType.TEMS
    else:
        return
    await Transaction.create(code=code, name=name, price=price, shares=shares, status=status, user_id=DEFAULT_USER_ID, flag=0)


async def auto_analysize_etf():
    """每天自动分析 ETF"""
    today = datetime.today()
    if today.weekday() >= 5:
        logger.info("周末未开市，跳过...")
        return
    # 先删除交易失败的数据
    await Transaction.query().equal(user_id=DEFAULT_USER_ID, status=TradeType.FAIL).delete()
    tool: Tools = await Tools.get_one("openDoor")
    capital: Capital = await Capital.get_one(tool.value)
    available = capital.available
    logger.info("🚀 开始获取新闻，分析筛选ETF")
    etfData = []
    # result = await analysizeEtfFromNews()
    # if result.success:
    #     # 兼容AI不同的返回格式
    #     if isinstance(result.data, dict):
    #         if 'result' in result.data:
    #             etfData = result.data['result'] if isinstance(result.data['result'], list) else [result.data['result']]
    #         else:
    #             etfData = [result.data]
    #     else:
    #         etfData = result.data
    #     logger.info(f"✅ 从财经新闻中筛选出 ETF 成功 - {result}")
    # else:
    #     logger.error(f"❌ Error: 从财经新闻中筛选出 ETF 失败 - {result}")
    etf_res = await getEtf()
    for r in etf_res.data:
        code = r["代码"]
        if code in EXCLUSIVE_ETF_LIST:
            continue
        news_etf_data = [etf for etf in etfData if etf['code'] == code]
        news_etf_result = news_etf_data[0]['reason'] if news_etf_data else None
        logger.info(f"📡 开始分析 ETF - {r}")
        res = await analysize(code=code, userId=DEFAULT_USER_ID, totalFund=capital.total, availableFund=available, newsRes=news_etf_result, isAuto=True)
        if res.success:
            try:
                # 所有分析记录保存
                analysis_data = res.data
                del analysis_data['date']
                await Analysis.create(code=code, day=time.strftime("%Y%m%d"), content=json.dumps(analysis_data, ensure_ascii=False))
                if res.data['action_plan']['operation'] == "不操作":
                    continue
                await write_analysize_result(res.data)
                if res.data['action_plan']['operation'] in ['建仓', '加仓']:
                    available -= float(res.data['action_plan']['operation_amount'])  # 买入需要扣减可用金额
                elif res.data['action_plan']['operation'] in ['减仓', '清仓']:
                    available += float(res.data['action_plan']['operation_amount'])  # 卖出需要加上可用金额
                available = max(available, 0)
                logger.info(f"✅ 分析 ETF 成功 - {res.data}")
            except:
                logger.error(f"❌ Error: 分析结果入库失败 - {r} - {traceback.format_exc()}")
        else:
            logger.error(f"❌ Error: 分析 ETF 失败 - {r} - {res.msg}")
    if time.strftime("%H:%M:%S") > "09:31:30":  # 如果已经开盘，则立即执行
        scheduler.add_job(auto_trade_etf, "date", run_date=datetime.now() + timedelta(seconds=10))
    else:   # 如果还未开盘，则设置定时执行
        scheduler.add_job(auto_trade_etf, 'date', run_date=get_schedule_time(9, 31, 30), misfire_grace_time=10)

    # 获取持仓数据和今日数据，用于发送邮件
    await auto_select_email()


async def auto_trade_etf():
    """开盘后自动先卖出、再买入ETF
    :params status: "B"-买入, "S"=卖出 """
    try:
        tool: Tools = await Tools.get_one("openDoor")
        current_day = time.strftime("%Y-%m-%d")
        capital: Capital = await Capital.get_one(tool.value)
        available = capital.available
        logger.info(f"current day {capital.day} available fund is {available}.")
        # 先卖出
        rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMS).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
        for r in rows:
            current_hold = await get_holding(user_id=DEFAULT_USER_ID, code=r.code)
            real_shares = min(current_hold[0]['shares'], r.shares)
            res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
            stockDo: StockModelDo = res_stock['data'][0]
            fee = max((stockDo.current_price * real_shares) * etf_fee_ratio, 5)
            # TODO: 真实的操作
            await Transaction.update(r.id, price=stockDo.current_price, shares=real_shares, fee=round(fee, 2), status=TradeType.AIS)  # 更新真实价格和佣金
            available = available + (stockDo.current_price * real_shares - fee)
            logger.info(f"Auto sell {r.code} - {r.name}, price: {stockDo.current_price}, shares: {real_shares}, fee: {fee}, fund: {stockDo.current_price * real_shares - fee}, current available fund is {available}")
            await asyncio.sleep(1)

        # 卖出后更新可用金额
        await Capital.update(tool.value, available=round(available, 2))
        logger.info(f"after sell ETF, current available fund is {available}")
        # 再买入
        buy_amount = 0.0
        price_dict = {}
        rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
        # 预买入，计算买入需要的金额
        for r in rows:
            res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
            stockDo: StockModelDo = res_stock['data'][0]
            amount = stockDo.current_price * r.shares   # 真实买入金额
            fee = max(amount * etf_fee_ratio, 5)
            buy_amount = buy_amount + amount + fee
            price_dict.update({r.code: stockDo.current_price})
            await Transaction.update(r.id, price=stockDo.current_price)  # 更新真实价格
            await asyncio.sleep(1)

        # 判断可用金额是否足够买入股票
        if available * 0.95 < buy_amount:  # 0.95是冗余系数，即5%的冗余，避免实际买入超出可用金额
            today_buy = []
            for r in rows:
                ai_content = await getAnalysizeResult(r.code, r.create_time.strftime("%Y%m%d"))
                d = json.loads(ai_content.data[0]['content'])
                d['action_plan']['current_price'] = price_dict[r.code]
                today_buy.append(d)
            etf_again = await analyze_buy_etf(available * 0.95, today_buy)
            logger.info(f"由于可用金额不足，再次分析后的结果 - {etf_again}")
            for r in etf_again:
                if r['action_plan']['operation'] != '不操作':
                    shares = int(r['action_plan']['operation_shares'])
                    if shares < 100:
                        logger.error(f"分析结果异常，建议股数不正确 - {r}")
                        continue
                    await Transaction.query().equal(code=r['code'], status=TradeType.TEMB, user_id=DEFAULT_USER_ID).greater(create_time=current_day + ' 08:30:00').update(shares=shares)
                else:
                    await Transaction.query().equal(code=r['code'], status=TradeType.TEMB, user_id=DEFAULT_USER_ID).greater(create_time=current_day + ' 08:30:00').update(status=TradeType.FAIL)
                    logger.warning(f"由于可用金额不足, 分析后决策不操作 - {r['code']}")

        # 开始真实交易
        rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
        for r in rows:
            res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
            stockDo: StockModelDo = res_stock['data'][0]
            curr_price = stockDo.current_price
            real_shares = r.shares
            amount = curr_price * real_shares   # 真实买入金额
            fee = max(amount * etf_fee_ratio, 5)
            available = available - (amount + fee)
            if available < 0:   # 如果不够买入，则减少买入数量
                delta_shares = (int((-1 * available) / (curr_price * 100)) + 1) * 100
                real_shares = real_shares - delta_shares
                amount = curr_price * real_shares  # 真实买入金额
                fee = max(amount * etf_fee_ratio, 5)
                available = available - (amount + fee)
            # TODO: 真实的操作
            await Transaction.update(r.id, price=curr_price, shares=real_shares, fee=round(fee, 2), status=TradeType.RECD)  # 更新真实价格和佣金
            logger.info(f"Auto buy {r.code} - {r.name}, price: {curr_price}, shares: {real_shares}, fee: {fee}, fund: {amount + fee}, current available fund is {available}")
            await asyncio.sleep(1)

        # 卖出后更新可用金额
        await Capital.update(tool.value, available=round(available, 2))
        logger.info(f"after buy ETF, current available fund is {available}")
        # hold_fund = await calc_hold_capital()
        await update_holding_capital()
    except:
        logger.error(traceback.format_exc())


async def update_holding_capital():
    """处理交易记录，更新清仓数据"""
    try:
        tool: Tools = await Tools.get_one("openDoor")
        current_day = tool.value
        if current_day == time.strftime("%Y%m%d"):
            _ = await get_holding()
            res = await get_today_hold()
            hold_fund = 0
            for r in res['holdList']:
                hold_fund += r["price"] * r['shares'] + r['profit']

            # 更新当天沪深300指数价格
            res: dict = await getStockHqFromTencent('', [{"sh000300": "沪深300", "sh000300count": 5}])
            stockDo: StockModelDo = res['data'][0]
            capital: Capital = await Capital.get_one(current_day)
            await Capital.update(current_day, total=round(capital.available + hold_fund, 2), hold=round(hold_fund, 2), campare=stockDo.current_price)
    except:
        logger.error(traceback.format_exc())


# async def calc_hold_capital() -> float:
#     """获取 持仓金额"""
#     try:
#         # 正持仓的数据
#         is_stop = time.strftime("%H:%M:%S") < "15:50:00" and time.strftime("%H:%M:%S") > "09:30:00"
#         tool: Tools = await Tools.get_one("openDoor")
#         hold_fund = 0   # 当天持仓总金额
#         rows1: list[dict] = await get_holding(user_id=DEFAULT_USER_ID)
#         for r in rows1:
#             if is_stop:
#                 res_stock: dict = await getStockHq('', [{r['code']: r['name'], f"{r['code']}count": 5}])
#                 stockDo: StockModelDo = res_stock['data'][0]
#             else:
#                 stockDo: Detail = await Detail.get_one((r['code'], tool.value))
#             hold_fund += stockDo.current_price * r['shares']

#         logger.info(f"current hold capital is {hold_fund}")
#         return hold_fund
#     except:
#         logger.error(traceback.format_exc())
#         return 0


async def auto_select_email():
    try:
        tradeStatus = {"TEMB": "买入", "TEMS": "卖出", "RECD": "买入", "AIS": "卖出"}
        res = await get_today_hold()
        today_str = ''
        hold_str = ''
        for r in res['todayList']:
            ai_content = await getAnalysizeResult(r['code'], r['create_time'].replace('-', ''))
            content = json.loads(ai_content.data[0]['content'])
            today_str += f'''<tr><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['name']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['code']}</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{tradeStatus[r['status']]}(待成交)</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['price']}(预估)</td>
            <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['shares']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;"><details style="color: #0052d9; cursor: pointer;">
                <summary style="outline: none; font-weight: bold; color: #0052d9; cursor: pointer;">点我</summary>
                <div style="position: absolute; top: 28px; left: 50%; margin-left: -210px; z-index: 999; width: 318px; height: 66%; overflow-y: auto; background-color: #ffffff; border: 1px solid #cccccc; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 15px; border-radius: 6px; line-height: 1.6;">
                    <p style="margin: 0 0 10px 0;"><strong>评级: </strong>{content['rating']}</p>
                    <p style="margin: 0 0 10px 0;"><strong>核心观点: </strong>{content['action_plan']['operation_reason'].replace('\\n', '\n')}</p>
                    <p style="margin: 0 0 10px 0;"><strong>详细分析: </strong>{content['detailed_analysis'].replace('\\n', '\n')}</p>
                    <p style="margin: 0 0 10px 0;"><strong>风险点: </strong>{content['risk_warning'].replace('\\n', '\n')}</p>
                    <p style="margin: 0 0 10px 0;"><strong>点位: </strong>{content['action_plan']['stop_loss_profit']}</p>
                </div></details></td></tr>'''
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
