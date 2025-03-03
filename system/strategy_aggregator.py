import os 
import sys 

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import vectorbt as vbt
import pandas as pd
import scipy.optimize as sco
import numpy as np
from strategy.private.SOTM_optimized import get_signals
from finstore.finstore import Finstore
from utils.db.fetch import fetch_entries
from utils.decorators import cache_decorator

from executor.constructor import construct_portfolio

finstore = Finstore(market_name='indian_equity', timeframe='1d')
symbol_list = finstore.read.get_symbol_list()
ohlcv_data = fetch_entries(market_name='indian_equity', timeframe='1d')

def annual_sharpe_ratio(weights, returns):
    # Calculate portfolio return
    portfolio_return = np.dot(weights, returns.mean()) * 252
    # Calculate portfolio standard deviation
    portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(returns.cov() * 252, weights)))
    # Return negative Sharpe ratio (since we minimize in optimization)
    return -portfolio_return / portfolio_volatility

def optimize_portfolio(returns):
    num_assets = returns.shape[1]
    # Initial guess for weights (equally weighted)
    initial_weights = np.ones(num_assets) / num_assets
    # Bounds for each weight
    bounds = tuple((0, 1) for _ in range(num_assets))
    # Constraint that weights must sum to 1
    constraints = ({'type': 'eq', 'fun': lambda weights: np.sum(weights) - 1})

    # Minimize the negative Sharpe ratio
    result = sco.minimize(
        annual_sharpe_ratio,
        initial_weights,
        args=(returns,),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints
    )
    
    return result.x if result.success else initial_weights

@cache_decorator(expire=60*60*24*365)
def calculate_optimized_weights(signal_function, params_list : list[dict]):

    portfolio_aggregrates = {}
    i = 0
    for params in params_list:
        
        entries, exits, close_data, open_data = signal_function(**params) 
        
        if 'top_n' in params:
            top_n = params['top_n']
        else:
            top_n = 10
        
        pf = vbt.Portfolio.from_signals(
            close=close_data,
            entries=entries,
            exits=exits,
            direction='longonly',
            init_cash = 100000,
            cash_sharing=True,
            size=1/top_n, 
            size_type="valuepercent",
            fees = 0.0005,
            slippage = 0.001,
            allow_partial=False,
            size_granularity=1.0,
            #sim_start=pd.Timestamp('2024-09-28'),
        )

        portfolio_aggregrates[i] = pf.get_daily_returns()
        i += 1
    
    df = pd.DataFrame(portfolio_aggregrates)
    df.dropna(inplace=True)

    years = df.index.year.unique()

    fitting_period = df[df.index.year == years[-2]]
    holdback_period = df[df.index.year == years[-1]]
    
    # Get optimal weights using the fitting period
    optimal_weights = optimize_portfolio(fitting_period)
    
    # Calculate the portfolio return for the holdback period
    combined_return = (holdback_period * optimal_weights).sum(axis=1)
    
    # Store the portfolio performance for the holdback period
    return combined_return, optimal_weights

    

def aggregated_entries_exits(portfolio_value : int ,
                             sim_start : pd.Timestamp,
                             sim_end : pd.Timestamp,
                             optimal_weights : list, 
                             params_list : list[dict], 
                             signal_function):
    
    assert len(params_list) == len(optimal_weights), "Length of params_list and optimal_weights must be the same"
    
    rounded_weights = [round(num, 1) for num in optimal_weights]
    portfolio_values = []
    
    for i in range(len(params_list)):
        adjusted_portfolio_value = portfolio_value * rounded_weights[i]
        pf = construct_portfolio(sim_start=sim_start, sim_end=sim_end, init_cash=adjusted_portfolio_value, params=params_list[i])
        portfolio_values.append(pf)
        
    return portfolio_values
    

if __name__ == '__main__':

    params_list = [
        {'ohlcv_data': ohlcv_data, 'symbol_list': symbol_list, 'top_n': 10},
        {'ohlcv_data': ohlcv_data, 'symbol_list': symbol_list, 'top_n': 5, 'configuration' : 2},
        {'ohlcv_data': ohlcv_data, 'symbol_list': symbol_list, 'top_n': 5, 'configuration' : 2, 'slope_period' : 30},
    ]
    combined_return, optimal_weights = calculate_optimized_weights(get_signals, params_list)

    print(combined_return)
    print(optimal_weights)



