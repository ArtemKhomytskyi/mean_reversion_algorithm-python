import pandas as pd

def find_swings(df: pd.DataFrame, window: int = 10):
    """
    Находит индексы swing high и swing low в данных OHLC.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame с колонками 'High' и 'Low'
    window : int
        Размер окна для поиска экстремумов

    Returns
    -------
    tuple[list[int], list[int]]
        Индексы swing highs и swing lows
    """
    highs, lows = [], []
    for i in range(window, len(df) - window):
        if df["High"][i] == max(df["High"][i - window:i + window + 1]):
            highs.append(i)
        if df["Low"][i] == min(df["Low"][i - window:i + window + 1]):
            lows.append(i)
    return highs, lows


def fibonacci_range(df: pd.DataFrame, window: int = 10):
    """
    Вычисляет диапазон Фибоначчи между последними swing high и swing low.

    Parameters
    ----------
    df : pd.DataFrame
        Должен содержать колонки ['High', 'Low', 'Close']
    window : int
        Размер окна для поиска swing high/low

    Returns
    -------
    dict
        {
            "high": float,
            "low": float,
            "levels": dict,
            "last_high_idx": int,
            "last_low_idx": int,
            "break_idx": int
        }
    """

    highs, lows = find_swings(df, window)

    if not highs or not lows:
        raise ValueError("Недостаточно swing high/low для построения диапазона")

    last_high_idx = highs[-1]
    last_low_idx = lows[-1]

    # Определяем направление диапазона
    if last_high_idx > last_low_idx:
        high = df["High"][last_high_idx]
        low = df["Low"][last_low_idx]
    else:
        high = df["High"][last_low_idx]
        low = df["Low"][last_high_idx]

    # Уровни Фибоначчи
    ratios = [-0.2, 0.0, 0.25, 0.5, 0.75, 1.0, 1.2]
    diff = high - low
    levels = {r: low + diff * r for r in ratios}

    # Ищем, когда диапазон пробит
    def find_break_index(df, high, low):
        for i in range(max(last_high_idx, last_low_idx), len(df)):
            if df["Close"][i] > high or df["Close"][i] < low:
                return i
        return len(df) - 1

    break_idx = find_break_index(df, high, low)

    return {
        "high": high,
        "low": low,
        "levels": levels,
        "last_high_idx": last_high_idx,
        "last_low_idx": last_low_idx,
        "break_idx": break_idx
    }
