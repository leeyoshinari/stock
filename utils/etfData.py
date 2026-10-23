#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import time
import json
import logging
import asyncio
import traceback
from utils.http_client import http
from utils.results import getStockRegion


logger = logging.getLogger(__name__)
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


async def getEtfInfoFromSH(page: int):
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


async def getEtfInfoFromSZ(page: int):
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


async def getEtfDetailFromDongCai(code: str):
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


async def getHoldStockOfEtfFromTencent(host: str, code: str) -> list[dict]:
    result = []
    try:
        if code == '159934':      # 黄金ETF过滤掉
            return []
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


async def getEtfShareFromSH(current_day: str) -> dict[str, float]:
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


async def getEtfShareFromSZ(code: str, current_day: str) -> list:
    """ 获取单个 code 的份额, https://fund.szse.cn/marketdata/fundslist/index.html
    :params current_day: format: %Y-%m-%d
    """
    shares = []
    try:
        t = int(time.time() * 1000)
        res = await http.get(f"https://fund.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON&CATALOGID=fund_jjgm&TABKEY=tab1&txtDm={code}&txtStart={current_day}&txtEnd={current_day}&random=0.574{t}")
        if res.status_code == 200:
            res_json = json.loads(res.text)
            shares = res_json[0]['data']
        else:
            raise Exception(f"request error: {res.status_code}")
    except:
        logger.error(traceback.format_exc())
    return shares


async def getEtfShareDictFromSZ(code: str, start_day: str, end_day: str) -> dict[str, float]:
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


def pre_filter_etf(records: list[dict]) -> tuple[bool, str]:
    """ETF 前置过滤。

    :param records: 包含单只ETF最近30-60天数据的 list[dict]，按日期升序排列。
    :return: (是否通过过滤, 过滤原因/放行原因)
    """
    if len(records) < 20:
        return False, "数据不足20天"

    latest = records[-1]
    recent_5 = records[-5:]
    recent_3 = records[-3:]

    # 极端溢价/折价排雷
    high_thres = 1
    low_thres = -1
    if latest['premium'] > high_thres or latest['premium'] < low_thres:
        return False, f"极端溢价/折价 - {latest['premium']}"

    # 明确的资金出逃（份额大幅减少，直接看空，无需分析）
    if latest['shares_delta'] < -1:  # 单日份额减少 > 1%
        return False, f"份额大幅流出(单日<-1%) - {latest['shares_delta']}"

    if latest['shares_delta'] >= 50:
        return False, f"份额异常增加，可能拆分 - {latest['shares_delta']}"

    # 份额显著流入（左侧建仓或右侧主升，必须分析）
    sum_delta_3 = sum(r['shares_delta'] for r in recent_3)
    if latest['shares_delta'] > 1 or sum_delta_3 > 2:
        return True, "白名单: 份额显著流入"

    # 真爆量（放量 且 份额必须增加，排除场内对倒）
    if latest['qrr'] > 1.5 and latest['shares_delta'] > 0.6:
        return True, "白名单: 真爆量(放量且份额增加)"

    # 处于20日线变盘临界点（误差1%以内）
    ma20 = latest['ma_twenty']
    if ma20 > 0 and abs(latest['current_price'] - ma20) / ma20 < 0.01:
        return True, "白名单: 贴近20日牛熊分界线"

    # 计算近5日均值
    avg_turnover_5 = sum(r['turnover_rate'] for r in recent_5) / 5
    avg_qrr_5 = sum(r['qrr'] for r in recent_5) / 5

    # 绝对死水（无量、无量比、无份额变化）
    max_abs_delta_5 = max(abs(r['shares_delta']) for r in recent_5)
    if avg_turnover_5 < 0.5 and avg_qrr_5 < 0.8 and max_abs_delta_5 < 0.5:
        return False, "常规过滤: 绝对死水"

    # 布林线极度缩口 且 均线无趋势（防止误杀缓慢上涨/下跌）
    bandwidth = (latest['boll_up'] - latest['boll_low']) / latest['ma_twenty']
    # 判断无趋势：5日、10日、20日均线极度粘合（最大差值 < 1%）
    ma_max = max(latest['ma_five'], latest['ma_ten'], latest['ma_twenty'])
    ma_min = min(latest['ma_five'], latest['ma_ten'], latest['ma_twenty'])
    is_ma_tangle = (ma_max - ma_min) / latest['ma_twenty'] < 0.01
    if bandwidth < 0.03 and is_ma_tangle:
        return False, "常规过滤: 布林缩口且均线粘合(无方向)"

    # 无抵抗空头排列（非左侧交易者适用）
    if (latest['current_price'] < latest['ma_twenty'] and latest['ma_five'] < latest['ma_ten'] < latest['ma_twenty']):
        # 检查近5日有无放量阳线（有则说明有抵抗，放行）
        has_vol_yang = any(r['qrr'] > 1.5 and r['current_price'] > r['open_price'] and r['current_price'] > r['last_price'] for r in recent_5)
        if not has_vol_yang:
            return False, "常规过滤: 无抵抗空头排列"

    # 通过所有常规过滤
    return True, "通过常规过滤"
