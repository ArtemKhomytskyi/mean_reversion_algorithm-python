from dataclasses import dataclass
import pandas as pd
import numpy as np
from datetime import datetime

# === 5.1–5.3: Структура диапазона Фибоначчи ===
@dataclass
class FibRange:
    high: float
    low: float
    generated_time: datetime
    last_update_time: datetime
    levels: dict

# === 5.2: Расчёт уровней ===
def construct_fibonacci_levels(high: float, low: float) -> dict:
    """Compute Fibonacci levels based on swing high and low."""
    diff = high - low
    levels = {
        -0.2: high + diff * (-0.2),
        0.0: low,
        0.25: low + diff * 0.25,
        0.5: low + diff * 0.5,
        0.75: low + diff * 0.75,
        1.0: high,
        1.2: high + diff * 0.2
    }
    return levels

# === 5.1 + 5.3: Построение диапазона на основе swing-пары ===
def build_fib_range(swings: pd.DataFrame, ohlc: pd.DataFrame) -> FibRange | None:
    """
    Build Fibonacci range based on the latest confirmed swing pair.
    """
    valid_swings = swings.dropna(subset=["HighLow"])
    if len(valid_swings) < 2:
        return None  # недостаточно точек для построения

    # Берём последние две swing-точки
    last_two = valid_swings.tail(2)
    idx1, idx2 = last_two.index[0], last_two.index[1]
    type1, type2 = last_two.iloc[0]["HighLow"], last_two.iloc[1]["HighLow"]
    price1, price2 = last_two.iloc[0]["Level"], last_two.iloc[1]["Level"]

    # Проверяем порядок: high → low или low → high
    if type1 == 1 and type2 == -1:
        high, low = price1, price2
    elif type1 == -1 and type2 == 1:
        high, low = price2, price1
    else:
        return None  # невалидная последовательность (два high подряд и т.п.)

    # Построение уровней
    levels = construct_fibonacci_levels(high, low)
    generated_time = idx2  # время последнего swing
    last_update_time = ohlc.index[-1]

    return FibRange(high, low, generated_time, last_update_time, levels)

# === 5.4: Проверка актуальности диапазона ===
def is_range_broken(fib_range: FibRange, current_price: float) -> bool:
    """Return True if price breaks the range (above high or below low)."""
    return current_price > fib_range.high or current_price < fib_range.low

# === Тестирование на текущих swing-данных ===
fib_range = build_fib_range(swings, ohlc)

if fib_range:
    print("Fibonacci Range Built:")
    print(f"High: {fib_range.high:.2f}")
    print(f"Low: {fib_range.low:.2f}")
    print("Levels:")
    for lvl, val in fib_range.levels.items():
        print(f"  {lvl:>4}: {val:.2f}")
else:
    print("Not enough valid swings to build Fibonacci range.")

# === Проверка пробоя диапазона ===
if fib_range:
    current_price = ohlc["close"].iloc[-1]
    broken = is_range_broken(fib_range, current_price)
    print(f"\nRange broken? {broken}")
