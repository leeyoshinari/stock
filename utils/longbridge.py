#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import random
import logging
import asyncio
import traceback
from urllib.parse import quote
from utils.http_client import http
from utils.results import getStockRegion
from settings import LONGBRIDGE_URL


logger = logging.getLogger(__name__)
h = {"accept": "text/plain"}


async def get_detail(n):
    await asyncio.sleep(random.random())
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
    # html_resp = await http.get(n["url"], headers=headers)
    cmd = f"longbridge news detail {n['id']}"
    html_resp = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=headers)
    content = n.get('excerpt')
    if html_resp.status_code == 200:
        # content = html_resp.text.split("---")[1].split("##")[0]
        content = html_resp.text
    return (
        f"【标题】: {n.get('title')}\n"
        f"【时间】: {n.get('time')}\n"
        f"【正文】: {content}\n"
    )


async def getNewsDetail(keyword: str, lastDay: str) -> str:
    """
    新闻搜索 + 并发获取正文详情\n
    :params lastDay: 筛选日期, 格式: YYYY-MM-DD
    """
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        # 搜索新闻列表
        cmd = f'longbridge news search "{keyword}" --format json'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.debug(f"Run cmd: {cmd} result is {result.text}")
        news_list = json.loads(result.text)
        if not isinstance(news_list, list) or not news_list:
            return "News: 未找到相关新闻"

        # 过滤最近 N 天的新闻
        target_date = lastDay + " 09:30:00"
        recent_news = []
        for news in news_list:
            time_str = news["time"].split('T')[0]
            if time_str >= target_date:
                recent_news.append(news)
            if len(recent_news) >= 2:
                break
        if not recent_news:
            return "最近 N 天内无相关新闻"

        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        logger.info(f"Run cmd: `{cmd}` result is {details}")
        return "\n---\n".join(details)
    except Exception as e:
        logger.error(result.text)
        logger.error(traceback.format_exc())
        return f"Get News Exception: {str(e)}"


async def getStockNews(code: str, lastDay: str) -> str:
    """
    获取股票新闻 + 并发获取正文详情. \n
    :params code: 000001.SZ
    :params lastDay: 筛选日期, 格式: YYYY-MM-DD
    """
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        # 搜索新闻列表
        cmd = f'longbridge news {code}.{getStockRegion(code).upper()} --format json'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.debug(f"Run cmd: {cmd} result is {result.text}")
        news_list = json.loads(result.text)
        if not isinstance(news_list, list) or not news_list:
            return "News: 未找到相关新闻"

        # 过滤最近 N 天的新闻
        target_date = lastDay + " 09:30:00"
        recent_news = []
        for news in news_list:
            time_str = news["published_at"].split('T')[0]
            if time_str >= target_date:
                news.update({'time': news['published_at'], 'excerpt': None})
                recent_news.append(news)
            if len(recent_news) >= 5:
                break
        if not recent_news:
            return "最近 N 天内无相关新闻"

        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        logger.info(f"Run cmd: `{cmd}` result is {details}")
        return "\n---\n".join(details)
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get News Exception: {str(e)}"


async def getStockReport(code: str) -> str:
    '''获取关键 KPI 摘要（如营收、EPS、ROE）'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'longbridge financial-report {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是股票的营收、EPS、ROE等关键摘要数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"


async def getStockFinancialStatement(code: str) -> str:
    '''获取层次化财务报表（利润表/资产负债表/现金流）及同比数据'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'longbridge financial-statement {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是股票的财务报表（利润表/资产负债表/现金流）及同比数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"


async def getStockCalcIndex(code: str) -> str:
    '''获取计算指数（如 PE, PB, 换手率, 股息率）'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'longbridge calc-index {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是股票的PE, PB, 换手率, 股息率等数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"


async def getStockCapital(code: str) -> str:
    '''获取盘中资金分布或资金流时间序列（主力资金流向）'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'longbridge capital {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是股票的主力资金流向数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"


async def getStockValuation(code: str) -> str:
    '''获取 PE, PB, PS, 股息率及同行比较数据'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'longbridge valuation {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是股票的PE, PB, PS, 股息率及同行比较数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"


async def getStockFinancialAnalysis(code: str) -> str:
    '''抓取财报、预期、行情等数据 进行财报分析'''
    await asyncio.sleep(random.random() * 1.5 + 0.5)
    try:
        cmd = f'python3 ~/.openclaw/skills/longbridge-earnings/scripts/collect.py {code}.{getStockRegion(code).upper()}'
        result = await http.get(f"{LONGBRIDGE_URL}?cmd={quote(cmd)}", headers=h)
        logger.info(f"Run cmd: {cmd} result is {result.text}")
        return "以下是财报分析数据:\n" + result.text
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"
