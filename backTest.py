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
    lookback = 6
    stockInfos = Stock.query(running=1).all()
    for s in stockInfos:
        try:
            stockList = Detail.query(code=s.code).order_by(desc(Detail.day)).limit(35).all()
            if len(stockList) < 23:
                continue
            stock_data = [StockDataList.from_orm_format(f).model_dump() for f in stockList]
            stock_data.reverse()
            for i in range(lookback, len(stock_data) - 1):
                sub = stock_data[: i + 1]
                res = analyze_buy_signal(sub, params)
                next_day_ret = (max(stock_data[i + 1]["current_price"], stock_data[i + 1]["max_price"]) / stock_data[i]["current_price"] - 1)
                res["next_day_return"] = next_day_ret
                if res["buy"]: logger.info(f"{s.code} - {s.name} - {res['day']} - {res['buy']} - {res['score']} - {next_day_ret >= 0.01} - {res['reasons']}")
                results.append(res)
        except:
            logger.error(f"{s.code} - {s.name}")
            # logger.error(traceback.format_exc())

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
    "qrr_strong": [1.1, 1.2, 1.3],
    "diff_delta": [0.01, 0.005, 0.015],
    "trix_delta_min": [0.001, 0.002, 0.003],
    "down_price_pct": [0.98, 0.97, 0.96],
    "too_hot": [0.045, 0.05, 0.055, 0.06],
    "min_score": [5, 6]
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
    logger.info(f"{i:02d}. 命中率 {s['hit_rate']:.2%}, 平均收益 {s['avg_return']:.2%}, 信号数 {s['signals']}, min_score={s['min_score']}, too_hot={s['too_hot']}, down_price_pct={s['down_price_pct']}, trix_delta_min={s['trix_delta_min']}, vol3_vs_vol5_ratio={s['vol3_vs_vol5_ratio']}, diff_delta={s['diff_delta']}, qrr_strong={s['qrr_strong']}")
