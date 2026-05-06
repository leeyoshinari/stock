#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
from utils.http_client import http


# 完整题材白名单（不可拆）
FULL_TOPICS = {"虚拟现实", "增强现实", "混合现实", "工业互联网", "新能源车", "新材料"}
# 词头无效词（仅能删在开头）
SUFFIX_STARTWORDS = ("人形")
# 词尾无效词（仅能删在末尾）
SUFFIX_STOPWORDS = ("概念", "行业", "板块", "相关", "受益", "标的", "龙头")
# 结构性无效词（安全删除）
STRUCT_STOPWORDS = ("开发", "服务", "制造", "加工", "生产", "供应", "销售", "流通", "贸易", "商业", "工程", "装备",
                    "施工", "咨询", "检测", "运维", "系统", "平台", "方案", "设备", "装置", "部件", "组件", "模块")


# 4. 核心清洗函数
def normalize_topic(name: str) -> str:
    name = name.strip()
    # 完整题材优先（不拆）
    for topic in FULL_TOPICS:
        if topic in name:
            return topic
    # 删除词头无效词
    for suffix in SUFFIX_STARTWORDS:
        if name.startswith(suffix):
            name = name[len(suffix) + 1:]
            break
    # 删除词尾无效词
    for suffix in SUFFIX_STOPWORDS:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    # 删除结构性无效词（只删一次，防止过度）
    for word in STRUCT_STOPWORDS:
        if name.endswith(word):
            name = name[:-len(word)]
            break
    return name.strip()


def getStockRegionNum(code: str) -> str:
    if code.startswith("60") or code.startswith("68"):
        return "1"
    elif code.startswith("00") or code.startswith("30"):
        return "0"
    else:
        return ""


def getStockRegion(code: str) -> str:
    if code.startswith("60") or code.startswith("68"):
        return "sh"
    elif code.startswith("00") or code.startswith("30"):
        return "sz"
    else:
        return ""


async def isOpenStock() -> bool:
    url = 'https://w.sinajs.cn/?&list=market_status_cn'
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    res = await http.get(url, headers=header)
    if res.status_code == 200:
        if "未开盘" in res.text:
            return False
        else:
            return True
    else:
        return False


# async def getStockZhuLiFundFromDongCai(code: str) -> float:
#     '''获取东方财富当前股票的主力净流入'''
#     '''https://data.eastmoney.com/stockdata/000045.html'''
#     current_time = int(time.time() * 1000)
#     rand = str(int(random.randint(10**17, 10**18 - 1) / 10))
#     header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
#     url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={getStockRegionNum(code)}.{code}&fields=f469,f137,f193,f140,f194,f143,f195,f146,f196,f149,f197,f470,f434,f454,f435,f455,f436,f456,f437,f457,f438,f458,f471,f459,f460,f461,f462,f463,f464,f465,f466,f467,f468,f170,f119,f291&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery11230{rand}_{current_time}&_={current_time + 1}'
#     res = await http.get(url, headers=header)
#     res_json = json.loads(res.text.split('(')[1].split(')')[0])
#     return round(res_json['data']['f137'] / 10000, 2)


async def getStockZhuLiFundFromSina(code: str) -> float:
    '''获取新浪当前股票的主力净流入：https://quotes.sina.cn/hs/company/quotes/view/sz002261?autocallup=no&isfromsina=yes'''
    header = {'Referer': 'https://finance.sina.com.cn', 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f"https://hq.sinajs.cn/?list=zjlxn_{getStockRegion(code)}{code}"
    res = await http.get(url, headers=header)
    res_list = res.text.split(',')
    fund = round(float(res_list[22]) / 10000, 2)
    return fund


async def getStockZhuLiFundFromTencent(code: str) -> float:
    '''获取腾讯财经当前股票的主力净流入'''
    '''https://gu.qq.com/sz300274/gp'''
    current_day = time.strftime("%Y-%m-%d")
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://proxy.finance.qq.com/cgi/cgi-bin/fundflow/hsfundtab?code={getStockRegion(code)}{code}&type=fiveDayFundFlow,todayFundFlow&klineNeedDay=20'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text)
    if 'todayFundFlow' in res_json['data'] and 'mainNetIn' in res_json['data']['todayFundFlow']:
        fund = round(float(res_json['data']['todayFundFlow']['mainNetIn']) / 10000, 2)
    else:
        day_list = res_json['data']['fiveDayFundFlow']['DayMainNetInList']
        fund = next((round(float(item['mainNetIn']) / 10000, 2) for item in day_list if item['date'] == current_day), 0)
    return fund


async def getStockFundFlowFromDongCai(stockCode: str) -> dict[str, float]:
    '''从东方财富获取资金流向，最近10日'''
    '''https://data.eastmoney.com/zjlx/600067.html'''
    fflow = {}
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(stockCode)}.{stockCode}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=10&ut=f057cbcbce2a86e2866ab8877db1d059&cb=cbrnd_F713A9A752FE43CA996C8E4BC0E854DB'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text.split('(')[1].split(')')[0])
    klines = res_json['data']['klines']
    for k in klines:
        datas = k.split(',')
        fflow.update({datas[0].replace('-', ''): round(float(datas[1]) / 10000, 2)})
    return fflow


async def getStockOrderByFundFromSina(page_size: int, p: int, is_price: bool = True) -> list[dict]:
    '''从新浪获取股票资金净流入排序, 分页从 0 开始'''
    '''https://gu.sina.cn/m/?vt=4&cid=76524&node_id=76524#/index/index'''
    fflow = []
    rand_num = time.strftime("%m%d%H%M%S")
    header = {'Referer': 'https://finance.sina.com.cn', 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f"https://cnrank.finance.sina.cn/getSymRankByNode?sort=rp_net&num={page_size}&hnew=1&hcnew=1&asc=0&node=hs&page={p + 1}&callback=hqccall{rand_num}"
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text.split('(')[1].split(')')[0])
    for k in res_json['data']:
        try:
            fund = round(float(k['rp_net']) / 10000, 2)
        except:
            fund = 0.0
        if is_price:
            fflow.append({'code': k['code'], 'name': k['name'], 'fund': fund, 'percent': float(k['percent']), 'price': float(k['price'])})
        else:
            fflow.append({'code': k['code'], 'fund': fund, 'total': res_json['total']})
    return fflow


async def getStockOrderByFundFromTencent(page_size: int, p: int, is_price: bool = True) -> list[dict]:
    '''从腾讯获取股票资金净流入排序, 分页从 0 开始'''
    '''网页：https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj&sort=6&page=1&max=20'''
    fflow = []
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset={page_size * p}&count={page_size}'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text)
    for k in res_json['data']['rank_list']:
        try:
            fund = float(k['zljlr'])
        except:
            fund = 0.0
        if is_price:
            fflow.append({'code': k['code'][2:], 'name': k['name'], 'fund': fund, 'percent': float(k['zdf']), 'price': float(k['zxj'])})
        else:
            fflow.append({'code': k['code'][2:], 'fund': fund, 'total': res_json['data']['total']})
    return fflow


async def getStockDaDanFromTencent(code: str) -> dict:
    '''获取买卖盘占比：https://gu.qq.com/sz300959/gp/dadan'''
    res = {}
    try:
        header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
        url = f'https://stock.gtimg.cn/data/index.php?appn=dadan&action=summary&c={getStockRegion(code)}{code}'
        res = await http.get(url, headers=header)
        res_json = res.text.split('],[')
        da_dan = res_json[9].split(',')
        total_num = float(da_dan[2].strip())
        buy_num = float(da_dan[4].strip())
        sale_num = float(da_dan[5].strip())
        m_num = float(da_dan[6].strip())
        res = {'b': round(buy_num / total_num * 100, 2), 's': round(sale_num / total_num * 100, 2), 'm': round(m_num / total_num * 100, 2)}
    except Exception as e:
        res = {'msg': type(e).__name__}
    return res


async def getStockDaDanFromSina(code: str) -> dict:
    '''从新浪获取买卖盘占比：https://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill.php?symbol=sz000534'''
    res = {}
    try:
        current_day = time.strftime("%Y-%m-%d")
        current_day = '2026-03-06'
        header = {'referer': 'https://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill.php',
                  'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
        url = f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_Bill.GetBillSum?symbol={getStockRegion(code)}{code}&num=60&sort=ticktime&asc=0&volume=40000&amount=0&type=0&day={current_day}'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text)
        total_num = float(res_json[0]['totalvol'])
        buy_num = float(res_json[0]['kuvolume'])
        sale_num = float(res_json[0]['kdvolume'])
        m_num = float(res_json[0]['kevolume'])
        res = {'b': round(buy_num / total_num * 100, 2), 's': round(sale_num / total_num * 100, 2), 'm': round(m_num / total_num * 100, 2)}
    except Exception as e:
        res = {'msg': type(e).__name__}
    return res


async def getStockBanKuaiFromDOngCai(code: str) -> dict:
    '''从东方财富获取股票的板块、概念信息'''
    '''https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=SH600693&color=b'''
    res = {}
    try:
        header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
        url = f'https://datacenter.eastmoney.com/securities/api/data/get?type=RPT_F10_CORETHEME_BOARDTYPE&sty=ALL&filter=(SECUCODE%3D%22{code}.{getStockRegion(code).upper()}%22)&p=1&ps=&sr=1&st=BOARD_RANK&source=HSF10&client=PC&v=02238{int(time.time() * 1000)}'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text)
        data_list = res_json['result']['data']
        region = ''
        industry = ''
        concept = []
        for d in data_list:
            if d['BOARD_TYPE'] == "行业" and d['BOARD_LEVEL'] == "1":
                industry = d['BOARD_NAME']
            elif d['BOARD_TYPE'] == "板块":
                region = d['BOARD_NAME'].replace("板块", "")
            else:
                a = d['BOARD_NAME']
                if ('昨日' in a or '连板' in a or '涨停' in a or '预增' in a or '预减' in a or '扭亏' in a or '财富热' in a or '百元股' in a or '次新股' in a or '最近' in a or 'ST股' in a or '0' in a or '创业' in a or '融资' in a or '沪股' in a or '转债' in a or '深股' in a or 'MSCI中国' in a or '标准普尔' in a or '富时罗素' in a or '证金持股' in a or '重仓' in a or '价值股' in a or '宁组合' in a or '茅指数' in a or '周期股' in a):
                    continue
                concept.append(d['BOARD_NAME'].rstrip('_').strip())
        res = {'region': region, 'industry': industry, 'concept': ','.join(concept)}
    except Exception as e:
        res = {'msg': type(e).__name__}
    return res
