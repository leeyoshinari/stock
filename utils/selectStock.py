#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import re
import time
import json
import requests


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


def getStockOrderByFundFromDOngCai(page: int) -> dict:
    '''从东方财富获取资金流向，最近10日'''
    fflow = {}
    header = {'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'}
    url = f'https://push2.eastmoney.com/api/qt/clist/get?cb=jQuery1123022029913423580905_{int(time.time() * 1000)}&fid=f62&po=1&pz=50&pn={page}&np=1&fltt=2&invt=2&ut=8dec03ba335b81bf4ebdf7b29ec27d15&fs=m%3A0%2Bt%3A6%2Bf%3A!2%2Cm%3A0%2Bt%3A13%2Bf%3A!2%2Cm%3A0%2Bt%3A80%2Bf%3A!2%2Cm%3A1%2Bt%3A2%2Bf%3A!2%2Cm%3A1%2Bt%3A23%2Bf%3A!2%2Cm%3A0%2Bt%3A7%2Bf%3A!2%2Cm%3A1%2Bt%3A3%2Bf%3A!2&fields=f12%2Cf14%2Cf2%2Cf3%2Cf62%2Cf184%2Cf66%2Cf69%2Cf72%2Cf75%2Cf78%2Cf81%2Cf84%2Cf87%2Cf204%2Cf205%2Cf124%2Cf1%2Cf13'
    res = requests.get(url, headers=header)
    res_json = json.loads(res.text.split('(')[1].split(')')[0])
    klines = res_json['data']['klines']
    for k in klines:
        datas = k.split(',')
        fflow.update({datas[0].replace('-', ''): round(float(datas[1]) / 10000, 2)})
    return fflow
