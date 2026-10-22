#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
# import asyncio
import json
# from openai import AsyncOpenAI
from settings import PROMPT_PATH, AUTH_CODE
from settings import OPENAI_KEY, OPENAI_URL, OPENAI_MODEL, HTTP_HOST_CLOUD, HTTP_HOST_VERCEL
from utils.http_client import http
from utils.dispatcher import AsyncRoundRobinDispatcher


def read_prompt(file_path) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        res = f.read()
    return res


# 支持的模型
# MODEL_LIST = [AI_MODEL]
# 重试，每次换一个模型
# max_retry = len(MODEL_LIST)

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


# async def queryGemini(msg: str, api_host: str, auth_code: str, promptType: int = 0) -> dict:
#     """
#     promptType:
#         0 - 每天选股任务的提示词
#         1 - 缩量下跌的提示词
#         2 - 通用判断是否买入的提示词
#         3 - 自动判断是否继续持有的提示词 (自动卖出决策, 先使用代码过滤, 然后用AI决策)
#         4 - 通用判断是否卖出的提示词
#     """
#     url = f"{api_host}/api/chat"
#     header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
#     if promptType == 1:
#         prompt = shrink_prompt
#     elif promptType == 2:
#         prompt = buy_common_prompt
#     elif promptType == 3:
#         prompt = auto_sell_prompt
#     elif promptType == 4:
#         prompt = sell_common_prompt
#     else:
#         prompt = auto_buy_prompt
#     for attempt in range(max_retry):
#         try:
#             model = MODEL_LIST[attempt]
#             data = {"model": model, "messages": [{"role": "user", "content": msg}], "systemRole": prompt, "temperature": 0}
#             res = await http.post(url=url, json_data=data, headers=header)
#             gemini_res = json.loads(res.text)
#             result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
#             res_json = json.loads(result_text.replace('```', '').replace('json', '').replace('\n', ''))
#             return res_json
#         except:
#             sleep_time = 5
#             await asyncio.sleep(sleep_time)
#     raise RuntimeError("Gemini 服务持续繁忙")


# async def queryOpenAi(msg: str, api_host: str, model: str, auth_code: str, promptType: int = 0) -> dict:
#     if promptType == 1:
#         prompt = shrink_prompt
#     elif promptType == 2:
#         prompt = buy_common_prompt
#     elif promptType == 3:
#         prompt = auto_sell_prompt
#     elif promptType == 4:
#         prompt = sell_common_prompt
#     else:
#         prompt = auto_buy_prompt
#     client = AsyncOpenAI(api_key=auth_code, base_url=api_host)
#     completion = await client.chat.completions.create(model=model, temperature=0,
#                                                       messages=[{'role': 'system', 'content': prompt}, {'role': 'user', 'content': msg}])
#     res = completion.choices[0].message.content
#     return json.loads(res)


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


# async def webSearchTopicBak(api_host: str, auth_code: str, current_date: str) -> str:
#     q = f'{current_date} A股市场 热门题材 热门板块 市场情绪'
#     prompts = f'你需要从【联网搜索资料】中找出 {current_date} 的内容，然后分析当前市场热点题材，将筛选出的热点信息，按照“事件/政策催化 -> 市场资金反应 -> 板块表现(包含个股表现)”的逻辑链进行组织，同时还要注意风险信息。请按照热点题材汇总(热点题材用,分隔)、热点题材逻辑链分析(和热点题材汇总中的题材数量要完全一样)、市场情绪、风险提示的顺序给出回答，不要输出没用的内容。【特别注意】热点题材是股票普遍涨势很好的题材，股票普遍下跌的题材不是热点题材'
#     url = f"{api_host}/api/search/ai"
#     header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
#     data = {"q": q, "dateRestrict": "d", "prompts": prompts}
#     res = await http.post(url=url, json_data=data, headers=header)
#     try:
#         gemini_res = json.loads(res.text)
#         result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
#         data = result_text.replace("#", "").replace("*", "").replace("-", "")
#         return data
#     except:
#         return res.text


# async def webSearchTopic(api_host: str, auth_code: str, current_date: str) -> str:
#     q = f'{current_date} 中国A股市场的热门题材和热门板块和市场情绪，按照“事件/政策催化 -> 市场资金反应 -> 板块表现”的逻辑链进行组织，同时还要注意风险信息。请按照热点题材汇总(热点题材用,分隔)、热点题材逻辑链分析(和热点题材汇总中的题材数量要完全一样)、市场情绪、风险提示的顺序给出回答，不要输出没用的内容。【特别注意】热点题材是股票普遍涨势很好的题材，股票普遍下跌的题材不是热点题材'
#     url = f"{api_host}/api/search/web"
#     header = {"Content-Type": "application/json", "Connection": "keep-alive", "Authorization": f"Bearer {auth_code}"}
#     data = {"prompts": q}
#     res = await http.post(url=url, json_data=data, headers=header)
#     try:
#         gemini_res = json.loads(res.text)
#         result_text = gemini_res['candidates'][0]['content']['parts'][0]['text']
#         data = result_text.replace("#", "").replace("*", "").replace("-", "")
#         return data
#     except:
#         return res.text


async def queryGeminiBak(baseUrl: str, systemPrompt: str, userMessage: str, model: str, stream: bool = False) -> str:
    """ 请求 Gemini, 官方url: https://generativelanguage.googleapis.com/v1beta
    :params baseUrl: 传入的url, 可以走代理
    :params systemPrompt: 系统提示词, 系统指令
    :params userMessage: 用户输入的信息
    :params model: 模型名称, 例如: gemini-3.0-flash
    :params stream: 是否流式输出
    """
    url = f"{baseUrl}/models/{model}:generateContent?key={AUTH_CODE}"
    if stream:
        url = f"{baseUrl}/models/{model}:streamGenerateContent?alt=sse&key={AUTH_CODE}"

    header = {"Content-Type": "application/json"}   # , "Connection": "keep-alive"}

    if not systemPrompt or len(systemPrompt.strip()) < 1:
        systemPrompt = "你是一个专业的AI助手。"

    # 【核心改变】：直接使用 Gemini 官方标准的请求体结构
    data = {
        "systemInstruction": {
            "parts": [{"text": systemPrompt}]   # 你的基本面/技术面分析框架提示词
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": userMessage}]
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"    # 强制输出纯 JSON，无需后续字符串清洗
        }
    }
    res = await http.post(url=url, json_data=data, headers=header)

    # 1. 解析 Next.js 代理层返回的 HTTP 响应
    proxy_res = json.loads(res.text)

    # 2. 检查是否有 Gemini 返回的错误 (如 400, 429)
    if "error" in proxy_res:
        raise Exception(f"Gemini API Error: {proxy_res['error']}")

    # 3. 提取模型生成的纯 JSON 文本
    result_text = proxy_res['candidates'][0]['content']['parts'][0]['text']
    return result_text


async def queryOpenAI(baseUrl: str, systemPrompt: str, userMessage: str, model: str, apiKey: str = AUTH_CODE) -> str:
    """ 请求 Gemini, 官方url: https://api.openai.com/v1
    :params baseUrl: 传入的url, 可以走代理
    :params systemPrompt: 系统提示词, 系统指令
    :params userMessage: 用户输入的信息
    :params model: 模型名称, 例如: gpt-5-mini
    """
    url = f"{baseUrl}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {apiKey}"  # 使用 AUTH_CODE 进行代理鉴权
    }

    if not systemPrompt or len(systemPrompt.strip()) < 1:
        systemPrompt = "你是一个专业的AI助手。"

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": systemPrompt},
            {"role": "user", "content": userMessage}
        ],
        "temperature": 0.1,
        "response_format": {"type": "json_object"}
    }
    res = await http.post(url=url, json_data=data, headers=headers)

    # 检查错误 (代理层或 OpenAI 返回的错误都会遵循 OpenAI 的 error 格式)
    res_json = json.loads(res.text)
    if "error" in res_json:
        raise Exception(f"API Error: {res_json['error']['message']}")
    return res_json['choices'][0]['message']['content']


async def queryChatGPTLocal(systemPrompt: str, userMessage: str) -> str:
    """本地直接请求 OpenAI 接口"""
    res = await queryOpenAI(OPENAI_URL, systemPrompt, userMessage, OPENAI_MODEL, apiKey=OPENAI_KEY)
    return res


async def queryChatGPTCloud(systemPrompt: str, userMessage: str) -> str:
    """请求云服务器的 OpenAI 转发请求"""
    url = f"{HTTP_HOST_CLOUD}/api/ai/openai/v1"
    res = await queryOpenAI(url, systemPrompt, userMessage, OPENAI_MODEL)
    return res


async def queryGeminiCloud(systemPrompt: str, userMessage: str) -> str:
    """请求云服务器的 Gemini 转发请求"""
    url = f"{HTTP_HOST_CLOUD}/api/ai/google/v1beta"
    model = "gemini-3.5-flash-lite"
    res = await queryGeminiBak(url, systemPrompt, userMessage, model)
    return res


async def queryGeminiVercel(systemPrompt: str, userMessage: str) -> str:
    """请求云服务器的 Gemini 转发请求"""
    url = f"{HTTP_HOST_VERCEL}/api/ai/google/v1beta"
    model = "gemini-3.5-flash-lite"
    res = await queryGeminiBak(url, systemPrompt, userMessage, model)
    return res


ai_method_list = [queryChatGPTLocal, queryGeminiCloud, queryGeminiVercel, queryChatGPTCloud]
ai_dispatcher = AsyncRoundRobinDispatcher(methods=ai_method_list, max_retries=5, timeout=120, cooldown=180, name="AIDispatcher")


async def chat(*args, **kwargs):
    return await ai_dispatcher.call(*args, **kwargs)
