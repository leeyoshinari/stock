#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from litestar import Litestar, Router, Controller, get, post
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.static_files.config import StaticFilesConfig
from contextlib import asynccontextmanager
from settings import PREFIX, HOST, PORT
from utils.scheduler import scheduler
from utils.database import Database
from utils.results import Result
from utils import model, views


Database.init_db()  # 初始化数据库


class StockController(Controller):
    path = ""
    tags = ['stock']

    @get("/list", summary="查询股票列表")
    async def query_stock_list(self, code: str = "", name: str = "", sortField: str = 'qrr', page: int = 1, pageSize: int = 20) -> Result:
        query = model.SearchStockParam()
        query.code = code if code else ""
        query.name = name if name else ""
        query.sortField = sortField if sortField else 'qrr'
        query.page = page
        query.pageSize = pageSize
        result = await views.queryStockList(query)
        return result

    @get('/get', summary="查询股票信息")
    async def create_file(self, code: str) -> Result:
        result = await views.queryByCode(code)
        return result

    @post('/query/tencent', summary="查询股票数据信息")
    async def query_stock(self, data: model.RequestData) -> Result:
        result = await views.query_tencent(data)
        return result

    @post('/query/xueqiu', summary="查询股票数据信息")
    async def query_stock_xueqiu(self, data: model.RequestData) -> Result:
        result = await views.query_xueqiu(data)
        return result

    @post('/query/sina', summary="查询股票数据信息")
    async def query_stock_sina(self, data: model.RequestData) -> Result:
        result = await views.query_sina(data)
        return result

    @get('/test')
    async def test(self) -> Result:
        result = await views.test()
        return result


@get("/")
async def index() -> Template:
    return Template("index.html", context={'prefix': PREFIX})


route_handlers = [Router(path=PREFIX, route_handlers=[StockController]), Router(path='', route_handlers=[index])]


@asynccontextmanager
async def lifespan(app: Litestar):
    scheduler.start()
    yield
    scheduler.shutdown()

render_file = SwaggerRenderPlugin(js_url=f'{PREFIX}/static/swagger-ui-bundle.js', css_url=f'{PREFIX}/static/swagger-ui.css', standalone_preset_js_url=f'{PREFIX}/static/swagger-ui-standalone-preset.js')
openapi_config = OpenAPIConfig(title="WinHub", version="1.0", description="This is API of WinHub.", path=PREFIX + "/schema", render_plugins=[render_file])
app = Litestar(route_handlers=route_handlers, template_config=TemplateConfig(directory="templates", engine=JinjaTemplateEngine,), openapi_config=openapi_config,
               lifespan=[lifespan], static_files_config=[StaticFilesConfig(path=f"{PREFIX}/static", directories=["static"]),], logging_config=None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app="main:app", host=HOST, port=PORT, reload=False)
