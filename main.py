# region imports
from AlgorithmImports import * 
# endregion
class CalculatingFluorescentOrangeCoyote(QCAlgorithm): 
    def initialize(self): 
        self.set_start_date(2024, 3, 29) 
        self.set_cash("USDT", 100000) 
        # Bybit spot ETHUSDT 
        self.set_brokerage_model(BrokerageName.BYBIT, AccountType.Cash) 
        self.eth = self.add_crypto("ETHUSDT", Resolution.MINUTE, Market.BYBIT).symbol 
        # Consolidator for ETHUSDT, 1-minute bars 
        self.consolidator = TradeBarConsolidator(timedelta(minutes=1))
        self.subscription_manager.add_consolidator(self.eth, self.consolidator)
        self.consolidator.data_consolidated += self.on_consolidated_bar
    
    def on_data(self, data: Slice): 
        if not self.portfolio.invested: 
            self.set_holdings(self.eth, 0.01) 
    
    def on_consolidated_bar(self, sender, bar: TradeBar): 
        # This will be called for every 1-minute completed bar 
        self.debug(f"{bar.end_time} | O:{bar.open} H:{bar.high} L:{bar.low} C:{bar.close}")