#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import os
import sys
from dotenv import load_dotenv, dotenv_values


if hasattr(sys, 'frozen'):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

TOKENs = {}


def sync_with_dotenv():
    example_config = dotenv_values('.env.example')
    if os.path.exists('.env'):
        current_config = dotenv_values('.env')
    else:
        current_config = {}
    new_keys = set(example_config.keys()) - set(current_config.keys())
    if new_keys:
        with open('.env', 'a', encoding='utf-8') as f:
            f.write('\n# 以下为自动添加的新配置\n')
            for key in new_keys:
                f.write(f"{key} = {example_config[key]}\n")


def get_config(key):
    value = os.getenv(key, None)
    return value


sync_with_dotenv()  # 更新配置
load_dotenv()   # 加载配置
PREFIX = get_config("backEndPrefix")
HOST = get_config("host")
PORT = int(get_config("port"))
DB_URL = get_config("dbUrl")
DB_POOL_SIZE = int(get_config("connectionPoolSize"))
BATCH_SIZE = int(get_config("batchSize"))
BATCH_INTERVAL = int(get_config("batchInterval"))
MAX_PRICE = int(get_config("maxPrice"))
THREAD_POOL_SIZE = int(get_config("threadPoolSize"))
LOGGER_LEVEL = get_config("logLevel")
