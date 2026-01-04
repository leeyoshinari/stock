#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from openai import OpenAI


# prompt = '''你是一个精通中国A股股票市场的交易员，你特别擅长做短线交易，有着足够股票交易知识，精通分析股票的数据来判断是否应该买入股票，特别擅长基于 价格站上5日/10日/20日均线、当日主力资金净流入、成交量大于昨日、换手率正常、MACD金叉或柱变长、KDJ金叉或向上、TRIX向上 等策略选股，下面将会给你1只股票的数据，你需要知道每个指标的含义并深入仔细严谨地分析各种指标数据，要重点分析最近连续几日的价格、均线价格、主力资金净流入情况、MACD、KDJ、TRIX指标，你需要判断股票所在的行业、概念是否是最近热门题材，然后判断每只股票是否处于强势上涨阶段且属于热门题材，你需要在强势上涨阶段买入股票，对于上涨趋势很弱的股票，不应该买入，你需要尽可能识别出最近几日高开低走、上下波动巨大、主力诱多、假金叉、较长的上影线、超买高位钝化、上涨动能很弱、主力出货(高换手率+小阳线/上影线)、单日暴涨但量能异常放大、均线系统未修复等这种假信号，你需要综合观察最近3-5日的数据变化趋势，而不仅仅是最后一天。请你直接返回一个判断结果列表的JSON，格式是{"code": "603128", "buy": true/false, "reason": ""}，buy表示是否买入，reason表示判断的简单依据，你直接输出结果，不要输出你的判断过程。\n
# 股票数据每个字段的含义如下：code：股票代码，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，fund：主力资金净流入，单位是万，turnover_rate：换手率，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。每个字段的数组值按照day的时间顺序排序。\n
# 这只股票的每一天的数据如下：'''

# prompt = '''你是一个精通中国A股短线交易的专业交易员，有着足够股票交易知识，精通分析股票的数据来判断是否应该买入股票，你根据股票最近3–5日的量价、均线、主力资金与技术指标变化，判断该股是否真正处于短线强势上涨阶段。你的任务是：判断该股是否值得买入（是否进入真正的上涨趋势）。输出格式必须为：{"code": "603128", "buy": true/false, "reason": ""}。你不能输出分析过程，只能输出最终结论和简短理由。
# 你需要根据下面的逻辑来判断，同时还要结合其他专业知识、综合所有给出来的指标来辅助判断：
# 1. 不买的假信号：1、下跌趋势中的“站上均线”（属于反抽，不是反转）；2、冲高回落、长上影线；3、连续多日主力资金流出；4、单日涨幅大但次日承接弱；5、放量突破但未站稳几日新高；6、单日暴涨且量能异常放大（量比大于5才认为量能异常放大）；7、最近3–5日股价整体呈下降趋势。
# 2. 买入条件：1、5/10日均线走平并开始拐头向上，收盘价持续站稳5日线；2、MACD绿柱衰减或DIFF金叉DEA；3、主力近2–3日呈现净流出减少到开始净流入的趋势，当日主力资金净流入、成交量大于昨日；4、换手率正常，不能过高也不能过低；5、当天无长上影线；
# 股票数据每个字段的含义如下：code：股票代码，name：股票名字，day：交易日期，current_price：当前价，last_price：前一天的收盘价，open_price：当天的开盘价，max_price：当天最高价，min_price：当天最低价，volume：当天成交量，fund：主力资金净流入，单位是万，turnover_rate：换手率，ma_five：5日均线价，ma_ten：10日均线价，ma_twenty：20日均线价，qrr：量比，diff：MACD指标的DIFF值，dea：MACD指标的DEA值，k：KDJ指标的K值，d：KDJ指标的D值，j：KDJ指标的J值，trix：TRIX指标的TRIX的值，trma：TRIX指标的MATRIX值。
# 这只股票的每一天的数据如下：
# '''

prompt = '''你是一个精通中国A股市场的短线交易员，擅长根据价格、均线、成交量、主力资金和技术指标判断是否应买入股票。你重点使用以下策略：价格站上5/10日均线、成交量大于昨日、主力资金净流入、换手率正常、MACD金叉或柱体变长、KDJ金叉或向上、TRIX向上等。
下面将提供1只股票最近多日的数据，这只股票数据已通过均线、量能、MACD、上影线等基础技术条件的程序化过滤，你需要理解每个字段含义，并重点判断其趋势质量与上涨持续性，需综合最近3日的连续变化趋势进行判断，而不是只看最后一天。
【判断规则】
题材与行业：判断industry/concept是否匹配hot_topic，若不匹配或关联度一般，直接判定不买入。
趋势判断（核心逻辑）：在已满足均线站上条件的前提下，判断5日均线是否持续向上、10日均线是否开始拐头向上或已经向上，均线运行是否平滑，是否存在走平或拐头向下迹象；判断价格是否持续运行在5/10日均线之上而非频繁回踩；判断成交量是否保持健康而非衰减；判断主力资金在最近几日内是否持续净流入或由负转正并保持稳定。
必须识别并规避的假信号：高开低走、长上影线、单日暴涨但量能异常、高换手率+小阳线或上影线（疑似出货）、假金叉、指标高位钝化、上涨动能明显减弱、均线系统未修复，或最近1–2日涨幅明显加速、价格远离均线导致短线情绪透支；若上述情况明显，应直接不买入。
【交易原则】
只在“热点题材+强势但仍处于趋势中段的上涨阶段”买入；若最近3日内价格、成交量、资金方向出现明显背离，应直接不买入；趋势不清晰、信号矛盾或偏弱，一律不买。
【输出要求】
只输出最终判断结果，不要输出分析过程；返回单个JSON对象，格式是：{"code":"603128","buy":true,"reason":"简要说明核心判断依据"}
【字段含义说明】
code：股票代码；hot_topic：当前市场热点题材；industry：所属行业；concept：相关概念；day：交易日期；current_price：当日收盘价；last_price：前一日收盘价；open_price：开盘价；max_price：最高价；min_price：最低价；volume：成交量；fund：主力资金净流入（单位：万）；turnover_rate：换手率；ma_five：5 日均线；ma_ten：10 日均线；ma_twenty：20 日均线；qrr：量比；diff：MACD 的 DIFF；dea：MACD 的 DEA；k：KDJ 的 K 值；d：KDJ 的 D 值；j：KDJ 的 J 值；trix：TRIX 指标值；trma：TRIX 均线。所有数组字段按 day 时间顺序排列。
这只股票最近每一天的数据如下：'''

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
