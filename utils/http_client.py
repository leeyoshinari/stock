#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import aiohttp
import asyncio
from typing import Optional, Any, Union
from curl_cffi.requests import AsyncSession, Response


class HttpResponse:
    def __init__(self, *, url: str, status: int, headers: dict, text: str, content: bytes):
        self.url = url
        self.status_code = status
        self.headers = headers
        self.text = text
        self.content = content


class HttpClient:
    def __init__(self, timeout: int = 120, max_connections: int = 50, max_per_host: int = 20, retry: int = 2):
        self.timeout = timeout
        self.max_connections = max_connections
        self.max_per_host = max_per_host
        self.retry = retry

        self.session: Optional[aiohttp.ClientSession] = None
        self.connector: Optional[aiohttp.TCPConnector] = None
        self._lock = asyncio.Lock()

    async def start(self):
        async with self._lock:
            if self.session and not self.session.closed:
                return

            timeout = aiohttp.ClientTimeout(total=self.timeout)

            self.connector = aiohttp.TCPConnector(
                limit=self.max_connections,
                limit_per_host=self.max_per_host,
                ssl=False,
            )

            self.session = aiohttp.ClientSession(
                timeout=timeout,
                connector=self.connector,
                raise_for_status=False,
            )

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def request(self, method: str, url: str, *, params=None, data=None, json_data=None, headers=None, **kwargs) -> HttpResponse:
        await self.start()
        for attempt in range(self.retry + 1):
            try:
                async with self.session.request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json_data,
                    headers=headers,
                    **kwargs,
                ) as resp:

                    text = await resp.text()
                    content = await resp.read()

                    return HttpResponse(
                        url=str(resp.url),
                        status=resp.status,
                        headers=dict(resp.headers),
                        text=text,
                        content=content,
                    )

            except Exception:
                if attempt >= self.retry:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))

    async def get(self, url: str, **kwargs) -> HttpResponse:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> HttpResponse:
        return await self.request("POST", url, **kwargs)


async def cffi_request(url: str, method: str = "GET", params: Optional[dict[str, Any]] = None,
                       data: Optional[Union[dict[str, Any], str]] = None, json_data: Optional[dict[str, Any]] = None,
                       headers: Optional[dict[str, str]] = None, impersonate: str = "chrome131", timeout: int = 15
                       ) -> Response:
    """
    通用的异步 HTTP 请求方法 (基于 curl_cffi，支持绕过 TLS 指纹反爬)

    :param url: 请求的 URL
    :param method: HTTP 方法，如 "GET", "POST"
    :param params: URL 查询参数 (字典)
    :param data: 表单数据或字符串 (用于 POST/PUT)
    :param json_data: JSON 格式的请求体 (用于 POST/PUT)
    :param headers: 请求头字典
    :param impersonate: 模拟的浏览器指纹，默认 "chrome131"
    :param timeout: 超时时间(秒)
    :return: Response对象
    """
    method = method.upper()
    session = AsyncSession()

    try:
        response: Response = await session.request(
            method=method,
            url=url,
            params=params,
            data=data,
            json=json_data,
            headers=headers,
            impersonate=impersonate,
            timeout=timeout
        )
        # 检查 HTTP 状态码
        response.raise_for_status()
        return response
    except:
        raise
    finally:
        await session.close()


# 全局单例
http = HttpClient()
