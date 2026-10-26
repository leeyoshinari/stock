#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari
import utils.logging

import os
import time
import asyncio
import aiofiles
from contextlib import asynccontextmanager, suppress
from litestar import Litestar, Request, Router, Controller, get, post
from litestar.openapi import OpenAPIConfig
from litestar.response import Template
from litestar.openapi.plugins import SwaggerRenderPlugin
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig
from litestar.static_files.config import StaticFilesConfig
from settings import PREFIX, HOST, PORT, BASE_PATH, checkout, BACKUP_PATH, RUN_ENV
from utils.scheduler import scheduler
from utils.backup import zip_file
from utils.database import Database, write_worker
from utils.results import Result
from utils import model, views, getStock


db_path = os.path.join(BASE_PATH, 'sqlite3.db')
zip_path = os.path.join(BACKUP_PATH, 'db.zip')


async def modify_sw():
    current_date = time.strftime("%Y-%m-%d-%H-%M-%S")
    if os.path.exists('static/sw.js'):
        async with aiofiles.open('static/sw.js', 'r', encoding='utf-8') as f:
            lines = await f.readlines()
        lines[0] = f"const CACHE_NAME = 'stock-{current_date}';\n"
        async with aiofiles.open('static/sw.js', 'w', encoding='utf-8') as f:
            await f.writelines(lines)


class StockController(Controller):
    path = ""
    tags = ['stock']

    @get("/list", summary="查询股票每天行情数据列表")
    async def query_stock_list(self, request: Request, code: str = "", name: str = "", day: str = "", sortField: str = '-qrr', page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.code = code if code else ""
            query.name = name if name else ""
            query.day = day.replace("-", "") if day else ""
            query.sortField = sortField if sortField else '-qrr'
            query.page = page
            query.pageSize = pageSize
            result = await views.queryStockList(query)
        return result

    @get('/get', summary="查询股票k-line等技术指标数据")
    async def create_file(self, request: Request, code: str, userId: str = None) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.queryByCode(code, userId)
        return result

    @get('/query/day/k', summary="查询股票当日K线")
    async def stock_real(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.calc_stock_real(code)
        return result

    @get('/stock/list', summary="查询股票列表")
    async def all_stock_list(self, request: Request, code: str = "", name: str = "", filter: str = "", region: str = "", industry: str = "", concept: str = "", userId: int = None, page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.code = code if code else ""
            query.name = name if name else ""
            query.region = region if region else ""
            query.industry = industry if industry else ""
            query.concept = concept if concept else ""
            query.filter = filter if filter else ""
            query.userId = userId
            query.page = page
            query.pageSize = pageSize
            result = await views.all_stock_info(query)
        return result

    @get('/etf/list', summary="查询ETF列表")
    async def all_etf_list(self, request: Request, code: str = "", name: str = "", sortField: str = "", filter: str = "1", page: int = 1, pageSize: int = 20) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            query = model.SearchStockParam()
            query.code = code if code else ""
            query.name = name if name else ""
            query.filter = filter if filter else "1"
            query.sortField = sortField if sortField else ""
            query.page = page
            query.pageSize = pageSize
            result = await views.all_etf_info(query)
        return result

    @get('/stock/init', summary="初始化股票数据")
    async def init_stock_data(self, request: Request, code: str) -> Result:
        result = Result()
        if not checkout(request.headers.get('referered', '123')):
            result = await views.init_stock_data(code)
        return result

    @post('/stock/fund/update', summary="更新股票主力资金数据")
    async def init_stock_fund_data(self, request: Request, data: model.updateFundDo) -> Result:
        result = Result()
        if not checkout(request.headers.get('referered', '123')):
            result = await views.init_stock_fund_data(data)
        return result

    @post('/set/stock', summary="设置股票数据(添加/删除标签)")
    async def set_stock(self, request: Request, data: model.SetStockParam) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.set_stock(data)
        return result

    @get('/hold/list', summary="查询仓位列表")
    async def get_hold_list(self, request: Request, userId: int = None, page: int = 1) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.queryTradeStockList(userId=userId, page=page)
        return result

    @get('/hold/get/{userId: str}', summary="查询仓位数据")
    async def get_user_hold(self, userId: str) -> Result:
        result = await views.get_user_hold(userId)
        return result

    @post('/hold/set', summary="设置仓位数据(买入和卖出)")
    async def set_hold(self, request: Request, data: model.SetStockHold) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.set_user_hold(data)
        return result

    @get('/deleteHold', summary="删除持仓的股票(交易记录或者已清仓数据)")
    async def delte_hold(self, request: Request, hId: int) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.deleteHoldStock(hId)
        return result

    @get('/etf/delete', summary="删除ETF")
    async def delte_etf(self, request: Request, code: str) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.deleteEtf(code)
        return result

    @get('/etf/set', summary="设置ETF(启用或者禁用)")
    async def set_etf(self, request: Request, code: str, running: int) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.setEtf(code, running)
        return result

    @get('/analyzer', summary="全面分析标的")
    async def analyzer(self, request: Request, code: str, userId: str | None = None) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.analysize(code=code, userId=int(userId))
        return result

    @get('/trade/data', summary="查询自动化交易数据")
    async def getTradeData(self, request: Request) -> Result:
        result = Result()
        if checkout(request.headers.get('referered', '123')):
            result = await views.getTradeData()
        return result

    @post('/test')
    async def test(self, request: Request) -> Result:
        result = await views.auto_select_email()
        return result


@get("/r")
async def index(request: Request) -> Template:
    return Template("recommend.html", context={'prefix': PREFIX})


@get("/s")
async def recommend(request: Request) -> Template:
    return Template("index.html", context={'prefix': PREFIX})


@get("/stock")
async def stock_list(request: Request) -> Template:
    return Template("stock.html", context={'prefix': PREFIX})


@get("/etf")
async def etf_list(request: Request) -> Template:
    return Template("etf.html", context={'prefix': PREFIX})


@get("/topic")
async def topic_list(request: Request) -> Template:
    return Template("topic.html", context={'prefix': PREFIX})


@get("/h")
async def hold_list(request: Request) -> Template:
    return Template("hold.html", context={'prefix': PREFIX})


@get("/")
async def home(request: Request) -> Template:
    return Template("home.html", context={'prefix': PREFIX})


route_handlers = [Router(path=PREFIX, route_handlers=[StockController]), Router(path='', route_handlers=[home, index, recommend, stock_list, etf_list, topic_list, hold_list])]


@asynccontextmanager
async def lifespan(app: Litestar):
    await Database.init_db()    # 初始化数据库
    if RUN_ENV != 'dev':
        scheduler.add_job(getStock.updateEtfShares, 'cron', hour=8, minute=30, second=20, misfire_grace_time=10)    # 更新前一天的ETF份额
        scheduler.add_job(views.auto_analysize_etf, 'cron', hour=8, minute=58, second=0, misfire_grace_time=10)     # 开始分析 ETF
        # scheduler.add_job(views.auto_trade_etf, 'cron', hour=9, minute=35, second=0, misfire_grace_time=10)
        scheduler.add_job(getStock.checkTradeDay, 'cron', hour=9, minute=30, second=50, misfire_grace_time=10)      # 检查今天是否开市
        scheduler.add_job(getStock.setAllSHStock, 'cron', hour=12, minute=0, second=20, args=["8"], misfire_grace_time=10)     # 中午更新股票信息
        scheduler.add_job(getStock.setAllSZStock, 'cron', hour=12, minute=0, second=20, misfire_grace_time=10)                 # 中午更新股票信息
        scheduler.add_job(getStock.updateStockDetail, 'cron', hour=15, minute=31, second=20, misfire_grace_time=10)            # 收盘后更新股票数据
        scheduler.add_job(getStock.updateStockFund, 'cron', hour=15, minute=50, second=20, args=[1], misfire_grace_time=10)    # 更新主力流入数据
        scheduler.add_job(getStock.updateEtfDetail, 'cron', hour='9,10,11,13,14', minute=45, second=20, misfire_grace_time=10)            # 更新ETF数据
        scheduler.add_job(views.update_holding_capital, 'cron', hour='10,11,13,14,15,16', minute='1,31', second=20, misfire_grace_time=10)   # 处理交易记录
        scheduler.add_job(zip_file, 'cron', hour=17, minute=0, second=0, args=[[db_path], zip_path], misfire_grace_time=10)             # 备份数据库
        scheduler.add_job(getStock.clearStockData, 'cron', day_of_week='sat', hour=0, minute=0, second=20, misfire_grace_time=10)       # 删除数据
        scheduler.add_job(getStock.updateStockBanKuai, 'cron', day_of_week='sat', hour=0, minute=20, second=0, misfire_grace_time=10)   # 更新股票行业、概念等数据
    scheduler.start()   # 启动定时任务
    worker_task = asyncio.create_task(write_worker())
    await modify_sw()
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
