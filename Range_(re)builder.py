# region imports
from AlgorithmImports import *
# endregion
import pandas as pd
from enum import Enum


# === Новое: Enum для состояния диапазона ===
class RangeState(str, Enum):
    IDLE = "Idle"        # ещё не подтверждён
    TRADING = "Trading"  # активен (подтверждён bounce'ом)
    BROKEN = "Broken"    # пробит


def find_swings(df: pd.DataFrame, window: int = 10):
    """Определяет индексы swing high и swing low."""
    highs, lows = [], []
    for i in range(window, len(df) - window):
        if df["High"].iloc[i] == max(df["High"].iloc[i - window:i + window + 1]):
            highs.append(i)
        if df["Low"].iloc[i] == min(df["Low"].iloc[i - window:i + window + 1]):
            lows.append(i)
    return highs, lows


def build_initial_range(df: pd.DataFrame, window: int = 10):
    """Находит последний swing range и строит уровни Фибоначчи (-0.2 → 1.2)."""
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
        "state": RangeState.IDLE,   # новый флаг
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
