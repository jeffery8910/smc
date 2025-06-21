# core/market_data.py
import pandas as pd

def load_csv_data(file_path, time_column='timestamp', open_col='open', high_col='high', low_col='low', close_col='close', volume_col='volume'):
    """
    Loads OHLCV data from a CSV file into a pandas DataFrame.
    It tries to automatically parse a datetime column.

    Args:
        file_path (str): The path to the CSV file.
        time_column (str): The name of the column containing timestamp information.
        open_col (str): Name of the open price column.
        high_col (str): Name of the high price column.
        low_col (str): Name of the low price column.
        close_col (str): Name of the close price column.
        volume_col (str): Name of the volume column.


    Returns:
        pd.DataFrame: DataFrame with OHLCV data, with a datetime index.
                      Columns will be renamed to ['open', 'high', 'low', 'close', 'volume'].
                      Returns None if loading fails or essential columns are missing.
    """
    try:
        # Attempt to infer datetime format
        df = pd.read_csv(file_path, parse_dates=[time_column])
        df.set_index(time_column, inplace=True)
    except Exception as e_time:
        try:
            # Fallback if specific time_column parsing fails, try without specific parsing
            df = pd.read_csv(file_path)
            if time_column in df.columns:
                df[time_column] = pd.to_datetime(df[time_column], infer_datetime_format=True)
                df.set_index(time_column, inplace=True)
            else:
                print(f"Warning: Time column '{time_column}' not found. Index not set to datetime.")
        except Exception as e_generic:
            print(f"Error loading CSV: {e_generic} (after initial error: {e_time})")
            return None

    # Rename columns to a standard format
    column_map = {
        open_col: 'open',
        high_col: 'high',
        low_col: 'low',
        close_col: 'close',
        volume_col: 'volume'
    }

    # Check if essential columns exist (using original names)
    required_original_cols = [open_col, high_col, low_col, close_col] # Volume is often optional
    missing_cols = [col for col in required_original_cols if col not in df.columns]
    if missing_cols:
        print(f"Error: Missing essential OHLC columns: {missing_cols}")
        return None

    df = df.rename(columns={k: v for k, v in column_map.items() if k in df.columns})

    # Ensure standard columns are present after renaming
    standard_cols = ['open', 'high', 'low', 'close']
    if not all(col in df.columns for col in standard_cols):
        print(f"Error: Standard OHLC columns are missing after renaming. Available: {df.columns.tolist()}")
        return None

    # Ensure numeric types for OHLCV columns
    for col in standard_cols + ['volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].isnull().any():
                print(f"Warning: Column '{col}' contains non-numeric data that was coerced to NaN.")

    df.sort_index(inplace=True) # Ensure data is sorted by time
    return df

# Example usage:
# if __name__ == '__main__':
#     # Create a dummy CSV for testing
#     data = {
#         'Date': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05', '2023-01-01 10:10']),
#         'Open': [100, 101, 102],
#         'High': [102, 103, 103],
#         'Low': [99, 100, 101],
#         'Close': [101, 102, 101.5],
#         'Volume': [1000, 1200, 1100]
#     }
#     dummy_df = pd.DataFrame(data)
#     dummy_df.to_csv('dummy_data.csv', index=False)

#     # Test loading
#     ohlcv = load_csv_data('dummy_data.csv', time_column='Date', open_col='Open', high_col='High', low_col='Low', close_col='Close', volume_col='Volume')
#     if ohlcv is not None:
#         print("Data loaded successfully:")
#         print(ohlcv.head())
#         print(ohlcv.info())
#     else:
#         print("Failed to load data.")
#
#     # Test with slightly different column names
#     data2 = {
#         'time': pd.to_datetime(['2023-01-01 10:00', '2023-01-01 10:05', '2023-01-01 10:10']),
#         'O': [100, 101, 102],
#         'H': [102, 103, 103],
#         'L': [99, 100, 101],
#         'C': [101, 102, 101.5],
#         'V': [1000, 1200, 1100]
#     }
#     dummy_df2 = pd.DataFrame(data2)
#     dummy_df2.to_csv('dummy_data2.csv', index=False)
#     ohlcv2 = load_csv_data('dummy_data2.csv', time_column='time', open_col='O', high_col='H', low_col='L', close_col='C', volume_col='V')
#     if ohlcv2 is not None:
#         print("\nData2 loaded successfully:")
#         print(ohlcv2.head())
#     else:
#         print("Failed to load data2.")
