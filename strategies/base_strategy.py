# strategies/base_strategy.py
from abc import ABC, abstractmethod

class BaseStrategy(ABC):
    """
    Abstract base class for all trading strategies.
    """
    def __init__(self, params=None):
        self.params = params if params else {}

    @abstractmethod
    def generate_signals(self, ohlcv_data):
        """
        Generates trading signals based on the provided OHLCV data.

        Args:
            ohlcv_data (pd.DataFrame): DataFrame with columns like
                                       ['timestamp', 'open', 'high', 'low', 'close', 'volume']
                                       or a list of candle objects.

        Returns:
            list: A list of signals (e.g., 'buy', 'sell', 'hold') or more complex signal objects.
                  Each signal should correspond to a data point in ohlcv_data.
        """
        pass

    def set_parameters(self, params):
        """
        Allows setting or updating strategy parameters.
        """
        self.params.update(params)

    def get_parameters(self):
        """
        Returns the current strategy parameters.
        """
        return self.params

    def __str__(self):
        return self.__class__.__name__
