#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI


prompt = '''你是一个精通中国A股股票市场的交易员，你特别擅长做短线交易，精通分析股票的数据来判断是否应该买入股票，下面将会给你1只股票的数据，你需要知道每个指标的含义并深入仔细严谨地分析各种指标数据，除了基础的数据分析外，你还要重点分析近几日的主力资金净流入情况、MACD、KDJ、TRIX指标，然后判断每只股票是否处于强势上涨阶段，你需要在强势上涨阶段买入股票，对于上涨趋势很弱的股票，不应该买入，你需要尽可能识别出最近几日上下波动巨大、主力诱多、假金叉、较长的上影线、超买高位钝化、上涨动能很弱等这种假信号，请你直接返回一个判断结果列表的JSON，格式是[{"603128": {"buy": True, "reason": ""}}]，buy表示是否买入，reason表示判断的简单依据，你直接输出结果，不要输出你的判断过程。\n
股票数据每个字段的含义如下：code：股票代码，name：股票名字，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，fund：主力资金净流入，单位是万，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。\n
这只股票的每一天的数据如下：'''

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


def queryOpenAi(msg: str, api_host: str, model: str, auth_code: str) -> dict:
    client = OpenAI(api_key=auth_code, base_url=api_host)
    completion = client.chat.completions.create(model=model, messages=[{'role': 'user', 'content': prompt + msg}])
    res = completion.choices[0].message.content
    return json.loads(res)


if __name__ == '__main__':
    msg = []
    queryGemini(json.dumps(msg), 'https://asdf.com', 'gemini-2.5-pro', '123456')
    queryOpenAi(json.dumps(msg), 'https://asdf.com', 'gpt-5', '123456')
