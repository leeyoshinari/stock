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
DEFAULT_USER_ID = 99    # 程序自动交易的默认用户
TOTAL_FUND = 100000     # 自动模拟买入股票的总仓位
FILE_PATH = os.path.join(BASE_PATH, "files")
HISTORY_PATH = os.path.join(BASE_PATH, "historys")
PROMPT_PATH = os.path.join(BASE_PATH, "prompts")
PREFIX = get_config("backEndPrefix")
HOST = get_config("host")
PORT = int(get_config("port"))
RUN_ENV = get_config("runEnv")
DB_URL = get_config("dbUrl")
DB_POOL_SIZE = int(get_config("connectionPoolSize"))
BATCH_SIZE = int(get_config("batchSize"))   # 每一个请求的股票数
BATCH_INTERVAL = int(get_config("batchInterval"))
LOGGER_LEVEL = get_config("logLevel")
SENDER_EMAIL = get_config("senderEmail")
RECEIVER_EMAIL = get_config("receiverEmail")
EMAIL_PASSWORD = get_config("emailPassword")
AUTH_CODE = get_config("authCode")
OPENAI_URL = get_config("openAIUrl")
OPENAI_MODEL = get_config("openAIModel")
OPENAI_KEY = get_config("openAIKey")
HTTP_HOST_CLOUD = get_config("HTTPHostCloud")
HTTP_HOST_VERCEL = get_config("HTTPHostVercel")
HTTP_HOST_NETLIFY = get_config("HTTPHostNetlify")
ACCESS_KEY = get_config("accessKey")
BACKUP_PATH = get_config("backupPath")
LONGBRIDGE_URL = get_config("longbridgeUrl")
EMAIL_TEMPLATE = os.path.join(PROMPT_PATH, "email.txt")
ETF_ANALYZE_NEWS = os.path.join(PROMPT_PATH, 'etf_analyzer_news.md')
ETF_ANALYZE_TECH = os.path.join(PROMPT_PATH, 'etf_analyzer_tech.md')
ETF_ANALYZE_FINALLY = os.path.join(PROMPT_PATH, 'etf_analyzer_finally.md')
AUTO_DECISION_MAKING = os.path.join(PROMPT_PATH, 'auto_decisio_making.md')


def checkout(pwd: str) -> bool:
    if ACCESS_KEY:
        if ACCESS_KEY == pwd:
            return True
        else:
            return False
    else:
        return True


if not os.path.exists(FILE_PATH):
    os.mkdir(FILE_PATH)
if not os.path.exists(HISTORY_PATH):
    os.mkdir(HISTORY_PATH)


def read_prompt(fileName: str) -> str:
    with open(os.path.join(PROMPT_PATH, fileName), 'r', encoding='utf-8') as f:
        res = f.read()
    return res


# 通用判断是否买入的提示词
# ANALYSIZE_PROMPT = read_prompt(os.path.join(PROMPT_PATH, 'buy-common.md'))
# 每天自动分析时，去除重复的ETF
EXCLUSIVE_ETF_LIST = ['510310', '159352', '159949', '562500']
