#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import asyncio
import traceback
from logging import Logger
from datetime import datetime, timedelta
from utils.http_client import http


async def run_command(command: str, logger: Logger) -> str:
    """异步执行单个 shell 命令"""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    logger.info(stdout.decode('utf-8').strip())
    if process.returncode == 0:
        return stdout.decode('utf-8').strip()
    else:
        raise Exception(f"Error: {stderr.decode('utf-8').strip()}")


async def get_detail(n):
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
    html_resp = await http.get(n["url"], headers=headers)
    content = n.get('excerpt')
    if html_resp.status_code == 200:
        content = html_resp.text.split("---")[1].split("##")[0]
    return (
        f"【标题】: {n.get('title')}\n"
        f"【时间】: {n.get('time')}\n"
        f"【来源】: {n.get('source_name')}\n"
        f"【摘要】: {n.get('excerpt')}\n"
        f"【正文】: {content}\n"
    )


async def getNewsDetail(keyword: str, logger: Logger) -> str:
    """
    新闻搜索 + 过滤最近 5 天 + 并发获取正文详情
    """
    try:
        days = 5
        # 1. 搜索新闻列表
        cmd = f'longbridge news search "{keyword}" --format json'
        result = await run_command(cmd)
        logger.info(result)
        news_list = json.loads(result)
        if not isinstance(news_list, list) or not news_list:
            return "News: 未找到相关新闻"

        # 2. 过滤最近 N 天的新闻
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_news = []
        for news in news_list:
            try:
                time_str = news.get("time", "").replace("Z", "+00:00")
                news_time = datetime.fromisoformat(time_str)
                if news_time.tzinfo is not None:
                    news_time = news_time.replace(tzinfo=None)  # 转为 naive 比较

                if news_time >= cutoff_date:
                    recent_news.append(news)
            except Exception:
                continue

            if len(recent_news) >= 5:
                break

        if not recent_news:
            return f"最近 {days} 天内无相关新闻"

        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        return "\n---\n".join(details)
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get News Exception: {str(e)}"


async def getStockNews(code: str, logger: Logger) -> str:
    """
    获取股票新闻 + 并发获取正文详情. code: 000001.SZ
    """
    try:
        days = 5
        # 1. 搜索新闻列表
        cmd = f'longbridge news {code} --format json'
        result = await run_command(cmd)
        news_list = json.loads(result)
        if not isinstance(news_list, list) or not news_list:
            return "News: 未找到相关新闻"

        # 2. 过滤最近 N 天的新闻
        cutoff_date = datetime.now() - timedelta(days=days)
        recent_news = []
        for news in news_list:
            try:
                time_str = news.get("time", "").replace("Z", "+00:00")
                news_time = datetime.fromisoformat(time_str)
                if news_time.tzinfo is not None:
                    news_time = news_time.replace(tzinfo=None)  # 转为 naive 比较

                if news_time >= cutoff_date:
                    recent_news.append(news)
            except Exception:
                continue

            if len(recent_news) >= 5:
                break

        if not recent_news:
            return f"最近 {days} 天内无相关新闻"

        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        return "\n---\n".join(details)
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get News Exception: {str(e)}"


async def getStockReport(code: str, logger: Logger) -> str:
    '''获取关键 KPI 摘要（如营收、EPS、ROE）'''
    try:
        cmd = f'longbridge financial-report {code}'
        result = await run_command(cmd)
        return result
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get Stock Financial Report Exception: {str(e)}"

