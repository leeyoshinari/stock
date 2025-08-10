#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import time
from litestar import Litestar, Router, Controller, get
from litestar.openapi import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin
from contextlib import asynccontextmanager
from settings import PREFIX, HOST, PORT, FRONT_END_PREFIX, THREAD_POOL_SIZE
from utils.scheduler import scheduler
from utils.database import Database
from utils.results import Result
from utils import model, views
from utils.getStock import queryTask


Database.init_db()  # 初始化数据库


class StockController(Controller):
    path = "/stock"
    tags = ['stock']

    @get("/list", summary="查询股票列表")
    async def query_stock_list(self, code: str, name: str, sort_field: str, page: int = 1, page_size: int = 20) -> Result:
        query = model.SearchStockParam()
        query.code = code if code else ""
        query.name = name if name else ""
        query.sortField = sort_field if sort_field else 'qrr'
        query.page = page
        query.pageSize = page_size
        result = await views.queryStockList(query)
        return result

    @get('/get', summary="查询股票信息")
    async def create_file(self, code: str) -> Result:
        result = await views.queryByCode(code)
        return result


route_handlers = [Router(path=PREFIX, route_handlers=[StockController])]


@asynccontextmanager
async def lifespan(app: Litestar):
    scheduler.start()
    yield
    scheduler.shutdown()
    for i in range(THREAD_POOL_SIZE):
        queryTask.put("end")
    time.sleep(2)

render_file = SwaggerRenderPlugin(js_url=f'{FRONT_END_PREFIX}/js/swagger-ui-bundle.js', css_url=f'{FRONT_END_PREFIX}/css/swagger-ui.css')
openapi_config = OpenAPIConfig(title="WinHub", version="1.0", description="This is API of WinHub.", path=PREFIX + "/schema", render_plugins=[render_file])
app = Litestar(route_handlers=route_handlers, openapi_config=openapi_config, lifespan=[lifespan], logging_config=None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app="main:app", host=HOST, port=PORT, reload=False)
