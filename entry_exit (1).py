from __future__ import annotations
# region imports
from AlgorithmImports import *
# endregion

# Your New Python File
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any


# ====== COMMON TYPES ======
class Side(str, Enum):
    LONG  = "long"
    SHORT = "short"

class RangeState(str, Enum):
    TRADING = "Trading"
    BROKEN  = "Broken"

# ====== ENTRY ======
@dataclass
class EntryParams:
    small_buffer: float = 0.0
    use_limit: bool = False
    enter_on_next_open: bool = True
    confirm_momentum: bool = False
    min_momentum_pct: float = 0.0

@dataclass
class EntrySignal:
    side: Side
    entry_price_hint: float
    stop_price: float
    tp_level: float
    reason: str
    meta: Dict[str, Any]

def _in_zone(price: float, a: float, b: float) -> bool:
    lo, hi = (a, b) if a <= b else (b, a)
    return lo <= price <= hi

def _was_above_short_range(prev_price: float, levels: Dict[float, float]) -> bool:
    # был в коридоре 1.0–1.2 или выше
    return prev_price is not None and prev_price >= levels[1.0]

def _was_below_long_range(prev_price: float, levels: Dict[float, float]) -> bool:
    # был в коридоре 0.0–(-0.2) или ниже
    return prev_price is not None and prev_price <= levels[0.0]

def make_long_signal(
    close_price: float,
    next_open: Optional[float],
    levels: Dict[float, float],
    p: EntryParams,
    range_state: RangeState,
    prev_close: Optional[float] = None
) -> Optional[EntrySignal]:
    # ✅ не входим, если range ещё не подтверждён
    if range_state != RangeState.TRADING:
        return None

    z0, z025 = levels[0.0], levels[0.25]
    if not _in_zone(close_price, z0, z025):
        return None
    if p.confirm_momentum and next_open is not None:
        need = close_price * (1.0 + p.min_momentum_pct / 100.0)
        if next_open <= need:
            return None
    entry = ((z0 + z025) / 2.0) if p.use_limit else (
        next_open if (p.enter_on_next_open and next_open is not None) else close_price)
    
    came_from_below = False
    if prev_close is not None:
        # если прошлый бар был ниже 0, но не ниже -0.2 → именно та зона, про которую ты говорил
        low_outer = levels[-0.2]
        if low_outer <= prev_close < levels[0.0]:
            came_from_below = True
        # если был вообще ниже -0.2 — тоже считаем, что пришли снизу
        if prev_close < low_outer:
            came_from_below = True

    # вот тут твоя правка:
    if came_from_below:
        # пришли снизу → стоп НЕ на 0, а глубже
        sl = levels[-0.2] - p.small_buffer
    else:
        # обычный случай → стоп на 0
        sl = levels[0.0] - p.small_buffer

    tp = levels[1.0]
    return EntrySignal(Side.LONG, float(entry), float(sl), float(tp),
                       "LONG: close in [0–0.25]", {"zone": [z0, z025]})


def make_short_signal(
    close_price: float,
    next_open: Optional[float],
    levels: Dict[float, float],
    p: EntryParams,
    range_state: RangeState,
    prev_close: Optional[float] = None
) -> Optional[EntrySignal]:
    if range_state != RangeState.TRADING:
        return None

    z075, z10 = levels[0.75], levels[1.0]
    if not _in_zone(close_price, z075, z10):
        return None
    if p.confirm_momentum and next_open is not None:
        need = close_price * (1.0 - p.min_momentum_pct / 100.0)
        if next_open >= need:
            return None
    entry = ((z075 + z10) / 2.0) if p.use_limit else (
        next_open if (p.enter_on_next_open and next_open is not None) else close_price)
    
    came_from_above = False
    if prev_close is not None:
        upper_outer = levels[1.2]
        # был в 1.0–1.2 → это твоя "спустился из диапазона 1–1.2"
        if levels[1.0] <= prev_close <= upper_outer:
            came_from_above = True
        if prev_close > upper_outer:
            came_from_above = True

    if came_from_above:
        # пришли сверху → стоп не на 1, а на 1.2
        sl = levels[1.2] + p.small_buffer
    else:
        # обычный случай → стоп на 1
        sl = levels[1.0] + p.small_buffer

    tp = levels[0.0]
    return EntrySignal(Side.SHORT, float(entry), float(sl), float(tp),
                       "SHORT: close in [0.75–1.0]", {"zone": [z075, z10]})

# ====== EXIT ======
class ExitReason(str, Enum):
    NONE         = "none"
    STOP         = "stop_loss"
    TAKE_PROFIT  = "take_profit"
    RANGE_BREAK  = "range_break"
    TIMEOUT      = "time_based"

@dataclass
class ExitParams:
    close_based: bool = True
    exit_on_next_open: bool = True
    max_bars_in_trade: Optional[int] = 48
    small_buffer: float = 0.0
    on_range_break: str = "close_now"      # "close_now" | "widen_stop"
    widen_stop_to: Optional[float] = None  # если widen_stop: новый SL

@dataclass
class ExitDecision:
    should_exit: bool
    reason: ExitReason
    exit_price_hint: Optional[float]
    new_stop: Optional[float] = None
    meta: Dict[str, Any] = None

def _tp_level(side: Side, levels: Dict[float, float]) -> float:
    return levels[1.0] if side == Side.LONG else levels[0.0]

def _sl_level(side: Side, levels: Dict[float, float], buf: float) -> float:
    return (levels[-0.2] - buf) if side == Side.LONG else (levels[1.2] + buf)

def _range_break_confirmed(side: Side, close_price: float, levels: Dict[float, float]) -> bool:
    return (close_price < float(levels[-0.2])) if side == Side.LONG else (close_price > float(levels[1.2]))

def decide_exit(
    *, side: Side, close_price: float, next_open_price: Optional[float],
    levels: Dict[float, float], bars_in_trade: int, range_state: RangeState, params: ExitParams
) -> ExitDecision:
    meta: Dict[str, Any] = {}
    # 1) STOP
    stop = _sl_level(side, levels, params.small_buffer)
    meta["stop_level"] = stop
    if params.close_based:
        if (side == Side.LONG and close_price < stop) or (side == Side.SHORT and close_price > stop):
            return ExitDecision(True, ExitReason.STOP,
                                next_open_price if (params.exit_on_next_open and next_open_price is not None) else close_price,
                                None, meta)
    # 2) TP
    tp = _tp_level(side, levels)
    meta["tp_level"] = tp
    if params.close_based:
        if (side == Side.LONG and close_price > tp) or (side == Side.SHORT and close_price < tp):
            return ExitDecision(True, ExitReason.TAKE_PROFIT,
                                next_open_price if (params.exit_on_next_open and next_open_price is not None) else close_price,
                                None, meta)
    # 3) RANGE BREAK
    range_broken_flag = (range_state == RangeState.BROKEN)
    break_by_levels   = _range_break_confirmed(side, close_price, levels)
    if range_broken_flag or break_by_levels:
        meta["range_broken_flag"] = range_broken_flag
        meta["range_break_by_levels"] = break_by_levels
        if params.on_range_break == "close_now":
            return ExitDecision(True, ExitReason.RANGE_BREAK,
                                next_open_price if (params.exit_on_next_open and next_open_price is not None) else close_price,
                                None, meta)
        else:
            if params.widen_stop_to is not None:
                new_sl = float(params.widen_stop_to)
            else:
                new_sl = float(levels[-0.2]) if side == Side.LONG else float(levels[1.2])
            return ExitDecision(False, ExitReason.RANGE_BREAK, None, new_sl, meta)
    # 4) TIMEOUT
    if params.max_bars_in_trade is not None and bars_in_trade >= int(params.max_bars_in_trade):
        return ExitDecision(True, ExitReason.TIMEOUT,
                            next_open_price if (params.exit_on_next_open and next_open_price is not None) else close_price,
                            None, {"bars_in_trade": bars_in_trade})
    return ExitDecision(False, ExitReason.NONE, None, None, meta)
