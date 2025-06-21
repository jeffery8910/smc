# strategies/__init__.py
# This file can be used to easily import strategies or define a list of available strategies.

from .example_strategy_1 import ExampleStrategy1
from .example_strategy_2 import ExampleStrategy2

available_strategies = {
    "OrderBlockEntry": ExampleStrategy1, # Renaming for clarity
    "FairValueGapEntry": ExampleStrategy2, # Renaming for clarity
}
