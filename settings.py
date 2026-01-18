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
All_STOCK_DATA_SIZE = int(get_config("allStockDataSize"))
LOGGER_LEVEL = get_config("logLevel")
SENDER_EMAIL = get_config("senderEmail")
RECEIVER_EMAIL = get_config("receiverEmail")
EMAIL_PASSWORD = get_config("emailPassword")
API_URL = get_config("apiUrl")
AI_MODEL = get_config("aiModel")
AUTH_CODE = get_config("authCode")
OPENAI_URL = get_config("openAIUrl")
OPENAI_MODEL = get_config("openAIModel")
OPENAI_KEY = get_config("openAIKey")
HTTP_HOST1 = get_config("HTTPHost1")
HTTP_HOST2 = get_config("HTTPHost2")
ACCESS_KEY = get_config("accessKey")


def checkout(pwd: str) -> bool:
    if ACCESS_KEY:
        if ACCESS_KEY == pwd:
            return True
        else:
            return False
    else:
        return True
