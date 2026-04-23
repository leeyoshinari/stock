#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import asyncio
import json
from logging import Logger
from openai import AsyncOpenAI
from settings import AI_MODEL, AI_MODEL25, PROMPT_PATH
from utils.http_client import http


def read_prompt(file_path) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        res = f.read()
    return res


# 支持的模型
MODEL_LIST = [AI_MODEL, AI_MODEL25]
# 重试，每次换一个模型
max_retry = len(MODEL_LIST)

# 每天自动选股任务的提示词
auto_buy_prompt = read_prompt(os.path.join(PROMPT_PATH, 'buy.md'))

# 缩量下跌的提示词
shrink_prompt = read_prompt(os.path.join(PROMPT_PATH, 'shrink.md'))

# 通用判断是否买入的提示词
buy_common_prompt = read_prompt(os.path.join(PROMPT_PATH, 'buy-common.md'))

# 自动判断是否继续持有的提示词 (自动卖出决策, 先使用代码过滤, 然后用AI决策)
auto_sell_prompt = read_prompt(os.path.join(PROMPT_PATH, 'sell.md'))

# 通用判断是否卖出的提示词
sell_common_prompt = read_prompt(os.path.join(PROMPT_PATH, 'sell-common.md'))


async def queryGemini(msg: str, api_host: str, auth_code: str, promptType: int = 0) -> dict:
    """
    promptType:
        0 - 每天选股任务的提示词
        1 - 缩量下跌的提示词
        2 - 通用判断是否买入的提示词
        3 - 自动判断是否继续持有的提示词 (自动卖出决策, 先使用代码过滤, 然后用AI决策)
        4 - 通用判断是否卖出的提示词
    """
    url = f"{api_host}/api/chat"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    if promptType == 1:
        prompt = shrink_prompt
    elif promptType == 2:
        prompt = buy_common_prompt
    elif promptType == 3:
        prompt = auto_sell_prompt
    elif promptType == 4:
        prompt = sell_common_prompt
    else:
        prompt = auto_buy_prompt
    for attempt in range(max_retry):
        try:
            model = MODEL_LIST[attempt]
            data = {"model": model, "messages": [{"role": "user", "content": msg}], "systemRole": prompt, "temperature": 0}
            res = await http.post(url=url, json_data=data, headers=header)
            gemini_res = json.loads(res.text)
            result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
            res_json = json.loads(result_text.replace('```', '').replace('json', '').replace('\n', ''))
            return res_json
        except:
            sleep_time = 5
            await asyncio.sleep(sleep_time)
    raise RuntimeError("Gemini 服务持续繁忙")


async def queryOpenAi(msg: str, api_host: str, model: str, auth_code: str, promptType: int = 0) -> dict:
    if promptType == 1:
        prompt = shrink_prompt
    elif promptType == 2:
        prompt = buy_common_prompt
    elif promptType == 3:
        prompt = auto_sell_prompt
    elif promptType == 4:
        prompt = sell_common_prompt
    else:
        prompt = auto_buy_prompt
    client = AsyncOpenAI(api_key=auth_code, base_url=api_host)
    completion = await client.chat.completions.create(model=model, temperature=0,
                                                      messages=[{'role': 'system', 'content': prompt}, {'role': 'user', 'content': msg}])
    res = completion.choices[0].message.content
    return json.loads(res)


async def webSearch(q: str, prompts: str, api_host: str, auth_code: str) -> str:
    url = f"{api_host}/api/search/ai"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    data = {"q": q, "dateRestrict": "d", "prompts": prompts}
    res = await http.post(url=url, json_data=data, headers=header)
    try:
        gemini_res = json.loads(res.text)
        result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
        return result_text
    except:
        return res.text


async def webSearchTopicBak(api_host: str, auth_code: str, current_date: str) -> str:
    q = f'{current_date} A股市场 热门题材 热门板块 市场情绪'
    prompts = f'你需要从【联网搜索资料】中找出 {current_date} 的内容，然后分析当前市场热点题材，将筛选出的热点信息，按照“事件/政策催化 -> 市场资金反应 -> 板块表现(包含个股表现)”的逻辑链进行组织，同时还要注意风险信息。请按照热点题材汇总(热点题材用,分隔)、热点题材逻辑链分析(和热点题材汇总中的题材数量要完全一样)、市场情绪、风险提示的顺序给出回答，不要输出没用的内容。【特别注意】热点题材是股票普遍涨势很好的题材，股票普遍下跌的题材不是热点题材'
    url = f"{api_host}/api/search/ai"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    data = {"q": q, "dateRestrict": "d", "prompts": prompts}
    res = await http.post(url=url, json_data=data, headers=header)
    try:
        gemini_res = json.loads(res.text)
        result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
        data = result_text.replace("#", "").replace("*", "").replace("-", "")
        return data
    except:
        return res.text


async def webSearchTopic(api_host: str, auth_code: str, current_date: str) -> str:
    q = f'{current_date} 中国A股市场的热门题材和热门板块和市场情绪，按照“事件/政策催化 -> 市场资金反应 -> 板块表现”的逻辑链进行组织，同时还要注意风险信息。请按照热点题材汇总(热点题材用,分隔)、热点题材逻辑链分析(和热点题材汇总中的题材数量要完全一样)、市场情绪、风险提示的顺序给出回答，不要输出没用的内容。【特别注意】热点题材是股票普遍涨势很好的题材，股票普遍下跌的题材不是热点题材'
    url = f"{api_host}/api/search/web"
    header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
    data = {"prompts": q}
    res = await http.post(url=url, json_data=data, headers=header)
    try:
        gemini_res = json.loads(res.text)
        result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
        data = result_text.replace("#", "").replace("*", "").replace("-", "")
        return data
    except:
        return res.text
