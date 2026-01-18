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


def getStockType(code: str) -> int:
    if code.startswith("60"):
        return 1
    elif code.startswith("00"):
        return 1
    elif code.startswith("30"):
        return 1
    else:
        return 0


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


async def getStockZhuLiFundFromDongCai(code: str) -> float:
    '''获取东方财富当前股票的主力净流入'''
    '''https://data.eastmoney.com/stockdata/000045.html'''
    current_time = int(time.time() * 1000)
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://push2.eastmoney.com/api/qt/stock/get?secid={getStockRegionNum(code)}.{code}&fields=f469,f137,f193,f140,f194,f143,f195,f146,f196,f149,f197,f470,f434,f454,f435,f455,f436,f456,f437,f457,f438,f458,f471,f459,f460,f461,f462,f463,f464,f465,f466,f467,f468,f170,f119,f291&ut=b2884a393a59ad64002292a3e90d46a5&cb=jQuery112303607637191727675_{current_time}&_={current_time + 1}'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text.split('(')[1].split(')')[0])
    return round(res_json['data']['f137'] / 10000, 2)


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


async def getStockFundFlowFromDongCai(stockCode: str) -> dict:
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


async def getStockOrderByFundFromDongCai():
    '''从东方财富获取股票资金净流入排序'''
    '''https://data.eastmoney.com/zjlx/detail.html'''
    fflow = []
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    current_time = int(time.time() * 1000)
    for p in range(15):
        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn={p + 1}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text.split('(')[1].split(')')[0])
        diffs = res_json['data']['diff']
        for k in diffs:
            if 1 <= k['f3'] <= 9 and getStockType(k['f12']) and k['f2'] < 51:
                fflow.append({'code': k['f12'], 'name': k['f14'], 'pcnt': k['f3'], 'fund': round(k['f62'] / 10000, 2), 'ratio': k['f184']})
            if k['f62'] < 100:
                break
        time.sleep(1)
    return fflow


async def getStockOrderByFundFromTencent():
    '''从腾讯获取股票资金净流入排序'''
    '''网页：https://stockapp.finance.qq.com/mstats/#mod=list&id=hs_hsj&module=hs&type=hsj&sort=6&page=1&max=20'''
    fflow = []
    page_size = 50
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    for p in range(15):
        url = f'https://proxy.finance.qq.com/cgi/cgi-bin/rank/hs/getBoardRankList?_appver=11.17.0&board_code=aStock&sort_type=netMainIn&direct=down&offset={page_size * p}&count={page_size}'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text)
        for k in res_json['data']['rank_list']:
            change_ratio = float(k['zdf'])
            if 1 <= change_ratio <= 9 and getStockType(k['code'][2:]) and float(k['zxj']) < 51:
                fflow.append({'code': k['code'][2:], 'name': k['name'], 'pcnt': change_ratio, 'fund': float(k['zljlr']), 'ratio': 0})
            if float(k['zljlr']) < 1:
                break
        time.sleep(1)
    return fflow


async def getStockOrderByFundFromSinaBackUp():
    '''从新浪财经获取股票资金净流入排序'''
    fflow = []
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    for p in range(10):
        url = f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_ssggzj?page={p + 1}&num=50&sort=r0_net&asc=0&bankuai=&shichang='
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text)
        for k in res_json:
            change_ratio = round(float(k['changeratio']) * 100, 2)
            if 1 <= change_ratio <= 7 and getStockType(k['symbol'][2:]) and float(k['trade']) < 51:
                fflow.append({'code': k['symbol'][2:], 'name': k['name'], 'pcnt': change_ratio, 'fund': round(float(k['r0_net']) / 10000, 2), 'ratio': round(float(k['r0_ratio']) * 100, 2)})
        time.sleep(1)
    return fflow


async def getStockOrderByFundFromSina():
    '''从新浪财经获取股票资金净流入排序'''
    fflow = []
    current_time = int(time.time())
    header = {'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'}
    for p in range(10):
        url = f'https://cnrank.finance.sina.cn/getSymRankByNode?sort=rp_net&num=50&hnew=0&hcnew=0&asc=0&node=hs&page={p + 1}&callback=hqccall{current_time}'
        res = await http.get(url, headers=header)
        res_json = json.loads(res.text.split('(')[1].split(')')[0])
        diffs = res_json['data']
        for k in diffs:
            change_ratio = round(float(k['percent']), 2)
            if 1 <= change_ratio <= 7 and getStockType(k['symbol'][2:]) and float(k['price']) < 51:
                fflow.append({'code': k['symbol'][2:], 'name': k['name'], 'pcnt': change_ratio, 'fund': round(float(k['rp_net']) / 10000, 2), 'ratio': 0})
        time.sleep(1)
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
        header = {'referer': 'https://vip.stock.finance.sina.com.cn/quotes_service/view/cn_bill.php', 'content-type': 'application/x-www-form-urlencoded',
                  "sec-ch-ua-mobile": "?0", "sec-fetch-dest": "empty", "sec-fetch-site": "same-origin",
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
            if d['BOARD_TYPE'] == '行业':
                industry = d['BOARD_NAME']
            elif d['BOARD_TYPE']:
                region = d['BOARD_NAME'].replace("板块", "")
            else:
                if ('连板' in d['BOARD_NAME'] or '涨停' in d['BOARD_NAME'] or '预增' in d['BOARD_NAME'] or '预减' in d['BOARD_NAME'] or '扭亏' in d['BOARD_NAME']):
                    continue
                concept.append(d['BOARD_NAME'].rstrip('_'))
        res = {'region': region, 'industry': industry, 'concept': ','.join(concept)}
    except Exception as e:
        res = {'msg': type(e).__name__}
    return res


async def getBanKuaiKlineFromDongCai(code: str) -> dict:
    '''从东方财富获取板块的日K数据'''
    '''https://quote.eastmoney.com/bk/90.BK0908.html'''
    res = {}
    try:
        header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
        url = f'https://datacenter.eastmoney.com/securities/api/data/get?type=RPT_F10_CORETHEME_BOARDTYPE&sty=ALL&filter=(SECUCODE%3D%22{code}.{getStockRegion(code).upper()}%22)&p=1&ps=&sr=1&st=BOARD_RANK&source=HSF10&client=PC&v=02238{int(time.time() * 1000)}'
        res = await http.get(url, headers=header)
        _ = json.loads(res.text)
    except Exception as e:
        res = {'msg': type(e).__name__}
    return res


async def getBanKuaiFundFlowFromDongCai(ban: str, page: int = 1) -> dict:
    '''从东方财富获取板块的资金流入数据'''
    '''https://quote.eastmoney.com/center/hsbk.html'''
    current_time = str(int(time.time() * 1000))
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
    if ban == 'concept':
        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123030598726898456863_{current_time}&fid=f62&po=1&pz=50&pn={page}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A90+t%3A3&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
    elif ban == 'industry':
        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery112303362322416527074_{current_time}&fid=f62&po=1&pz=50&pn={page}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A90+t%3A2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
    else:
        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery112303362322416527074_{current_time}&fid=f62&po=1&pz=50&pn=1&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A90+t%3A1&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text.split(current_time + '(')[1][: -2])
    return res_json['data']['diff']


async def getStockTopicFromTongHuaShun() -> dict:
    '''从同花顺获取最新热点主题'''
    '''https://focus.10jqka.com.cn/zttz.html'''
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'}
    current_time = str(int(time.time() * 1000))
    url = f'https://ai.iwencai.com/mobile/NewHotSpotStocks/indexData?params=zcxjh:5,jrjh:7&source=wzzttz&callback=jQuery1830609281377850579_{current_time}&_={current_time}'
    res = await http.get(url, headers=header)
    res_json = json.loads(res.text.split(current_time + '(')[1][: -1])
    return res_json['data']['jrjh']
