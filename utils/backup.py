#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import zipfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Union
from logging import Logger
from utils.database import Stock, Detail, ETF, Transaction, TradeType


def get_past_date(days_diff: int) -> str:
    """
    根据当前日期和相差天数，计算之前的日期
    :param days_diff: 相差天数
    :return: 之前的日期字符串
    """
    date_format = "%Y%m%d"  # 日期字符串格式
    current_date = datetime.now()
    past_date = current_date - timedelta(days=days_diff)
    return past_date.strftime(date_format)


async def zip_file(file_paths: list[Union[str, Path]], output_zip: Union[str, Path], logger: Logger):
    """
    异步压缩多个文件到 zip 包
    Args:
        file_paths: 要压缩的文件路径列表
        output_zip: 输出的 zip 文件路径
    """
    output_path = Path(output_zip)
    if output_path.exists():
        os.remove(output_zip)
        logger.info(f"删除已经存在的zip文件 - {output_zip}")

    with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            file_path = Path(file_path)
            if not file_path.exists():
                logger.warning(f"警告: 文件不存在 {file_path}")
                continue
            if file_path.is_file():
                zipf.write(file_path, arcname=file_path.name)
            else:
                logger.warning(f"警告: {file_path} 不是文件")


async def clear_detail_data(logger: Logger):
    try:
        stock: list[Stock] = await Stock.query().all()
        etf: list[ETF] = await ETF.query().equal(running=1).all()
        code = [f.code for f in stock] + [f.code for f in etf]
        past_day = get_past_date(383)    # 383天大概是一年多的数据，大概共256个交易日
        for c in code:
            trans: list[Transaction] = await Transaction.query().equal(code=c).order_by(Transaction.id.desc()).limit(3).all()
            if len(trans) == 0 or trans[0].status == TradeType.MAN:
                _ = await Detail.query().equal(code=c).less_equal(day=past_day).delete()
                logger.info(f"Delete detail data success, {c} - {past_day}")
    except:
        logger.error(traceback.format_exc())
