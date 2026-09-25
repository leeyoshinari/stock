#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import traceback
from logging import Logger
from urllib.parse import urlencode
from datetime import datetime, timedelta
from utils.http_client import http
from utils.results import getStockRegion
from settings import TUSHARE_API_KEY


HOST = "https://data.infoway.io"


async def get(path: str, params: dict) -> dict:
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36',
              "Accept": "application/json", "apiKey": TUSHARE_API_KEY}
    query_string = urlencode(params)
    url = f"{HOST}{path}?{query_string}"
    res = await http.get(url, headers=header)
    if res.status_code == 200:
        return json.loads(res.text)
    else:
        raise Exception(f"{path} status code is {res.status_code}, request data: {params}, response: {res.text}")


async def getStockInfo(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-symbol-basic-info
    用于获取标的的基础信息
    '''
    try:
        path = '/common/basic/symbols/info'
        params = {'type': 'STOCK_CN', 'symbols': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 用于获取标的的基础信息 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockDetail(code: str, logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-symbol-basic-info-1
    用于获取标的的详细信息
    '''
    try:
        path = '/common/basic/stock/detail'
        params = {'type': 'STOCK_CN', 'symbols': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 用于获取标的的详细信息 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockEarningStatus(code: str, logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    用于获取个股的财报发布状态
    '''
    try:
        path = '/common/basic/financial/earning_status'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 用于获取个股的财报发布状态 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockIncome(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    用于获取公司的收入、成本、利润等经营数据
    '''
    try:
        post_date = datetime.now() - timedelta(days=720)
        formatted = post_date.strftime("%Y-%m-%d")
        path = '/common/basic/financial/income_statement'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 用于获取公司的收入、成本、利润等经营数据 - {code}")
        result = [d for d in res['data'] if d['periodDate'] > formatted]
        return result
    except:
        logger.error(traceback.format_exc())


async def getStockRevenue(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询收入按业务板块或地区的拆分明细
    '''
    try:
        post_date = datetime.now() - timedelta(days=1096)
        formatted = post_date.strftime("%Y")
        path = '/common/basic/financial/revenue'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询收入按业务板块或地区的拆分明细 - {code}")
        result = [d for d in res['data'] if d['periodDate'] > formatted]
        return result
    except:
        logger.error(traceback.format_exc())


async def getStockCashFlow(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询经营/投资/筹资三大现金流数据
    '''
    try:
        path = '/common/basic/financial/cash_flow'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询经营/投资/筹资三大现金流数据 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockBalance(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询资产、负债、股东权益等时点数据
    '''
    try:
        path = '/common/basic/financial/balance_sheet'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询资产、负债、股东权益等时点数据 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockStatistics(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询 PE、PB、ROE 等估值与财务比率
    '''
    try:
        post_date = datetime.now() - timedelta(days=720)
        formatted = post_date.strftime("%Y-%m-%d")
        path = '/common/basic/financial/statistics'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}", 'period_type': 'fq'}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询 PE、PB、ROE 等估值与财务比率 - {code}")
        result = [d for d in res['data'] if d['periodDate'] > formatted]
        return result
    except:
        logger.error(traceback.format_exc())


async def getStockDividend(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询每股股息、股息率、派息率等指标
    '''
    try:
        path = '/common/basic/financial/dividend'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询每股股息、股息率、派息率等指标 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockEarnings(code: str, logger: Logger) -> list[dict]:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-financial-data
    查询 EPS 和 Revenue 的实际值与预期值（Beat/Miss）
    '''
    try:
        path = '/common/basic/financial/earnings'
        params = {'type': 'STOCK_CN', 'symbol': f"{code}.{getStockRegion(code).upper()}"}
        res: dict = await get(path, params)
        logger.info(f"{path} - 查询 EPS 和 Revenue 的实际值与预期值（Beat/Miss） - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockValuation(code: str, logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-fundamental
    获取标的PE/PB历史数据，可用于画估值走势图
    '''
    try:
        path = f'/common/v2/basic/stock/valuation/{code}.{getStockRegion(code).upper()}'
        params = {'lang': 'zh-CN'}
        res: dict = await get(path, params)
        logger.info(f"{path} - 获取标的PE/PB历史数据，可用于画估值走势图 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockRatings(code: str, logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-fundamental
    获取机构买入/增持/持有/减持/卖出评级家数统计趋势
    '''
    try:
        path = f'/common/v2/basic/stock/ratings/{code}.{getStockRegion(code).upper()}'
        params = {'lang': 'zh-CN'}
        res: dict = await get(path, params)
        logger.info(f"{path} - 获取机构买入/增持/持有/减持/卖出评级家数统计趋势 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getStockDrivers(code: str, logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-stock-fundamental
    获取AI生成的业务驱动因素分析
    '''
    try:
        path = f'/common/v2/basic/stock/drivers/{code}.{getStockRegion(code).upper()}'
        params = {'lang': 'zh-CN'}
        res: dict = await get(path, params)
        logger.info(f"{path} - 获取AI生成的业务驱动因素分析 - {code}")
        return res['data']
    except:
        logger.error(traceback.format_exc())


async def getMarketOverview(logger: Logger) -> dict:
    '''
    https://docs.infoway.io/rest-api/basic-info/get-market-overview
    获取该市场当日的大盘点评（由上游根据当日行情自动生成的一段文字），可直接用于首页市场快讯位
    '''
    try:
        path = '/common/v2/basic/market/overview/CN'
        params = {'lang': 'zh-CN'}
        res: dict = await get(path, params)
        logger.info(f"{path} - 获取该市场当日的大盘点评 - {res}")
        return res['data']
    except:
        logger.error(traceback.format_exc())
