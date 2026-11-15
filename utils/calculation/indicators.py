import pandas as pd
from utils.decorators import result_df_decorator
import fin_primitives as fp
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score


def _on_valid_rows(func, df, columns):
    """
    Run ``func`` on the rows of ``df`` where every column in ``columns`` is present and
    return the result aligned to ``df.index`` (NaN where an input was missing).
    fin_primitives rejects NaN inputs, so missing bars are skipped instead of failing.
    """
    valid = df[columns].dropna()
    if valid.empty:
        return pd.Series(np.nan, index=df.index, dtype='float64')
    return pd.Series(func(valid), index=valid.index, dtype='float64').reindex(df.index)

def _supertrend_line(df, length, multiplier):
    """
    Supertrend line: hl2 +/- multiplier * ATR (Wilder), with the bands ratcheting while the
    trend holds. Same rules as pandas_ta.supertrend's SUPERT column.
    """
    atr = fp.compute('wilder_smoothed_range', df['close'], length, high=df['high'], low=df['low']).to_numpy(dtype='float64')
    hl2 = ((df['high'] + df['low']) / 2).to_numpy(dtype='float64')
    close = df['close'].to_numpy(dtype='float64')
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    trend = np.full(close.shape, np.nan)
    direction = 1
    for i in range(1, close.shape[0]):
        if close[i] > upper[i - 1]:
            direction = 1
        elif close[i] < lower[i - 1]:
            direction = -1
        else:
            if direction > 0 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if direction < 0 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]
        trend[i] = lower[i] if direction > 0 else upper[i]
    return trend

@result_df_decorator(lambda length: f'ema_{length}')
def calculate_ema(df, length):
    """
    Calculate the Exponential Moving Average (EMA) for a given length.

    Parameters:
    df (pd.DataFrame): DataFrame containing OHLCV data with a 'timestamp' column.
    length (int): The length of the EMA (e.g., 10, 20, 100).

    Returns:
    pd.DataFrame: DataFrame with columns 'timestamp', 'indicator_name', 'indicator_value'.
    """
    ema = df['close'].ewm(span=length, adjust=False).mean()
    return ema

@result_df_decorator(lambda length: f'rsi_{length}')
def calculate_rsi(df, length):
    """
    Calculate the Relative Strength Index (RSI) for a given length with Wilder's smoothing
    (same values as TA-Lib's RSI).

    Parameters:
    df (pd.DataFrame): DataFrame containing OHLCV data with a 'timestamp' column.
    length (int): The length of the RSI (e.g., 14).

    Returns:
    pd.DataFrame: DataFrame with columns 'timestamp', 'indicator_name', 'indicator_value'.
    """
    return _on_valid_rows(lambda d: fp.rsi(d['close'], length), df, ['close'])

@result_df_decorator(lambda length, atr_multiplier: f'supertrend_{length}_{atr_multiplier}')
def calculate_supertrend(df, atr_multiplier=3.0, length=10):
    """
    Calculate Supertrend for a given dataframe using ta library.

    Parameters:
    df (pd.DataFrame): DataFrame with 'high', 'low', 'close' prices.
    atr_period (int): The period for ATR calculation.
    multiplier (float): The multiplier for Supertrend.

    Returns:
    pd.Series: Supertrend values.
    """
    return _on_valid_rows(lambda d: _supertrend_line(d, length, atr_multiplier), df, ['high', 'low', 'close'])

@result_df_decorator(lambda length: f'roc_{length}')
def calculate_roc(df, lookback_period):
    return _on_valid_rows(lambda d: fp.compute('roc', d['close'], lookback_period), df, ['close'])

@result_df_decorator(lambda lookback_period: f'average_volume_{lookback_period}')
def calculate_average_volume(df,lookback_period):
    df['volume_usdt'] = df['close'] * df['volume']
    return df['volume_usdt'].rolling(window=lookback_period).mean()

@result_df_decorator(lambda window: f'slope_r2_product_{window}')
def calculate_exponential_regression(df, window=90):
    # Convert the timestamp to datetime and set it as the index
    data = df.copy()
    data['timestamp'] = pd.to_datetime(data['timestamp'])
    data = data.set_index('timestamp')
    data['log_close'] = np.log(data['close'])
    slopes = []
    r2_values = []
    dates = []

    for end in range(window, len(data) + 1):
        subset = data.iloc[end-window:end]
        X = (subset.index - subset.index.min()).days.values.reshape(-1, 1)
        y = np.log(subset['close']).values

        reg = LinearRegression().fit(X, y)
        slope = reg.coef_[0]
        r2 = r2_score(y, reg.predict(X))

        slopes.append(slope)
        r2_values.append(r2)
        dates.append(subset.index[-1])

    # Create a temporary DataFrame to hold the results
    results_df = pd.DataFrame({'timestamp': dates, f'Slope_{window}': slopes, f'R2_{window}': r2_values})
    results_df.set_index('timestamp', inplace=True)

    # Join the results back to the original data
    data = data.join(results_df, how='left')
    data.reset_index(inplace=True)
    _slope_r2_product = data[f'Slope_{window}'] * data[f'R2_{window}']
    return _slope_r2_product

@result_df_decorator(lambda lookback_period, spike_threshold: f'spike_{lookback_period}_{spike_threshold}')
def calculate_spike(df, lookback_period, spike_threshold=0.5):
    """
    Calculate if there has been a spike of `spike_threshold` or more in the last `lookback_period`.

    Parameters:
    df (pd.DataFrame): DataFrame with 'open' and 'close' prices.
    lookback_period (int): The period to look back for spikes.
    spike_threshold (float): The threshold for spike detection (e.g., 0.5 for 50%).

    Returns:
    pd.Series: Series with 1 if a spike is present, 0 otherwise.
    """
    spikes = pd.Series(0, index=df.index)
    for i in range(lookback_period, len(df)):
        window = df.iloc[i-lookback_period:i]
        if any((window['close'] - window['open']) / window['open'] >= spike_threshold):
            spikes.iloc[i] = 1
        elif any((window['high'] - window['low']) / window['low'] >= spike_threshold*2):
            spikes.iloc[i] = 1
    return spikes

@result_df_decorator(lambda lookback_period, gap_threshold: f'gap_{lookback_period}_{gap_threshold}')
def detect_large_gap(df, lookback_period=90, gap_threshold=0.15):
    """
    Detect if there has been a gap up or gap down greater than the specified threshold
    in the last lookback_period days.

    Parameters:
    df (pd.DataFrame): DataFrame with 'open' and 'close' prices.
    lookback_period (int): The period to look back for gaps.
    gap_threshold (float): The threshold for gap detection (e.g., 0.15 for 15%).

    Returns:
    pd.Series: Series with 1 if a large gap is present, 0 otherwise.
    """
    gaps = pd.Series(0, index=df.index)
    for i in range(1, len(df)):
        if i >= lookback_period:
            window = df.iloc[i-lookback_period:i+1]
            gap_up = (window['open'] - window['close'].shift(1)) / window['close'].shift(1)
            gap_down = (window['open'] - window['close'].shift(1)) / window['close'].shift(1)
            
            if any(gap_up >= gap_threshold) or any(gap_down <= -gap_threshold):
                gaps.iloc[i] = 1
    
    return gaps