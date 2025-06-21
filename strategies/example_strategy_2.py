# strategies/example_strategy_2.py
from .base_strategy import BaseStrategy
from core.smc_concepts import identify_fair_value_gaps
import pandas as pd

class ExampleStrategy2(BaseStrategy):
    """
    Strategy based on Fair Value Gap (FVG) entry.
    - Identifies bullish and bearish FVGs.
    - Enters long when price retraces into a bullish FVG.
    - Enters short when price retraces into a bearish FVG.
    Simplified exit: holds until an opposite signal or end of data.
    """
    def __init__(self, params=None):
        super().__init__(params)
        # proximity_factor could define how deep into FVG price must go
        self.entry_fill_ratio = self.params.get('entry_fill_ratio', 0.1) # e.g., enter if 10% of FVG is touched

    def generate_signals(self, ohlcv_data: pd.DataFrame):
        """
        Generates trading signals based on Fair Value Gaps.

        Args:
            ohlcv_data (pd.DataFrame): DataFrame with OHLCV data.
                                       Must have 'open', 'high', 'low', 'close' columns.
                                       Index should be datetime.
        Returns:
            list: A list of signals ('buy', 'sell', 'hold').
        """
        signals = ['hold'] * len(ohlcv_data)
        if len(ohlcv_data) < 3: # Need at least 3 candles for FVG
            return signals

        if not isinstance(ohlcv_data.index, pd.DatetimeIndex):
            try:
                ohlcv_data.index = pd.to_datetime(ohlcv_data.index)
            except Exception as e:
                print(f"Error converting index to DatetimeIndex in ExampleStrategy2: {e}")
                return signals

        fair_value_gaps = identify_fair_value_gaps(ohlcv_data)

        # Keep track of active (unfilled or partially filled) FVGs
        # For simplicity, let's consider the latest relevant FVG
        active_bullish_fvg = None
        active_bearish_fvg = None
        current_position = 'none' # 'long', 'short', 'none'

        for i in range(len(ohlcv_data)):
            current_candle = ohlcv_data.iloc[i]
            current_time = ohlcv_data.index[i]

            # Update active FVGs based on current time
            # FVG is defined by 3 candles; its existence is known after the 3rd candle closes.
            # The FVG itself is "on" the second candle of the triplet.
            for fvg in fair_value_gaps:
                # An FVG is valid if the current candle is after the FVG's formation (end_time of FVG)
                if fvg.end_time < current_time: # FVG is formed and known
                    if fvg.is_bullish: # Potential support
                        active_bullish_fvg = fvg
                    else: # Potential resistance
                        active_bearish_fvg = fvg

            # Entry Logic
            if current_position == 'none' or current_position == 'short': # Looking to buy
                if active_bullish_fvg and not active_bullish_fvg.filled:
                    # Bullish FVG: Top is fvg.high (c1.low), Bottom is fvg.low (c3.high)
                    # Price must dip into this FVG.
                    entry_target_price = active_bullish_fvg.high - (active_bullish_fvg.high - active_bullish_fvg.low) * self.entry_fill_ratio
                    if current_candle['low'] <= entry_target_price and current_candle['low'] >= active_bullish_fvg.low : # Price enters FVG
                        signals[i] = 'buy'
                        current_position = 'long'
                        active_bullish_fvg.filled_time = current_time # Mark as (at least partially) filled
                        active_bearish_fvg = None # Invalidate counter FVGs
                        # print(f"Debug BUY FVG at {current_time}, FVG: {active_bullish_fvg}")
                        continue

            if current_position == 'none' or current_position == 'long': # Looking to sell
                if active_bearish_fvg and not active_bearish_fvg.filled:
                    # Bearish FVG: Top is fvg.high (c3.low), Bottom is fvg.low (c1.high)
                    # Price must rally into this FVG.
                    entry_target_price = active_bearish_fvg.low + (active_bearish_fvg.high - active_bearish_fvg.low) * self.entry_fill_ratio
                    if current_candle['high'] >= entry_target_price and current_candle['high'] <= active_bearish_fvg.high: # Price enters FVG
                        signals[i] = 'sell'
                        current_position = 'short'
                        active_bearish_fvg.filled_time = current_time # Mark as (at least partially) filled
                        active_bullish_fvg = None # Invalidate counter FVGs
                        # print(f"Debug SELL FVG at {current_time}, FVG: {active_bearish_fvg}")
                        continue

            # Simplified Exit (similar to OB strategy, if opposite FVG appears)
            if current_position == 'long' and active_bearish_fvg and not active_bearish_fvg.filled:
                # If a new Bearish FVG forms and price touches it, consider exiting.
                entry_target_price = active_bearish_fvg.low + (active_bearish_fvg.high - active_bearish_fvg.low) * self.entry_fill_ratio
                if current_candle['high'] >= entry_target_price:
                    signals[i] = 'sell' # Signal to close long
                    current_position = 'none'
                    active_bearish_fvg.filled_time = current_time
                    active_bullish_fvg = None
                    # print(f"Debug EXIT LONG FVG at {current_time} due to new Bearish FVG")
                    continue

            if current_position == 'short' and active_bullish_fvg and not active_bullish_fvg.filled:
                # If a new Bullish FVG forms and price touches it, consider exiting.
                entry_target_price = active_bullish_fvg.high - (active_bullish_fvg.high - active_bullish_fvg.low) * self.entry_fill_ratio
                if current_candle['low'] <= entry_target_price:
                    signals[i] = 'buy' # Signal to close short
                    current_position = 'none'
                    active_bullish_fvg.filled_time = current_time
                    active_bearish_fvg = None
                    # print(f"Debug EXIT SHORT FVG at {current_time} due to new Bullish FVG")
                    continue
        return signals
