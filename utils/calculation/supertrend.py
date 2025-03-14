#from vectorbt import vbt
from numba import njit
import numpy as np
from utils.db.fetch import fetch_entries
import os
from utils.decorators import result_df_decorator
import pandas as pd

def get_med_price(high, low):
    return (high + low) / 2

def get_atr_np(high, low, close, period):
    shifted_close = vbt.nb.fshift_1d_nb(close)
    tr0 = np.abs(high - low)
    tr1 = np.abs(high - shifted_close)
    tr2 = np.abs(low - shifted_close)
    tr = np.column_stack((tr0, tr1, tr2)).max(axis=1)
    atr = vbt.nb.wwm_mean_1d_nb(tr, period)
    return atr

def get_basic_bands(med_price, atr, multiplier):
    matr = multiplier * atr
    upper = med_price + matr
    lower = med_price - matr
    return upper, lower

@njit
def get_final_bands_nb(close, upper, lower):
    trend = np.full(close.shape, np.nan)
    dir_ = np.full(close.shape, 1)
    long = np.full(close.shape, np.nan)
    short = np.full(close.shape, np.nan)

    for i in range(1, close.shape[0]):
        if close[i] > upper[i - 1]:
            dir_[i] = 1
        elif close[i] < lower[i - 1]:
            dir_[i] = -1
        else:
            dir_[i] = dir_[i - 1]
            if dir_[i] > 0 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if dir_[i] < 0 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]

        if dir_[i] > 0:
            trend[i] = long[i] = lower[i]
        else:
            trend[i] = short[i] = upper[i]
            
    return trend, dir_, long, short

@result_df_decorator(lambda period, multiplier: f'supertrend_{period}_{multiplier}')
def faster_supertrend(df, period=7, multiplier=3):
    high = df['high'].values
    low = df['low'].values
    close = df['close'].values
    
    med_price = get_med_price(high, low)
    atr = get_atr_np(high, low, close, period)
    upper, lower = get_basic_bands(med_price, atr, multiplier)
    supert, superd, superl, supers = get_final_bands_nb(close, upper, lower)
    
    # Convert numpy array to pandas Series
    return pd.Series(supert, index=df.index)
