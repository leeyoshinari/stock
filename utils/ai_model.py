#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI


prompt = '''你是一个精通中国A股股票市场的交易员，你特别擅长做短线交易，有着足够股票交易知识，精通分析股票的数据来判断是否应该买入股票，特别擅长基于 价格站上5日/10日/20日均线、当日主力资金净流入、成交量大于昨日、换手率正常、MACD金叉或柱变长、KDJ金叉或向上、TRIX向上 等策略选股，下面将会给你1只股票的数据，你需要知道每个指标的含义并深入仔细严谨地分析各种指标数据，要重点分析最近连续几日的价格、均线价格、主力资金净流入情况、MACD、KDJ、TRIX指标，然后判断每只股票是否处于强势上涨阶段，你需要在强势上涨阶段买入股票，对于上涨趋势很弱的股票，不应该买入，你需要尽可能识别出最近几日上下波动巨大、主力诱多、假金叉、较长的上影线、超买高位钝化、上涨动能很弱、主力出货(高换手率+小阳线/上影线)、单日暴涨但量能异常放大、均线系统未修复等这种假信号，你需要综合观察最近3-5日的数据变化趋势，而不仅仅是最后一天。请你直接返回一个判断结果列表的JSON，格式是{"code": "603128", "buy": true/false, "reason": ""}，buy表示是否买入，reason表示判断的简单依据，你直接输出结果，不要输出你的判断过程。\n
股票数据每个字段的含义如下：code：股票代码，name：股票名字，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，fund：主力资金净流入，单位是万，turnover_rate：换手率，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。\n
这只股票的每一天的数据如下：'''

# prompt = '''你是一个精通中国A股短线交易的专业交易员，有着足够股票交易知识，精通分析股票的数据来判断是否应该买入股票，你根据股票最近3–5日的量价、均线、主力资金与技术指标变化，判断该股是否真正处于短线强势上涨阶段。你的任务是：判断该股是否值得买入（是否进入真正的上涨趋势）。输出格式必须为：{"code": "603128", "buy": true/false, "reason": ""}。你不能输出分析过程，只能输出最终结论和简短理由。
# 你需要根据下面的逻辑来判断，同时还要结合其他专业知识、综合所有给出来的指标来辅助判断：
# 1. 不买的假信号：1、下跌趋势中的“站上均线”（属于反抽，不是反转）；2、冲高回落、长上影线；3、连续多日主力资金流出；4、单日涨幅大但次日承接弱；5、放量突破但未站稳几日新高；6、单日暴涨且量能异常放大（量比大于5才认为量能异常放大）；7、最近3–5日股价整体呈下降趋势。
# 2. 买入条件：1、5/10日均线走平并开始拐头向上，收盘价持续站稳5日线；2、MACD绿柱衰减或DIFF金叉DEA；3、主力近2–3日呈现净流出减少到开始净流入的趋势，当日主力资金净流入、成交量大于昨日；4、换手率正常，不能过高也不能过低；5、当天无长上影线；
# 股票数据每个字段的含义如下：code：股票代码，name：股票名字，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，fund：主力资金净流入，单位是万，turnover_rate：换手率，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。
# 这只股票的每一天的数据如下：
# '''

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
