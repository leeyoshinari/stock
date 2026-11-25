#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
import logging
# import asyncio
import traceback
# import aiofiles
from datetime import datetime, timedelta
from utils.model import SearchStockParam, StockModelDo, StockMinuteDo
from utils.model import StockInfoList, ToolsInfoList, SetStockParam, TradeRecordList
from utils.model import EtfInfoList, TradeStockList, SetStockHold, AnalysisResultList
from utils.results import Result
from utils.common import calc_stock_real_data, get_past_date, queryByCodeForAI, get_holding, get_today_hold
# from utils.etfData import pre_filter_etf
# from utils.scheduler import scheduler
from utils.aiAnalyzer import AsyncETFAnalyzer, analyze_etf_from_news, analyze_buy_etf
from utils.initData import initStockData, getStockFundFlow
from utils.queryStockHq import getMinuteKFromDongcai, getMinuteKFromSina
from utils.database import Stock, Detail, Tools, ETF, Transaction, TradeType, Capital, Analysis
from settings import DEFAULT_USER_ID, EMAIL_TEMPLATE, EXCLUSIVE_ETF_LIST, TOTAL_FUND, DEFAULT_AI_RESULT
from settings import stock_fee_ratio, etf_fee_ratio, stamp_duty


logger = logging.getLogger(__name__)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


async def queryByCode(code: str, userId: int = None) -> Result:
    result = Result()
    try:
        past_date = get_past_date()
        tool: Tools = await Tools.get_one("openDoor")
        day = tool.value
        isEtf = code.startswith("1") or code.startswith("5")
        current_day = time.strftime("%Y%m%d")
        current_time = time.strftime("%H:%M:%S")
        stockInfo: list[Detail] = await Detail.query().equal(code=code).order_by(Detail.day.asc()).all()
        if day == stockInfo[-1].day and current_time > "09:30:00" and current_time < "15:30:00" and current_day == day:
            stockInfo.pop()
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
                create_time = r.create_time.strftime("%Y%m%d")
                if create_time > past_date:
                    coords.append([r.status, r.create_time.strftime("%Y%m%d"), r.price, r.shares, r.fee])

        if day != stockInfo[-1].day:
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

        profit_res = await get_holding(user_id=userId, code=code)
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
        logger.error(f"Query stock k-line fail - code: {code} - userId: {userId} - {traceback.format_exc()}")
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


async def query_stock_real_data(code: str) -> Result:
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
        logger.error(f"query Recommend stock minute real data fail - {code} - {traceback.format_exc()}")
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
    '''设置股票数据(添加/删除标签)'''
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
        logger.error(f"{SetStockParam.model_validate(data).model_dump()} - {traceback.format_exc()}")
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
        logger.error(f"code: {code} - {traceback.format_exc()}")
        result.success = False
        result.msg = str(e)
    return result


async def init_stock_fund_data(code: str) -> Result:
    result = Result()
    try:
        if code.startswith('1') or code.startswith('5'):
            stock: ETF = await ETF.get_one(code)
        else:
            stock: Stock = await Stock.get_one(code)
        await getStockFundFlow(code)
        logger.info(f"更新股票主力资金数据成功 - {stock.code} - {stock.name}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = str(e)
    return result


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
        logger.error(f"get_user_hold - userId: {userId} - {traceback.format_exc()}")
    return result


async def set_user_hold(data: SetStockHold) -> Result:
    '''
    data.status, 0-卖出, 1-买入, 2-除权分红
    '''
    result = Result()
    try:
        if data.status == 2:
            stock: Stock = await Stock.get_one(data.code)
            await Transaction.create(code=data.code, name=stock.name, price=0, shares=0, status=TradeType.DR,
                                     fee=data.price, user_id=data.userId, flag=0)
            logger.info(f"设置除权分红数据成功, 用户: {data.userId}, 股票: {data.code}, 数据: {data}")
            return result

        # 设置买入卖出交易数据
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
        logger.error(f"{SetStockHold.model_validate(data).model_dump()} - {traceback.format_exc()}")
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
        logger.error(f"userId: {userId}, page: {page} - {traceback.format_exc()}")
        result.success = False
        result.msg = str(e)
    return result


async def deleteHoldStock(rId: int) -> Result:
    result = Result()
    try:
        _ = await Transaction.query().equal(id=rId).delete()
        logger.info(f"Delete Hold Stock {rId} Success ~")
    except Exception as e:
        logger.error(f"Delete Hold Stock {rId} Fail - {traceback.format_exc()}")
        result.success = False
        result.msg = str(e)
    return result


async def deleteEtf(code: str) -> Result:
    result = Result()
    try:
        _ = await ETF.query().equal(code=code).delete()
        logger.info(f"Delete ETF {code} Success ~")
    except Exception as e:
        logger.error(f"Delete ETF {code} Fail - {traceback.format_exc()}")
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
        logger.error(f"Update ETF {code} Running Fail - {traceback.format_exc()}")
        result.success = False
        result.msg = str(e)
    return result


async def getEtf() -> Result:
    result = Result()
    try:
        index = []
        etfInfo: list[ETF] = await ETF.query().equal(running=1).order_by(ETF.capital.desc()).all()
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


async def test(code: ToolsInfoList) -> Result:
    result = Result()
    try:
        logger.info(f"{code}")
    except:
        logger.error(traceback.format_exc())
    return result


# async def analysizeEtfFromNews() -> Result:
#     """从财经新闻中筛选出ETF"""
#     result = Result()
#     try:
#         res = await getEtf()
#         tool = await Tools.get_one("openDoor")
#         open_time = tool.value
#         lastDay = f"{open_time[:4]}-{open_time[4:6]}-{open_time[6:]} 16:00:00"
#         resp = await analyze_etf_from_news(res.data, lastDay)
#         result.data = resp
#         logger.info(f"从新闻中提取出的ETF结果 {resp}")
#     except Exception as e:
#         logger.error(traceback.format_exc())
#         result.success = False
#         result.msg = str(e)
#     return result


async def getAnalysizeResult(code: str, userId: int, day: str = None) -> Result:
    """获取 AI 分析结, day的格式是: %Y%m%d"""
    result = Result()
    try:
        if day:
            datas: list[Analysis] = await Analysis.query().equal(code=code, day=day).all()
        else:
            datas: list[Analysis] = await Analysis.query().equal(code=code).order_by(Analysis.day.desc()).limit(22).all()
        hold = await get_holding(user_id=userId, code=code)
        analysis = [AnalysisResultList.from_orm_format(f).model_dump() for f in datas]
        result.data = {'hold': hold[0] if hold else {}, 'analysis': analysis}
        result.total = len(datas)
        logger.info(f"get AI analysis result success, {code} - {day}")
    except Exception as e:
        logger.error(f"code: {code}, userId: {userId}, day: {day} - {traceback.format_exc()}")
        result.success = False
        result.msg = str(e)
    return result


async def analysize(code: str, userId: int, hold: list[dict] = None, kline: list[dict] = None, totalFund: float = 100000, availableFund: float = 100000) -> Result:
    """分析标的，判断怎么操作 \n
    :params code: code
    :params userId: 用户Id
    :params hold: 用户持仓数据
    :params kline: code的 K 线数据
    :params totalFund: 用户总金额
    :params availableFund: 用户可用金额
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
        if kline is None:
            res: Result = await queryByCodeForAI(code, 30)
            kline = res.data
        current_price = kline[-1]['current_price']
        # 获取持仓数据
        if hold is None:
            hold = await get_holding(user_id=userId, code=stock.code)

        user_hold = None
        if hold:
            amount = round(hold[0]['price'] * hold[0]["shares"], 2)
            current_position = round((amount / totalFund) * 100, 2)
            profit = (current_price - hold[0]['price']) / hold[0]['price'] * 100
            user_hold = {"price": round(hold[0]['price'], 2), "shares": hold[0]['shares'], "amount": amount, "current_position": current_position, "profit": round(profit, 2)}

        # 获取交易记录
        tradeList: list[Transaction] = await Transaction.query().equal(code=code, user_id=userId, flag=0).order_by(Transaction.id.desc()).limit(5).all()
        trade = [TradeRecordList.from_orm_format(f).model_dump() for f in tradeList]

        # 获取AI分析数据
        analysisList: list[Analysis] = await Analysis.query().equal(code=code).order_by(Analysis.day.desc()).limit(5).all()
        analysis = []
        for r in analysisList:
            analysis.append(json.loads(r.content))

        # 组合AI分析参数
        user_input = {
            "type": "etf" if isEtf else "stock",
            "name": stock.name,
            "code": stock.code,
            "toDay": f"{open_time[:4]}-{open_time[4:6]}-{open_time[6:]}",
            "totalFund": totalFund,
            "availableFund": availableFund,
            "current_price": current_price,
            "userId": userId,
            "industry": stock.name.split("ETF")[0] if isEtf else stock.industry,
            "concept": stock.industry if isEtf else stock.concept,
            "stocks": stock.stocks if isEtf else "",
            "k_line": json.dumps(kline, ensure_ascii=False),
            "hold": user_hold,
            "trade": trade,
            "analysis": analysis
        }
        analyzer = AsyncETFAnalyzer(input_data=user_input)
        result.data = await analyzer.analyze()
        logger.info(f"{stock.code} - {stock.name} analyze result is : {result.data['rating']} - {result.data['core_logic']}")
    except Exception as e:
        logger.error(f"code: {code}, userId: {userId} - {traceback.format_exc()}")
        result.msg = str(e)
        result.success = False
    return result


''' ======================== Scheduler ========================  '''


# async def write_analysize_result(data: dict):
#     """将分析结果写入到数据库中"""
#     operation = data['action_plan']['operation']
#     amount = float(data['action_plan']['operation_amount'])
#     shares = int(data['action_plan']['operation_shares'])
#     if shares < 100:
#         logger.error(f"分析结果异常，建议股数不正确 - {data}")
#         return
#     price = round(amount / shares, 3)
#     code = data['code']
#     name = data['name']

#     if operation in ['建仓', '加仓']:
#         status = TradeType.TEMB
#     elif operation in ['减仓', '清仓']:
#         status = TradeType.TEMS
#     else:
#         return
#     await Transaction.create(code=code, name=name, price=price, shares=shares, status=status, user_id=DEFAULT_USER_ID, flag=0)


# async def auto_analysize_etf():
#     """每天自动分析 ETF"""
#     tool: Tools = await Tools.get_one("openDoor")
#     if tool.value != time.strftime("%Y%m%d"):
#         logger.info("今天未开市，跳过...")
#         return

#     # 先删除交易失败的数据
#     await Transaction.query().equal(user_id=DEFAULT_USER_ID, status=TradeType.FAIL).delete()
#     capital: Capital = await Capital.get_one(tool.value)
#     available = capital.available
#     # logger.info("🚀 开始获取新闻，分析筛选ETF")
#     # etfData = []
#     # result = await analysizeEtfFromNews()
#     # if result.success:
#     #     # 兼容AI不同的返回格式
#     #     if isinstance(result.data, dict):
#     #         if 'result' in result.data:
#     #             etfData = result.data['result'] if isinstance(result.data['result'], list) else [result.data['result']]
#     #         else:
#     #             etfData = [result.data]
#     #     else:
#     #         etfData = result.data
#     #     logger.info(f"✅ 从财经新闻中筛选出 ETF 成功 - {result}")
#     # else:
#     #     logger.error(f"❌ Error: 从财经新闻中筛选出 ETF 失败 - {result}")
#     hold_res = await get_holding(user_id=DEFAULT_USER_ID)
#     etf_res = await getEtf()
#     hold_code_list = [f['code'] for f in hold_res]
#     hold_etf_list = [f for f in etf_res.data if f["代码"] in hold_code_list]
#     not_hold_etf_list = [f for f in etf_res.data if f["代码"] not in hold_code_list]
#     all_etf = hold_etf_list + not_hold_etf_list
#     for r in all_etf:
#         code = r["代码"]
#         if code in EXCLUSIVE_ETF_LIST:
#             continue
#         # news_etf_data = [etf for etf in etfData if etf['code'] == code]
#         # news_etf_result = news_etf_data[0]['reason'] if news_etf_data else None
#         logger.info(f"📡 开始分析 ETF - {r}")
#         detail_res: Result = await queryByCodeForAI(code, 30)
#         hold = await get_holding(user_id=DEFAULT_USER_ID, code=code)
#         if not detail_res.success:
#             logger.error(f"Get K-line Error: code:{code}, {detail_res.msg}")
#             continue
#         if len(hold) < 1:    # 如果未持仓，则需要预过滤，已持仓则直接走AI决策
#             res_flag, reason = pre_filter_etf(detail_res.data)
#             if not res_flag:
#                 default_result = DEFAULT_AI_RESULT
#                 default_result["date"] = f"{tool.value[:4]}-{tool.value[4:6]}-{tool.value[6:]}"
#                 default_result["code"] = code
#                 default_result["name"] = r["名称"]
#                 default_result["core_logic"] = reason
#                 default_result["detailed_analysis"] = reason
#                 default_result["action_plan"]["current_position"] = hold
#                 default_result["action_plan"]["operation_reason"] = reason
#                 await Analysis.create(code=code, day=time.strftime("%Y%m%d"), content=json.dumps(default_result, ensure_ascii=False))
#                 logger.error(f"❌ Error: 分析 ETF 失败 - {code} - {res_flag} - {reason}")
#                 continue
#         res = await analysize(code=code, userId=DEFAULT_USER_ID, hold=hold, kline=detail_res.data, totalFund=capital.total, availableFund=available)
#         if res.success:
#             try:
#                 # 所有分析记录保存
#                 await Analysis.create(code=code, day=time.strftime("%Y%m%d"), content=json.dumps(res.data, ensure_ascii=False))
#                 if res.data['action_plan']['operation'] == "不操作":
#                     continue
#                 await write_analysize_result(res.data)
#                 if res.data['action_plan']['operation'] in ['建仓', '加仓']:
#                     available -= float(res.data['action_plan']['operation_amount'])  # 买入需要扣减可用金额
#                 elif res.data['action_plan']['operation'] in ['减仓', '清仓']:
#                     available += float(res.data['action_plan']['operation_amount'])  # 卖出需要加上可用金额
#                 available = max(available, 0)
#                 logger.info(f"✅ 分析 ETF 成功 - {res.data}")
#             except:
#                 logger.error(f"❌ Error: 分析结果入库失败 - {r} - {traceback.format_exc()}")
#         else:
#             default_result = DEFAULT_AI_RESULT
#             default_result["date"] = f"{tool.value[:4]}-{tool.value[4:6]}-{tool.value[6:]}"
#             default_result["code"] = code
#             default_result["name"] = r["名称"]
#             default_result["core_logic"] = res.msg
#             default_result["detailed_analysis"] = res.msg
#             default_result["action_plan"]["current_position"] = hold
#             default_result["action_plan"]["operation_reason"] = res.msg
#             await Analysis.create(code=code, day=time.strftime("%Y%m%d"), content=json.dumps(default_result, ensure_ascii=False))
#             logger.error(f"❌ Error: 分析 ETF 失败 - {r} - {res.msg}")

#     # 获取持仓数据和今日数据，用于发送邮件
#     await auto_select_email()
#     scheduler.add_job(auto_trade_etf, "date", run_date=datetime.now() + timedelta(seconds=10), misfire_grace_time=10)


# async def auto_trade_etf():
#     """开盘后自动先卖出、再买入ETF
#     :params status: "B"-买入, "S"=卖出 """
#     try:
#         tool: Tools = await Tools.get_one("openDoor")
#         current_day = time.strftime("%Y-%m-%d")
#         capital: Capital = await Capital.get_one(tool.value)
#         available = capital.available
#         logger.info(f"current day {capital.day} available fund is {available}.")
#         # 先卖出
#         rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMS).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
#         for r in rows:
#             current_hold = await get_holding(user_id=DEFAULT_USER_ID, code=r.code)
#             real_shares = min(current_hold[0]['shares'], r.shares)
#             res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
#             stockDo: StockModelDo = res_stock['data'][0]
#             fee = max((stockDo.current_price * real_shares) * etf_fee_ratio, 5)
#             # TODO: 真实的操作
#             await Transaction.update(r.id, price=stockDo.current_price, shares=real_shares, fee=round(fee, 2), status=TradeType.AIS)  # 更新真实价格和佣金
#             available = available + (stockDo.current_price * real_shares - fee)
#             logger.info(f"Auto sell {r.code} - {r.name}, price: {stockDo.current_price}, shares: {real_shares}, fee: {fee}, fund: {stockDo.current_price * real_shares - fee}, current available fund is {available}")
#             await asyncio.sleep(1)

#         # 卖出后更新可用金额
#         await Capital.update(tool.value, available=round(available, 2))
#         logger.info(f"after sell ETF, current available fund is {available}")
#         # 再买入
#         buy_amount = 0.0
#         price_dict = {}
#         rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
#         # 预买入，计算买入需要的金额
#         for r in rows:
#             res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
#             stockDo: StockModelDo = res_stock['data'][0]
#             amount = stockDo.current_price * r.shares   # 真实买入金额
#             fee = max(amount * etf_fee_ratio, 5)
#             buy_amount = buy_amount + amount + fee
#             price_dict.update({r.code: stockDo.current_price})
#             await Transaction.update(r.id, price=stockDo.current_price)  # 更新真实价格
#             await asyncio.sleep(1)

#         # 判断可用金额是否足够买入股票
#         if available * 0.95 < buy_amount:  # 0.95是冗余系数，即5%的冗余，避免实际买入超出可用金额
#             today_buy = []
#             for r in rows:
#                 ai_content = await getAnalysizeResult(code=r.code, userId=DEFAULT_USER_ID, day=r.create_time.strftime("%Y%m%d"))
#                 d = json.loads(ai_content.data['analysis'][0]['content'])
#                 d['action_plan']['current_price'] = price_dict[r.code]
#                 today_buy.append(d)
#             etf_again = await analyze_buy_etf(capital.total, available * 0.95, today_buy)
#             logger.info(f"由于可用金额不足，再次分析后的结果 - {etf_again}")
#             for r in etf_again:
#                 if r['action_plan']['operation'] != '不操作':
#                     shares = int(r['action_plan']['operation_shares'])
#                     if shares < 100:
#                         logger.error(f"分析结果异常，建议股数不正确 - {r}")
#                         continue
#                     await Transaction.query().equal(code=r['code'], status=TradeType.TEMB, user_id=DEFAULT_USER_ID).greater(create_time=current_day + ' 08:30:00').update(shares=shares)
#                 else:
#                     await Transaction.query().equal(code=r['code'], status=TradeType.TEMB, user_id=DEFAULT_USER_ID).greater(create_time=current_day + ' 08:30:00').update(status=TradeType.FAIL)
#                     await Analysis.query().equal(code=r['code'], day=tool.value).update(content=json.dumps(r, ensure_ascii=False))
#                     logger.warning(f"由于可用金额不足, 分析后决策不操作 - {r['code']}")

#         # 开始真实交易
#         rows: list[Transaction] = await Transaction.query().equal(user_id=DEFAULT_USER_ID, flag=0, status=TradeType.TEMB).greater(create_time=current_day + ' 08:30:00').less(fee=0.1).all()
#         for r in rows:
#             res_stock: dict = await getStockHq('', [{r.code: r.name, f"{r.code}count": 5}])
#             stockDo: StockModelDo = res_stock['data'][0]
#             curr_price = stockDo.current_price
#             real_shares = r.shares
#             amount = curr_price * real_shares   # 真实买入金额
#             fee = max(amount * etf_fee_ratio, 5)
#             available = available - (amount + fee)
#             if available < 0:   # 如果不够买入，则减少买入数量
#                 delta_shares = (int((-1 * available) / (curr_price * 100)) + 1) * 100
#                 real_shares = real_shares - delta_shares
#                 amount = curr_price * real_shares  # 真实买入金额
#                 fee = max(amount * etf_fee_ratio, 5)
#                 available = available - (amount + fee)
#             # TODO: 真实的操作
#             await Transaction.update(r.id, price=curr_price, shares=real_shares, fee=round(fee, 2), status=TradeType.RECD)  # 更新真实价格和佣金
#             logger.info(f"Auto buy {r.code} - {r.name}, price: {curr_price}, shares: {real_shares}, fee: {fee}, fund: {amount + fee}, current available fund is {available}")
#             await asyncio.sleep(1)

#         # 卖出后更新可用金额
#         await Capital.update(tool.value, available=round(available, 2))
#         logger.info(f"after buy ETF, current available fund is {available}")
#         # await update_holding_capital()
#     except:
#         logger.error(traceback.format_exc())


# async def auto_select_email():
#     try:
#         tradeStatus = {"TEMB": "买入", "TEMS": "卖出", "RECD": "买入", "AIS": "卖出"}
#         res = await get_today_hold()
#         today_str = ''
#         hold_str = ''
#         for r in res['todayList']:
#             if r['status'] not in tradeStatus:
#                 continue
#             ai_content = await getAnalysizeResult(code=r['code'], userId=DEFAULT_USER_ID, day=r['create_time'].replace('-', ''))
#             content = json.loads(ai_content.data['analysis'][0]['content'])
#             operation = content['action_plan']['operation']
#             share = ''
#             if operation != '':
#                 share = f'''<strong style="margin-left:15px;">股数: </strong>{content['action_plan']['operation_shares']}'''
#             today_str += f'''<tr><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['name']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['code']}</td>
#             <td style="border: 1px solid #e0e0e0; padding: 10px;">{tradeStatus[r['status']]}(待成交)</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['price']}(预估)</td>
#             <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['shares']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;"><details style="color: #0052d9; cursor: pointer;">
#                 <summary style="outline: none; font-weight: bold; color: #0052d9; cursor: pointer;">点我</summary>
#                 <div style="position: absolute; top: 28px; left: 50%; margin-left: -210px; z-index: 999; width: 318px; height: 66%; overflow-y: auto; background-color: #ffffff; border: 1px solid #cccccc; box-shadow: 0 4px 12px rgba(0,0,0,0.15); padding: 15px; border-radius: 6px; line-height: 1.6;">
#                     <p style="margin: 0 0 10px 0;"><strong>评级: </strong>{content['rating']}<strong style="margin-left:15px;">操作: </strong>{operation}{share}</p>
#                     <p style="margin: 0 0 10px 0;"><strong>核心观点: </strong>{content['core_logic'].replace('\\n', '\n')}</p>
#                     <p style="margin: 0 0 10px 0;"><strong>详细分析: </strong>{content['detailed_analysis'].replace('\\n', '\n')}</p>
#                     <p style="margin: 0 0 10px 0;"><strong>风险点: </strong>{content['risk_warning'].replace('\\n', '\n')}</p>
#                     <p style="margin: 0 0 10px 0;"><strong>操作理由: </strong>{content['action_plan']['operation_reason'].replace('\\n', '\n')}</p>
#                     <p style="margin: 0 0 10px 0;"><strong>点位: </strong>{content['action_plan']['stop_loss_profit']}</p>
#                 </div></details></td></tr>'''
#         for r in res['holdList']:
#             hold_str += f'''<tr><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['name']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['code']}</td>
#             <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['create_time']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['price']}</td>
#             <td style="border: 1px solid #e0e0e0; padding: 10px;">{r['shares']}</td><td style="border: 1px solid #e0e0e0; padding: 10px;">{r['profit']}</td></tr>'''
#         async with aiofiles.open(EMAIL_TEMPLATE, 'r', encoding='utf-8') as f:
#             template = await f.read()
#         template = template.replace("today_filter_stock", today_str).replace("has_hold_stock", hold_str)
#         sendEmail("今日数据", template)
#         logger.info("send email success ~")
#     except:
#         logger.error(traceback.format_exc())
