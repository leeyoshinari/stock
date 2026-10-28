#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import random
import asyncio
import logging
import traceback
from bs4 import BeautifulSoup
from urllib.parse import quote
from utils.http_client import http
from utils.longbridge import getNewsDetail
from utils.dispatcher import AsyncRoundRobinDispatcher
from settings import HTTP_HOST_CLOUD, LONGBRIDGE_URL


logger = logging.getLogger(__name__)


async def searchWithSerper(query: str, df: str = 'w') -> str:
    '''使用 serper 搜索，每月 2000 次搜索
    :params df: h-过去一小时 / d-过去一天 / w-过去一周 / m-过去一个月 / y-过去一年
    '''
    url = f"{HTTP_HOST_CLOUD}/api/search/serper?q={quote(query)}&tbs={df}"
    try:
        resp = await http.get(url)
        if resp.status_code == 200:
            detail = []
            datas = json.loads(resp.text)
            for r in datas['results']:
                if len(r['content']) > 100:
                    detail.append(f"【标题】: {r['title']}\n【正文】: {r['content']}\n")
            return "\n---\n".join(detail)
        return f"Get News error: http status code is {resp.status_code}"
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Get News Exception: {str(e)}"


async def getNewsFromLongBridge(keyword: str, lastDay: str) -> str:
    return await getNewsDetail(keyword, lastDay)


async def getNewsFromDongCai(keyword: str, lastDay: str) -> str:
    """
    东方财富-个股新闻-最近 100 条新闻 https://so.eastmoney.com/news/s?keyword=603777

    :params keyword: 股票代码
    :params lastDay: 筛选日期, 格式: YYYY-MM-DD
    :return: 新闻
    :rtype: str
    """
    url = "https://search-api-web.eastmoney.com/search/jsonp"
    inner_param = {
        "uid": "",
        "keyword": keyword,
        "type": ["cmsArticleWebOld"],
        "client": "web",
        "clientType": "web",
        "clientVersion": "curr",
        "param": {
            "cmsArticleWebOld": {
                "searchScope": "default",
                "sort": "default",
                "pageIndex": 1,
                "pageSize": 10,
                "preTag": "<em>",
                "postTag": "</em>",
            }
        },
    }
    params = {
        "cb": "jQuery35101792940631092459_1764599530165",
        "param": json.dumps(inner_param, ensure_ascii=False),  # 保留中文，
        "_": "1764599530176",
    }
    headers = {
        "accept": "*/*",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
        "cache-control": "no-cache",
        "connection": "keep-alive",
        "cookie": "qgqp_b_id=652bf4c98a74e210088f372a17d4e27b; st_nvi=ulN5JAj9FUocz3p4klMME9f20; emshistory=%5B%22603777%22%5D; nid18=010d039dd427dc4d187090491f47d7ad; nid18_create_time=1764582801999; gviem=gSdeY51VWSuTzM3kWaagtf560; gviem_create_time=1764582801999; st_si=55269775884615; st_pvi=66803244437563; st_sp=2025-11-19%2014%3A19%3A16; st_inirUrl=https%3A%2F%2Fso.eastmoney.com%2Fnews%2Fs; st_sn=2; st_psi=20251201223210488-118000300905-0940816858; st_asi=delete",
        "host": "search-api-web.eastmoney.com",
        "pragma": "no-cache",
        "referer": "https://so.eastmoney.com/news/s?keyword=603777",
        "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "no-cors",
        "sec-fetch-site": "same-site",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    }
    res = await http.get(url, params=params, headers=headers)
    if res.status_code == 200:
        res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
        datas = json.loads('{' + res_text + '}')
        news_list = datas['result']['cmsArticleWebOld']
        target_day = lastDay + " 09:30:00"
        recent_news = [r for r in news_list if r['date'] > target_day]
        details = await asyncio.gather(*[get_detail(n) for n in recent_news])
        logger.info(f"Search News from dongcai local - {details}")
        return "\n---\n".join(details)
    else:
        return ''


async def get_detail(n):
    await asyncio.sleep(random.random())
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"}
    html_resp = await http.get(n["url"], headers=headers)
    content = n.get('excerpt')
    if html_resp.status_code == 200:
        content = await extract_paragraphs_async(html_resp.text, 'ContentBody')
    return (
        f"【标题】: {n.get('title', '').replace('<em>', '').replace('</em>', '')}\n"
        f"【时间】: {n.get('date')}\n"
        f"【正文】: {content}\n"
    )


async def extract_paragraphs_async(html_content: str, target_id: str = None) -> str:
    """
    同步的 HTML 解析函数。
    """
    if not html_content:
        return ""

    def _parse_html_sync(html_content: str, target_id: str) -> str:
        soup = BeautifulSoup(html_content, 'html.parser')
        # 如果指定了目标区域，则优先在该区域内查找，提高准确率并减少解析量
        search_area = soup.find(id=target_id) if target_id else soup
        if not search_area:
            search_area = soup  # 降级为全局搜索

        extracted_texts = []
        for p in search_area.find_all('p'):
            # separator='' 防止块级元素被意外加空格，strip=True 去除首尾空白
            text = p.get_text(separator='', strip=True)
            if text:
                extracted_texts.append(text)
        return '\n'.join(extracted_texts)

    result = await asyncio.to_thread(_parse_html_sync, html_content, target_id)
    return result


async def getNewsFromDongCaiCloud(keyword: str, lastDay: str) -> str:
    try:
        res = await http.get(f'{LONGBRIDGE_URL}/getNews?keyword={keyword}&lastDay={lastDay}')
        logger.info(f"Search News from dongcai cloud - {res.text}")
    except:
        logger.error(traceback.format_exc())
        return ''


search_method_list = [getNewsFromDongCai, getNewsFromDongCaiCloud, getNewsFromLongBridge]
search_dispatcher = AsyncRoundRobinDispatcher(methods=search_method_list, max_retries=3, timeout=99, cooldown=200, name="AIDispatcher")


async def getNews(*args, **kwargs):
    return await search_dispatcher.call(*args, **kwargs)
