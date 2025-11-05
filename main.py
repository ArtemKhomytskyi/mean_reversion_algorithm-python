# region imports
from AlgorithmImports import *
# endregion
import pandas as pd
from math import floor

# === Импорты твоих модулей ===
from swing_high_low_detection import find_swings
from Fibonacci_Retracement import build_initial_range
from Range_rebuilder import update_fib_range, RangeState
from entry_exit import (
    make_long_signal, make_short_signal,
    decide_exit, EntryParams, ExitParams, Side
)


class CalculatingFluorescentOrangeCoyote(QCAlgorithm):

    def Initialize(self):
        # === Основная инициализация ===
        self.SetStartDate(2024, 3, 29)
        self.SetCash("USDT", 100000)
        self.SetBrokerageModel(BrokerageName.BYBIT, AccountType.Cash)

        # === Подписка на ETHUSDT ===
        self.symbol = self.AddCrypto("ETHUSDT", Resolution.MINUTE, Market.BYBIT).Symbol

        # === История и состояния ===
        self.history_df = pd.DataFrame(columns=["Time", "Open", "High", "Low", "Close"])
        self.current_range = None
        self.range_state = RangeState.IDLE
        self.position_side = None
        self.entry_price = None
        self.bars_in_trade = 0

        # === Параметры стратегий ===
        self.entry_params = EntryParams(small_buffer=1.0, use_limit=False)
        self.exit_params = ExitParams(close_based=True, max_bars_in_trade=48)

        # === Консолидация по минутам ===
        consolidator = TradeBarConsolidator(timedelta(minutes=1))
        self.SubscriptionManager.AddConsolidator(self.symbol, consolidator)
        consolidator.DataConsolidated += self.OnConsolidatedBar

        self.Debug("Algorithm initialized.")

    # === Главный обработчик минутных баров ===
    def OnConsolidatedBar(self, sender, bar: TradeBar):
        # Сохраняем бар в DataFrame
        new_row = {
            "Time": bar.EndTime,
            "Open": bar.Open,
            "High": bar.High,
            "Low": bar.Low,
            "Close": bar.Close
        }
        self.history_df.loc[len(self.history_df)] = new_row

        # Достаточно данных для анализа?
        if len(self.history_df) < 100:
            return

        df = self.history_df.copy()

        # === Построение / обновление ренджа ===
        if self.current_range is None:
            try:
                self.current_range = build_initial_range(df, window=10)
                self.range_state = self.current_range["state"]
                self.Debug(f"Initial range built: {self.current_range}")
            except ValueError:
                return
        else:
            updated_range, rebuild_idx, broken = update_fib_range(df, self.current_range)
            self.current_range = updated_range
            self.range_state = updated_range["state"]

            if broken:
                self.Debug(f"Range broken at {bar.EndTime}. Rebuilding next.")
                self.current_range = None
                self.range_state = RangeState.IDLE
                return

        # === Торговая логика ===
        if self.range_state == RangeState.TRADING:
            levels = self.current_range["levels"]
            close = bar.Close

            # === Вход в сделку ===
            if not self.Portfolio.Invested:
                long_signal = make_long_signal(close, None, levels, self.entry_params, self.range_state)
                short_signal = make_short_signal(close, None, levels, self.entry_params, self.range_state)

                if long_signal:
                    qty = self.CalculatePositionSize(long_signal.entry_price_hint, long_signal.stop_price)
                    if qty > 0:
                        self.MarketOrder(self.symbol, qty)
                        self.position_side = Side.LONG
                        self.entry_price = long_signal.entry_price_hint
                        self.bars_in_trade = 0
                        self.Debug(f"Opened LONG at {self.entry_price} | SL {long_signal.stop_price} | TP {long_signal.tp_level}")

                elif short_signal:
                    qty = self.CalculatePositionSize(short_signal.entry_price_hint, short_signal.stop_price)
                    if qty > 0:
                        self.MarketOrder(self.symbol, -qty)
                        self.position_side = Side.SHORT
                        self.entry_price = short_signal.entry_price_hint
                        self.bars_in_trade = 0
                        self.Debug(f"Opened SHORT at {self.entry_price} | SL {short_signal.stop_price} | TP {short_signal.tp_level}")

            # === Выход из сделки ===
            elif self.Portfolio.Invested:
                self.bars_in_trade += 1
                side = self.position_side
                exit_decision = decide_exit(
                    side=side,
                    close_price=bar.Close,
                    next_open_price=None,
                    levels=levels,
                    bars_in_trade=self.bars_in_trade,
                    range_state=self.range_state,
                    params=self.exit_params
                )
                if exit_decision.should_exit:
                    self.Liquidate(self.symbol)
                    self.Debug(f"Exit ({exit_decision.reason}) at {bar.Close}")
                    self.position_side = None
                    self.entry_price = None
                    self.bars_in_trade = 0

    # === Расчёт размера позиции по 1%-правилу ===
    def CalculatePositionSize(self, entry_price, stop_price):
        account_value = self.Portfolio.TotalPortfolioValue
        risk_amount = account_value * 0.01  # 1% риск
        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return 0
        qty = risk_amount / stop_distance
        lot_size = floor(qty)
        return max(lot_size, 0)
