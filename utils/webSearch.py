#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import traceback
import lxml.html
import trafilatura
from logging import Logger
from urllib.parse import quote
from utils.http_client import http
from settings import HTTP_HOST1


async def searchWithSerper(query: str, logger: Logger, df: str = 'w'):
    '''使用 serper 搜索，每月 2000 次搜索
    :params df: h-过去一小时 / d-过去一天 / w-过去一周 / m-过去一个月 / y-过去一年
    '''
    url = f"{HTTP_HOST1}/api/search/serper?q={quote(query)}&dateRestrict={df}"
    try:
        resp = await http.get(url)
        logger.info(resp.text)
        if resp.status_code == 200:
            logger.info(resp.text)
    except:
        logger.error(traceback.format_exc())


async def searchWithDuckDuckGo(query: str, logger: Logger, df: str = 'w', max_results: int = 5) -> list[dict]:
    """DuckDuckGo 搜索 (限制最近一周 df=w) + trafilatura 正文提取"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "priority": "u=0, i",
        "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Referer": "https://html.duckduckgo.com/"
    }
    data = {'q': query, 'df': df, 'b': None, 'kl': None}
    url = "https://html.duckduckgo.com/html/"  # ?q={urllib.parse.quote(query)}&b=&kl=&df=w"
    try:
        resp = await http.post(url, data=data, headers=headers)
        if resp.status_code != 200:
            return "Search Error: HTTP " + str(resp.status_code) + resp.text
        logger.debug(f"Web Search KeyWord: {query}, result: {resp.text}")
        tree = lxml.html.fromstring(resp.text)
        content = []
        snippetList = tree.xpath('//a[@class="result__snippet"]')
        links = tree.xpath('//a[@class="result__url"]/@href')
        for snippet, link in zip(snippetList, links):
            text = snippet.text_content().strip()
            text_len = len(text)
            try:
                html_resp = await http.get(link, headers=headers)
                if html_resp.status_code == 200:
                    extracted = trafilatura.extract(html_resp.text, include_comments=False, include_tables=False)
                    if extracted:
                        if len(extracted) < text_len * 2:
                            continue
                        content.append({"snippet": text, "content": extracted[:1000]})
                        logger.info(f"Fetch Content success: {query} - {text} - {link}")
                if len(content) > max_results:
                    break
            except Exception as e:
                logger.error(f"WebSearch Fetch Content Error: {text} - {link} - {e}")
        return content
    except:
        logger.error(traceback.format_exc())
