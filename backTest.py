#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: leeyoshinari
import json
import traceback
import statistics
import itertools
from sqlalchemy import desc, asc
from utils.metric import analyze_buy_signal
from utils.database import Database, Stock, Detail
from utils.model import StockDataList
from utils.logging import logger


Database.init_db()


def backtest(params):
    results = []
    lookback = 5
    stockInfos = Stock.query(running=1).all()
    for s in stockInfos:
        try:
            stockList = Detail.query(code=s.code).order_by(desc(Detail.day)).all()
            if len(stockList) < 5:
                continue
            stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
            stock_data.reverse()
            for i in range(1, len(stock_data) - lookback - 1):
                sub = stock_data[i: i + lookback]
                if ((sub[-1]['current_price'] - sub[-1]['last_price']) / sub[-1]['last_price'] * 100) > 9.95:
                    continue
                res = analyze_buy_signal(sub, params)
                next_day_ret = (max(stock_data[i + lookback]["current_price"], stock_data[i + lookback]["max_price"]) / stock_data[i + lookback - 1]["current_price"] - 1)
                res["next_day_return"] = next_day_ret
                if res["buy"]: logger.info(f"{s.code} - {s.name} - {res['day']} - {res['buy']} - {res['score']} - {next_day_ret >= 0.01} - {res['reasons']}")
                results.append(res)
        except:
            logger.error(f"{s.code} - {s.name}")
            logger.error(traceback.format_exc())

    buy_results = [r for r in results if r["buy"]]

    if not buy_results:
        return {
            "signals": 0,
            "hit_rate": 0,
            "avg_return": 0,
            "max_drawdown": 0,
            "avg_conf": 0,
        }
    hit_rate = sum(1 for r in buy_results if r["next_day_return"] >= 0.01) / len(buy_results)
    avg_return = statistics.mean([r["next_day_return"] for r in buy_results])
    max_drawdown = min([r["next_day_return"] for r in buy_results])

    return {
        "signals": len(buy_results),
        "hit_rate": hit_rate,
        "avg_return": avg_return,
        "max_drawdown": max_drawdown
    }


param_grid = {
    'min_days_for_trend': [4, 3],
    'qrr_threshold': [1.5, 1.4, 1.3],
    'min_total_rise_pct': [0.02],
    'macd_gold_cross_days': [0],
    'trix_upward_threshold': [0.0],
    'trix_slow_increase_pct': [0.05],
    'upper_shadow_ratio': [0.3],
    'kdj_gold_cross_days': [0, 1],
    'kdj_strong_zone': [50.0],
    'kdj_overbought_threshold': [80.0],
    'kdj_overbought_max_days': [3]
}

# 笛卡尔积生成所有参数组合
keys = list(param_grid.keys())
param_combinations = [dict(zip(keys, v)) for v in itertools.product(*param_grid.values())]

summary = []
logger.info("开始参数回测，共 %d 组参数..." % len(param_combinations))
for idx, params in enumerate(param_combinations, 1):
    stats = backtest(params)
    record = {**params, **stats}
    summary.append(record)
    logger.info(f"{idx:03d}/{len(param_combinations)} | signals={stats['signals']:3d} | hit={stats['hit_rate']:.2%} | avg={stats['avg_return']:.2%} | max_drawDown={stats['max_drawdown']:.2%} - {json.dumps(params)}")


# 排序规则：优先命中率、次优平均收益
summary.sort(key=lambda x: x["hit_rate"], reverse=True)
logger.info("\n===== 最优参数组合前10名 =====")
for i, s in enumerate(summary[:10], 1):
    logger.info(f"{i:02d}. 命中率 {s['hit_rate']:.2%}, 平均收益 {s['avg_return']:.2%}, 信号数 {s['signals']}, params: {json.dumps(s)}")
