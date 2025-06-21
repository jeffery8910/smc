# Flask App
from flask import Flask, render_template, request, jsonify
import os
import pandas as pd # Required for read_csv in load_csv_data, and for backtester
import traceback # For detailed error logging

from core.backtester import Backtester
from strategies import available_strategies
from core.market_data import load_csv_data
# from core.smc_concepts import _ensure_datetime_index_and_columns # This is internal to smc_concepts

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    strategy_names = list(available_strategies.keys())
    return render_template('index.html', strategies=strategy_names)

@app.route('/backtest', methods=['POST'])
def run_backtest_route(): # Renamed to avoid conflict with any potential 'backtest' variable
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    strategy_name = request.form.get('strategy')
    if not strategy_name:
        return jsonify({'error': 'No strategy selected'}), 400
    if strategy_name not in available_strategies:
        return jsonify({'error': f'Invalid strategy selected: {strategy_name}'}), 400

    # Optional parameters from form (with defaults)
    try:
        initial_capital = float(request.form.get('initial_capital', 100000))
        commission_bps = float(request.form.get('commission_bps', 2))
        slippage_bps = float(request.form.get('slippage_bps', 1))
        default_position_size = float(request.form.get('default_position_size', 1))
        execution_price_type = request.form.get('execution_price_type', 'close')
    except ValueError:
        return jsonify({'error': 'Invalid numerical input for backtest parameters.'}), 400


    if file:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)

        try:
            # Load data using the function from market_data.py
            # It handles various CSV date formats and standardizes columns.
            ohlcv_df = load_csv_data(filename)
            if ohlcv_df is None:
                return jsonify({'error': 'Failed to load or process CSV data. Check column names (timestamp, open, high, low, close) and data format.'}), 400

            # Ensure data has DatetimeIndex and required columns (double check, though load_csv_data should handle much of it)
            if not isinstance(ohlcv_df.index, pd.DatetimeIndex):
                 ohlcv_df.index = pd.to_datetime(ohlcv_df.index)

            required_cols = ['open', 'high', 'low', 'close']
            if not all(col in ohlcv_df.columns for col in required_cols):
                return jsonify({'error': f'Loaded data is missing one or more required columns: {required_cols}. Found: {ohlcv_df.columns.tolist()}'}),400


            StrategyClass = available_strategies.get(strategy_name)
            if not StrategyClass: # Should have been caught earlier, but good to double check
                return jsonify({'error': f'Strategy class for {strategy_name} not found.'}), 500

            strategy_instance = StrategyClass() # Instantiate the strategy

            backtester = Backtester(
                ohlcv_data=ohlcv_df,
                strategy_instance=strategy_instance,
                initial_capital=initial_capital,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
                default_position_size=default_position_size,
                execution_price_type=execution_price_type
            )
            results = backtester.run()

            # Convert Timestamps in trade_log to string for JSON serialization
            if 'trade_log' in results:
                for trade in results['trade_log']:
                    if 'timestamp' in trade and isinstance(trade['timestamp'], pd.Timestamp):
                        trade['timestamp'] = trade['timestamp'].isoformat()

            return jsonify(results)

        except ValueError as ve: # Catch specific ValueErrors from Backtester or data loading
            app.logger.error(f"ValueError during backtest: {ve}\n{traceback.format_exc()}")
            return jsonify({'error': f"Configuration or Data Error: {str(ve)}"}), 400
        except Exception as e:
            app.logger.error(f"Exception during backtest: {e}\n{traceback.format_exc()}")
            return jsonify({'error': f'An unexpected error occurred during backtesting: {str(e)}'}), 500
        finally:
            # Clean up uploaded file
            if os.path.exists(filename):
                os.remove(filename)

    return jsonify({'error': 'File processing failed.'}), 500


if __name__ == '__main__':
    app.run(debug=True)
