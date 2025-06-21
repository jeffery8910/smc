# core/smc_concepts.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import pandas as pd

class StructureType(Enum):
    HIGH = "High"
    LOW = "Low"
    BOS_HIGH = "Break of Structure High" # Bullish BoS
    BOS_LOW = "Break of Structure Low"   # Bearish BoS
    CHoCH_HIGH = "Change of Character High" # Bearish CHoCH (after HH, makes LL)
    CHoCH_LOW = "Change of Character Low"   # Bullish CHoCH (after LL, makes HH)

class Trend(Enum):
    UPTREND = "Uptrend"
    DOWNTREND = "Downtrend"
    SIDEWAYS = "Sideways"
    UNCERTAIN = "Uncertain"

@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_bullish(self) -> bool:
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

@dataclass
class MarketStructurePoint:
    timestamp: datetime
    price: float
    type: StructureType
    wick_price: float = None # Price at the extreme of the wick for highs/lows

@dataclass
class OrderBlock:
    start_time: datetime # Timestamp of the candle forming the OB
    end_time: datetime   # Same as start_time for a single candle OB
    high: float          # High price of the OB candle
    low: float           # Low price of the OB candle
    volume: float = None
    is_bullish: bool     # True: Bullish OB (a bearish candle expected to act as support for future up-move)
                         # False: Bearish OB (a bullish candle expected to act as resistance for future down-move)
    mitigated_time: datetime = None
    mitigated_by_wick: bool = False

    @property
    def mitigated(self) -> bool:
        return self.mitigated_time is not None

@dataclass
class FairValueGap:
    start_time: datetime # Timestamp of the first candle in the 3-candle FVG pattern
    end_time: datetime   # Timestamp of the third candle in the 3-candle FVG pattern (FVG is confirmed after this candle closes)
    high: float          # Top of the FVG zone. For Bullish FVG: c1.low. For Bearish FVG: c3.low.
    low: float           # Bottom of the FVG zone. For Bullish FVG: c3.high. For Bearish FVG: c1.high.
    is_bullish: bool     # True if it's a price void upwards (gap between c1.low and c3.high, expecting support)
                         # False for downwards (gap between c1.high and c3.low, expecting resistance)
    filled_time: datetime = None
    partially_filled_level: float = None

    @property
    def filled(self) -> bool:
        return self.filled_time is not None

@dataclass
class LiquidityPoint:
    timestamp: datetime
    price: float
    is_high: bool # True for liquidity above a high, False for liquidity below a low
    taken_time: datetime = None

    @property
    def taken(self) -> bool:
        return self.taken_time is not None


# --- Helper functions to identify SMC concepts from OHLCV data (usually pandas DataFrame) ---

def _ensure_datetime_index_and_columns(ohlcv_data: pd.DataFrame) -> pd.DataFrame:
    """
    Ensures DataFrame has a DatetimeIndex and standard OHLC column names.
    Tries to convert 'timestamp', 'time', or 'date' columns to index if current index is not datetime.
    """
    df = ohlcv_data.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        time_cols = ['timestamp', 'time', 'Date', 'date'] # Common time column names
        converted = False
        for col_name in time_cols:
            if col_name in df.columns:
                try:
                    df[col_name] = pd.to_datetime(df[col_name])
                    df = df.set_index(col_name)
                    converted = True
                    break
                except Exception:
                    continue # Try next common column name
        if not converted:
            print(f"Warning: Could not automatically convert index to DatetimeIndex. Current index type: {type(df.index)}")
            # Attempt to convert the existing index if it's not already DatetimeIndex
            try:
                 df.index = pd.to_datetime(df.index)
            except Exception as e:
                 print(f"Warning: Failed to convert existing index to DatetimeIndex. {e}")


    # Standardize column names (case-insensitive check)
    rename_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if col_lower == 'open': rename_map[col] = 'open'
        elif col_lower == 'high': rename_map[col] = 'high'
        elif col_lower == 'low': rename_map[col] = 'low'
        elif col_lower == 'close': rename_map[col] = 'close'
        elif col_lower == 'volume': rename_map[col] = 'volume'
    df = df.rename(columns=rename_map)

    # Check for essential columns after renaming
    essential_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in essential_cols):
        print(f"Error: Essential OHLC columns missing after attempting to standardize. Found: {df.columns.tolist()}")
        # Potentially raise an error here or return None, as strategies will fail
        raise ValueError(f"Essential OHLC columns missing. Required: {essential_cols}")

    return df


def _get_timestamp_from_index(idx_val):
    """Helper to convert an index value to a pandas Timestamp (which is like datetime)."""
    if isinstance(idx_val, pd.Timestamp):
        return idx_val
    try:
        return pd.to_datetime(idx_val)
    except ValueError:
        print(f"Warning: Could not convert index value {idx_val} to Timestamp.")
        return pd.Timestamp.now() # Fallback, though not ideal

def identify_order_blocks(ohlcv_data: pd.DataFrame, strength_factor=1.2) -> list[OrderBlock]:
    """
    Identifies Order Blocks.
    - Bullish OB: A bearish candle preceding a strong bullish move.
    - Bearish OB: A bullish candle preceding a strong bearish move.
    The OB itself is the candle *before* the strong move.
    """
    order_blocks = []
    try:
        df = _ensure_datetime_index_and_columns(ohlcv_data)
    except ValueError as e:
        print(f"Error during data preparation in identify_order_blocks: {e}")
        return order_blocks

    if not isinstance(df.index, pd.DatetimeIndex):
        print("Error: DataFrame index is not DatetimeIndex in identify_order_blocks after _ensure_datetime_index_and_columns. Cannot proceed.")
        return order_blocks

    for i in range(1, len(df)):
        prev_candle = df.iloc[i-1]
        curr_candle = df.iloc[i]

        prev_ts = _get_timestamp_from_index(df.index[i-1])

        # Bullish Order Block (previous candle was bearish, current is strongly bullish)
        is_prev_bearish = prev_candle['close'] < prev_candle['open']
        is_curr_bullish = curr_candle['close'] > curr_candle['open']

        prev_body = abs(prev_candle['open'] - prev_candle['close'])
        curr_body = abs(curr_candle['open'] - curr_candle['close'])

        # Criteria for strong bullish move following a bearish candle
        if is_prev_bearish and is_curr_bullish and \
           curr_candle['close'] > prev_candle['high'] and \
           curr_body > prev_body * strength_factor:
            order_blocks.append(OrderBlock(
                start_time=prev_ts,
                end_time=prev_ts,
                high=prev_candle['high'],
                low=prev_candle['low'],
                volume=prev_candle.get('volume'),
                is_bullish=True # The bearish prev_candle is the Bullish OB
            ))

        # Bearish Order Block (previous candle was bullish, current is strongly bearish)
        is_prev_bullish = prev_candle['close'] > prev_candle['open']
        is_curr_bearish = curr_candle['close'] < curr_candle['open']

        if is_prev_bullish and is_curr_bearish and \
           curr_candle['low'] < prev_candle['low'] and \
           curr_body > prev_body * strength_factor:
            order_blocks.append(OrderBlock(
                start_time=prev_ts,
                end_time=prev_ts,
                high=prev_candle['high'],
                low=prev_candle['low'],
                volume=prev_candle.get('volume'),
                is_bullish=False # The bullish prev_candle is the Bearish OB
            ))

    return order_blocks


def identify_fair_value_gaps(ohlcv_data: pd.DataFrame) -> list[FairValueGap]:
    """
    Identifies Fair Value Gaps (FVGs).
    - Bullish FVG: Low of candle 0 > High of candle 2. FVG zone is [c2.high, c0.low].
    - Bearish FVG: High of candle 0 < Low of candle 2. FVG zone is [c0.high, c2.low].
    The FVG is formed after candle 2 closes, relating to the price action of candles 0, 1, and 2.
    """
    fvgs = []
    try:
        df = _ensure_datetime_index_and_columns(ohlcv_data)
    except ValueError as e:
        print(f"Error during data preparation in identify_fair_value_gaps: {e}")
        return fvgs

    if not isinstance(df.index, pd.DatetimeIndex):
        print("Error: DataFrame index is not DatetimeIndex in identify_fair_value_gaps after _ensure_datetime_index_and_columns. Cannot proceed.")
        return fvgs

    if len(df) < 3:
        return fvgs

    for i in range(len(df) - 2):
        c0 = df.iloc[i]      # First candle
        # c1 = df.iloc[i+1]  # Middle candle (where the visual gap is)
        c2 = df.iloc[i+2]  # Third candle

        c0_ts = _get_timestamp_from_index(df.index[i])
        c2_ts = _get_timestamp_from_index(df.index[i+2]) # FVG is confirmed after c2 closes

        # Bullish FVG: c0.low > c2.high (gap between c0.low and c2.high)
        if c0['low'] > c2['high']:
            fvgs.append(FairValueGap(
                start_time=c0_ts,    # Start of the 3-candle pattern
                end_time=c2_ts,      # FVG confirmed after c2
                high=c0['low'],      # Top of the bullish FVG zone
                low=c2['high'],      # Bottom of the bullish FVG zone
                is_bullish=True
            ))

        # Bearish FVG: c0.high < c2.low (gap between c0.high and c2.low)
        elif c0['high'] < c2['low']:
            fvgs.append(FairValueGap(
                start_time=c0_ts,
                end_time=c2_ts,
                high=c2['low'],      # Top of the bearish FVG zone
                low=c0['high'],      # Bottom of the bearish FVG zone
                is_bullish=False
            ))
    return fvgs

# Placeholder for BoS/CHoCH - requires swing point identification first
def identify_market_structure(ohlcv_data: pd.DataFrame, swing_lookback=5) -> list[MarketStructurePoint]:
    return []

def identify_liquidity_points(ohlcv_data: pd.DataFrame, lookback=10) -> list[LiquidityPoint]:
    return []


# Example usage:
# if __name__ == '__main__':
#     # Sample Data
#     data = {
#         'timestamp': pd.to_datetime([
#             '2023-01-01 09:00', '2023-01-01 09:05', '2023-01-01 09:10', # Bullish OB
#             '2023-01-01 09:15', '2023-01-01 09:20', '2023-01-01 09:25', # Bearish OB
#             '2023-01-01 09:30', '2023-01-01 09:35', '2023-01-01 09:40', # Bullish FVG
#             '2023-01-01 09:45', '2023-01-01 09:50', '2023-01-01 09:55'  # Bearish FVG
#         ]),
#         'open':  [100, 98, 100,  105, 107, 105,  110, 112, 115,  120, 118, 115],
#         'high':  [101, 99, 103,  106, 108, 106,  111, 114, 118,  121, 119, 116],
#         'low':   [99,  97, 99,   104, 106, 103,  109, 110, 113,  119, 117, 113],
#         'close': [98,  102,102,  107, 104, 104,  110.5,113, 117,  118, 116, 114],
#         'volume':[100, 200,150,  100, 200, 150,  100, 100, 250,  100, 200, 150]
#     }
#     df = pd.DataFrame(data).set_index('timestamp')

#     print("--- Order Blocks ---")
#     # Expected Bullish OB: candle at 09:00 (high=101, low=99) because 09:05 is strong bullish move
#     # Expected Bearish OB: candle at 09:15 (high=106, low=104) because 09:20 is strong bearish move
#     obs = identify_order_blocks(df.copy()) # Pass a copy
#     for ob in obs:
#         print(ob)

#     print("\n--- Fair Value Gaps ---")
#     # Expected Bullish FVG: candles 09:30 (c0), 09:35 (c1), 09:40 (c2)
#     # c0.low = 109, c2.high = 118. This is not a bullish FVG. Let's adjust data for a clear one.
#     # Bullish FVG: c0.low > c2.high. Example: c0(L=110), c1, c2(H=108). FVG [108,110]
#     # Bearish FVG: c0.high < c2.low. Example: c0(H=115), c1, c2(L=117). FVG [115,117]

#     data_fvg = {
#         'timestamp': pd.to_datetime([
#             '2023-02-01 10:00', '2023-02-01 10:05', '2023-02-01 10:10', # Bullish FVG
#             '2023-02-01 10:15', '2023-02-01 10:20', '2023-02-01 10:25'  # Bearish FVG
#         ]),
#         # Bullish FVG: c0.low (110) > c2.high (108) -> FVG: low=108, high=110
#         'open':  [109, 111, 107,  116, 114, 118],
#         'high':  [112, 112, 108,  115, 113, 119], # c2.high for Bullish = 108, c0.high for Bearish = 115
#         'low':   [110, 109, 106,  114, 112, 117], # c0.low for Bullish = 110, c2.low for Bearish = 117
#         'close': [111, 110, 107.5,114.5,112.5,118],
#         'volume':[100, 50,  100,  100, 60,  100]
#     }
#     df_fvg = pd.DataFrame(data_fvg).set_index('timestamp')
#     fvgs = identify_fair_value_gaps(df_fvg.copy()) # Pass a copy
#     for fvg in fvgs:
#         print(fvg)
#
#     # Test with non-datetime index and non-standard column names
#     data_alt_format = {
#         'Time': ['2023-03-01 10:00', '2023-03-01 10:05', '2023-03-01 10:10'],
#         'Open':  [109, 111, 107],
#         'High':  [112, 112, 108],
#         'Low':   [110, 109, 106],
#         'Close': [111, 110, 107.5],
#         'Volume':[100, 50,  100]
#     }
#     df_alt = pd.DataFrame(data_alt_format)
#     print("\n--- FVGs with alternative format ---")
#     fvgs_alt = identify_fair_value_gaps(df_alt.copy())
#     for fvg in fvgs_alt:
#         print(fvg)
#
#     print("\n--- OBs with alternative format ---")
#     # OB Data: prev bearish (100->98), curr bullish strong (98->102) -> OB is 100,98,99,101
#     data_ob_alt = {
#         'Date': pd.to_datetime(['2023-04-01 09:00', '2023-04-01 09:05']),
#         'OPEN': [100, 98],
#         'HIGH': [101, 103], # curr.close (102) > prev.high (101)
#         'LOW':  [98, 97],   # Using 'OPEN', 'HIGH', 'LOW', 'CLOSE' for column names
#         'CLOSE':[98, 102],  # prev body = 2, curr body = 4. 4 > 2 * 1.2 (2.4)
#     }
#     df_ob_alt = pd.DataFrame(data_ob_alt)
#     obs_alt = identify_order_blocks(df_ob_alt.copy())
#     for ob in obs_alt:
#         print(ob)
#
#
#     # Test with missing columns (should raise ValueError or print error and return empty)
#     data_missing_cols = {
#         'timestamp': pd.to_datetime(['2023-01-01 09:00']),
#         'open': [100],
#         # 'high': [101], # Missing high
#         'low': [99],
#         'close': [100]
#     }
#     df_missing = pd.DataFrame(data_missing_cols).set_index('timestamp')
#     print("\n--- Test with missing columns (FVG) ---")
#     fvgs_missing = identify_fair_value_gaps(df_missing.copy())
#     print(f"FVGs found (missing cols): {len(fvgs_missing)}")
#
#     print("\n--- Test with missing columns (OB) ---")
#     obs_missing = identify_order_blocks(df_missing.copy())
#     print(f"OBs found (missing cols): {len(obs_missing)}")
#
