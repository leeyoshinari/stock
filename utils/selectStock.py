#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import time
import json
import requests


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


def getStockFundFlowFromDongCai(stockCode: str) -> dict:
    '''从东方财富获取资金流向，最近10日'''
    fflow = {}
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid={getStockRegionNum(stockCode)}.{stockCode}&fields1=f1,f2,f3,f7&fields2=f51,f52,f62,f63&lmt=10&ut=f057cbcbce2a86e2866ab8877db1d059&cb=cbrnd_F713A9A752FE43CA996C8E4BC0E854DB'
    res = requests.get(url, headers=header)
    res_json = json.loads(res.text.split('(')[1].split(')')[0])
    klines = res_json['data']['klines']
    for k in klines:
        datas = k.split(',')
        fflow.update({datas[0].replace('-', ''): round(float(datas[1]) / 10000, 2)})
    return fflow


def getStockFundFlowFromStockStar(stockCode: str) -> dict:
    '''从证券之星获取资金流向，最近10日'''
    fflow = {}
    pattern = r'<tr>(.*?)</tr>'
    url = f'https://stock.quote.stockstar.com/capital_{stockCode}.shtml'
    header = {
        'content-type': 'application/x-www-form-urlencoded',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
    }
    data = {'code': stockCode}
    res = requests.post(url, data=data, headers=header)
    rows = re.findall(pattern, res.text, re.DOTALL)
    for row in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', row)
        if cells and len(cells) == 9:
            cleaned_cells = [cell.strip() for cell in cells]
            fflow.update({cleaned_cells[0].replace('-', ''): round(float(cleaned_cells[1].replace('万', '')) + float(cleaned_cells[3].replace('万', '')), 2)})
    return fflow


def getStockOrderByFundFromDongCai() -> dict:
    '''从东方财富获取股票资金净流入排序'''
    fflow = []
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    current_time = int(time.time() * 1000)
    for p in range(10):
        url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{current_time}&fid=f62&po=1&pz=50&pn={p + 1}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
        res = requests.get(url, headers=header)
        res_json = json.loads(res.text.split('(')[1].split(')')[0])
        diffs = res_json['data']['diff']
        for k in diffs:
            if 1 <= k['f3'] <= 6 and getStockType(k['f12']) and k['f2'] < 51:
                fflow.append({'code': k['f12'], 'name': k['f14'], 'pcnt': k['f3'], 'fund': round(k['f62'] / 10000, 2), 'ratio': k['f184']})
        time.sleep(1)
    return fflow


def getStockOrderByFundFromSina() -> dict:
    '''从新浪财经获取股票资金净流入排序'''
    fflow = []
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    for p in range(10):
        url = f'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_bkzj_ssggzj?page={p + 1}&num=50&sort=r0_net&asc=0&bankuai=&shichang='
        res = requests.get(url, headers=header)
        res_json = json.loads(res.text)
        for k in res_json:
            change_ratio = round(float(k['changeratio']) * 100, 2)
            if 1 <= change_ratio <= 6 and getStockType(k['symbol'][2:]) and float(k['trade']) < 51:
                fflow.append({'code': k['symbol'][2:], 'name': k['name'], 'pcnt': change_ratio, 'fund': round(float(k['r0_net']) / 10000, 2), 'ratio': round(float(k['r0_ratio']) * 100, 2)})
        time.sleep(1)
    return fflow
