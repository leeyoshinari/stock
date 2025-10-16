#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


prompt = '''你是一个精通股票市场交易的交易员，你精通分析股票的数据来判断是否应该买入股票，下面将会给你5只股票的数据，你需要知道每个指标的含义并深入仔细严谨地分析各种指标数据，然后判断每只股票是否应该买入，你需要尽可能识别出主力诱多等这种假信号，请你直接返回一个列表的JSON，格式是{"603128": {"buy": True, "reason": ""},"601801": {"buy": False, "reason": ""}}，buy表示是否买入，reason表示判断的简单依据。\n
股票数据每个字段的含义如下：code：股票代码，name：股票名字，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。\n
每只股票的每一天的数据如下：'''

# 配置会话对象：支持重试 + keep-alive
session = requests.Session()
retries = Retry(
    total=5,                # 总重试次数
    backoff_factor=2,       # 每次重试间隔翻倍
    status_forcelist=[500, 502, 503, 504],  # 针对服务器错误重试
    allowed_methods=["POST"]
)
adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
session.mount("http://", adapter)
session.mount("https://", adapter)


def queryGemini(msg: str, api_host: str, model: str, auth_code: str) -> dict:
    url = f"{api_host}/api/chat"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt + msg}]}
    res = session.post(url=url, json=data, headers=header, timeout=(10, 600))
    res.raise_for_status()
    gemini_res = json.loads(res.text)
    result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
    res_json = json.loads(result_text.replace('```', '').replace('json', '').replace('\n', ''))
    return res_json


if __name__ == '__main__':
    msg = []
    queryGemini(json.dumps(msg), 'https://asdf.com', 'gemini-2.5-pro', '123456')
