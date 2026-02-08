#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
import traceback
from logging import Logger
from utils.model import StockModelDo, StockMinuteDo
from utils.http_client import http


headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
}


def getStockRegion(code: str) -> str:
    if code.startswith("60") or code.startswith("68"):
        return "sh"
    elif code.startswith("00") or code.startswith("30"):
        return "sz"
    else:
        return ""


def getStockType(code: str) -> int:
    if code.startswith("60"):
        return 1
    elif code.startswith("00"):
        return 1
    elif code.startswith("68"):
        return 0
    elif code.startswith("30"):
        return 1
    else:
        return 0


def normalizeHourAndMinute() -> str:
    local_time = time.localtime(time.time())
    hour = local_time.tm_hour
    minute = local_time.tm_min
    remainder = minute % 10
    if remainder != 0:
        minute += (10 - remainder)
        if minute >= 60:
            minute -= 60
            hour += 1
    return f"{hour:02d}{minute:02d}"


def generateStockCode(data: dict) -> str:
    s = []
    for r in list(data.keys()):
        s.append(f"{getStockRegion(r)}{r}")
    return ",".join(s)


def generateStockCodeForSina(data: dict) -> str:
    s = []
    for r in list(data.keys()):
        s.append(f"{getStockRegion(r)}{r}_i")
    return ",".join(s)


async def getStockHqFromTencent(host: str, datas: list[dict], logger: Logger) -> dict[str, list]:
    '''
    从腾讯获取股票实时行情数据
    '''
    result = {'data': [], 'error': []}
    try:
        error_list = []
        data_list = []
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        if host and host.startswith('http'):
            param_data = {"url": f"https://qt.gtimg.cn/q={stockCode}", "method": "GET"}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://qt.gtimg.cn/q={stockCode}", headers=headers)
        if res.status_code == 200:
            res_list = res.text.split(';')
            for s in res_list:
                try:
                    stockDo = StockModelDo()
                    if len(s) < 30:
                        continue
                    stockInfo = s.split('~')
                    stockDo.name = stockInfo[1]
                    stockDo.code = stockInfo[2]
                    stockDo.current_price = float(stockInfo[3])
                    stockDo.last_price = float(stockInfo[4])
                    stockDo.open_price = float(stockInfo[5])
                    if int(stockInfo[6]) < 2:
                        logger.info(f"Tencent({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volume = int(int(stockInfo[6]))
                    stockDo.max_price = float(stockInfo[33])
                    stockDo.min_price = float(stockInfo[34])
                    stockDo.turnover_rate = float(stockInfo[38])
                    stockDo.day = stockInfo[30][:8]
                    data_list.append(stockDo)
                    logger.info(f"Tencent({host}): {stockDo}")
                except:
                    logger.error(f"Tencent({host}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    key_stock = f"{stockDo.code}count"
                    if dataCount[key_stock] < 5:
                        error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
            result['data'] = data_list
            result['error'] = error_list
        else:
            logger.error(f"Tencent({host}) - 请求未正常返回... {datas}")
            result['error'] = datas
    except:
        logger.error(f"Tencent({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        result['error'] = datas
    return result


async def getStockHqFromXueQiu(host: str, datas: list[dict], logger: Logger) -> dict[str, list]:
    '''
    从雪球获取股票实时行情数据
    '''
    result = {'data': [], 'error': []}
    try:
        error_list = []
        data_list = []
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        if host and host.startswith('http'):
            param_data = {"url": f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", "method": "GET"}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text)
            if len(res_json['data']) > 0:
                for s in res_json['data']:
                    try:
                        stockDo = StockModelDo()
                        code = s['symbol'][2:]
                        stockDo.name = dataDict[code]
                        stockDo.code = code
                        stockDo.current_price = s['current']
                        stockDo.open_price = s['open']
                        stockDo.last_price = s['last_close']
                        stockDo.max_price = s['high']
                        stockDo.min_price = s['low']
                        stockDo.turnover_rate = s['turnover_rate']
                        if not s['volume'] or s['volume'] < 2:
                            logger.info(f"XueQiu({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volume = int(s['volume'] / 100)
                        stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                        data_list.append(stockDo)
                        logger.info(f"XueQiu({host}): {stockDo}")
                    except:
                        logger.error(f"XueQiu({host}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
                result['data'] = data_list
                result['error'] = error_list
            else:
                logger.error(f"XueQiu({host}) - 请求未正常返回...响应值: {res_json}")
                result['error'] = datas
        else:
            logger.error(f"XueQiu({host}) - 请求未正常返回... {datas}")
            result['error'] = datas
    except:
        logger.error(f"XueQiu({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        result['error'] = datas
    return result


async def getStockHqFromSina(host: str, datas: list[dict], logger: Logger) -> dict[str, list]:
    '''
    从新浪获取股票实时行情数据
    '''
    result = {'data': [], 'error': []}
    try:
        error_list = []
        data_list = []
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        stockCode_i = generateStockCodeForSina(dataDict)
        h = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        if host and host.startswith('http'):
            param_data = {"url": f"http://hq.sinajs.cn/list={stockCode},{stockCode_i}", "method": "GET", "headers": h}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"http://hq.sinajs.cn/list={stockCode},{stockCode_i}", headers=h)
        if res.status_code == 200:
            res_list = res.text.split(';')
            data_dict = {}
            for line in res_list:
                try:
                    if len(line.strip()) < 30:
                        continue
                    stockInfo = line.strip().split(',')
                    code = stockInfo[0].split('=')[0].split('_')[2][2:].strip()
                    if code in data_dict:
                        stockDo: StockModelDo = data_dict[code]
                        if f"{code}_i" in line:
                            if float(stockInfo[8]) < 0.5:
                                logger.info(f"Sina({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.turnover_rate = round(stockDo.volume / float(stockInfo[8]), 2)
                        else:
                            stockDo.name = stockInfo[0].split('"')[-1]
                            stockDo.current_price = float(stockInfo[3])
                            stockDo.open_price = float(stockInfo[1])
                            if int(stockInfo[8]) < 2:
                                logger.info(f"Sina({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.volume = int(int(stockInfo[8]) / 100)
                            stockDo.last_price = float(stockInfo[2])
                            stockDo.max_price = float(stockInfo[4])
                            stockDo.min_price = float(stockInfo[5])
                            stockDo.day = stockInfo[30].replace('-', '')
                        data_dict.update({code: stockDo})
                    else:
                        stockDo = StockModelDo()
                        stockDo.code = code
                        if f"{code}_i" in line:
                            if float(stockInfo[8]) < 0.5:
                                logger.info(f"Sina({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.turnover_rate = float(stockInfo[8])
                        else:
                            stockDo.name = stockInfo[0].split('"')[-1]
                            stockDo.current_price = float(stockInfo[3])
                            stockDo.open_price = float(stockInfo[1])
                            if int(stockInfo[8]) < 2:
                                logger.info(f"Sina({host}) - {stockDo.code} - {stockDo.name} 休市, 跳过")
                                continue
                            stockDo.volume = int(int(stockInfo[8]) / 100)
                            stockDo.last_price = float(stockInfo[2])
                            stockDo.max_price = float(stockInfo[4])
                            stockDo.min_price = float(stockInfo[5])
                            stockDo.day = stockInfo[30].replace('-', '')
                        data_dict.update({code: stockDo})
                except:
                    logger.error(f"Sina({host}) - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {line}")
                    logger.error(traceback.format_exc())
                    key_stock = f"{stockDo.code}count"
                    if dataCount[key_stock] < 5:
                        error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
            for _, v in data_dict.items():
                data_list.append(v)
                logger.info(f"Sina({host}): {v}")
            result['data'] = data_list
            if len(error_list) > 0:
                result['error'] = error_list
        else:
            logger.error(f"Sina({host}) - 请求未正常返回... {datas}")
            result['error'] = datas
    except:
        logger.error(f"Sina({host}) - 出现异常...... {datas}")
        logger.error(traceback.format_exc())
        result['error'] = datas
    return result


async def getMinuteKFromTencent(host: str, code: str, logger: Logger) -> list[StockMinuteDo]:
    '''
    从腾讯获取股票当天的分钟级数据
    '''
    result = []
    try:
        stockCode = f"{getStockRegion(code)}{code}"
        if host and host.startswith('http'):
            param_data = {"url": f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data_{stockCode}&code={stockCode}&r=0.367603{int(time.time())}", "method": "GET"}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data_{stockCode}&code={stockCode}&r=0.367603{int(time.time())}", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text.split(f"{code}=")[-1])
            if len(res_json['data'][stockCode]['data']['data']) > 0:
                pre_volume = 0
                for s in res_json['data'][stockCode]['data']['data']:
                    d = s.split(" ")
                    if d[0] > '1500': continue
                    stockDo = StockMinuteDo()
                    stockDo.code = code
                    stockDo.time = d[0]
                    stockDo.price = float(d[1])
                    stockDo.volume = int(d[2]) - pre_volume
                    result.append(stockDo)
                    pre_volume = int(d[2])
                logger.info(f"Tencent-minute({host}) - {code}")
            else:
                logger.error(f"Tencent-minute({host}) - {code} - {res.text}")
        else:
            logger.error(f"Tencent-minute({host}) - 请求未正常返回...")
    except:
        logger.error(traceback.format_exc())
    return result


async def getMinuteKFromTongHuaShun(host: str, code: str, logger: Logger) -> list[StockMinuteDo]:
    '''
    从同花顺获取股票当天的分钟级数据
    '''
    result = []
    try:
        if host and host.startswith('http'):
            param_data = {"url": f"https://d.10jqka.com.cn/v6/time/hs_{code}/defer/last.js", "method": "GET"}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://d.10jqka.com.cn/v6/time/hs_{code}/defer/last.js", headers=headers)
        if res.status_code == 200:
            res_json = json.loads(res.text.split("(")[1].split(")")[0])
            if len(res_json[f"hs_{code}"]['data']) > 0:
                data_list = res_json[f"hs_{code}"]['data'].split(";")
                for s in data_list:
                    d = s.split(",")
                    if d[0].strip() > '1500': continue
                    stockDo = StockMinuteDo()
                    stockDo.code = code
                    stockDo.time = d[0].strip()
                    stockDo.price = float(d[1])
                    stockDo.volume = int(int(d[4]) / 100)
                    stockDo.price_avg = round(float(d[3]), 2)
                    result.append(stockDo)
                logger.info(f"TongHuaShun-minute({host}) - {code}")
            else:
                logger.error(f"TongHuaShun-minute({host}) - {code} - {res.text}")
        else:
            logger.error(f"TongHuaShun-minute({host}) - 请求未正常返回...")
    except:
        logger.error(traceback.format_exc())
    return result


async def getMinuteKFromSina(host: str, code: str, logger: Logger) -> list[StockMinuteDo]:
    '''
    从新浪获取股票当天的分钟级数据
    '''
    result = []
    try:
        stockCode = f"{getStockRegion(code)}{code}"
        h = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        if host and host.startswith('http'):
            param_data = {"url": f"https://cn.finance.sina.com.cn/minline/getMinlineData?symbol={stockCode}&callback=var%20t1{stockCode}=&dpc=1", "method": "GET", "headers": h}
            res = await http.post(f'{host}/api/proxy', json_data=param_data, headers={'Content-Type': 'application/json'})
        else:
            res = await http.get(f"https://cn.finance.sina.com.cn/minline/getMinlineData?symbol={stockCode}&callback=var%20t1{stockCode}=&dpc=1", headers=h)
        if res.status_code == 200:
            res_json = json.loads(res.text.split("(")[1].split(")")[0])
            if len(res_json["result"]['data']) > 0:
                for s in res_json["result"]['data']:
                    m = s['m'][:5].replace(':', '')
                    if m > '1500': continue
                    stockDo = StockMinuteDo()
                    stockDo.code = code
                    stockDo.time = m
                    stockDo.price = float(s['p'])
                    stockDo.volume = int(int(s['v']) / 100)
                    stockDo.price_avg = round(float(s['avg_p']), 2)
                    result.append(stockDo)
                logger.info(f"Sina-minute({host}) - {code}")
            else:
                logger.error(f"Sina-minute({host}) - {code} - {res.text}")
        else:
            logger.error(f"Sina-minute({host}) - 请求未正常返回...")
    except:
        logger.error(traceback.format_exc())
    return result
