#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

import asyncio
from typing import Iterable, Any
from contextlib import asynccontextmanager
from sqlalchemy import Column, Integer, Float, String, Text, ForeignKey, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import and_
from sqlalchemy import func, select, delete
from datetime import datetime
from settings import DB_URL, DB_POOL_SIZE
from utils.writer_queue import writer_queue

Base = declarative_base()


async def write_worker():
    while True:
        writer, future = await writer_queue.get()
        try:
            result = await writer()
            if not future.done():
                future.set_result(result)
        except Exception as e:
            if not future.done():
                future.set_exception(e)
        finally:
            writer_queue.task_done()


class Database:
    engine = create_async_engine(DB_URL, echo=False, pool_size=DB_POOL_SIZE, max_overflow=DB_POOL_SIZE * 2, pool_timeout=30, pool_recycle=3600, pool_pre_ping=True)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    @classmethod
    async def get_session(cls) -> AsyncSession:
        return cls.session_factory()

    @classmethod
    async def init_db(cls):
        async with cls.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @classmethod
    async def dispose(cls):
        await cls.engine.dispose()


class DBExecutor:
    @staticmethod
    @asynccontextmanager
    async def session_scope():
        session: AsyncSession = await Database.get_session()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


class BaseQueryBuilder:
    def __init__(self, model):
        self.model = model
        self._select_columns = None
        self._conditions = []
        self._group_by = []
        self._order_by = []
        self._limit = None
        self._offset = None
        self._with_count = False

    # 查询指定的字段
    def select(self, *columns: str):
        self._select_columns = [getattr(self.model, c) for c in columns]
        return self

    # where 条件
    def equal(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) == v)
        return self

    def not_equal(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) != v)
        return self

    def like(self, **kwargs):
        for k, v in kwargs.items():
            if v:
                self._conditions.append(getattr(self.model, k).like(f"%{v}%"))
        return self

    def greater_equal(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) >= v)
        return self

    def greater(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) > v)
        return self

    def less_equal(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) <= v)
        return self

    def less(self, **kwargs):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k) < v)
        return self

    def isin(self, **kwargs: dict[str, Iterable[Any]]):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k).in_(v))
        return self

    def notin(self, **kwargs: dict[str, Iterable[Any]]):
        for k, v in kwargs.items():
            self._conditions.append(getattr(self.model, k).notin_(v))
        return self

    def is_null(self, *columns: str):
        for c in columns:
            self._conditions.append(getattr(self.model, c).is_(None))
        return self

    def is_not_null(self, *columns: str):
        for c in columns:
            self._conditions.append(getattr(self.model, c).isnot(None))
        return self

    # group / order / limit
    def group_by(self, *columns: str, with_count=True):
        self._group_by = [getattr(self.model, c) for c in columns]
        self._with_count = with_count
        return self

    def order_by(self, *clauses):
        self._order_by.extend(clauses)
        return self

    def order_by_key(self, model, sort: str):
        order_type = sort.startswith("-")
        key = sort.lstrip("+-")
        col = model.__sortable__.get(key.strip())
        expr = col.desc() if order_type else col.asc()
        self._order_by.append(expr)
        return self

    def limit(self, limit: int):
        self._limit = limit
        return self

    def offset(self, offset: int):
        self._offset = offset
        return self

    # build select
    def _build_select(self):
        if self._select_columns:
            columns = list(self._select_columns)
        else:
            columns = [self.model]

        if self._with_count:
            columns.append(func.count("*").label("count"))

        stmt = select(*columns)

        if self._conditions:
            stmt = stmt.where(and_(*self._conditions))

        if self._group_by:
            stmt = stmt.group_by(*self._group_by)

        if self._order_by:
            stmt = stmt.order_by(*self._order_by)

        if self._limit is not None:
            stmt = stmt.limit(self._limit)
        if self._offset is not None:
            stmt = stmt.offset(self._offset)

        return stmt

    # 执行（async）
    async def all(self):
        async with DBExecutor.session_scope() as session:
            stmt = self._build_select()
            result = await session.execute(stmt)
            return result.scalars().all() if self._select_columns is None else result.all()

    async def first(self):
        async with DBExecutor.session_scope() as session:
            stmt = self._build_select()
            result = await session.execute(stmt)
            row = result.first()
            return row[0] if row else None

    async def one(self):
        async with DBExecutor.session_scope() as session:
            stmt = self._build_select()
            result = await session.execute(stmt)
            return result.scalar_one()

    async def count(self) -> int:
        base_stmt = select(self.model)
        if self._conditions:
            base_stmt = base_stmt.where(*self._conditions)
        if self._group_by:
            base_stmt = base_stmt.group_by(*self._group_by)
        stmt = select(func.count()).select_from(base_stmt.subquery())
        async with DBExecutor.session_scope() as session:
            result = await session.execute(stmt)
            return result.scalar_one()

    async def delete(self):
        async with DBExecutor.session_scope() as session:
            stmt = delete(self.model)
            if self._conditions:
                stmt = stmt.where(and_(*self._conditions))
            result = await session.execute(stmt)
            return result.rowcount


class CRUDBase:
    @classmethod
    async def create2return(cls, **kwargs):
        async with DBExecutor.session_scope() as session:
            instance = cls(**kwargs)
            session.add(instance)
            await session.flush()
            return instance

    @classmethod
    async def create(cls, **kwargs):
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async def _write():
            async with DBExecutor.session_scope() as session:
                instance = cls(**kwargs)
                session.add(instance)
                await session.flush()
                return instance
        await writer_queue.put((_write, future))
        return await future

    @classmethod
    async def get(cls, value):
        """
        user = await User.get("cat001")
        """
        async with DBExecutor.session_scope() as session:
            return await session.get(cls, value)

    @classmethod
    async def get_one(cls, value):
        """
        If not existed, raise NoResultFound
        user = await User.get_one("cat001")
        """
        async with DBExecutor.session_scope() as session:
            return await session.get_one(cls, value)

    @classmethod
    def query(cls) -> BaseQueryBuilder:
        """
        users = await User.query().equal(name="Documents", is_delete=0).all()
        rows = await User.query().select("id", "name").equal(is_delete=0).all()
        rows = await User.query().select("id", "name").equal(is_delete=0).group_by("id", "name", with_count=True).all()
        count = await User.query().equal(status=0).greater(id=10).delete()
        """
        return BaseQueryBuilder(cls)

    @classmethod
    async def update2return(cls, pk, **kwargs):
        """
        await User.update(user_id, name="New Name", is_backup=1)
        """
        async with DBExecutor.session_scope() as session:
            instance = await session.get(cls, pk)
            if not instance:
                return None
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await session.flush()
            return instance

    @classmethod
    async def update(cls, pk, **kwargs):
        """
        await User.update(user_id, name="New Name", is_backup=1)
        """
        loop = asyncio.get_running_loop()
        future = loop.create_future()

        async def _write():
            async with DBExecutor.session_scope() as session:
                instance = await session.get(cls, pk)
                if not instance:
                    return None
                for key, value in kwargs.items():
                    setattr(instance, key, value)
                await session.flush()
                return instance
        await writer_queue.put((_write, future))
        return await future


class Stock(Base, CRUDBase):
    __tablename__ = 'stock'

    code = Column(String(8), primary_key=True, comment="股票代码")
    name = Column(String(8), nullable=False, comment="股票名称")
    running = Column(Integer, default=1, nullable=False, comment="0-不获取数据，1-获取数据")
    filter = Column(String(16), nullable=True, comment="标签")
    region = Column(String(16), nullable=True, comment="地域")
    industry = Column(String(32), nullable=True, comment="行业")
    concept = Column(String(255), nullable=True, comment="概念")
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Detail(Base, CRUDBase):
    __tablename__ = 'detail'
    __table_args__ = (
        PrimaryKeyConstraint('code', 'day'),
        Index('idx_code', 'code'),
        Index('idx_day', 'day')
    )

    code = Column(String(8), ForeignKey('stock.code', ondelete="CASCADE"), nullable=False, comment="股票代码")
    day = Column(String(8), nullable=False, comment="日期")
    name = Column(String(8), nullable=False, comment="股票名称")
    current_price = Column(Float, nullable=False, comment="当前价")
    open_price = Column(Float, nullable=False, comment="开盘价")
    last_price = Column(Float, nullable=False, comment="前一天收盘价")
    max_price = Column(Float, nullable=False, comment="最高价")
    min_price = Column(Float, nullable=False, comment="最低价")
    volumn = Column(Integer, nullable=False, comment="成交量（手）")
    ma_five = Column(Float, nullable=True, comment="5日均线")
    ma_ten = Column(Float, nullable=True, comment="10日均线")
    ma_twenty = Column(Float, nullable=True, comment="20日均线")
    qrr = Column(Float, nullable=True, comment="量比")
    emas = Column(Float, nullable=True, comment="MACD ema12")
    emal = Column(Float, nullable=True, comment="MACD ema26")
    dea = Column(Float, nullable=True, comment="MACD dea")
    kdjk = Column(Float, nullable=True, comment="KDJ k")
    kdjd = Column(Float, nullable=True, comment="KDJ d")
    kdjj = Column(Float, nullable=True, comment="KDJ j")
    trix_ema_one = Column(Float, nullable=True, comment="TRIX ema1")
    trix_ema_two = Column(Float, nullable=True, comment="TRIX ema2")
    trix_ema_three = Column(Float, nullable=True, comment="TRIX ema3")
    trix = Column(Float, nullable=True, comment="TRIX")
    trma = Column(Float, nullable=True, comment="MA_TRIX")
    turnover_rate = Column(Float, nullable=True, comment="换手率")
    fund = Column(Float, nullable=True, comment="主力资金")
    boll_up = Column(Float, nullable=True, comment="Boll up")
    boll_low = Column(Float, nullable=True, comment="Boll low")
    create_time = Column(DateTime, default=datetime.now)

    __sortable__ = {
        'volumn': volumn, 'qrr': qrr, 'turnover_rate': turnover_rate, 'fund': fund, 'create_time': create_time
    }


class Recommend(Base, CRUDBase):
    __tablename__ = 'recommend'
    __table_args__ = (
        Index('idx_recommend_code', 'code'),
        {'sqlite_autoincrement': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(8), nullable=False, comment="股票代码")
    name = Column(String(8), nullable=False, comment="股票名称")
    price = Column(Float, nullable=False, comment="推荐时的价格")
    last_one_price = Column(Float, nullable=True, comment="1天后的收盘价")
    last_one_high = Column(Float, nullable=True, comment="1天后的最高")
    last_one_low = Column(Float, nullable=True, comment="1天后的最低")
    last_two_price = Column(Float, nullable=True, comment="2天后的收盘价")
    last_two_high = Column(Float, nullable=True, comment="2天后的最高")
    last_two_low = Column(Float, nullable=True, comment="2天后的最低")
    last_three_price = Column(Float, nullable=True, comment="3天后的收盘价")
    last_three_high = Column(Float, nullable=True, comment="3天后的最高")
    last_three_low = Column(Float, nullable=True, comment="3天后的最低")
    last_four_price = Column(Float, nullable=True, comment="4天后的收盘价")
    last_four_high = Column(Float, nullable=True, comment="4天后的最高")
    last_four_low = Column(Float, nullable=True, comment="4天后的最低")
    last_five_price = Column(Float, nullable=True, comment="5天后的收盘价")
    last_five_high = Column(Float, nullable=True, comment="5天后的最高")
    last_five_low = Column(Float, nullable=True, comment="5天后的最低")
    content = Column(Text, nullable=True, comment="推荐 reason")
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MinuteK(Base, CRUDBase):
    __tablename__ = 'minutek'
    __table_args__ = (
        Index('idx_minutek_code', 'code'),
        {'sqlite_autoincrement': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(8), ForeignKey('stock.code', ondelete="CASCADE"), nullable=False, comment="股票代码")
    day = Column(String(8), nullable=False, comment="日期")
    minute = Column(String(6), nullable=False, comment="分钟")
    price = Column(Float, nullable=False, comment="价格")
    volume = Column(Integer, nullable=False, comment="成交量（手）")
    create_time = Column(DateTime, default=datetime.now)


class Tools(Base, CRUDBase):
    __tablename__ = 'tools'

    key = Column(String(8), primary_key=True, comment="键")
    value = Column(String(255), nullable=False, comment="值")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
