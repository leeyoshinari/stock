#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from pydantic import BaseModel
from typing import Any


class Result(BaseModel):
    success: bool = True
    msg: str = 'Success!'
    data: Any = None
    total: int = 0
