#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import time
import json
import asyncio
import traceback
from logging import Logger
from utils.http_client import http
from utils.results import getStockRegion


headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


async def getEtfInfoFromSH(page: int, logger: Logger):
    hh = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'
    }
    t = int(time.time() * 1000)
    result = None
    try:
        url = f"https://query.sse.com.cn/commonSoaQuery.do?jsonCallBack=jsonpCallback77527968&isPagination=true&pageHelp.pageSize=25&pageHelp.pageNo={page}&pageHelp.beginPage={page}&pageHelp.cacheSize=1&pageHelp.endPage={page}&pagecache=false&sqlId=FUND_LIST&fundType=00&subClass=03&_={t}"
        res = await http.get(url, headers=hh)
        if res.status_code == 200:
            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
            datas = json.loads('{' + res_text + '}')
            result = datas['pageHelp']
        else:
            logger.error(f"上交所获取ETF列表异常 --- {res.text}")
    except:
        logger.error(traceback.format_exc())
    return result


async def getEtfInfoFromSZ(page: int, logger: Logger):
    hh = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
        'host': 'www.szse.cn', 'referer': 'https://www.szse.cn/market/product/stock/list/index.html', 'content-type': 'application/json'
    }
    t = int(time.time() * 1000)
    result = []
    try:
        url = f"https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=1945&tab1PAGENO={page}&random=0.113{t}"
        res = await http.get(url, headers=hh)
        if res.status_code == 200:
            result = json.loads(res.text)[0]
        else:
            logger.error(f"深交所获取ETF列表异常 --- {res.text}")
    except:
        logger.error(traceback.format_exc())
    return result


async def getEtfDetailFromDongCai(code: str, logger: Logger):
    result = None
    try:
        url = f"https://fundf10.eastmoney.com/jbgk_{code}.html"
        res = await http.get(url, headers=headers)
        if res.status_code == 200:
            result = extract_fund_info(res.text)
            if not result['name'] or len(result['name']) < 1:
                logger.error(f"获取ETF信息请求未正常返回... {res.text}")
        else:
            logger.error(f"获取ETF信息请求code未正常返回... {res.text}")
    except:
        logger.error(traceback.format_exc())
    return result


async def getHoldStockOfEtfFromTencent(host: str, code: str, logger: Logger) -> list[dict]:
    result = None
    try:
        stockCode = f"{getStockRegion(code)}{code}"
        if host and host.startswith('http'):
            param_data = {"url": f"https://zxg.txfund.com/ifzqgtimg/appstock/fund/baseInfo/asset?code={stockCode}&_callback=jQuery1124014406183612592238_{int(time.time() * 1000)}&_={int(time.time() * 1000)}", "method": "GET"}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://zxg.txfund.com/ifzqgtimg/appstock/fund/baseInfo/asset?code={stockCode}&_callback=jQuery1124014406183612592238_{int(time.time() * 1000)}&_={int(time.time() * 1000)}", headers=headers)
        if res.status_code == 200:
            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
            datas = json.loads('{' + res_text + '}')
            res = [{'code': r['code'], 'name': r['name'], 'ratio': r['ratio']} for r in datas['data']['stock']]
            return res
        else:
            logger.error(f"获取ETF信息请求code未正常返回... {res.text}")
    except:
        logger.error(traceback.format_exc())
    return result


def extract_fund_info(html):
    def to_float(val, res=None):
        if not val or '---' in val:
            return res
        try:
            return float(val)
        except ValueError:
            return res

    # 1. 基金简称
    match = re.search(r'<th>基金简称</th><td>(.*?)</td>', html)
    fund_name = match.group(1).strip() if match else ''

    # 2. 基金代码
    match = re.search(r'<th>基金代码</th><td>(\d+)', html)
    fund_code = match.group(1).strip() if match else ''

    # 3. 成立日期
    match = re.search(r'成立日期[：:/]*\s*(?:<span>)?\s*(\d{4}-\d{2}-\d{2})', html)
    establish_date = match.group(1).strip() if match else ''

    # 4. 净资产规模（只匹配“亿”，如果是“万”则匹配不上返回None）
    # 优先从表格中匹配，其次从外部 div 匹配
    match = re.search(r'<th>净资产规模</th><td>\s*([\d.]+)\s*亿元', html)
    if not match:
        match = re.search(r'净资产规模.*?([\d.]+)\s*亿元', html, re.DOTALL)
    nav_scale = to_float(match.group(1), res=0.0) if match else 0.0

    # 5. 管理费率
    match = re.search(r'<th>管理费率</th><td>\s*([\d.]+)%', html)
    management_fee = to_float(match.group(1), res=0.0) if match else 0.0

    # 6. 托管费率
    match = re.search(r'<th>托管费率</th><td>\s*([\d.]+)%', html)
    custodian_fee = to_float(match.group(1), res=0.0) if match else 0.0

    # 7. 销售服务费率
    match = re.search(r'<th>销售服务费率</th><td>\s*([\d.]+)%', html)
    sales_service_fee = to_float(match.group(1), res=0.0) if match else 0.0

    # 8. 跟踪标的
    match = re.search(r'<th>跟踪标的</th><td>(.*?)</td>', html)
    tracking_index = match.group(1).strip() if match else ''

    return {
        "name": fund_name,
        "code": fund_code,
        "date": establish_date,
        "capital": round(nav_scale, 2),
        "fee": round(management_fee + custodian_fee + sales_service_fee, 2),
        "management_fee": management_fee,
        "custodian_fee": custodian_fee,
        "sales_service_fee": sales_service_fee,
        "tracking": tracking_index
    }


async def getEtfShareFromSH(current_day: str, logger: Logger) -> dict[str, float]:
    """ 只能拉取整个 etf 列表, https://www.sse.com.cn/market/funddata/volumn/etfvolumn
    :params current_day: format: %Y-%m-%d
    """
    etf = {}
    try:
        # current_day = time.strftime("%Y-%m-%d")
        t = int(time.time() * 1000)
        page = 1
        hh = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36',
            'host': 'query.sse.com.cn', 'referer': 'https://www.sse.com.cn/'
        }
        res = await http.get(f"https://query.sse.com.cn/commonQuery.do?jsonCallBack=jsonpCallback29249111&isPagination=true&pageHelp.pageSize=100&pageHelp.pageNo={page}&pageHelp.beginPage={page}&pageHelp.cacheSize=1&pageHelp.endPage={page}&sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L&STAT_DATE={current_day}&_={t}", headers=hh)
        if res.status_code == 200:
            res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
            res_json = json.loads('{' + res_text + '}')
            total_page = res_json['pageHelp']['pageCount']
            logger.info(f"上交所获取ETF份额, 第 {page} / {total_page} 页")
            for r in res_json['pageHelp']['data']:
                etf.update({r['SEC_CODE']: float(r['TOT_VOL']) / 10000})
            for p in range(1, total_page):
                res = await http.get(f"https://query.sse.com.cn/commonQuery.do?jsonCallBack=jsonpCallback29249111&isPagination=true&pageHelp.pageSize=100&pageHelp.pageNo={p + 1}&pageHelp.beginPage={p + 1}&pageHelp.cacheSize=1&pageHelp.endPage={p + 1}&sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L&STAT_DATE={current_day}&_={t}", headers=hh)
                if res.status_code == 200:
                    res_text = res.text.replace('({', 'q1a2z3').replace('})', 'q1a2z3').split('q1a2z3')[1]
                    res_json = json.loads('{' + res_text + '}')
                    logger.info(f"上交所获取ETF份额, 第 {p + 1} / {total_page} 页")
                    for r in res_json['pageHelp']['data']:
                        etf.update({r['SEC_CODE']: float(r['TOT_VOL']) / 10000})
                    await asyncio.sleep(3)
    except:
        logger.error(traceback.format_exc())
    return etf


async def getEtfShareFromSZ(code: str, current_day: str, logger: Logger) -> float:
    """ 获取单个 code 的份额, https://fund.szse.cn/marketdata/fundslist/index.html
    :params current_day: format: %Y-%m-%d
    """
    shares = 0.0
    try:
        t = int(time.time() * 1000)
        res = await http.get(f"https://fund.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=fund_jjgm&TABKEY=tab1&txtDm={code}&txtStart={current_day}&txtEnd={current_day}&random=0.574{t}")
        if res.status_code == 200:
            res_json = json.loads(res.text)
            shares = float(res_json[0]['data'][0]['current_size'].replace(',', ''))
        else:
            raise Exception(f"request error: {res.status_code}")
    except:
        logger.error(traceback.format_exc())
    return shares / 10000


async def getEtfShareDictFromSZ(code: str, start_day: str, end_day: str, logger: Logger) -> dict[str, float]:
    """ 获取单个 code 的份额, 用于刷数据, https://fund.szse.cn/marketdata/fundslist/index.html
    :params current_day: format: %Y-%m-%d
    """
    etf = {}
    try:
        t = int(time.time() * 1000)
        res = await http.get(f"https://fund.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=fund_jjgm&TABKEY=tab1&txtDm={code}&txtStart={start_day}&txtEnd={end_day}&random=0.574{t}")
        if res.status_code == 200:
            res_json = json.loads(res.text)
            for r in res_json[0]['data']:
                day = r['size_date'].replace('-', '')
                shares = float(r['current_size'].replace(',', ''))
                etf.update({day: shares / 10000})
        else:
            raise Exception(f"request error: {res.status_code}")
    except:
        logger.error(traceback.format_exc())
    return etf
