# region imports
from AlgorithmImports import *
# endregion
import pandas as pd
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List

# === Новое: Enum для состояния диапазона ===
class RangeState(str, Enum):
    IDLE = "Idle"        # ещё не подтверждён
    TRADING = "Trading"  # активен (подтверждён bounce'ом)
    BROKEN = "Broken"    # пробит


# -------------------------------------------------------------
# Состояние, которое можно хранить в алгоритме между вызовами
# -------------------------------------------------------------
@dataclass
class SwingState:
    last_ph_value: Optional[float] = None
    last_pl_value: Optional[float] = None
    last_ph_idx:   Optional[int]   = None
    last_pl_idx:   Optional[int]   = None

    # сюда будем складывать «последние» метки и диапазон
    last_labels:   List[Dict[str, Any]] = None   # список свингов за последний вызов
    current_range: Optional[Dict[str, float]] = None  # {"high","low","mid","span"}

    def __post_init__(self):
        if self.last_labels is None:
            self.last_labels = []


# -------------------------------------------------------------
# Основная функция: снаружи та же, внутри — уже взрослая
# -------------------------------------------------------------
def find_swings(
    df: pd.DataFrame,
    window: int = 10,
    *,
    state: Optional[SwingState] = None,
    min_span_pct: float = 0.003,
    pad_frac: float = 0.0,
    smooth: float = 0.0
):
    """
    Определяет индексы swing high и swing low, как и раньше:
        highs, lows = find_swings(df, window)

    ДОПОЛНИТЕЛЬНО (если передать state=SwingState()):
      - внутри использует pine-style pivot (строгий центр окна)
      - считает HH/LH/HL/LL
      - строит диапазон от последних свингов и кладёт его в state.current_range
      - метки свингов за последний вызов лежат в state.last_labels
    """

    highs: List[int] = []
    lows:  List[int] = []

    h = df["High"].to_numpy()
    l = df["Low"].to_numpy()
    n = len(df)

    # Pine-логика: экстремум в центральной свече окна [i-window, i+window]
    for i in range(window, n - window):
        win_hi = h[i - window : i + window + 1]
        win_lo = l[i - window : i + window + 1]

        # swing high
        if h[i] == np.max(win_hi) and np.argmax(win_hi) == window:
            highs.append(i)

        # swing low
        if l[i] == np.min(win_lo) and np.argmin(win_lo) == window:
            lows.append(i)

    # Если state не передали – ведём себя как старый простой вариант:
    if state is None:
        return highs, lows

    # ---------------------------------------------------------
    # Дальше «танцы с бубном»: HH/LH/HL/LL + диапазон
    # ---------------------------------------------------------
    labels: List[Dict[str, Any]] = []
    last_sh = None
    last_sl = None

    # high'и
    for idx in highs:
        price = float(df["High"].iloc[idx])
        if state.last_ph_value is None or price > state.last_ph_value:
            lbl = "HH"
        else:
            lbl = "LH"

        labels.append({"type": "H", "idx": idx, "price": price, "label": lbl})
        state.last_ph_value = price
        state.last_ph_idx = idx
        last_sh = {"idx": idx, "price": price}

    # low'ы
    for idx in lows:
        price = float(df["Low"].iloc[idx])
        if state.last_pl_value is None or price > state.last_pl_value:
            lbl = "HL"
        else:
            lbl = "LL"

        labels.append({"type": "L", "idx": idx, "price": price, "label": lbl})
        state.last_pl_value = price
        state.last_pl_idx = idx
        last_sl = {"idx": idx, "price": price}

    # если новых свингов в этот раз не было – возьмём старые из state
    if last_sh is None and state.last_ph_value is not None and state.last_ph_idx is not None:
        last_sh = {"idx": state.last_ph_idx, "price": state.last_ph_value}

    if last_sl is None and state.last_pl_value is not None and state.last_pl_idx is not None:
        last_sl = {"idx": state.last_pl_idx, "price": state.last_pl_value}

    # построим диапазон от последней пары свингов
    range_dict = _build_range_from_swings(
        df,
        last_sh,
        last_sl,
        state.current_range,
        min_span_pct=min_span_pct,
        pad_frac=pad_frac,
        smooth=smooth
    )

    state.last_labels = labels
    if range_dict is not None:
        state.current_range = range_dict

    # ВНЕШНЕЕ API НЕ МЕНЯЕМ:
    return highs, lows


def build_initial_range(
    df: pd.DataFrame,
    window: int = 10,
    *,
    state: Optional[SwingState] = None,
    min_span_pct: float = 0.003
):
    """
    Находит последний swing-range и строит уровни Фибоначчи (-0.2 → 1.2),
    сохраняя СТАРУЮ структуру возвращаемого dict'а.

    Если передан state=SwingState, внутри ещё и обновятся:
    - state.last_ph_value / last_pl_value
    - state.last_labels
    - state.current_range (через внутреннюю логику find_swings)
    """
    # если есть state, то используем "умный" find_swings с бубном
    if state is not None:
        highs, lows = find_swings(
            df,
            window=window,
            state=state,
            min_span_pct=min_span_pct,
            pad_frac=0.0,
            smooth=0.0
        )
    else:
        # если state не передали – просто берём индексы свингов
        highs, lows = find_swings(df, window)

    if len(highs) == 0 or len(lows) == 0:
        raise ValueError("Недостаточно swing high/low для построения диапазона")

    last_high_idx = highs[-1]
    last_low_idx = lows[-1]

    if last_high_idx > last_low_idx:
        high = df["High"].iloc[last_high_idx]
        low = df["Low"].iloc[last_low_idx]
        direction = "up"
    else:
        high = df["High"].iloc[last_low_idx]
        low = df["Low"].iloc[last_high_idx]
        direction = "down"

    # классические твои уровни Фибо
    ratios = [-0.2, 0.0, 0.25, 0.5, 0.75, 1.0, 1.2]
    diff = high - low
    levels = {r: low + diff * r for r in ratios}

    return {
        "high": high,
        "low": low,
        "levels": levels,
        "direction": direction,
        "high_idx": last_high_idx,
        "low_idx": last_low_idx,
        "state": RangeState.IDLE,
    }


def update_fib_range(df: pd.DataFrame, last_range: dict, lookback: int = 20):
    """Проверяет разрушение или перестроение диапазона Фибоначчи."""
    high = last_range["high"]
    low = last_range["low"]
    levels = last_range["levels"]
    direction = last_range["direction"]
    state = last_range.get("state", RangeState.IDLE)

    for i in range(lookback, len(df)):
        close = df["Close"].iloc[i]

        # === Разрушение диапазона ===
        if close > levels[1.2] or close < levels[-0.2]:
            last_range["state"] = RangeState.BROKEN
            return last_range, i, True  # broken = True

        # === Подтверждение ренджа (bounce) ===
        if state == RangeState.IDLE:
            if direction == "up" and close >= levels[0.75]:
                last_range["state"] = RangeState.TRADING
            elif direction == "down" and close <= levels[0.25]:
                last_range["state"] = RangeState.TRADING

        # === Перестроение при ап-тренде ===
        if direction == "up" and state == RangeState.TRADING:
            if close < levels[0.75]:
                for j in range(i, min(i + lookback, len(df))):
                    if df["Close"].iloc[j] >= levels[0.75]:
                        window_df = df.iloc[i:j+1]
                        new_high = window_df["High"].max()
                        new_high_idx = window_df["High"].idxmax()
                        diff = new_high - low
                        new_levels = {r: low + diff * r for r in [-0.2, 0.0, 0.25, 0.5, 0.75, 1.0, 1.2]}
                        new_range = {
                            "low": low,
                            "high": new_high,
                            "levels": new_levels,
                            "direction": "up",
                            "state": RangeState.TRADING
                        }
                        return new_range, new_high_idx, False

        # === Перестроение при даун-тренде ===
        elif direction == "down" and state == RangeState.TRADING:
            if close > levels[0.25]:
                for j in range(i, min(i + lookback, len(df))):
                    if df["Close"].iloc[j] <= levels[0.25]:
                        window_df = df.iloc[i:j+1]
                        new_low = window_df["Low"].min()
                        new_low_idx = window_df["Low"].idxmin()
                        diff = high - new_low
                        new_levels = {r: high - diff * (1 - r) for r in [-0.2, 0.0, 0.25, 0.5, 0.75, 1.0, 1.2]}
                        new_range = {
                            "low": new_low,
                            "high": high,
                            "levels": new_levels,
                            "direction": "down",
                            "state": RangeState.TRADING
                        }
                        return new_range, new_low_idx, False

    # Если ничего не произошло
    return last_range, None, False

