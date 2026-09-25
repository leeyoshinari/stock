#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import time
import traceback
from logging import Logger
from datetime import datetime, timedelta
import akshare as ak
from utils.http_client import http
from utils.results import getStockRegion


async def getStockRealData(code: str, logger: Logger):
    # res = ak.stock_zh_valuation_comparison_em(symbol=f"{getStockRegion(code).upper()}{code}")
    # res = ak.stock_gsrl_gsdt_em(date="20260924")
    # res = ak.stock_comment_detail_zlkp_jgcyd_em(symbol="002413")
    # res = ak.stock_news_em(symbol=code)
    # res = ak.stock_zh_a_disclosure_relation_cninfo(symbol="000001", market="沪深京", start_date="20260819", end_date="20260924")
    url = "https://reportapi.eastmoney.com/report/list"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"}
    post_date = datetime.now() - timedelta(days=180)
    formatted = post_date.strftime("%Y-%m-%d")
    params = {
        "industryCode": "*",
        "pageSize": "5000",
        "industry": "*",
        "rating": "*",
        "ratingChange": "*",
        "beginTime": formatted,
        "endTime": datetime.now().strftime("%Y-%m-%d"),
        "pageNo": "1",
        "fields": "",
        "qType": "0",
        "orgCode": "",
        "code": code,
        "rcode": "",
        "p": "1",
        "pageNum": "1",
        "pageNumber": "1",
    }
    r = await http.get(url, params=params, headers=headers)
    print(json.loads(r.text))
    
    res = ak.stock_research_report_em(symbol=code)
    for r in res.itertuples():
        logger.info(r)
    return res


def getStockDivideDate(day: str, logger: Logger) -> list[dict]:
    '''获取指定 date 的分红派息数据\n
    [{'name': '平安银行', 'code': '000001', 'date': '20260924'}]'''
    result = [{}]
    res = ak.news_trade_notify_dividend_baidu(date=day)
    for r in res.itertuples():
        code = r.股票代码
        if len(code) == 6 and (r.交易所 == 'SH' or r.交易所 == 'SZ') and (getStockRegion(code) == 'sh' or getStockRegion(code) == 'sz'):
            s = {'name': r.股票简称, 'code': code, 'date': r.除权日.strftime("%Y%m%d")}
            result.append(s)
            logger.info(f"Stock 股票除权数据: {s}")
    return result


async def getStockResearchReport(code: str, logger: Logger):
    '''获取个股研报\n
    ak.stock_research_report_em\n
    {'name': '格力电器', 'code': '000651', 'title': '2026年中报点评：高基数下收入承压，盈利能力维持稳定', 'orgName': '国信证券', 'ratingName': '增持', 'time': '2026-09-24', 'url': 'https://pdf.dfcfw.com/pdf/H3_AP202609241829832275_1.pdf'}
    '''
    result = []
    try:
        url = "https://reportapi.eastmoney.com/report/list"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"}
        post_date = datetime.now() - timedelta(days=60)
        formatted = post_date.strftime("%Y-%m-%d")
        params = {
            "industryCode": "*",
            "pageSize": "5000",
            "industry": "*",
            "rating": "*",
            "ratingChange": "*",
            "beginTime": formatted,
            "endTime": datetime.now().strftime("%Y-%m-%d"),
            "pageNo": "1",
            "fields": "",
            "qType": "0",
            "orgCode": "",
            "code": code,
            "rcode": "",
            "p": "1",
            "pageNum": "1",
            "pageNumber": "1",
        }
        res = await http.get(url, params=params, headers=headers)
        data = json.loads(res.text)
        for r in data['data']:
            s = {'name': r['stockName'], 'code': r['stockCode'], 'title': r['title'], 'orgName': r['orgSName'], 
                 'ratingName': r['emRatingName'], 'time': r['publishDate'].split(' ')[0], 'url': f"https://pdf.dfcfw.com/pdf/H3_{r['infoCode']}_1.pdf"}
            result.append(s)
            logger.info(f"{s}")
    except:
        logger.error(traceback.format_exc())
    return result
