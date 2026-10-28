#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import asyncio
import logging
import time
from typing import Callable, Any, List, Optional

logger = logging.getLogger(__name__)


class Worker:
    """封装可调用的方法及其状态"""
    def __init__(self, func: Callable, name: Optional[str] = None):
        self.func = func
        self.name = name or getattr(func, '__name__', str(func))
        self.fail_count = 0     # 方法调用失败次数
        self.is_disabled = False    # 方法当前是否可用
        self.disabled_until = 0.0   # 冷近期截止时间，时间戳

    def __repr__(self):
        return f"<Worker: {self.name}, disabled: {self.is_disabled}>"


class AsyncRoundRobinDispatcher:
    """
    通用异步容错轮询调度器
    支持：轮询、超时控制、自定义成功校验、失败计数剔除与冷却恢复
    """
    def __init__(self, methods: List[Callable], max_retries: int = 5, timeout: Optional[float] = None, cooldown: float = 0, success_validator: Optional[Callable[[Any], bool]] = None, name: str = "Dispatcher"):
        """初始化异步轮询调度器\n
        :params methods: 调用方法列表
        :params max_retries: 失败重试次数
        :params timeout: 超时时间, 单位:s。 默认不超时，建议设置，避免死循环
        :params cooldown: 冷静时间, 单位:s。设置为0就是不冷静，达到失败次数直接踢出
        :params success_validator: 自定义业务级成功校验
        :params name: 名称
        """
        if not methods:
            raise ValueError("至少需要提供一个调用方法")
        self.name = name
        self.max_retries = max_retries
        self.timeout = timeout
        self.cooldown = cooldown
        # 自定义校验器：默认只要不抛异常就算成功
        self.success_validator = success_validator or (lambda _: True)

        self._workers = [Worker(m) for m in methods]
        self._index = 0
        self._lock = asyncio.Lock()

    async def call(self, *args, **kwargs) -> Any:
        """执行调度调用"""
        tried_workers = set()

        while True:
            async with self._lock:
                # 1. 清理已过冷却期的 worker
                current_time = time.time()
                for w in self._workers:
                    if w.is_disabled and current_time >= w.disabled_until:
                        w.is_disabled = False
                        w.fail_count = 0
                        logger.info(f"🔄 [{self.name}] Worker '{w.name}' 冷却期结束，已恢复。")

                # 2. 获取下一个可用的 worker
                available_workers = [w for w in self._workers if not w.is_disabled]
                if not available_workers:
                    raise RuntimeError(f"[{self.name}] 所有方法均已被禁用或剔除，无可用方法。")

                # 轮询获取
                worker = available_workers[self._index % len(available_workers)]
                self._index = (self._index + 1) % len(available_workers)

            # 3. 防止单次请求内死循环
            if worker in tried_workers:
                raise RuntimeError(f"[{self.name}] 当前所有可用方法在本次请求中均已失败。")
            tried_workers.add(worker)

            try:
                # 4. 实际调用 (带超时控制)
                if self.timeout:
                    result = await asyncio.wait_for(worker.func(*args, **kwargs), timeout=self.timeout)
                else:
                    result = await worker.func(*args, **kwargs)

                # 5. 业务级成功校验
                if not self.success_validator(result):
                    raise ValueError(f"业务校验失败，返回值: {result}")

                # 6. 调用成功，重置状态
                async with self._lock:
                    worker.fail_count = 0
                logger.info(f"✅ [{self.name}] Worker '{worker.name}' 调用成功")
                return result

            except asyncio.TimeoutError:
                err_msg = f"调用超时 ({self.timeout}s)"
                await self._handle_failure(worker, err_msg)
            except Exception as e:
                await self._handle_failure(worker, str(e))

    async def _handle_failure(self, worker: Worker, error_msg: str):
        """统一的失败处理逻辑"""
        async with self._lock:
            worker.fail_count += 1
            if worker.fail_count > self.max_retries:
                worker.is_disabled = True
                if self.cooldown > 0:
                    worker.disabled_until = time.time() + self.cooldown
                    logger.error(f"🚫 [{self.name}] Worker '{worker.name}' 失败超限，进入冷却期 ({self.cooldown}s)。原因: {error_msg}")
                else:
                    worker.disabled_until = float('inf')
                    logger.error(f"🗑️ [{self.name}] Worker '{worker.name}' 失败超限，永久禁用。原因: {error_msg}")
            else:
                logger.warning(f"⚠️ [{self.name}] Worker '{worker.name}' 失败 {worker.fail_count}/{self.max_retries} 次。原因: {error_msg}")
