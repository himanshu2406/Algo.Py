import numpy as np
import pandas as pd

from utils.calculation.indicators import calculate_roc, calculate_rsi, calculate_supertrend


def _ohlcv(n=400, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.1, 2.0, n)
    low = close - rng.uniform(0.1, 2.0, n)
    return pd.DataFrame({
        'timestamp': pd.date_range('2024-01-01', periods=n, freq='D').strftime('%Y-%m-%d %H:%M:%S'),
        'open': close,
        'high': high,
        'low': low,
        'close': close,
        'volume': rng.uniform(1e3, 1e4, n),
    })


def _wilder(values, length):
    # Wilder smoothing seeded with the simple mean of the first `length` values (TA-Lib style).
    out = np.full(len(values), np.nan)
    out[length - 1] = np.mean(values[:length])
    for i in range(length, len(values)):
        out[i] = (out[i - 1] * (length - 1) + values[i]) / length
    return out


def _reference_rsi(close, length):
    delta = np.diff(close)
    gain = _wilder(np.clip(delta, 0, None), length)
    loss = _wilder(np.clip(-delta, 0, None), length)
    return np.concatenate([[np.nan], 100 * gain / (gain + loss)])


def _reference_supertrend(high, low, close, length, multiplier):
    # Transcribed from pandas_ta.supertrend (ATR with RMA smoothing), SUPERT column.
    prev_close = np.concatenate([[np.nan], close[:-1]])
    tr = np.nanmax(np.vstack([high - low, np.abs(high - prev_close), np.abs(low - prev_close)]), axis=0)
    atr = _wilder(tr, length)
    hl2 = (high + low) / 2
    upper, lower = hl2 + multiplier * atr, hl2 - multiplier * atr
    trend, direction = np.full(len(close), np.nan), [1] * len(close)
    for i in range(1, len(close)):
        if close[i] > upper[i - 1]:
            direction[i] = 1
        elif close[i] < lower[i - 1]:
            direction[i] = -1
        else:
            direction[i] = direction[i - 1]
            if direction[i] > 0 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if direction[i] < 0 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]
        trend[i] = lower[i] if direction[i] > 0 else upper[i]
    return trend


def test_rsi_matches_wilder_reference():
    df = _ohlcv()
    out = calculate_rsi(df, 14)
    assert list(out.columns) == ['timestamp', 'indicator_name', 'indicator_value']
    assert (out['indicator_name'] == 'rsi_14').all()
    np.testing.assert_allclose(out['indicator_value'], _reference_rsi(df['close'].to_numpy(), 14), atol=1e-9)


def test_roc_is_percent_change_over_lookback():
    df = _ohlcv()
    out = calculate_roc(df, 10)
    assert (out['indicator_name'] == 'roc_10').all()
    expected = 100 * (df['close'] / df['close'].shift(10) - 1)
    np.testing.assert_allclose(out['indicator_value'], expected, atol=1e-9)


def test_supertrend_matches_pandas_ta_rules():
    df = _ohlcv()
    out = calculate_supertrend(df, atr_multiplier=3.0, length=10)
    assert (out['indicator_name'] == 'supertrend_10_3.0').all()
    expected = _reference_supertrend(df['high'].to_numpy(), df['low'].to_numpy(), df['close'].to_numpy(), 10, 3.0)
    np.testing.assert_allclose(out['indicator_value'], expected, atol=1e-9)


def test_missing_bars_are_skipped_not_fatal():
    df = _ohlcv(60)
    df.loc[30, 'close'] = np.nan
    out = calculate_rsi(df, 14)
    assert len(out) == len(df)
    assert np.isnan(out['indicator_value'].iloc[30])
    assert out['indicator_value'].iloc[31:].notna().all()

