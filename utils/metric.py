#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Author: leeyoshinari

import math
import logging
from typing import Any, Optional
from dataclasses import dataclass


logger = logging.getLogger(__name__)


def bollinger_bands(prices, middle, n=20, k=2):
    if len(prices) < n:
        return middle, middle
    window = prices[-n:]
    data_len = len(window)
    variance = sum((p - middle) ** 2 for p in window) / data_len
    std = math.sqrt(variance)
    up = middle + k * std
    dn = middle - k * std
    return up, dn


@dataclass
class StrategyConfig:
    # ---------- 买入: 硬性门槛 ----------
    min_gain: float = 5.0             # 当日涨幅 ≥ 5%
    vol_ma_period: int = 20           # 均量回看周期
    require_diff_above_zero: bool = False  # ★问题2: True=严格模式(会漏底部反转股)

    # ---------- 买入: 量能分档 ----------
    # A档: 当日量 ≥ A×20日均量
    # B档: 当日量 ≥ B×20日均量 或 量比≥b_qrr
    # C档: 换手率≥c_turnover% 且 突破前20日最高收盘×(1+c_break_pct)
    vol_tier_a: float = 7
    vol_tier_b: float = 5
    # vol_tier_c_turnover: float = 8.0
    # vol_tier_c_break_pct: float = 0.03

    # ---------- 买入: 尾盘确认 ----------
    close_position_min: float = 0.7  # (收-低)/(高-低) ≥ 0.60
    body_ratio_min: float = 0.35      # (收-开)/(高-低) ≥ 0.35
    hold_above_last: float = 0.99     # 收盘 ≥ 昨收×0.99

    # ---------- 买入: 其他 ----------
    min_score: int = 85               # 综合评分门槛(满分140)
    macd_cross_lookback: int = 5      # 近N日内出现新金叉才加满分
    pre_heat_days: int = 5            # 启动前N日若连续过热则降级
    pre_heat_turnover: float = 8.0    # 过热换手率阈值
    buy_cooldown_days: int = 3        # 连续买入冷静期

    # ---------- 买入: T+1确认 ----------
    confirm_ratio: float = 0.97       # T+1收盘价不能比信号日跌太多
    confirm_max_drop: float = -5.0    # T+1最大跌幅

    # ---------- 买入: 资金分配 ----------
    amount_level_1: float = 40000.0
    amount_level_2: float = 20000.0
    amount_level_3: float = 5000.0
    score_level_1: int = 100
    score_level_2: int = 85
    score_level_3: int = 70

    # ---------- 卖出规则 ----------
    hard_stop_pct: float = 0.07       # S1 硬止损 -7%
    profit_lock_threshold: float = 0.03   # S2 浮盈>8%后启用移动止盈
    trail_stop_pct: float = 0.03      # S2 从最高收盘回撤3%止盈
    big_vol_ratio: float = 1.5        # S4 巨量阈值(×20日均量)
    max_hold_days: int = 6            # S8 最大持仓天数
    time_stop_min_profit: float = 0.03  # S8 到期最低浮盈要求
    grace_period_days: int = 2        # 卖出保护期，防止频繁交易

    # ---------- 回测 ----------
    cost_rate: float = 1 / 10000          # 股票交易佣金，默认万分之一，不免5
    stamp_duty: float = 5 / 10000         # 印花税，默认万分之5


def calc_vol_ma(data: list[dict], idx: int, period: int):
    """计算第idx天之前period个交易日的平均成交量"""
    start = max(0, idx - period)
    end = idx
    count = end - start
    if count < 5:
        return None
    total = 0
    for i in range(start, end):
        total += data[i]['volume']
    return total / count


def calc_shares(price: float, target_amount: float):
    """计算买入股数（100整数倍，金额接近目标）"""
    if price <= 0 or target_amount <= 0:
        return 0
    raw_shares = target_amount / price
    shares = round(raw_shares / 100) * 100
    if shares < 100:
        shares = 0
    return shares


def get_score_level(score, cfg):
    """根据分数返回等级和目标金额"""
    if score >= cfg.score_level_1:
        return '极强', cfg.amount_level_1
    elif score >= cfg.score_level_2:
        return '强', cfg.amount_level_2
    elif score >= cfg.score_level_3:
        return '中', cfg.amount_level_3
    else:
        return '弱', 0


def detect_buy(data: list[dict], cfg: StrategyConfig = None, positions: list[dict] = None, isFund: bool = True) -> Optional[dict[str, Any]]:
    """
    检测买入信号 —— 检查data的最后一天是否触发买入，（注意：仅产生信号，需T+1确认后才买入）

    回测模式: 逐日调用 detect_buy(data[:i+1], cfg, positions)
    实时模式: 传入最近40天数据 detect_buy(last_40_days, cfg, positions)

    参数:
        data:      list[dict] - K线数据（最后一天为待判断日）
        cfg:       StrategyConfig - 策略参数
        isFund:    bool - 是否判断主力资金，第一次筛选无法获取主力资金数据
        positions: list[dict] - 当前持仓 [{'day':..., 'price':..., 'shares':...}]

    返回:
        None 或 dict{'day','price','score','reasons','shares'}
    """
    if cfg is None:
        cfg = StrategyConfig()

    if positions is None:
        positions = []

    n = len(data)
    if n < cfg.vol_ma_period + 5:
        return None

    # ---- 持仓冷却检查：最近N天内买入过则不再买入 ----
    if positions:
        last_n_days = []
        for i in range(max(0, n - cfg.buy_cooldown_days), n):
            last_n_days.append(data[i]['day'])
        for pos in positions:
            if pos['day'] in last_n_days:
                return None

    d = data[-1]
    prev = data[-2]
    gain = (d['current_price'] - d['last_price']) / d['last_price'] * 100.0
    reasons = []

    # ===== 硬性条件 =====
    # 涨幅
    if gain < cfg.min_gain:
        return None

    # 主力资金
    if isFund and d['fund'] < 100:
        return None

    # 当前价必须大于开盘价，避免高开低走
    if d['current_price'] <= d['open_price']:
        return None

    # 一字板，成交量和量比没意义
    if d['min_price'] == d['max_price']:
        return None

    # 站上均线
    if d['current_price'] <= d['ma_five']:
        return None
    if d['current_price'] <= d['ma_ten']:
        return None
    if d['current_price'] <= d['ma_twenty']:
        return None

    # MACD金叉
    if d['diff'] <= d['dea']:
        return None
    if cfg.require_diff_above_zero and d['diff'] <= 0:
        return None

    # 突破前高
    closes = []
    for k in range(n - 1):
        closes.append(data[k]['current_price'])
    if len(closes) < 10:
        return None

    max_close_10 = max(closes[-10:])
    if len(closes) >= 20:
        max_close_20 = max(closes[-20:])
    else:
        max_close_20 = max(closes)

    # 收盘突破前10日最高收盘价(或前20日的97%)
    broke_10 = d['current_price'] > max_close_10
    broke_20 = d['current_price'] > max_close_20 * 0.97
    if not broke_10 and not broke_20:
        return None

    # 量能
    vol_ma = calc_vol_ma(data, n - 1, cfg.vol_ma_period)
    if vol_ma is None or vol_ma <= 0:
        return None

    vol_ratio = d['volume'] / vol_ma
    qrr = d['qrr']
    turnover = d['turnover_rate']

    vol_tier = ''
    if vol_ratio >= cfg.vol_tier_a:
        vol_tier = 'A'
    elif vol_ratio >= cfg.vol_tier_b:
        vol_tier = 'B'
    # elif turnover >= cfg.vol_tier_c_turnover and d['current_price'] > max_close_20 * (1 + cfg.vol_tier_c_break_pct):
    #     vol_tier = 'C'

    if vol_tier == '':
        return None

    # 尾盘确认
    day_range = d['max_price'] - d['min_price']
    if day_range > 0:
        close_position = (d['current_price'] - d['min_price']) / day_range
        body_ratio = (d['current_price'] - d['open_price']) / day_range
    else:
        return None

    if close_position < cfg.close_position_min:
        return None
    if gain < 9.0 and body_ratio < cfg.body_ratio_min:
        return None
    if d['current_price'] < d['last_price'] * cfg.hold_above_last:
        return None

    # ===== 评分（满分116） =====
    score = 0

    # 1) 涨幅 (max 20)
    if gain >= 9.5:
        score += 20
        reasons.append(f'涨幅{gain:.1f}% ≥ 9.5% (+20)')
    elif gain >= 7.0:
        score += 15
        reasons.append(f'涨幅{gain:.1f}% ≥ 7% (+15)')
    else:
        score += 10
        reasons.append(f'涨幅{gain:.1f}% ≥ 5% (+10)')

    # 2) 量能 (max 25)
    if vol_tier == 'A':
        score += 25
        reasons.append(f'成交量 {vol_ratio:.1f} 倍均量 (+25)')
    elif vol_tier == 'B':
        score += 20
        reasons.append(f'成交量 {vol_ratio:.1f} 倍/量比 {qrr:.1f} (+20)')
    else:
        score += 10
        reasons.append(f'换手 {turnover:.1f}%+ 突破前高 (+10)')

    # 3) 突破前高 (max 15)
    if broke_10:
        score += 15
        reasons.append('突破前10日高点 (+15)')
    else:
        score += 8
        reasons.append('突破前20日高点 (+8)')

    # 4) 均线多头（实际判断） (max 15)
    if d['ma_five'] > d['ma_ten'] and d['ma_ten'] > d['ma_twenty']:
        score += 15
        reasons.append('均线多头排列 MA5>MA10>MA20 (+15)')
    elif d['ma_five'] > d['ma_ten']:
        score += 10
        reasons.append('MA5>MA10 (+10)')
    else:
        score += 5
        reasons.append('站上均线 (+5)')

    # 5) 布林上轨 (max 12)
    boll_up = d['boll_up']
    if boll_up > 0:
        if d['current_price'] >= boll_up:
            score += 12
            reasons.append('突破布林上轨 (+12)')
        elif d['current_price'] >= boll_up * 0.97:
            score += 6
            reasons.append('接近布林上轨 (+6)')

    # 6) MACD (max 14)
    new_cross = False
    lb = min(cfg.macd_cross_lookback, n - 1)
    for k in range(max(1, n - lb), n):
        if data[k]['diff'] > data[k]['dea'] and data[k - 1]['diff'] <= data[k - 1]['dea']:
            new_cross = True
            break

    if new_cross:
        score += 10
        reasons.append('近5日新金叉 (+10)')
    else:
        score += 6
        reasons.append('MACD金叉持续 (+6)')

    if d['diff'] > 0:
        score += 4
        reasons.append('DIFF>0 (+4)')
    elif d['diff'] > prev['diff']:
        score += 2
        reasons.append('DIFF拐头 (+2)')

    # 7) KDJ (max 5)
    j_val = d['j']
    if j_val >= 70:
        score += 5
        reasons.append(f'J值 = {j_val:.0f} ≥ 70 (+5)')

    # 8) 前期蓄势/过热 (max +10, min -15)
    pre_start = max(0, n - 1 - cfg.pre_heat_days)
    pre_days = data[pre_start: n - 1]
    if len(pre_days) >= 3:
        hot_count = 0
        total_tr = 0.0
        for x in pre_days:
            tr = x['turnover_rate']
            total_tr += tr
            if tr > cfg.pre_heat_turnover:
                hot_count += 1
        if hot_count >= 3:
            score -= 15
            reasons.append('⚠前期过热 (-15)')
        else:
            avg_tr = total_tr / len(pre_days)
            if avg_tr < 3.0:
                score += 10
                reasons.append('前期缩量蓄势 (+10)')

    # =====  分数门槛 + 分级  =====
    if score < cfg.min_score:
        return None

    level, target_amount = get_score_level(score, cfg)
    if target_amount <= 0:
        return None

    shares = calc_shares(d['current_price'], target_amount)
    if shares <= 0:
        return None

    return {
        'day': d['day'],
        'score': score,
        'level': level,
        'price': d['current_price'],
        'shares': shares,
        'actual_amount': round(d['current_price'] * shares, 2),
        'reasons': ', '.join(reasons)
    }


def check_confirmation(data: list[dict], cfg: StrategyConfig = None) -> tuple[bool, Any]:
    """
    检查data的最后一天是否确认买入信号

    参数:
        data: 完整K线数据
        cfg: 策略参数

    返回:
        (True, buy_price) - 确认，返回买入价
        (False, None) - 未确认
    """
    if cfg is None:
        cfg = StrategyConfig()

    signal_day = data[-2]
    confirm_day = data[-1]

    if confirm_day['fund'] < 100:
        return False, None

    # 条件1: T+1收盘价不能比信号日跌太多
    if confirm_day['current_price'] < signal_day['current_price'] * cfg.confirm_ratio:
        return False, None

    # 条件2: T+1收盘价不能跌破信号日最低价（不能跌回突破起点）
    if confirm_day['current_price'] < signal_day['min_price']:
        return False, None

    # 条件3: T+1不能暴跌
    t1_gain = (confirm_day['current_price'] - confirm_day['last_price']) / confirm_day['last_price'] * 100.0
    if t1_gain < cfg.confirm_max_drop:
        return False, None

    # 条件4: T+1必须可买入（不能是一字涨停无法成交）
    if confirm_day['max_price'] == confirm_day['min_price']:
        return False, None

    # T+1不能高开低走
    if confirm_day['current_price'] <= confirm_day['open_price']:
        return False, None

    return True, confirm_day['current_price']


def detect_sell(data: list[dict], pos: dict, cfg: StrategyConfig = None) -> Optional[dict[str, Any]]:
    """
    检测卖出信号 —— 检查data的最后一天是否触发卖出

    参数:
        data: list[dict] - K线数据
        pos:  dict - {'day':..., 'price':..., 'shares':...}
        cfg:  StrategyConfig

    返回:
        None 或 dict{'day','price','reason','hold_days','pnl_pct'}
    """
    if cfg is None:
        cfg = StrategyConfig()

    entry_price = pos['price']
    entry_day = pos['day']

    entry_idx = -1
    for i in range(len(data)):
        if data[i]['day'] == entry_day:
            entry_idx = i
            break

    if entry_idx < 0:
        return None
    # 买入日必须是最后一天之前（T+1）
    if entry_idx + 1 >= len(data):
        return None

    n = len(data)
    d = data[-1]
    prev = data[-2]
    price = d['current_price']
    pnl = (price - entry_price) / entry_price
    hold_days = n - entry_idx - 1

    # 是否在保护期内
    in_grace = hold_days <= cfg.grace_period_days

    # 买入后最高收盘
    max_close = entry_price
    for k in range(entry_idx + 1, n):
        if data[k]['current_price'] > max_close:
            max_close = data[k]['current_price']

    # 20日均量
    vol_ma = calc_vol_ma(data, n - 1, cfg.vol_ma_period)

    # ---- S1: 硬止损 ----
    if price <= entry_price * (1 - cfg.hard_stop_pct):
        return {
            'day': d['day'],
            'price': price,
            'reason': f'S1-硬止损: 亏 {round(pnl * 100, 2)}%',
            'hold_days': hold_days,
            'pnl_pct': round(pnl * 100, 2)
        }

    # ---- S2: 移动止盈 ----
    if not in_grace and pnl > cfg.profit_lock_threshold:
        trail_price = max_close * (1 - cfg.trail_stop_pct)
        if price <= trail_price:
            return {
                'day': d['day'],
                'price': price,
                'reason': f'S2-移动止盈: 从 {max_close:.2f} 回撤 ≥ {round(cfg.trail_stop_pct * 100, 2)}%',
                'hold_days': hold_days,
                'pnl_pct': round(pnl * 100, 2)
            }

    # ---- S4: 巨量滞涨/大阴 ----
    if not in_grace and vol_ma is not None and vol_ma > 0:
        day_vol_ratio = d['volume'] / vol_ma
        # day_vol_ratio = d['qrr']
        day_gain = (d['current_price'] - d['last_price']) / d['last_price'] * 100.0
        if day_vol_ratio >= cfg.big_vol_ratio:
            if price < d['open_price']:
                return {
                    'day': d['day'],
                    'price': price,
                    'reason': f'S4-巨量大阴: 量 {day_vol_ratio:.2f} 倍',
                    'hold_days': hold_days,
                    'pnl_pct': round(pnl * 100, 2)
                }
            if day_gain < 2.0:
                return {
                    'day': d['day'],
                    'price': price,
                    'reason': f'S4-巨量滞涨: 量 {day_vol_ratio:.2f} 倍涨 {day_gain:.2f}%',
                    'hold_days': hold_days,
                    'pnl_pct': round(pnl * 100, 2)
                }

    # ---- S5: MACD死叉（盈利时） ----
    if pnl > 0:
        if d['diff'] < d['dea'] and prev['diff'] >= prev['dea']:
            return {
                'day': d['day'],
                'price': price,
                'reason': f'S5-MACD死叉: 浮盈 {round(pnl * 100, 2)}%',
                'hold_days': hold_days,
                'pnl_pct': round(pnl * 100, 2)
            }

    # ---- S7: 时间止损 ----
    if hold_days >= cfg.max_hold_days and pnl < cfg.time_stop_min_profit:
        return {
            'day': d['day'],
            'price': price,
            'reason': f'S7-时间止损: {hold_days}天盈 {round(pnl * 100, 2)}%',
            'hold_days': hold_days,
            'pnl_pct': round(pnl * 100, 2)
        }

    return None


def backtest_single_stock(data: list[dict], cfg: StrategyConfig = None):
    """
    对单只股票回测，支持多次买入卖出

    参数:
        data: list[dict] - 完整K线数据
        cfg:  StrategyConfig

    返回:
        list[dict] - 已完成的交易记录
    """
    if cfg is None:
        cfg = StrategyConfig()

    trades = []
    position = None
    pending_signal = None
    pending_idx = -1

    for i in range(cfg.vol_ma_period + 5, len(data)):
        sub_data = data[:i + 1]
        if position is not None:
            # ---- 持仓中：检查是否卖出 ----
            sell = detect_sell(sub_data, position, cfg)
            if sell is not None:
                # 计算收益
                cost = max((position['price'] + sell['price']) * position['shares'] * cfg.cost_rate, 10) + sell['price'] * position['shares'] * cfg.stamp_duty
                pnl_amount = (sell['price'] - position['price']) * position['shares'] - cost
                trades.append({
                    'buy_day': position['day'],
                    'buy_price': position['price'],
                    'shares': position['shares'],
                    'sell_day': sell['day'],
                    'sell_price': sell['price'],
                    'sell_reason': sell['reason'],
                    'hold_days': sell['hold_days'],
                    'pnl_pct': sell['pnl_pct'],
                    'pnl_amount': round(pnl_amount, 2),
                    'buy_score': position.get('score', 0),
                    'buy_level': position.get('level', '')
                })
                position = None
                pending_signal = None
        else:
            # ---- 空仓：检查是否有待确认信号 ----
            if pending_signal is not None and pending_idx >= 0:
                confirmed, buy_price = check_confirmation(sub_data, cfg)
                if confirmed and buy_price is not None:
                    # 确认成功，今天买入
                    position = {
                        'day': pending_signal['day'],  # data[i]['day'],
                        'price': buy_price,
                        'shares': pending_signal['shares'],
                        'score': pending_signal['score'],
                        'level': pending_signal['level'],
                        'actual_amount': pending_signal['actual_amount'],
                        'reasons': pending_signal['reasons']
                    }
                pending_signal = None
                pending_idx = -1
                if position is not None:
                    continue
            # ---- 空仓：检查是否买入 ----
            positions_for_check = []
            signal = detect_buy(sub_data, cfg, positions_for_check)
            if signal is not None:
                pending_signal = signal
                pending_idx = i

    return trades


def backtest_all(all_data: dict, cfg: StrategyConfig = None):
    """
    对所有股票回测

    参数:
        all_data: dict - {code: {'name': str, 'data': list[dict]}}
        cfg: StrategyConfig

    返回:
        list[dict] - 所有交易记录（含code和name）
    """
    if cfg is None:
        cfg = StrategyConfig()

    all_trades = []
    for code in sorted(all_data.keys()):
        stock_info = all_data[code]
        name = stock_info.get('name', code)
        data = stock_info['data']
        trades = backtest_single_stock(data, cfg)
        for t in trades:
            t['code'] = code
            t['name'] = name
        all_trades.extend(trades)

    return all_trades


def realtime_check(code: str, name: str, data: list[dict], positions: list[dict], cfg: StrategyConfig = None) -> Optional[dict[str, Any]]:
    """
    实时决策：传入最近40天数据，判断今天是否买入或卖出

    参数:
        code:      str - 股票代码
        name:      str - 股票名称
        data:      list[dict] - 最近40天K线（含今天）
        positions: list[dict] - 该股票当前持仓 [{'day':..., 'price':..., 'shares':...}]
        cfg:       StrategyConfig

    返回:
        dict - {'action': 'buy'/'sell'/'hold', 'detail': ...}
    """
    if cfg is None:
        cfg = StrategyConfig()

    result = {'code': code, 'name': name, 'action': 'hold', 'detail': None}

    # 如果有持仓，先检查是否卖出; 无持仓，则检查是否买入
    if positions:
        pos = positions[0]
        sell = detect_sell(data, pos, cfg)
        if sell is not None:
            result['action'] = 'sell'
            result['detail'] = sell
        return result
    else:
        buy = detect_buy(data, cfg, positions)
        if buy is not None:
            result['action'] = 'buy'
            result['detail'] = buy
            return result
        return None


def calc_metrics(trades):
    """计算回测统计指标"""
    if not trades:
        return {
            'total_trades': 0,
            'win_count': 0,
            'loss_count': 0,
            'win_rate': 0.0,
            'total_pnl_pct': 0.0,
            'avg_pnl_pct': 0.0,
            'max_win_pct': 0.0,
            'max_loss_pct': 0.0,
            'profit_factor': 0.0,
            'avg_hold_days': 0.0
        }

    n = len(trades)
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]

    total_pnl = sum(t['pnl_pct'] for t in trades)
    gross_profit = sum(t['pnl_pct'] for t in wins) if wins else 0.0
    gross_loss = abs(sum(t['pnl_pct'] for t in losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    return {
        'total_trades': n,
        'win_count': len(wins),
        'loss_count': len(losses),
        'win_rate': round(len(wins) / n * 100, 1),
        'total_pnl_pct': round(total_pnl, 2),
        'avg_pnl_pct': round(total_pnl / n, 2),
        'max_win_pct': round(max(t['pnl_pct'] for t in trades), 2),
        'max_loss_pct': round(min(t['pnl_pct'] for t in trades), 2),
        'profit_factor': round(profit_factor, 2),
        'avg_hold_days': round(sum(t['hold_days'] for t in trades) / n, 1)
    }


if __name__ == '__main__':
    # ============================================================
    # 场景1: 从数据库获取数据并回测
    # ============================================================
    # 伪代码 - 实际替换为数据库查询
    # stock_list = db.query("SELECT code, name FROM stocks")
    # all_data = {}
    # for stock in stock_list:
    #     kline = db.query(f"SELECT * FROM kline WHERE code='{stock.code}' ORDER BY day")
    #     all_data[stock.code] = {'name': stock.name, 'data': kline}

    # 示例：手动构建数据（实际从数据库获取）
    # all_data = {
    #     '300006': {'name': '莱美药业', 'data': [...]},
    #     '688386': {'name': '泛亚微透', 'data': [...]},
    # }
    pass
