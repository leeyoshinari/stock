#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import json
# from openai import AsyncOpenAI
from settings import AUTH_CODE, HTTP_HOST_CLOUD, HTTP_HOST_VERCEL
from settings import OPENAI_KEY, OPENAI_URL, OPENAI_MODEL
from utils.http_client import http
from utils.dispatcher import AsyncRoundRobinDispatcher


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


async def queryGemini(baseUrl: str, systemPrompt: str, userMessage: str, model: str, stream: bool = False) -> str:
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
    res = await queryGemini(url, systemPrompt, userMessage, model)
    return res


async def queryGeminiVercel(systemPrompt: str, userMessage: str) -> str:
    """请求云服务器的 Gemini 转发请求"""
    url = f"{HTTP_HOST_VERCEL}/api/ai/google/v1beta"
    model = "gemini-3.5-flash-lite"
    res = await queryGemini(url, systemPrompt, userMessage, model)
    return res


ai_method_list = [queryChatGPTLocal, queryGeminiCloud, queryGeminiVercel, queryChatGPTCloud]
ai_dispatcher = AsyncRoundRobinDispatcher(methods=ai_method_list, max_retries=3, timeout=99, cooldown=600, name="AIDispatcher")


async def chat(*args, **kwargs):
    return await ai_dispatcher.call(*args, **kwargs)
