import sys
import os

# Add the parent directory of the root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.store.crypto_binance import store_crypto_binance
from data.store.indian_equity import store_indian_equity
from utils.decorators import clear_cache  # Import clear_cache function

if __name__ == '__main__':
    # Ask user for input
    print("Please choose the data type to save:")
    print("1. crypto-binance")
    print("2. equity-india")
    print("3. clear cache")  # Add option to clear cache
    data_type_choice = input("Enter the number corresponding to your choice: ")

    if data_type_choice == '1':
        data_type = 'crypto-binance'
        type = input("Enter the type (e.g., spot, futures): ")
        suffix = input("Enter the suffix (e.g., USDT, BTC): ")
    elif data_type_choice == '2':
        data_type = 'equity-india'
        complete_list_input = input("Fetch complete list? (y/n): ")
        complete_list = complete_list_input.lower() == 'y'
    elif data_type_choice == '3':
        clear_cache()  # Clear the cache
        print("Cache cleared successfully.")
        sys.exit(0)
    else:
        print("Invalid choice. Please choose 1, 2, or 3.")
        sys.exit(1)

    timeframe = input("Enter the timeframe (e.g., 1y, 1d, 1h, 1m): ")
    data_points = int(input("Enter the number of data points: "))

    # Save data based on user input
    if data_type == 'crypto-binance':
        store_crypto_binance(timeframe, data_points, type, suffix)
    elif data_type == 'equity-india':
        store_indian_equity(timeframe, data_points, complete_list)
    else:
        print("Invalid data type. Please choose 'crypto-binance' or 'equity-india'.")
