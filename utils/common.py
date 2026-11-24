#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import time
import logging
import traceback
from typing import Any, Optional
from datetime import datetime, timedelta
from utils.queryStockHq import getStockHqFromTencent, getStockHq
from utils.model import StockModelDo, StockDataList, TradeStockList
from utils.database import Detail, Tools, Transaction, TradeType
from utils.selectStock import getStockZhuLiFund
from utils.metric import bollinger_bands
from settings import DEFAULT_USER_ID


logger = logging.getLogger(__name__)
alpha_s = 2.0 / (12 + 1)
alpha_l = 2.0 / (26 + 1)
alpha_sig = 2.0 / (9 + 1)


def getStockRegion(code: str) -> str:
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return "sh"
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return "sz"
    else:
        return ""


def getStockRegionNum(code: str) -> str:
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return "1"
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return "0"
    else:
        return ""


def getMarketCode(code: str) -> int:
    """同花顺-股票所属市场判断"""
    if code.startswith("60") or code.startswith("68") or code.startswith("5"):
        return 17
    elif code.startswith("00") or code.startswith("30") or code.startswith("1"):
        return 33
    else:
        return 0


def get_past_date(days_diff: int = 373, date_format: str = "%Y%m%d") -> str:
    """根据当前日期和相差天数，计算之前的日期

    :param days_diff: 相差天数, 默认373, 373天大概是一年多的数据, 大概共250个交易日
    :param date_format: 默认"%Y%m%d"
    :return: 之前的日期字符串
    """
    current_date = datetime.now()
    past_date = current_date - timedelta(days=days_diff)
    return past_date.strftime(date_format)


def real_traded_minutes() -> int:
    """
    实时获取当前时间，计算 A 股当日已交易分钟数
    返回范围：1 ~ 240
    """
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    current = hour * 60 + minute
    morning_start = 9 * 60 + 30     # 09:30
    morning_end = 11 * 60 + 30    # 11:30
    afternoon_start = 13 * 60       # 13:00
    afternoon_end = 15 * 60       # 15:00

    if current < morning_start:
        traded = 0
    elif morning_start <= current <= morning_end:
        traded = current - morning_start
    elif morning_end < current < afternoon_start:
        traded = 120
    elif afternoon_start <= current <= afternoon_end:
        traded = 120 + (current - afternoon_start)
    else:
        traded = 240

    if traded < 1:
        return 1
    if traded > 240:
        return 240
    return traded


def calc_MA(data: list, window: int, digit: int = 2) -> float:
    return round(sum(data[:window]) / len(data[:window]), digit)


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


async def calc_stock_real_data(code: str) -> dict[str, Any]:
    isEtf = code.startswith('1') or code.startswith('5')
    if isEtf:
        digit = 3
        res_stock: dict = await getStockHqFromTencent('', {code: "-"})
    else:
        digit = 2
        res_stock: dict = await getStockHq('', {code: "-"})
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
    stockDo.update({'ma_five': calc_MA(stock_price, 5, digit)})
    stockDo.update({'ma_ten': calc_MA(stock_price, 10, digit)})
    stockDo.update({'ma_twenty': calc_MA(stock_price, 20, digit)})
    stockDo.update({'qrr': round(stockDo['volume'] / average_volume, 2)})
    stockDo.update({'diff': macd['emas'] - macd['emal']})
    stockDo.update({'dea': macd['dea']})
    stockDo.update({'k': kdj['k']})
    stockDo.update({'d': kdj['d']})
    stockDo.update({'j': kdj['j']})
    stockDo.update({'volume': stockDo['volume']})
    stockDo.update({'shares': stockDo['shares'] if isEtf else 0})
    stockDo.update({'premium': stockDo['premium'] if isEtf else 0})
    stockDo.update({'fund': await getStockZhuLiFund(code)})
    up, dn = bollinger_bands(stock_price[:20], calc_MA(stock_price, 20, digit))
    stockDo.update({'boll_up': round(up, 2)})
    stockDo.update({'boll_low': round(dn, 2)})
    logger.info(stockDo)
    return stockDo


async def queryByCodeForAI(code: str, limit: int = 40, flag: bool = True) -> Optional[list[dict[str, Any]]]:
    """ 查询K线数据, 只用于AI分析
    :params code: 标的code
    :params limit: 查询多少天的数据
    :params flag: 盘中是否获取最新数据, True获取, False不获取
    """
    try:
        if not limit:
            limit = 22
        isEtf = code.startswith("1") or code.startswith("5")
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        stockInfo: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.desc()).limit(limit).all()
        stockInfo.reverse()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockInfo]

        current_day = time.strftime("%Y%m%d")
        current_time = time.strftime("%H:%M:%S")
        if flag and current_day == day and current_time > "09:30:00" and current_time < "15:30:00":
            stockDo: dict = await calc_stock_real_data(code)
            if stockDo:
                if stock_data[-1]['day'] == day:
                    _ = stock_data.pop()
                today = {'code': code, 'name': '', 'day': day, 'current_price': stockDo['current_price'], 'last_price': stockDo['last_price'],
                         'open_price': stockDo['open_price'], 'max_price': stockDo['max_price'], 'min_price': stockDo['min_price'],
                         'volume': stockDo['volume'], 'fund': stockDo['fund'], 'ma_five': stockDo['ma_five'], 'ma_ten': stockDo['ma_ten'],
                         'ma_twenty': stockDo['ma_twenty'], 'qrr': stockDo['qrr'], 'diff': round(stockDo['diff'], 3), 'dea': round(stockDo['dea'], 3),
                         'k': round(stockDo['k'], 3), 'd': round(stockDo['d'], 3), 'j': round(stockDo['j'], 3), 'shares': round(stockDo['shares'], 2),
                         'premium': round(stockDo['premium'], 2), 'turnover_rate': stockDo['turnover_rate'], 'boll_up': stockDo['boll_up'],
                         'boll_low': stockDo['boll_low']}
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
        logger.info(f"Query AI stock k-line success - code: {code}")
        return stock_data
    except:
        logger.error(f"Query AI stock k-line fail, code: {code}, limit: {limit} - {traceback.format_exc()}")
        return None


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
        elif status == TradeType.DR:    # 分红派息
            total_value = cost * shares - fee
            cost = round(total_value / shares, 6)
            profit = (price - cost) * shares + fee
        else:    # 减仓/清仓
            if number > shares:
                raise Exception(f"卖出数量大于持仓数量, {number} > {shares} ...")
            profit = (price - cost) * number - fee
            shares -= number
            if shares != 0:
                cost = cost - (profit / shares)

        result = {'cost': cost, 'shares': shares, 'profit': profit}
    except:
        logger.error(f"status: {status}, price: {price}, number: {number}, cost: {cost}, shares: {shares}, fee: {fee} - {traceback.format_exc()}")
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
                filter = [TradeType.RECD, TradeType.AIS] if r[0] == DEFAULT_USER_ID else [TradeType.BUY, TradeType.SELL, TradeType.DR]
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


async def get_today_hold() -> dict:
    status = [TradeType.TEMB, TradeType.TEMS, TradeType.FAIL]
    today: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0).isin(status=status).all()
    todayList = [TradeStockList.from_orm_format(f).model_dump() for f in today]
    holdList = await get_holding(user_id=DEFAULT_USER_ID)
    for h in holdList:
        detail: Detail = await Detail.query().equal(code=h['code']).order_by(Detail.day.desc()).first()
        h['price'] = round(h['price'], 3)
        h['profit'] = round((detail.current_price - h['price']) * h['shares'], 2)
    return {'todayList': todayList, 'holdList': holdList}
