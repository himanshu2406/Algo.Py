import pandas as pd
import vectorbt as vbt
from pandas.tseries.frequencies import to_offset
from pathlib import Path
import json
import uuid
from typing import Callable, Optional, List, Tuple, Dict, Any

from finstore.finstore import Finstore
from data.store.crypto_binance import store_crypto_binance
from data.store.indian_equity import store_indian_equity
from strategy.strategy_builder import StrategyBaseClass


class Backtester:
    """
    A class to backtest trading strategies on various financial markets.
    """

    BACKTEST_DIR = Path("database/backtest")
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    def __init__(
        self,
        market_name: str,
        symbol_list: List[str],
        timeframe: str,
        strategy_object: StrategyBaseClass,
        strategy_type: str,
        start_date: pd.Timestamp,
        end_date: pd.Timestamp,
        init_cash: float,
        fees: float,
        slippage: float,
        size: float,
        cash_sharing: bool,
        allow_partial: bool,
        progress_callback: Callable[[int, str], None],
        pair: Optional[str] = None,
    ) -> None:
        """
        Initialize the Backtester with the given parameters.

        Args:
            market_name (str): The market name, e.g., 'crypto_binance', 'indian_equity'.
            symbol_list (List[str]): List of symbols to backtest on.
            timeframe (str): The timeframe of the data, e.g., '1d', '1h'.
            strategy_object (StrategyBaseClass): An initialized strategy object.
            strategy_type (str): Type of strategy, e.g., 'single', 'multi'.
            start_date (pd.Timestamp): Start date of the backtest.
            end_date (pd.Timestamp): End date of the backtest.
            init_cash (float): Initial cash in the portfolio.
            fees (float): Transaction fees per trade.
            slippage (float): Slippage per trade.
            size (float): Size of each trade, interpreted based on size_type.
            cash_sharing (bool): Whether to share cash among assets.
            allow_partial (bool): Allow partial orders.
            progress_callback (Callable[[int, str], None]): Callback for progress updates.
            pair (Optional[str]): The trading pair, e.g., 'USDT', 'BTC' (for crypto).
        """
        self.market_name = market_name
        self.symbol_list = symbol_list
        self.pair = pair
        self.timeframe = timeframe
        self.strategy_object = strategy_object
        self.strategy_type = strategy_type
        self.start_date = pd.Timestamp(start_date)
        self.end_date = pd.Timestamp(end_date)
        self.init_cash = init_cash
        self.fees = fees
        self.slippage = slippage
        self.size = size
        self.cash_sharing = cash_sharing
        self.allow_partial = allow_partial
        self.progress_callback = progress_callback

        self.portfolio = self.backtest()

    def backtest(self) -> vbt.Portfolio:
        """
        Execute the backtest by fetching data, running the strategy, and simulating the portfolio.

        Returns:
            vbt.Portfolio: The simulated portfolio.
        """
        self.progress_callback(0, "Fetching data...")
        ohlcv_data = self.data_fetch()

        self.progress_callback(25, "Running strategy...")
        entries, exits, close_data, open_data = self.strategy_object.run(ohlcv_data)

        self.progress_callback(50, "Simulating portfolio...")
        pf = vbt.Portfolio.from_signals(
            close=close_data,
            entries=entries,
            exits=exits,
            direction='longonly',
            init_cash=self.init_cash,
            fees=self.fees,
            slippage=self.slippage,
            size=self.size,
            size_type = 2, 
            cash_sharing=self.cash_sharing,
            allow_partial=self.allow_partial,
            freq=self._convert_timeframe_to_freq(),
            # sim_start=self.start_date, # TODO : Implement this outside vbt , trim close data based on sim_start , sim_end
            # sim_end=self.end_date,
        )

        self.progress_callback(75, "Saving results...")

        self.progress_callback(100, "Backtest complete.")
        return pf

    def data_fetch(self) -> pd.DataFrame:
        """
        Fetch OHLCV data, fetching new data if necessary.

        Returns:
            pd.DataFrame: The fetched OHLCV data.
        """
        finstore = Finstore(market_name=self.market_name, timeframe=self.timeframe, pair=self.pair)
        ohlcv_dict = {}
        try:
            self.progress_callback(5, "Reading existing data...")
            ohlcv_dict = finstore.read.symbol_list(self.symbol_list)
            self._validate_data_dates(ohlcv_dict)
        except Exception as e:
            self.progress_callback(10, f"Data read failed: {str(e)}. Fetching new data...")
            print(f"Data read failed: {str(e)}. Fetching new data...")
            self.fetch_new_data()
            self.progress_callback(15, "Retrying data read...")
            ohlcv_dict = finstore.read.symbol_list(self.symbol_list)
            self._validate_data_dates(ohlcv_dict)

        # Ensure we have dataframes for all requested symbols
        missing_symbols = set(self.symbol_list) - set(ohlcv_dict.keys())
        if missing_symbols:
            print(f"Missing data for symbols: {', '.join(missing_symbols)}")

        return ohlcv_dict

    def _validate_data_dates(self, ohlcv_dict: pd.DataFrame) -> None:
        """
        Validate that each symbol's data covers the required date range.
        """
        try:
            for symbol, original_df in ohlcv_dict.items():
                df = original_df.copy()
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                if df['timestamp'].iloc[0] > self.start_date:
                    print(f"Warning: Data for {symbol} starts after backtest start date.")

                if df['timestamp'].iloc[-1] < self.end_date:
                    print(f"Warning: Data for {symbol} ends before backtest end date.")
        except Exception as e:
            print(f'Error while validating dates : {e}')

    def fetch_new_data(self) -> None:
        """
        Fetch new data from the appropriate store based on market name.
        """
        self.progress_callback(10, "Calculating required data points...")
        timeframe_offset = to_offset(self.timeframe)
        if not timeframe_offset:
            raise ValueError(f"Invalid timeframe: {self.timeframe}")

        date_range = pd.date_range(start=self.start_date, end=self.end_date, freq=timeframe_offset)
        data_points = len(date_range)
        data_points = int(data_points * 1.2)  # Add buffer

        self.progress_callback(15, f"Fetching {data_points} data points...")
        if self.market_name == 'crypto_binance':
            store_crypto_binance(
                timeframe=self.timeframe,
                data_points_back=data_points,
                suffix=self.pair
            )
        elif self.market_name == 'indian_equity':
            store_indian_equity(
                timeframe=self.timeframe,
                data_points_back=data_points,
                complete_list=False
            )
        else:
            raise ValueError(f"Unsupported market: {self.market_name}")

    def _convert_timeframe_to_freq(self) -> str:
        """
        Convert the user-friendly timeframe to a pandas frequency string.

        Returns:
            str: The pandas frequency string.
        """
        tf_map = {
            '1m': 'T',
            '1h': 'H',
            '1d': 'D',
            '1w': 'W',
            '1M': 'M'
        }
        return tf_map.get(self.timeframe, self.timeframe)

    def save_backtest(self, pf: vbt.Portfolio = None, save_name : str = None) -> None:
        """
        Save the backtest results and parameters.
        """
        if not pf:
            pf = self.portfolio
        if save_name:
            backtest_id = save_name
        else:
            backtest_id = f"{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        save_dir = Path("database/backtest") / backtest_id
        save_dir.mkdir(parents=True, exist_ok=True)

        # Create consolidated parameters with proper serialization
        full_params = {
            "backtest_id": backtest_id,
            "created_at": pd.Timestamp.now().isoformat(),
            "strategy_name": self.strategy_object.display_name,
            "market_name": self.market_name,
            "symbol_list": self.symbol_list,
            "pair": self.pair,
            "timeframe": self.timeframe,
            "strategy_type": self.strategy_type,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "init_cash": self.init_cash,
            "fees": self.fees,
            "slippage": self.slippage,
            "size": self.size,
            "cash_sharing": self.cash_sharing,
            "allow_partial": self.allow_partial,
            "strategy_params": self.strategy_object.params,
            "performance": {
                "returns": float(pf.total_return()),
                "sharpe_ratio": float(pf.sharpe_ratio()),
                "max_drawdown": float(pf.max_drawdown()),
                "duration_days": (self.end_date - self.start_date).days
            }
        }

        # Save parameters (single consolidated file)
        with open(save_dir / "params.json", 'w') as f:
            json.dump(full_params, f, indent=4, default=str)

        # Save portfolio and trades
        self.progress_callback(80, "Saving portfolio...")
        pf.save(str(save_dir / "portfolio.pkl"))

        self.progress_callback(85, "Saving trades...")
        trades = pf.trades.records_readable
        trades.to_parquet(save_dir / "trades.parquet")

        self.progress_callback(100, "Backtest saved.")
    
    @staticmethod
    def list_backtests() -> Dict[str, Dict[str, Any]]:
        """
        List all saved backtests with their parameters.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary of backtest names mapped to their parameters.
        """
        backtests = {}
        if not Backtester.BACKTEST_DIR.exists():
            print("No backtest directory found.")
            return backtests

        for backtest_folder in Backtester.BACKTEST_DIR.iterdir():
            if backtest_folder.is_dir():
                params_file = backtest_folder / "params.json"
                if params_file.exists():
                    try:
                        with open(params_file, 'r') as f:
                            params = json.load(f)
                        backtests[backtest_folder.name] = params
                    except Exception as e:
                        print(f"Error reading {params_file}: {e}")

        return backtests

    @staticmethod
    def load_backtest(backtest_name: str) -> Tuple[vbt.Portfolio, Dict[str, Any]]:
        """
        Load a saved backtest by name.

        Args:
            backtest_name (str): The name of the backtest to load.

        Returns:
            Tuple[vbt.Portfolio, Dict[str, Any]]: A tuple containing the loaded Portfolio object and its parameters.
        """
        backtest_path = Backtester.BACKTEST_DIR / backtest_name
        params_file = backtest_path / "params.json"
        portfolio_file = backtest_path / "portfolio.pkl"

        if not params_file.exists() or not portfolio_file.exists():
            raise FileNotFoundError(f"Backtest {backtest_name} not found or incomplete.")

        # Load parameters
        with open(params_file, 'r') as f:
            params = json.load(f)

        # Load portfolio
        portfolio = vbt.Portfolio.load(str(portfolio_file))

        return portfolio, params


if __name__ == '__main__':
    def dummy_progress(progress: int, status: str) -> None:
        print(f"Progress: {progress}% - {status}")

    class ExampleStrategy(StrategyBaseClass):
        def __init__(self, threshold: float):
            super().__init__()
            self.threshold = threshold

        def run(self, ohlcv_data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
            close_prices = ohlcv_data.xs('close', axis=1, level=1, drop_level=False)
            open_prices = ohlcv_data.xs('open', axis=1, level=1, drop_level=False)
            
            entries = close_prices > self.threshold
            exits = close_prices < self.threshold
            
            return entries, exits, close_prices, open_prices

    strategy = ExampleStrategy(threshold=30000)
    Backtester(
        market_name='crypto_binance',
        symbol_list=['BTC/USDT'],
        timeframe='1d',
        strategy_object=strategy,
        strategy_type='multi',
        start_date=pd.Timestamp('2023-01-01'),
        end_date=pd.Timestamp('2023-12-31'),
        init_cash=100000,
        fees=0.0001,
        slippage=0.0001,
        size=0.1,
        cash_sharing=True,
        allow_partial=True,
        progress_callback=dummy_progress,
        pair='USDT'
    )