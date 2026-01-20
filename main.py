#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import asyncio
from contextlib import asynccontextmanager, suppress
from litestar import Litestar, Request, Router, Controller, get, post
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.static_files.config import StaticFilesConfig
from settings import PREFIX, HOST, PORT, checkout
from utils.scheduler import scheduler
from utils.database import Database, write_worker
from utils.results import Result
from utils import model, views


class StockController(Controller):
    path = ""
    tags = ['stock']

    @get("/list", summary="查询股票列表")
    async def query_stock_list(self, request: Request, code: str = "", name: str = "", sortField: str = '-qrr', page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.code = code if code else ""
            query.name = name if name else ""
            query.sortField = sortField if sortField else '-qrr'
            query.page = page
            query.pageSize = pageSize
            result = await views.queryStockList(query)
        return result

    @get('/get', summary="查询股票信息")
    async def create_file(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.queryByCode(code)
        return result

    @get('/getRecommend', summary="获取推荐的股票")
    async def get_recommend(self, request: Request, page: int = 1) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.queryRecommendStockList(page)
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

    @get('/query/ai')
    async def stock_ai_data(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.query_ai_stock(code)
        return result

    @get('/query/stock/return', summary="查询选出来的股票的收益")
    async def stock_return(self, request: Request) -> Result:
        result = await views.calc_stock_return()
        return result

    @get('/query/recommend/real', summary="查询选出来的股票的分钟级走势")
    async def stock_real(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.calc_stock_real(code)
        return result

    @get('/stock/list', summary="查询股票信息")
    async def all_stock_list(self, request: Request, code: str = "", name: str = "", filter: str = "", region: str = "", industry: str = "", concept: str = "", page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.code = code if code else ""
            query.name = name if name else ""
            query.region = region if region else ""
            query.industry = industry if industry else ""
            query.concept = concept if concept else ""
            query.filter = filter if filter else ""
            query.page = page
            query.pageSize = pageSize
            result = await views.all_stock_info(query)
        return result

    @get('/stock/info', summary="查询股票板块、概念等信息")
    async def get_stock_info(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.get_stock_info(code)
        return result

    @get('/stock/setFilter', summary="设置股票标签")
    async def set_stock_filter(self, request: Request, code: str, filter: str, operate: int) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.set_stock_filter(code, filter, operate)
        return result

    @get('/stock/init', summary="初始化股票数据")
    async def init_stock_data(self, request: Request, code: str) -> Result:
        result = Result()
        if not checkout(request.headers.get('referered', '123')):
            result = await views.init_stock_data(code)
        return result

    @get('/topic/list', summary="查询热门题材列表")
    async def all_topic_list(self, request: Request, page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.page = page
            query.pageSize = pageSize
            result = await views.all_topic_info(query)
        return result

    @get('/topic/get', summary="查询实时热门题材")
    async def get_current_topic(self, request: Request) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.get_current_topic()
        return result

    @get('/test')
    async def test(self, request: Request, code: str) -> Result:
        result = await views.test(code)
        return result


@get("/")
async def index() -> Template:
    return Template("recommend.html", context={'prefix': PREFIX})


@get("/s")
async def recommend() -> Template:
    return Template("index.html", context={'prefix': PREFIX})


@get("/stock")
async def stock_list() -> Template:
    return Template("stock.html", context={'prefix': PREFIX})


@get("/topic")
async def topic_list() -> Template:
    return Template("topic.html", context={'prefix': PREFIX})


@get("/home")
async def home() -> Template:
    return Template("home.html", context={'prefix': PREFIX})


route_handlers = [Router(path=PREFIX, route_handlers=[StockController]), Router(path='', route_handlers=[home, index, recommend, stock_list, topic_list])]


@asynccontextmanager
async def lifespan(app: Litestar):
    await Database.init_db()    # 初始化数据库
    scheduler.start()   # 启动定时任务，在启动前，必须已经add_job
    worker_task = asyncio.create_task(write_worker())
    yield
    worker_task.cancel()
    with suppress(asyncio.CancelledError):
        await worker_task
    scheduler.shutdown()
    await Database.dispose()


render_file = SwaggerRenderPlugin(js_url=f'{PREFIX}/static/swagger-ui-bundle.js', css_url=f'{PREFIX}/static/swagger-ui.css', standalone_preset_js_url=f'{PREFIX}/static/swagger-ui-standalone-preset.js')
openapi_config = OpenAPIConfig(title="Stock", version="1.0", description="This is API of Stock.", path=PREFIX + "/schema", render_plugins=[render_file])
app = Litestar(route_handlers=route_handlers, template_config=TemplateConfig(directory="templates", engine=JinjaTemplateEngine,), openapi_config=openapi_config,
               lifespan=[lifespan], static_files_config=[StaticFilesConfig(path=f"{PREFIX}/static", directories=["static"]),], logging_config=None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app="main:app", host=HOST, port=PORT, reload=False)
