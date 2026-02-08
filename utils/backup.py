#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import os
import zipfile
import aiofiles
from pathlib import Path
from typing import Union
from logging import Logger


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
                async with aiofiles.open(file_path, 'rb') as f:
                    content = await f.read()
                zipf.writestr(file_path.name, content)
            else:
                logger.warning(f"警告: {file_path} 不是文件")
