#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari

from sqlalchemy import create_engine, Column, BigInteger, Integer, Float, String, ForeignKey, DateTime, Index, PrimaryKeyConstraint
from sqlalchemy.orm import relationship, scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import text, desc
from typing import List
from datetime import datetime
from settings import DB_URL, DB_POOL_SIZE

Base = declarative_base()


class Database:
    engine = create_engine(DB_URL, echo=False, pool_size=DB_POOL_SIZE, max_overflow=DB_POOL_SIZE * 2, pool_timeout=30, pool_recycle=3600, pool_pre_ping=True, pool_use_lifo=True)
    session_factory = sessionmaker(bind=engine)
    session = scoped_session(session_factory)

    @classmethod
    def get_session(cls):
        return cls.session()

    @classmethod
    def close_session(cls):
        cls.session.remove()

    @classmethod
    def init_db(cls):
        Base.metadata.create_all(bind=cls.engine)


class CRUDBase:
    @classmethod
    def create(cls, **kwargs):
        session = Database.get_session()
        try:
            instance = cls(**kwargs)
            session.add(instance)
            session.commit()
            session.refresh(instance)
            return instance
        except:
            session.rollback()
            raise
        finally:
            Database.close_session()

    @classmethod
    def get(cls, value):
        """
        user = User.get("cat001")
        """
        session = Database.get_session()
        try:
            return session.get(cls, value)
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def get_one(cls, value):
        """
        If not existed, raise NoResultFound
        user = User.get_one("cat001")
        """
        session = Database.get_session()
        try:
            return session.get_one(cls, value)
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def all(cls):
        """
        Query all datas.
        users = User.all()
        """
        session = Database.get_session()
        try:
            return session.query(cls)
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def query(cls, **kwargs):
        """
        users = User.query(name="Documents", is_delete=0).all()
        """
        session = Database.get_session()
        try:
            return session.query(cls).filter_by(**kwargs)
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def query_fields(cls, columns: list, **kwargs):
        """
        users = User.query(columns=['id', 'name'], name="Documents", is_delete=0).all()
        """
        session = Database.get_session()
        try:
            column_attrs = [getattr(cls, col) for col in columns]
            query = session.query(*column_attrs)
            return query.filter_by(**kwargs)
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def filter_condition(cls, equal_condition: dict = None, not_equal_condition: dict = None, like_condition: dict = None):
        """
        users = User.filter_condition(equal_condition={'status': 1, 'name': '222'}, not_equal_condition={'description': 'temp'})
        SELECT * FROM catuseralog WHERE status = 1 AND name = '222' AND description != 'temp';
        """
        session = Database.get_session()
        try:
            query = session.query(cls)
            if equal_condition:
                for column, value in equal_condition.items():
                    query = query.filter(getattr(cls, column) == value)
            if like_condition:
                for column, value in like_condition.items():
                    query = query.filter(getattr(cls, column).like(f'%{value}%'))
            if not_equal_condition:
                for column, value in not_equal_condition.items():
                    query = query.filter(getattr(cls, column) != value)
            return query
        except:
            raise
        finally:
            Database.close_session()

    @classmethod
    def update(cls, instance, **kwargs):
        """
        updated_user = User.update(user, name="New Name", is_backup=1)
        """
        session = Database.get_session()
        try:
            if instance in session:
                current_instance = instance
            else:
                current_instance = session.merge(instance, load=False)
            for key, value in kwargs.items():
                setattr(current_instance, key, value)
            session.commit()
            session.refresh(current_instance)
            return current_instance
        except:
            session.rollback()
            raise
        finally:
            Database.close_session()

    @classmethod
    def delete(cls, instance):
        """
        User.delete(user)
        """
        session = Database.get_session()
        try:
            current_instance = session.get(cls, instance.id)
            session.delete(current_instance)
            session.commit()
        except:
            session.rollback()
            raise
        finally:
            Database.close_session()


class CRUDBaseVolumn(CRUDBase):
    @classmethod
    def queryByCodeAndDate(cls, code: List, date: str):
        session = Database.get_session()
        try:
            return session.query(cls).filter_by(getattr(cls, 'code').in_(code), getattr(cls, 'date') == date).order_by(getattr(cls, 'code'), desc(getattr(cls, 'create_time')))
        except:
            raise
        finally:
            Database.close_session()


class Stock(Base, CRUDBase):
    __tablename__ = 'stock'

    code = Column(String(8), primary_key=True, comment="股票代码")
    name = Column(String(8), nullable=False, comment="股票名称")
    running = Column(Integer, default=1, nullable=False, comment="0-不获取数据，1-获取数据")
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
    volumn = Column(Integer, nullable=False, comment="成交量（股）")
    ma_three = Column(Float, nullable=True, comment="3日均线")
    ma_five = Column(Float, nullable=True, comment="5日均线")
    ma_ten = Column(Float, nullable=True, comment="10日均线")
    ma_twenty = Column(Float, nullable=True, comment="20日均线")
    qrr = Column(Float, nullable=True, comment="量比")
    create_time = Column(DateTime, default=datetime.now)


class Volumn(Base, CRUDBaseVolumn):
    __tablename__ = 'volumn'
    __table_args__ = (
        Index('idx_code_date_create_time_desc', 'code', 'date', 'create_time'),
        {'sqlite_autoincrement': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(8), ForeignKey('stock.code', ondelete="CASCADE"), nullable=False, comment="股票代码")
    date = Column(String(4), nullable=False, comment="时间")
    volumn = Column(Integer, nullable=False, comment="成交量（股）")
    create_time = Column(DateTime, default=datetime.now)


class Recommend(Base, CRUDBase):
    __tablename__ = 'recommend'
    __table_args__ = (
        Index('idx_recommend_code', 'code'),
        {'sqlite_autoincrement': True}
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(8), nullable=False, comment="股票代码")
    name = Column(String(8), nullable=False, comment="股票名称")
    type = Column(Integer, nullable=False, comment="类型, 0-短期, 1-长期")
    price = Column(Float, nullable=False, comment="推荐时的价格")
    last_one_price = Column(Float, nullable=True, comment="1天后的收盘价")
    last_two_price = Column(Float, nullable=True, comment="2天后的收盘价")
    rate = Column(Integer, nullable=True, comment="胜率, 0, 33, 67, 100")
    create_time = Column(DateTime, default=datetime.now)
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Tools(Base, CRUDBase):
    __tablename__ = 'tools'

    key = Column(String(8), primary_key=True, comment="键")
    value = Column(String(64), nullable=False, comment="值")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now)
