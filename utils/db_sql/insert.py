import os
import sqlite3
import pandas as pd
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path='config/.env')

# Database path from the .env file
DATABASE_PATH = os.getenv('DATABASE_PATH')

def get_db_connection():
    """Establish a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        return conn
    except sqlite3.Error as e:
        print(f"Error connecting to database: {e}")
        return None

def insert_market_if_not_exists(conn, market_name):
    """Insert a market into the market table if it does not exist, and return the market_id."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO market (market_name) VALUES (?);
    """, (market_name,))
    conn.commit()
    
    cursor.execute("""
        SELECT market_id FROM market WHERE market_name = ?;
    """, (market_name,))
    market_id = cursor.fetchone()[0]
    return market_id

def insert_symbol_if_not_exists(conn, symbol_name, market_id):
    """Insert a symbol into the symbols table if it does not exist, and return the symbol_id."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO symbols (symbol, market_id) VALUES (?, ?);
    """, (symbol_name, market_id))
    conn.commit()
    
    cursor.execute("""
        SELECT symbol_id FROM symbols WHERE symbol = ?;
    """, (symbol_name,))
    symbol_id = cursor.fetchone()[0]
    return symbol_id

def insert_ohlcv_data(conn, symbol_id, timeframe, df):
    """Insert OHLCV data into the ohlcv_data table."""
    cursor = conn.cursor()

    # Prepare data for insertion
    ohlcv_records = df.to_records(index=False)  # Convert DataFrame to records for SQLite insertion
    ohlcv_records_list = list(ohlcv_records)

    cursor.executemany("""
        INSERT OR IGNORE INTO ohlcv_data (symbol_id, timeframe, timestamp, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """, [(symbol_id, timeframe, record['timestamp'], float(record['open']), float(record['high']), float(record['low']), float(record['close']), float(record['volume'])) for record in ohlcv_records_list])  # Ensure all data is in float
    conn.commit()

def insert_technical_indicators(conn, symbol_id, timeframe, df):
    """Insert technical indicators into the technical_indicators table."""
    cursor = conn.cursor()

    # Prepare data for insertion
    indicator_records = df.to_records(index=False)  # Convert DataFrame to records for SQLite insertion
    indicator_records_list = list(indicator_records)

    cursor.executemany("""
        INSERT OR REPLACE INTO technical_indicators (symbol_id, timeframe, timestamp, indicator_name, indicator_value)
        VALUES (?, ?, ?, ?, ?);
    """, [(symbol_id, timeframe, record['timestamp'], record['indicator_name'], float(record['indicator_value'])) for record in indicator_records_list])
    
    conn.commit()

def insert_data(market_name, symbol_name, timeframe, df, indicators=False, indicators_df=None):
    """
    Main function to insert data into the database.
    
    Input:
    market_name: str 
    symbol_name: str
    timeframe: str
    df: pd.DataFrame of format: timestamp, open, high, low, close, volume
    indicators: bool : True if indicators are to be inserted, False if OHLCV data is to be inserted
    indicators_df: pd.DataFrame of format: timestamp, indicator_name, indicator_value
    
    """
    conn = get_db_connection()
    if not conn:
        return
    
    try:
        # Ensure market exists and get market_id
        market_id = insert_market_if_not_exists(conn, market_name)
        
        # Ensure symbol exists and get symbol_id
        symbol_id = insert_symbol_if_not_exists(conn, symbol_name, market_id)
        
        # Insert technical indicators for the symbol
        if indicators:
            insert_technical_indicators(conn, symbol_id, timeframe, indicators_df)
        else:
            # Insert OHLCV data for the symbol
            insert_ohlcv_data(conn, symbol_id, timeframe, df)
        
        print(f"Data for {symbol_name} in {market_name} inserted successfully.")
    except Exception as e:
        print(f"Error inserting data: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    # Example usage
    # Replace the following with actual data fetching logic or input
    market_name = "US Equity"
    symbol_name = "AAPL"
    # Sample DataFrame creation as an example (Replace this with actual data fetching)
    df = pd.DataFrame({
        'timestamp': [1633046400000, 1633046460000],
        'open': [145.1, 145.2],
        'high': [145.5, 145.6],
        'low': [144.9, 145.0],
        'close': [145.3, 145.4],
        'volume': [1000, 2000]
    })
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['timestamp'] = df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Sample indicators DataFrame creation as an example (Replace this with actual data fetching)
    indicators_df = pd.DataFrame({
        'timestamp': [1633046400000, 1633046460000],
        'indicator_name': ['ema', 'ema'],
        'indicator_value': [145.3, 145.4]
    })
    indicators_df['timestamp'] = pd.to_datetime(indicators_df['timestamp'], unit='ms')
    indicators_df['timestamp'] = indicators_df['timestamp'].dt.strftime('%Y-%m-%d %H:%M:%S')

    # Insert the data into the database
    insert_data(market_name, symbol_name, '1d', df, indicators_df)
