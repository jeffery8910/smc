# strategies/example_strategy_1.py
from .base_strategy import BaseStrategy
from core.smc_concepts import identify_order_blocks
import pandas as pd

class ExampleStrategy1(BaseStrategy):
    """
    Strategy based on Order Block (OB) entry.
    - Identifies bullish and bearish OBs.
    - Enters long when price revisits a bullish OB.
    - Enters short when price revisits a bearish OB.
    Simplified exit: holds until an opposite signal or end of data.
    """
    def __init__(self, params=None):
        super().__init__(params)
        self.proximity_factor = self.params.get('proximity_factor', 0.001) # e.g., 0.1% of price for proximity

    def generate_signals(self, ohlcv_data: pd.DataFrame):
        """
        Generates trading signals based on Order Blocks.

        Args:
            ohlcv_data (pd.DataFrame): DataFrame with OHLCV data.
                                       Must have 'open', 'high', 'low', 'close' columns.
                                       Index should be datetime.

        Returns:
            list: A list of signals ('buy', 'sell', 'hold').
        """
        signals = ['hold'] * len(ohlcv_data)
        if len(ohlcv_data) < 2: # Need at least 2 candles for basic OB logic
            return signals

        # Ensure datetime index for OB identification compatibility
        if not isinstance(ohlcv_data.index, pd.DatetimeIndex):
            try:
                ohlcv_data.index = pd.to_datetime(ohlcv_data.index)
            except Exception as e:
                # If conversion fails, cannot proceed with time-based concepts reliably
                print(f"Error converting index to DatetimeIndex in ExampleStrategy1: {e}")
                return signals


        order_blocks = identify_order_blocks(ohlcv_data)

        active_bullish_ob = None
        active_bearish_ob = None
        current_position = 'none' # 'long', 'short', 'none'

        for i in range(len(ohlcv_data)):
            current_candle = ohlcv_data.iloc[i]
            current_time = ohlcv_data.index[i]

            # Check for new OBs formed up to the *previous* candle,
            # as current candle's OB would be based on its close.
            # OBs are identified based on past completed candles.
            # For simplicity, we check if current candle's time matches an OB's start time.
            # A more robust approach would be to filter OBs whose start_time <= current_time.

            for ob in order_blocks:
                if ob.start_time <= current_time: # OB is known at this point
                    if ob.is_bullish and (active_bullish_ob is None or ob.start_time > active_bullish_ob.start_time):
                        # This is a bullish OB (typically a prior bearish candle before up-move)
                        # We are looking to buy when price returns to it.
                        # The OB itself is the bearish candle. The expectation is it holds as support.
                        active_bullish_ob = ob
                    elif not ob.is_bullish and (active_bearish_ob is None or ob.start_time > active_bearish_ob.start_time):
                        # This is a bearish OB (typically a prior bullish candle before down-move)
                        # We are looking to sell when price returns to it.
                        active_bearish_ob = ob

            # Entry logic
            if current_position == 'none' or current_position == 'short':
                if active_bullish_ob:
                    # Price enters the zone of the bullish OB (last bearish candle body)
                    # Condition: current low dips into the bullish OB's range (high-low of the bearish candle)
                    # or is very close to its high.
                    # The bullish OB is a down candle, so its high is the entry trigger level.
                    if current_candle['low'] <= active_bullish_ob.high and \
                       current_candle['high'] >= active_bullish_ob.low: # Price touches the OB
                        signals[i] = 'buy'
                        current_position = 'long'
                        active_bullish_ob = None # Consume OB
                        active_bearish_ob = None # Invalidate counter OBs
                        # print(f"Debug BUY at {current_time}, OB: {active_bullish_ob}")
                        continue # Move to next candle after action

            if current_position == 'none' or current_position == 'long':
                if active_bearish_ob:
                    # Price enters the zone of the bearish OB (last bullish candle body)
                    # Condition: current high reaches into the bearish OB's range
                    # or is very close to its low.
                    # The bearish OB is an up candle, so its low is the entry trigger level.
                    if current_candle['high'] >= active_bearish_ob.low and \
                       current_candle['low'] <= active_bearish_ob.high: # Price touches the OB
                        signals[i] = 'sell'
                        current_position = 'short'
                        active_bearish_ob = None # Consume OB
                        active_bullish_ob = None # Invalidate counter OBs
                        # print(f"Debug SELL at {current_time}, OB: {active_bearish_ob}")
                        continue # Move to next candle after action

            # Simple Exit (if an opposite OB appears and we are in a trade)
            # This is a very basic exit, actual SMC exits are more nuanced (e.g. targeting liquidity, FVG fill, CHoCH)
            if current_position == 'long' and active_bearish_ob:
                 # If a new bearish OB forms while long, and price is near it, consider closing.
                 # For simplicity, if a bearish OB is now the most recent, exit long.
                 if current_candle['high'] >= active_bearish_ob.low:
                    signals[i] = 'sell' # Signal to close long
                    current_position = 'none'
                    active_bearish_ob = None
                    active_bullish_ob = None
                    # print(f"Debug EXIT LONG at {current_time} due to new Bearish OB")
                    continue

            if current_position == 'short' and active_bullish_ob:
                # If a new bullish OB forms while short, and price is near it, consider closing.
                if current_candle['low'] <= active_bullish_ob.high:
                    signals[i] = 'buy' # Signal to close short
                    current_position = 'none'
                    active_bullish_ob = None
                    active_bearish_ob = None
                    # print(f"Debug EXIT SHORT at {current_time} due to new Bullish OB")
                    continue
        return signals
