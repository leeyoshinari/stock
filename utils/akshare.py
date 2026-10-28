#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import json
import time
import random
import logging
import asyncio
import traceback
import aiohttp
from datetime import datetime, timedelta
import trafilatura
# import akshare as ak
from bs4 import BeautifulSoup
from utils.http_client import http
from utils.results import getStockRegion


logger = logging.getLogger(__name__)
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36"}


# def testAkShare(s):
#     res = ak.tool_trade_date_hist_sina()
#     print(res)


async def getGlobalShortInfoFromSina(lastDay: str) -> str:
    """
    新浪财经-全球财经快讯\n
    :param lastDay: '2026-09-24 16:00:00'\n
    https://finance.sina.com.cn/7x24
    """
    try:
        # 1-宏观，5-市场，7-央行，102-国际
        tagList = ['1', '5', '7', '102']
        content = ''
        url = "https://zhibo.sina.com.cn/api/zhibo/feed"
        for tag in tagList:
            params = {
                "page": "1",
                "page_size": "20",
                "zhibo_id": "152",
                "tag_id": tag,
                "dire": "f",
                "dpc": "1",
                "pagesize": "20",
                "type": "1",
            }
            r = await http.get(url, params=params, headers=headers)
            data_json = json.loads(r.text)
            data = data_json['result']['data']['feed']['list']
            for d in data:
                if d['create_time'] > lastDay:
                    if len(d['rich_text']) > 50:
                        content += f"【时间】：{d['create_time']}【内容】：{d['rich_text']} \n"
                else:
                    break
            await asyncio.sleep(0.5)
        logger.info(content)
        return content
    except:
        logger.error(traceback.format_exc())
        return ''


async def getShortInfoMorning() -> str:
    """
    东方财富-财经早餐\n
    https://stock.eastmoney.com/a/czpnc.html
    """
    try:
        url = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
        params = {
            "client": "web",
            "biz": "web_news_col",
            "column": "1207",
            "order": "1",
            "needInteractData": "0",
            "page_index": "1",
            "page_size": "1",
            "req_trace": str(int(time.time() * 1000)),
            "fields": "code,showTime,title,mediaName,summary,image,url,uniqueUrl,Np_dst",
        }
        r = await http.get(url, params=params, headers=headers)
        data_json = json.loads(r.text)
        data = data_json['data']['list'][0]
        res = await http.get(data['url'], headers=headers)
        if res.status_code == 200:
            extracted = trafilatura.extract(res.text, include_comments=False, include_tables=False)
            content = f"【摘要】：{data['summary']}\n【正文】：{extracted}"
            logger.info(content)
            return content
        else:
            return ''
    except:
        logger.error(traceback.format_exc())
        return ''


async def getGlobalShortInfoFromThs(lastDay: str) -> str:
    """
    同花顺财经-全球财经直播\n
    :param lastDay: '2026-09-24 16:00:00'\n
    https://news.10jqka.com.cn/realtimenews.html
    """
    try:
        url = "https://news.10jqka.com.cn/tapp/news/push/stock"
        params = {
            "page": "1", "pagesize": 400,
            "tag": "",
            "track": "website",
        }
        r = await http.get(url, params=params, headers=headers)
        data_json = json.loads(r.text)
        data = data_json['data']['list']
        content = ''
        for d in data:
            rtime = datetime.fromtimestamp(int(d['rtime'])).strftime("%Y-%m-%d %H:%M:%S")
            if rtime > lastDay:
                content += f"【时间】：{rtime}【内容】：{d['digest']} \n"
            else:
                break
        logger.info(content)
        return content
    except:
        logger.error(traceback.format_exc())
        return ''


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
        return "\n---\n".join(details)
    else:
        return ''


async def getStockResearchReport(code: str) -> list[dict]:
    '''获取个股研报\n
    ak.stock_research_report_em\n
    返回值: {'name': '格力电器', 'code': '000651', 'title': '2026年中报点评：高基数下收入承压，盈利能力维持稳定', 'orgName': '国信证券', 'ratingName': '增持', 'time': '2026-09-24', 'url': 'https://pdf.dfcfw.com/pdf/H3_AP202609241829832275_1.pdf'}
    '''
    result = []
    try:
        url = "https://reportapi.eastmoney.com/report/list"
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


async def getStockFinanceReportFromSina(code: str) -> str:
    '''获取股票的财务报表-关键指标\n
    code: 000001, stock_financial_abstract
    '''
    try:
        url = "https://quotes.sina.cn/cn/api/openapi.php/CompanyFinanceService.getFinanceReport2022"
        params = {
            "paperCode": f"{getStockRegion(code)}{code}",
            "source": "gjzb",
            "type": "0",
            "page": "1",
            "num": "8",
        }
        r = await http.get(url, params=params)
        data_json = json.loads(r.text)
        dataDict: dict = data_json['result']['data']['report_list']
        dates = sorted(dataDict.keys(), reverse=True)
        indicators = {}
        for date in dates:
            for item in dataDict[date].get('data', []):
                if item.get('item_display_type') != 1:
                    title = item.get('item_title')
                    value = item.get('item_value')
                    display_value = value if value is not None else '-'

                    # 如果指标名称未记录，则初始化；保留首次出现的指标（去重）
                    if title not in indicators:
                        indicators[title] = {}
                    indicators[title][date] = display_value

        # 构建 Markdown 表格
        # 表头
        header = "| 指标 | " + " | ".join(dates) + " |"
        # 分隔线
        separator = "|---|" + "|".join(["---"] * len(dates)) + "|"
        # 表体数据行
        rows = []
        for title, date_values in indicators.items():
            row_vals = [str(date_values.get(date, '-')) for date in dates]
            row_str = f"| {title} | " + " | ".join(row_vals) + " |"
            rows.append(row_str)
        # 拼接完整的 Markdown 表格
        markdown_table = "\n".join([header, separator] + rows)
        return f"股票{code}的财务报表数据如下:\n" + markdown_table
    except Exception as e:
        logger.error(traceback.format_exc())
        return f"Stock Finance Report Error: {e}"


async def _get_baidu_cookie(session: aiohttp.ClientSession, headers: dict) -> str:
    """
    安全异步获取百度股市通所需的 Cookie
    :param session: aiohttp.ClientSession 实例
    :param headers: 基础请求头
    """
    try:
        # 第一步：获取基础 Cookie (BAIDUID系列)
        async with session.get("https://finance.baidu.com/calendar", headers=headers, ssl=False, timeout=10) as resp1:
            resp1.raise_for_status()
            text1 = await resp1.text()
            # aiohttp 的 cookies 是 Morsel 对象，需通过 .value 获取值
            baiduid_morsel = resp1.cookies.get("BAIDUID")
            baiduid_bfess_morsel = resp1.cookies.get("BAIDUID_BFESS")
            baiduid = baiduid_morsel.value if baiduid_morsel else None
            baiduid_bfess = baiduid_bfess_morsel.value if baiduid_bfess_morsel else None
            if not all([baiduid, baiduid_bfess]):
                raise ValueError("Missing BAIDUID cookies in first response")

            # 第二步：提取并请求 hm.js
            hm_match = re.search(r"https?://hm\.baidu\.com/hm\.js\?\w+", text1)
            if not hm_match:
                hm_match = re.search(r"//hm\.baidu\.com/hm\.js\?\w+", text1)

            if not hm_match:
                raise ValueError("Failed to extract hm.js URL from response")

            hm_url = (
                "https:" + hm_match.group()
                if hm_match.group().startswith("//")
                else hm_match.group()
            )

        # 第二步请求 (自动携带第一步的 Cookie)
        async with session.get(hm_url, headers=headers, ssl=False, timeout=10) as resp2:
            resp2.raise_for_status()
            hmac_count_morsel = resp2.cookies.get("HMACCOUNT")
            hmac_count_bfess_morsel = resp2.cookies.get("HMACCOUNT_BFESS")
            hmac_count = hmac_count_morsel.value if hmac_count_morsel else None
            hmac_count_bfess = hmac_count_bfess_morsel.value if hmac_count_bfess_morsel else None

            if not all([hmac_count, hmac_count_bfess]):
                raise ValueError("Missing HMACCOUNT cookies in second response")

            # 安全拼接 Cookie
            return (
                f"BAIDUID={baiduid}; "
                f"BAIDUID_BFESS={baiduid_bfess}; "
                f"HMACCOUNT={hmac_count}; "
                f"HMACCOUNT_BFESS={hmac_count_bfess}"
            )

    except aiohttp.ClientError as e:
        raise ConnectionError(f"Network request failed: {str(e)}") from e
    except re.error as e:
        raise ValueError(f"Regex pattern error: {str(e)}") from e


async def getStockDivideDate(day: str) -> list[dict]:
    """
    百度股市通日历数据基础函数（支持分页），获取指定 date 的分红派息数据\n
    :param date: 查询日期 (格式: YYYYMMDD)\n
    :return: [{'name': '平安银行', 'code': '000001', 'date': '20260924'}]
    """
    # 构建请求参数
    pageSize = 100     # 每页100条
    base_params = {
        "start_date": day,
        "end_date": day,
        "market": "ab",
        "pn": "0",
        "rn": pageSize,
        "cate": "notify_divide",
        "finClientType": "pc",
    }

    # 构建请求头
    headers = {
        "accept": "application/vnd.finance-web.v1+json",
        "accept-encoding": "gzip, deflate, br, zstd",
        "accept-language": "en,zh-CN;q=0.9,zh;q=0.8",
        "cache-control": "no-cache",
        "origin": "https://finance.baidu.com",
        "pragma": "no-cache",
        "priority": "u=1, i",
        "referer": "https://finance.baidu.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.138 Safari/537.36",
    }

    # 使用单个 Session 复用连接，提升性能
    async with aiohttp.ClientSession() as session:
        try:
            cookie = await _get_baidu_cookie(session, headers.copy())
        except Exception as e:
            raise RuntimeError(f"Failed to obtain Baidu cookies: {str(e)}") from e

        headers["cookie"] = cookie
        url = "https://finance.pae.baidu.com/sapi/v1/financecalendar"
        big_list = []
        target_date = day
        total_records = 0

        # 第一次请求
        params = base_params.copy()
        async with session.get(url=url, params=params, headers=headers, timeout=15, ssl=False,) as response:
            response.raise_for_status()
            data_json = await response.json()

        # 从 JSON 中提取指定日期的总记录数
        if "Result" in data_json and "calendarInfo" in data_json["Result"]:
            calendar_info = data_json["Result"]["calendarInfo"]
            for item in calendar_info:
                if item.get("date") == target_date:
                    total_records = item.get("total", 0)
                    break

        # 计算总页数 (每页100条)
        total_pages = int((total_records + pageSize - 1) / pageSize) if total_records > 0 else 1
        logger.info(f"{day} 总共 {total_pages} 页数")
        # 处理所有页码
        for page in range(total_pages):
            if page > 0:  # 第一页已在前面获取
                params = base_params.copy()
                params["pn"] = str(page)
                async with session.get(url=url, params=params, headers=headers, timeout=15) as response:
                    response.raise_for_status()
                    data_json = await response.json()
                    logger.info(f"{day} 分红派息信息正在获取第 {page} / {total_pages} 页")

            # 提取并处理指定日期的数据
            if "Result" in data_json and "calendarInfo" in data_json["Result"]:
                for item in data_json["Result"]["calendarInfo"]:
                    if item.get("date") == target_date and item.get("list"):
                        for item in item["list"]:
                            processed_data = {"name": item["name"], "code": item["code"], "diviDate": item["diviDate"]}
                            big_list.append(processed_data)
        return big_list


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
