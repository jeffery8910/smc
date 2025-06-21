# core/backtester.py
import pandas as pd
import numpy as np

class Backtester:
    def __init__(self, ohlcv_data, strategy_instance,
                 initial_capital=100000,
                 commission_bps=2, # Example: 2 bps = 0.02%
                 slippage_bps=1,   # Example: 1 bps = 0.01%
                 default_position_size=1,
                 execution_price_type='close' # 'close' or 'next_open'
                ):
        """
        Initializes the Backtester.
        Args:
            ohlcv_data (pd.DataFrame): DataFrame with OHLCV data. Must have DatetimeIndex
                                       and 'open', 'high', 'low', 'close' columns.
                                       'volume' is optional but good to have.
            strategy_instance (BaseStrategy): An instance of a trading strategy.
            initial_capital (float): Starting capital.
            commission_bps (float): Commission fee in basis points.
            slippage_bps (float): Slippage in basis points.
            default_position_size (float): Fixed number of units to trade.
            execution_price_type (str): 'close' (execute at current bar close) or
                                        'next_open' (execute at next bar open).
        """
        if not isinstance(ohlcv_data, pd.DataFrame) or not isinstance(ohlcv_data.index, pd.DatetimeIndex):
            raise ValueError("ohlcv_data must be a pandas DataFrame with a DatetimeIndex.")
        required_cols = ['open', 'high', 'low', 'close']
        if not all(col in ohlcv_data.columns for col in required_cols):
            raise ValueError(f"ohlcv_data must contain {required_cols} columns.")
        if execution_price_type == 'next_open' and 'open' not in ohlcv_data.columns:
            raise ValueError("ohlcv_data must contain 'open' column for 'next_open' execution_price_type.")


        self.ohlcv_data = ohlcv_data.copy() # Work on a copy
        self.strategy = strategy_instance
        self.initial_capital = float(initial_capital)
        self.commission_rate = float(commission_bps) / 10000.0
        self.slippage_rate = float(slippage_bps) / 10000.0
        self.default_position_size = float(default_position_size)
        self.execution_price_type = execution_price_type.lower()


        # Initialize tracking structures
        self.positions_df = pd.DataFrame(index=self.ohlcv_data.index,
                                      columns=['signal', 'position_qty', 'entry_price',
                                               'trade_pnl', 'cash', 'holdings_value', 'portfolio_value'])
        self.trade_log = []

        self.current_cash = self.initial_capital
        self.current_position_qty = 0 # Shares/contracts: positive for long, negative for short
        self.avg_entry_price = 0.0    # Average entry price for the current open position

    def _get_execution_price(self, current_bar_index, signal_type):
        """Determines the execution price for a trade."""
        if self.execution_price_type == 'next_open':
            if current_bar_index + 1 < len(self.ohlcv_data):
                intended_price = self.ohlcv_data['open'].iloc[current_bar_index + 1]
            else: # Cannot execute on next_open if it's the last bar
                return None
        else: # Default to 'close' of current bar
            intended_price = self.ohlcv_data['close'].iloc[current_bar_index]

        # Apply slippage
        if signal_type == 'buy': # Buying, price might be worse (higher)
            return intended_price * (1 + self.slippage_rate)
        elif signal_type == 'sell': # Selling, price might be worse (lower)
            return intended_price * (1 - self.slippage_rate)
        return intended_price # Should not happen if signal_type is 'buy' or 'sell'

    def _calculate_commission(self, trade_value):
        return abs(trade_value) * self.commission_rate

    def run(self):
        """Runs the backtest."""
        signals = self.strategy.generate_signals(self.ohlcv_data)
        if len(signals) != len(self.ohlcv_data):
            raise ValueError("Number of signals must match number of data points.")

        self.positions_df['signal'] = signals
        self.positions_df['cash'] = self.initial_capital
        self.positions_df['holdings_value'] = 0.0
        self.positions_df['portfolio_value'] = self.initial_capital

        last_price = self.ohlcv_data['close'].iloc[0] # For initial mark-to-market if needed

        for i, timestamp in enumerate(self.ohlcv_data.index):
            signal = self.positions_df['signal'].iloc[i]
            current_close_price = self.ohlcv_data['close'].iloc[i]

            # Carry forward values from previous step for cash, holdings, portfolio
            if i > 0:
                self.positions_df.loc[timestamp, 'cash'] = self.positions_df['cash'].iloc[i-1]
                self.positions_df.loc[timestamp, 'position_qty'] = self.current_position_qty # Carry position
                self.positions_df.loc[timestamp, 'entry_price'] = self.avg_entry_price # Carry entry price

            # Mark-to-market current holdings
            self.positions_df.loc[timestamp, 'holdings_value'] = self.current_position_qty * current_close_price
            self.positions_df.loc[timestamp, 'portfolio_value'] = self.positions_df['cash'].loc[timestamp] + self.positions_df['holdings_value'].loc[timestamp]

            execution_price = self._get_execution_price(i, signal)
            if execution_price is None: # Cannot execute (e.g. next_open on last bar)
                continue

            trade_pnl = 0.0

            # --- BUY SIGNAL ---
            if signal == 'buy':
                if self.current_position_qty < 0: # Closing a short position
                    qty_to_trade = abs(self.current_position_qty)
                    trade_value = qty_to_trade * execution_price
                    commission = self._calculate_commission(trade_value)

                    trade_pnl = qty_to_trade * (self.avg_entry_price - execution_price) - commission
                    self.current_cash -= (trade_value + commission) # Buying back shares

                    self.trade_log.append({
                        'timestamp': timestamp, 'type': 'cover_short', 'price': execution_price,
                        'size': qty_to_trade, 'commission': commission, 'pnl': trade_pnl,
                        'cash': self.current_cash, 'portfolio_value': self.current_cash
                    })
                    self.current_position_qty = 0
                    self.avg_entry_price = 0

                # Opening a new long or adding to existing long (simple fixed size for now)
                if self.current_position_qty == 0: # Can be configurable to allow adding to position
                    qty_to_trade = self.default_position_size
                    trade_value = qty_to_trade * execution_price
                    commission = self._calculate_commission(trade_value)

                    if self.current_cash >= trade_value + commission:
                        self.current_cash -= (trade_value + commission)
                        self.avg_entry_price = (self.avg_entry_price * self.current_position_qty + execution_price * qty_to_trade) / (self.current_position_qty + qty_to_trade) if self.current_position_qty != 0 else execution_price # Handles adding to position
                        self.current_position_qty += qty_to_trade

                        self.trade_log.append({
                            'timestamp': timestamp, 'type': 'buy_long', 'price': execution_price,
                            'size': qty_to_trade, 'commission': commission, 'pnl': 0, # PnL is realized on sell
                            'cash': self.current_cash, 'portfolio_value': self.current_cash + self.current_position_qty * current_close_price
                        })
                    else:
                        # Insufficient funds, log or handle
                        pass


            # --- SELL SIGNAL ---
            elif signal == 'sell':
                if self.current_position_qty > 0: # Closing a long position
                    qty_to_trade = self.current_position_qty
                    trade_value = qty_to_trade * execution_price
                    commission = self._calculate_commission(trade_value)

                    trade_pnl = qty_to_trade * (execution_price - self.avg_entry_price) - commission
                    self.current_cash += (trade_value - commission)

                    self.trade_log.append({
                        'timestamp': timestamp, 'type': 'sell_long', 'price': execution_price,
                        'size': qty_to_trade, 'commission': commission, 'pnl': trade_pnl,
                        'cash': self.current_cash, 'portfolio_value': self.current_cash
                    })
                    self.current_position_qty = 0
                    self.avg_entry_price = 0

                # Opening a new short position
                if self.current_position_qty == 0: # Can be configurable
                    qty_to_trade = self.default_position_size # Sell short this many units
                    trade_value = qty_to_trade * execution_price # Value of shares borrowed and sold
                    commission = self._calculate_commission(trade_value)

                    # Assuming margin requirements are met (not explicitly modeled here)
                    self.current_cash += (trade_value - commission) # Cash increases from selling borrowed shares
                    self.avg_entry_price = (self.avg_entry_price * abs(self.current_position_qty) + execution_price * qty_to_trade) / (abs(self.current_position_qty) + qty_to_trade) if self.current_position_qty !=0 else execution_price
                    self.current_position_qty -= qty_to_trade # Position becomes negative

                    self.trade_log.append({
                        'timestamp': timestamp, 'type': 'sell_short', 'price': execution_price,
                        'size': qty_to_trade, 'commission': commission, 'pnl': 0, # PnL is realized on cover
                        'cash': self.current_cash, 'portfolio_value': self.current_cash + self.current_position_qty * current_close_price
                    })


            # Update DataFrame for the current timestamp after potential trades
            self.positions_df.loc[timestamp, 'trade_pnl'] = trade_pnl if trade_pnl != 0 else np.nan
            self.positions_df.loc[timestamp, 'position_qty'] = self.current_position_qty
            self.positions_df.loc[timestamp, 'entry_price'] = self.avg_entry_price if self.current_position_qty != 0 else np.nan
            self.positions_df.loc[timestamp, 'cash'] = self.current_cash
            self.positions_df.loc[timestamp, 'holdings_value'] = self.current_position_qty * current_close_price
            self.positions_df.loc[timestamp, 'portfolio_value'] = self.current_cash + self.positions_df.loc[timestamp, 'holdings_value']

            last_price = current_close_price


        return self.calculate_performance_metrics()

    def calculate_performance_metrics(self):
        """Calculates performance metrics for the backtest."""

        final_portfolio_value = self.positions_df['portfolio_value'].iloc[-1] if not self.positions_df.empty else self.initial_capital
        total_pnl_from_trades = self.positions_df['trade_pnl'].sum(skipna=True) # Sum of PnL from closed trades

        # Verify PnL: Final Portfolio Value - Initial Capital should roughly match sum of trade_pnl
        # (differences can arise from open position value)
        # print(f"Debug: Final Portfolio Value: {final_portfolio_value}, Initial: {self.initial_capital}, Sum of Trade PnL: {total_pnl_from_trades}")


        num_closed_trades = 0
        winning_trades = 0
        losing_trades = 0

        # A "trade" is a round trip (e.g. buy_long then sell_long, or sell_short then cover_short)
        # We can count based on PnL entries in trade_log
        for trade in self.trade_log:
            if trade.get('pnl', 0) != 0 : # A non-zero PnL means a trade was closed
                num_closed_trades +=1
                if trade['pnl'] > 0:
                    winning_trades +=1
                elif trade['pnl'] < 0:
                    losing_trades +=1

        win_rate = (winning_trades / num_closed_trades * 100) if num_closed_trades > 0 else 0

        # Max Drawdown calculation
        portfolio_values = self.positions_df['portfolio_value']
        peak = portfolio_values.expanding(min_periods=1).max()
        drawdown = (portfolio_values - peak) / peak
        max_drawdown = drawdown.min() * 100 # as percentage

        # Sharpe Ratio (simple version, assuming risk-free rate = 0)
        returns = portfolio_values.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if not returns.empty and returns.std() !=0 else 0 # Annualized for daily data
        # Note: 252 is a common annualization factor for daily stock returns. This might need adjustment based on data frequency.


        return {
            "initial_capital": self.initial_capital,
            "final_portfolio_value": final_portfolio_value,
            "total_pnl_realized": total_pnl_from_trades, # PnL from closed trades
            "total_return_pct": ((final_portfolio_value / self.initial_capital) - 1) * 100 if self.initial_capital > 0 else 0,
            "num_closed_trades": num_closed_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": win_rate,
            "max_drawdown_pct": max_drawdown if max_drawdown is not None else 0, # handle case where no trades or values
            "sharpe_ratio": sharpe_ratio if not np.isnan(sharpe_ratio) else 0,
            "trade_log": self.trade_log
            # "portfolio_history_df": self.positions_df[['cash', 'holdings_value', 'portfolio_value']] # Can be returned for plotting
        }

# Example Usage
# if __name__ == '__main__':
#     from strategies.base_strategy import BaseStrategy # Assuming base_strategy.py is in strategies folder
#     class TestStrategy(BaseStrategy):
#         def generate_signals(self, ohlcv_data):
#             signals = ['hold'] * len(ohlcv_data)
#             if len(signals) > 2 : signals[1] = 'buy'  # Buy at index 1
#             if len(signals) > 5 : signals[4] = 'sell' # Sell at index 4 (close long / open short)
#             # if len(signals) > 7 : signals[6] = 'buy'  # Cover short at index 6 / open long
#             # if len(signals) > 9 : signals[8] = 'sell' # Close long at index 8
#             return signals

#     # Create dummy data
#     dates = pd.to_datetime([f'2023-01-{d:02d}' for d in range(1, 11)])
#     data = pd.DataFrame({
#         'open':  [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
#         'high':  [102, 103, 104, 105, 106, 107, 108, 109, 110, 111],
#         'low':   [99,  100, 101, 102, 103, 104, 105, 106, 107, 108],
#         'close': [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
#         'volume':[1000]*10
#     }, index=dates)

#     strategy = TestStrategy()
#     # Test 1: Long only
#     backtester_long = Backtester(data.copy(), strategy, initial_capital=10000, default_position_size=10, commission_bps=10, slippage_bps=5)
#     results_long = backtester_long.run()
#     print("--- Long Only Scenario (Buy at 102, Sell at 105) ---")
#     for key, val in results_long.items():
#         if key != 'trade_log': print(f"{key}: {val}")
#     # print("Trade Log (Long):", results_long['trade_log'])
#     # print(results_long['portfolio_history_df'].tail())


#     class TestShortStrategy(BaseStrategy):
#         def generate_signals(self, ohlcv_data):
#             signals = ['hold'] * len(ohlcv_data)
#             if len(signals) > 2 : signals[1] = 'sell' # Sell short
#             if len(signals) > 5 : signals[4] = 'buy'  # Cover short
#             return signals

#     strategy_short = TestShortStrategy()
#     backtester_short = Backtester(data.copy(), strategy_short, initial_capital=10000, default_position_size=10, commission_bps=10, slippage_bps=5)
#     results_short = backtester_short.run()
#     print("\n--- Short Only Scenario (Sell short at 102, Cover at 105) ---")
#     for key, val in results_short.items():
#         if key != 'trade_log': print(f"{key}: {val}")
#     # print("Trade Log (Short):", results_short['trade_log'])
#     # print(results_short['portfolio_history_df'].tail())

#     # Test execution_price_type = 'next_open'
#     # Buy at open of index 2 (102), Sell at open of index 5 (105)
#     backtester_next_open = Backtester(data.copy(), strategy, initial_capital=10000, default_position_size=10,
#                                     commission_bps=10, slippage_bps=5, execution_price_type='next_open')
#     results_next_open = backtester_next_open.run()
#     print("\n--- Long Only (Next Open Execution) ---")
#     for key, val in results_next_open.items():
#         if key != 'trade_log': print(f"{key}: {val}")
#     # print("Trade Log (Next Open):", results_next_open['trade_log'])
#     # print(results_next_open['portfolio_history_df'].tail())
