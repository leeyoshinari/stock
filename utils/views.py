#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import time
import json
import traceback
import requests
from sqlalchemy import desc, asc
from utils.model import SearchStockParam, StockModelDo, RequestData, StockDataList, RecommendStockDataList, AiModelStockList
from utils.selectStock import getStockFundFlowFromDongCai, getStockFundFlowFromStockStar
from utils.logging import logger
from utils.results import Result
from utils.metric import analyze_buy_signal
from utils.database import Detail, Tools, Recommend


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


def normalizeHourAndMinute():
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


async def queryByCode(code: str) -> Result:
    result = Result()
    try:
        stockInfo = Detail.query(code=code).order_by(asc(Detail.create_time)).all()
        data = [[getattr(row, k) for k in ['open_price', 'current_price', 'min_price', 'max_price', 'volumn', 'qrr', 'emas', 'emal', 'dea', 'turnover_rate', 'fund']] for row in stockInfo]
        x = []
        volumn = []
        qrr = []
        ma_five = []
        ma_ten = []
        ma_twenty = []
        turnover_rate = []
        fund = []
        diff = []
        dea = []
        macd = []
        kdjk = []
        kdjd = []
        kdjj = []
        trix = []
        trma = []
        for index, d in enumerate(data):
            x.append(stockInfo[index].day)
            volumn.append(d[4])
            qrr.append(d[5])
            ma_five.append(stockInfo[index].ma_five)
            ma_ten.append(stockInfo[index].ma_ten)
            ma_twenty.append(stockInfo[index].ma_twenty)
            turnover_rate.append(d[9])
            fund.append(d[10])
            diff_x = d[6] - d[7]
            macd_x = (diff_x - d[8]) * 2
            diff.append(round(diff_x, 3))
            dea.append(round(d[8], 3))
            macd.append(round(macd_x, 3))
            kdjk.append(round(stockInfo[index].kdjk, 3))
            kdjd.append(round(stockInfo[index].kdjd, 3))
            kdjj.append(round(stockInfo[index].kdjj, 3))
            trix.append(round(stockInfo[index].trix, 3))
            trma.append(round(stockInfo[index].trma, 3))
        result.data = {
            'x': x,
            'price': data, 'volumn': volumn, 'qrr': qrr, 'turnover_rate': turnover_rate,
            'ma_five': ma_five, 'ma_ten': ma_ten, 'ma_twenty': ma_twenty,
            'diff': diff, 'dea': dea, 'macd': macd, 'fund': fund,
            'k': kdjk, 'd': kdjd, 'j': kdjj, 'trix': trix, 'trma': trma
        }
        result.total = len(result.data)
        logger.info(f"查询信息成功, 代码: {code}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def queryStockList(query: SearchStockParam) -> Result:
    result = Result()
    try:
        tool = Tools.get_one("openDoor")
        day = tool.value
        tool = Tools.get_one("openDoor2")
        day2 = tool.value
        if query.code:
            stockInfo = Detail.get((query.code, day))
            if stockInfo:
                stockInfo = Detail.get_one((query.code, day2))
            stockList = [StockModelDo.model_validate(stockInfo).model_dump()]
        elif query.name:
            stockInfo = Detail.filter_condition(equal_condition={"day": day}, like_condition={"name": query.name}).all()
            if len(stockInfo) < 1:
                stockInfo = Detail.filter_condition(equal_condition={"day": day2}, like_condition={"name": query.name}).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
        else:
            logger.info(query)
            sort_key = query.sortField.split('-')[0]
            sort_type = query.sortField.split('-')[1]
            if sort_type == 'desc':
                detail_sort = desc(getattr(Detail, sort_key))
            else:
                detail_sort = asc(getattr(Detail, sort_key))
            offset = (query.page - 1) * query.pageSize
            total_num = Detail.query(day=day).count()
            stockInfo = Detail.query(day=day).order_by(detail_sort).offset(offset).limit(query.pageSize).all()
            if total_num < 1:
                total_num = Detail.query(day=day2).count()
                stockInfo = Detail.query(day=day2).order_by(detail_sort).offset(offset).limit(query.pageSize).all()
            stockList = [StockModelDo.model_validate(f).model_dump() for f in stockInfo]
            result.total = total_num
        result.data = stockList
        logger.info(f"查询列表成功, 查询参数: {query}")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def queryRecommendStockList(page: int = 1) -> Result:
    result = Result()
    pageSize = 20
    try:
        offset = (page - 1) * pageSize
        total_num = Recommend.query().count()
        stockInfo = Recommend.query().order_by(desc(Recommend.create_time)).offset(offset).limit(pageSize).all()
        stockList = [RecommendStockDataList.from_orm_format(f).model_dump() for f in stockInfo]
        result.total = total_num
        result.data = stockList
        logger.info("查询推荐股票列表成功～")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = e
    return result


async def queryStockMetric(code: str) -> Result:
    result = Result()
    params = {"qrr_strong": 1.1, "diff_delta": 0.01, "trix_delta_min": 0.001, "down_price_pct": 0.98, "too_hot": 0.055, "min_score": 6}
    try:
        rr = []
        stockList = Detail.query(code=code).order_by(desc(Detail.day)).limit(-35).all()
        stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
        stock_data.reverse()
        logger.info(stock_data[-30:])
        for i in range(6, len(stock_data) - 1):
            sub = stock_data[: i + 1]
            res = analyze_buy_signal(sub, params)
            next_day_ret = (max(stock_data[i + 1]["current_price"], stock_data[i + 1]["max_price"]) / stock_data[i]["current_price"] - 1)
            res["next_day_return"] = next_day_ret
            if res["buy"]: logger.info(f"{code} - {res['day']} - {res['buy']} - {res['score']} - {next_day_ret > 0} - {res['reasons']}")
            rr.append(res)
        result.data = rr
        logger.info(f"query {code} successful")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.msg = e
        result.success = False
    return result


async def queryAllStockData(code: str) -> Result:
    result = Result()
    try:
        code_list = code.split(',')
        stock_data_list = Detail.filter_condition(in_condition={'code': code_list}).order_by(desc(Detail.day)).all()
        stockData = [AiModelStockList.from_orm_format(f).model_dump() for f in stock_data_list]
        stockData.reverse()
        fflow = {}
        try:
            # fflow = getStockFundFlowFromStockStar(code)
            fflow = getStockFundFlowFromDongCai(code)
        except:
            logger.error(traceback.format_exc())
            fflow = {}
        if fflow:
            for i in range(len(stockData)):
                if stockData[i]['day'] in fflow:
                    stockData[i].update({"fund": fflow[stockData[i]['day']]})
        result.data = stockData
        logger.info(f"query {code} successful")
    except Exception as e:
        logger.error(traceback.format_exc())
        result.msg = e
        result.success = False
    return result


async def calc_stock_return() -> Result:
    result = Result()
    try:
        init_fund = 10000
        r1, r1h, r1l, r2, r2h, r2l, r3, r3h, r3l, r4, r4h, r4l, r5, r5h, r5l = 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0
        x = []
        y1, y1h, y1l, y2, y2h, y2l, y3, y3h, y3l, y4, y4h, y4l, y5, y5h, y5l = [], [], [], [], [], [], [], [], [], [], [], [], [], [], []
        stocks = Recommend.query().order_by(asc(Recommend.id)).all()
        for s in stocks:
            s_time = s.create_time.strftime("%Y-%m-%d")
            if s_time in x:
                index = x.index(s_time)
                y1[index] = y1[index] + round(init_fund * (s.last_one_price or 0) / 100, 2)
                y1h[index] = y1h[index] + round(init_fund * (s.last_one_high or 0) / 100, 2)
                y1l[index] = y1l[index] + round(init_fund * (s.last_one_low or 0) / 100, 2)
                y2[index] = y2[index] + round(init_fund * (s.last_two_price or 0) / 100, 2)
                y2h[index] = y2h[index] + round(init_fund * (s.last_two_high or 0) / 100, 2)
                y2l[index] = y2l[index] + round(init_fund * (s.last_two_low or 0) / 100, 2)
                y3[index] = y3[index] + round(init_fund * (s.last_three_price or 0) / 100, 2)
                y3h[index] = y3h[index] + round(init_fund * (s.last_three_high or 0) / 100, 2)
                y3l[index] = y3l[index] + round(init_fund * (s.last_three_low or 0) / 100, 2)
                y4[index] = y4[index] + round(init_fund * (s.last_four_price or 0) / 100, 2)
                y4h[index] = y4h[index] + round(init_fund * (s.last_four_high or 0) / 100, 2)
                y4l[index] = y4l[index] + round(init_fund * (s.last_four_low or 0) / 100, 2)
                y5[index] = y5[index] + round(init_fund * (s.last_five_price or 0) / 100, 2)
                y5h[index] = y5h[index] + round(init_fund * (s.last_five_high or 0) / 100, 2)
                y5l[index] = y5l[index] + round(init_fund * (s.last_five_low or 0) / 100, 2)
            else:
                x.append(s_time)
                y1.append(round(init_fund * (s.last_one_price or 0) / 100, 2))
                y1h.append(round(init_fund * (s.last_one_high or 0) / 100, 2))
                y1l.append(round(init_fund * (s.last_one_low or 0) / 100, 2))
                y2.append(round(init_fund * (s.last_two_price or 0) / 100, 2))
                y2h.append(round(init_fund * (s.last_two_high or 0) / 100, 2))
                y2l.append(round(init_fund * (s.last_two_low or 0) / 100, 2))
                y3.append(round(init_fund * (s.last_three_price or 0) / 100, 2))
                y3h.append(round(init_fund * (s.last_three_high or 0) / 100, 2))
                y3l.append(round(init_fund * (s.last_three_low or 0) / 100, 2))
                y4.append(round(init_fund * (s.last_four_price or 0) / 100, 2))
                y4h.append(round(init_fund * (s.last_four_high or 0) / 100, 2))
                y4l.append(round(init_fund * (s.last_four_low or 0) / 100, 2))
                y5.append(round(init_fund * (s.last_five_price or 0) / 100, 2))
                y5h.append(round(init_fund * (s.last_five_high or 0) / 100, 2))
                y5l.append(round(init_fund * (s.last_five_low or 0) / 100, 2))
            r1 += round(init_fund * (s.last_one_price or 0) / 100, 2)
            r1h += round(init_fund * (s.last_one_high or 0) / 100, 2)
            r1l += round(init_fund * (s.last_one_low or 0) / 100, 2)
            r2 += round(init_fund * (s.last_two_price or 0) / 100, 2)
            r2h += round(init_fund * (s.last_two_high or 0) / 100, 2)
            r2l += round(init_fund * (s.last_two_low or 0) / 100, 2)
            r3 += round(init_fund * (s.last_three_price or 0) / 100, 2)
            r3h += round(init_fund * (s.last_three_high or 0) / 100, 2)
            r3l += round(init_fund * (s.last_three_low or 0) / 100, 2)
            r4 += round(init_fund * (s.last_four_price or 0) / 100, 2)
            r4h += round(init_fund * (s.last_four_high or 0) / 100, 2)
            r4l += round(init_fund * (s.last_four_low or 0) / 100, 2)
            r5 += round(init_fund * (s.last_five_price or 0) / 100, 2)
            r5h += round(init_fund * (s.last_five_high or 0) / 100, 2)
            r5l += round(init_fund * (s.last_five_low or 0) / 100, 2)

        result.data = {'r1': r1, 'r1h': r1h, 'r1l': r1l, 'r2': r2, 'r2h': r2h, 'r2l': r2l, 'r3': r3, 'r3h': r3h,
                       'r3l': r3l, 'r4': r4, 'r4h': r4h, 'r4l': r4l, 'r5': r5, 'r5h': r5h, 'r5l': r5l, 'x': x,
                       'y1': y1, 'y1h': y1h, 'y1l': y1l, 'y2': y2, 'y2h': y2h, 'y2l': y2l, 'y3': y3, 'y3h': y3h,
                       'y3l': y3l, 'y4': y4, 'y4h': y4h, 'y4l': y4l, 'y5': y5, 'y5h': y5h, 'y5l': y5l}
    except:
        logger.error(traceback.format_exc())
        result.success = False
    return result


async def query_tencent(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        res = requests.get(f"https://qt.gtimg.cn/q={stockCode}", headers=headers)
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
                        logger.info(f"Tencent - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volumn = int(int(stockInfo[6]))
                    stockDo.max_price = float(stockInfo[33])
                    stockDo.min_price = float(stockInfo[34])
                    stockDo.turnover_rate = float(stockInfo[38])
                    stockDo.day = stockInfo[30][:8]
                    r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                    logger.info(f"Tencent: {stockDo}")
                except:
                    logger.error(f"Tencent - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    key_stock = f"{stockDo.code}count"
                    if dataCount[key_stock] < 5:
                        error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("Tencent - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def query_xueqiu(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        res = requests.get(f"https://stock.xueqiu.com/v5/stock/realtime/quotec.json?symbol={stockCode.upper()}", headers=headers)
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
                            logger.info(f"XueQiu - {stockDo.code} - {stockDo.name} 休市, 跳过")
                            continue
                        stockDo.volumn = int(s['volume'] / 100)
                        stockDo.day = time.strftime("%Y%m%d", time.localtime(s['timestamp'] / 1000))
                        r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                        logger.info(f"XueQiu: {stockDo}")
                    except:
                        logger.error(f"XueQiu - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                        logger.error(traceback.format_exc())
                        key_stock = f"{stockDo.code}count"
                        if dataCount[key_stock] < 5:
                            error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
            else:
                logger.error(f"XueQiu - 请求未正常返回...响应值: {res_json}")
                result.success = False
                result.msg = "请求未正常返回"
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("XueQiu - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def query_sina(query: RequestData) -> Result:
    result = Result()
    try:
        r_list = []
        error_list = []
        datas = query.data
        dataDict = {k: v for d in datas for k, v in d.items() if 'count' not in k}
        dataCount = {k: v for d in datas for k, v in d.items() if 'count' in k}
        stockCode = generateStockCode(dataDict)
        h = {
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36'
        }
        res = requests.get(f"http://hq.sinajs.cn/list={stockCode}", headers=h)
        if res.status_code == 200:
            res_list = res.text.split(';')
            for s in res_list:
                try:
                    stockDo = StockModelDo()
                    if len(s) < 30:
                        continue
                    stockInfo = s.split(',')
                    stockDo.name = stockInfo[0].split('"')[-1]
                    stockDo.code = stockInfo[0].split('=')[0].split('_')[-1][2:]
                    stockDo.current_price = float(stockInfo[3])
                    stockDo.open_price = float(stockInfo[1])
                    if int(stockInfo[8]) < 2:
                        logger.info(f"Sina - {stockDo.code} - {stockDo.name} 休市, 跳过")
                        continue
                    stockDo.volumn = int(int(stockInfo[8]) / 100)
                    stockDo.last_price = float(stockInfo[2])
                    stockDo.max_price = float(stockInfo[4])
                    stockDo.min_price = float(stockInfo[5])
                    stockDo.day = stockInfo[30].replace('-', '')
                    r_list.append(StockModelDo.model_validate(stockDo).model_dump())
                    logger.info(f"Sina: {stockDo}")
                except:
                    logger.error(f"Sina - 数据解析保存失败, {stockDo.code} - {stockDo.name} - {s}")
                    logger.error(traceback.format_exc())
                    key_stock = f"{stockDo.code}count"
                    if dataCount[key_stock] < 5:
                        error_list.append({stockDo.code: stockDo.name, key_stock: dataCount[key_stock] + 1})
            result.data = {"data": r_list, "error": error_list}
        else:
            logger.error("Sina - 请求未正常返回...")
            result.success = False
            result.msg = "请求未正常返回"
    except:
        logger.error(traceback.format_exc())
        result.success = False
        result.msg = "请求失败, 请重试～"
    return result


async def test() -> Result:
    result = Result()
    stock_volumn_obj = Detail.query_fields(columns=['volumn'], code='688045').order_by(desc(Detail.day)).all()
    stock_volumn = [r[0] for r in stock_volumn_obj]
    result.data = stock_volumn
    return result
