import pandas as pd
import vectorbt as vbt
from strategy.private.SOTM import get_signals

def construct_portfolio(init_cash : float = 100000,
                     buy_on_open: bool = False,
                     sim_start: pd.Timestamp = None, 
                     sim_end: pd.Timestamp = None,
                     params : dict = None):
    """
    Creates and returns a vectorbt portfolio object based on the provided OHLCV data, symbol list, and other parameters.

    Parameters
    ----------
    ohlcv_data : pd.DataFrame
        A DataFrame containing OHLCV (Open, High, Low, Close, Volume) data.
    
    symbol_list : list
        List of symbols for which to create the portfolio.
    
    market_name : str, optional
        The market name to use, default is 'indian_equity'.
    
    timeframe : str, optional
        Timeframe for the data, default is '1d'.
    
    complete_list : bool, optional
        If True, consider all symbols in the complete list, default is False.
    
    buy_on_open : bool, optional
        If True, simulates buying on open prices, default is False.
    
    sim_start : datetime or None, optional
        The start date of the simulation, default is None.
    
    sim_end : datetime or None, optional
        The end date of the simulation, default is None.

    Returns
    -------
    vbt.Portfolio
        A vectorbt portfolio object.
    """


    entries, exits, close_data, open_data = get_signals(**params)


    if buy_on_open:
        entries = entries.shift(1).fillna(False)
        exits = exits.shift(1).fillna(False)

    close = close_data

    if sim_end is not None:
        sim_end = (pd.Timestamp(sim_end) + pd.Timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
    
    if 'test' != 'test':
        sim_start = sim_start.strftime('%Y-%m-%d 00:00:00')
        entries = entries[entries.index >= sim_start]
        exits = exits[exits.index >= sim_start]
        exits = exits[exits.index < sim_end]
        close = close[close.index >= sim_start]
    
    # Create the portfolio
    if 'top_n' in params:
        top_n = params['top_n']
    else: 
        top_n = 10
    
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        direction='longonly',
        init_cash=init_cash,
        cash_sharing=True,
        size=1/top_n,
        size_type="valuepercent",
        fees=0.0005,
        slippage=0.001,
        allow_partial=False,
        size_granularity=1.0,
        sim_start=sim_start,
        sim_end=sim_end,
    )

    return pf 
