# region imports
from AlgorithmImports import *
# endregion

from dataclasses import dataclass
from typing import Optional, Dict
import pandas as pd
from datetime import datetime

# === 5.3: структура диапазона Фибоначчи ===
@dataclass
class FibRange:
    high: float
    low: float
    generated_time: pd.Timestamp
    last_update_time: pd.Timestamp
    levels: Dict[float, float]

# === 5.2: расчёт уровней ===
def construct_fibonacci_levels(high: float, low: float) -> Dict[float, float]:
    """
    Compute Fibonacci-style levels according to spec.
    Returns dict: { -0.2: ..., 0.0: low, 0.25: ..., 0.5: ..., 0.75: ..., 1.0: high, 1.2: ... }
    """
    diff = high - low
    return {
        -0.2: high + diff * (-0.2),
         0.0: low,
         0.25: low + diff * 0.25,
         0.5: low + diff * 0.5,
         0.75: low + diff * 0.75,
         1.0: high,
         1.2: high + diff * 0.2
    }

# === 5.1 + 5.3: построение диапазона на основе последней подтверждённой пары swings ===
def build_fib_range(swings: pd.DataFrame, ohlc: pd.DataFrame) -> Optional[FibRange]:
    """
    Build a FibRange from confirmed swings + ohlc.

    Parameters
    ----------
    swings : pd.DataFrame
        DataFrame indexed by timestamps with columns:
            - "HighLow" :  1 for swing high, -1 for swing low, NaN otherwise
            - "Level"   : price level (prefer close/high/low as stored by swing detector)
    ohlc : pd.DataFrame
        OHLC DataFrame indexed by timestamps (used to set last_update_time and reference).

    Returns
    -------
    FibRange or None
        FibRange when last two swings form a valid pair (high->low or low->high),
        otherwise None.
    """
    # only consider confirmed swings
    valid_swings = swings.dropna(subset=["HighLow"])
    if len(valid_swings) < 2:
        return None

    # take last two confirmed swings in chronological order
    last_two = valid_swings.tail(2)
    idx1, idx2 = last_two.index[0], last_two.index[1]
    type1 = float(last_two.iloc[0]["HighLow"])
    type2 = float(last_two.iloc[1]["HighLow"])
    price1 = float(last_two.iloc[0]["Level"])
    price2 = float(last_two.iloc[1]["Level"])

    # valid sequences: high (1) then low (-1)  OR  low (-1) then high (1)
    if type1 == 1.0 and type2 == -1.0:
        high, low = price1, price2
    elif type1 == -1.0 and type2 == 1.0:
        high, low = price2, price1
    else:
        # sequence invalid (e.g., two highs in a row) — do not build
        return None

    levels = construct_fibonacci_levels(high, low)
    generated_time = pd.Timestamp(idx2)
    last_update_time = pd.Timestamp(ohlc.index[-1]) if len(ohlc.index) > 0 else pd.Timestamp.now()

    return FibRange(high=high, low=low, generated_time=generated_time,
                    last_update_time=last_update_time, levels=levels)

# === 5.4 Утилита: проверка "сломался ли диапазон" ===
def is_range_broken(fib_range: FibRange, current_price: float) -> bool:
    """
    Range is considered broken when current_price closes beyond high or below low.
    (This is a pure numeric check — interpretation of 'close' vs intrabar handling
    should be done by caller.)
    """
    return current_price > fib_range.high or current_price < fib_range.low

# === Пример использования (комментарий) ===
# В main алгоритме:
#   1) Вызываешь swing detector: swings = swing_highs_lows_online(ohlc, ...)
#   2) Передаёшь swings и ohlc в build_fib_range(swings, ohlc)
#   3) Если build_fib_range вернул объект, используешь fib_range.levels для логики входа/стопов/TP
#   4) Перестраиваешь диапазон только если:
#         - появился новый confirmed swing pair (build_fib_range вернул новую пару), или
#         - is_range_broken(...) вернул True (range сломан)
#
# Пример (в main):
#   swings = swing_highs_lows_online(ohlc, N_candidates=[10], N_confirmation=3, ...)
#   fib_range = build_fib_range(swings, ohlc)
#   if fib_range:
#       lvl_025 = fib_range.levels[0.25]
#       # использовать уровни для логики
