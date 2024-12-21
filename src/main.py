from flask import Flask, jsonify
from alpha_vantage.timeseries import TimeSeries
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

# Alpha Vantage API key - you'll need to set this up
API_KEY = "9YJ94WG9JYJ2PS6D"
ts = TimeSeries(key=API_KEY, output_format='pandas')

def fetch_stock_data(symbol):
    """
    Fetch historical data for a given stock symbol using Alpha Vantage API
    """
    try:
        # Append .BSE for Indian stocks if not already present
        if not (symbol.endswith('.BSE') or symbol.endswith('.NSE')):
            symbol = f"{symbol}.BSE"
            
        # Changed from 'compact' to 'full' to get complete historical data
        data, meta_data = ts.get_daily(symbol=symbol, outputsize='full')
        
        # Rename columns to match our existing structure
        data.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
        
        # Sort index in ascending order
        data = data.sort_index()
        
        # Remove the 100-day limit to get all available data
        # data = data.last('100D')
        
        return data
        
    except Exception as e:
        # If BSE fails, try NSE
        if symbol.endswith('.BSE'):
            try:
                symbol = symbol.replace('.BSE', '.NSE')
                return fetch_stock_data(symbol)
            except Exception as nested_e:
                raise ValueError(f"Error fetching data for {symbol}: {str(nested_e)}")
        raise ValueError(f"Error fetching data for {symbol}: {str(e)}")

def calculate_indicators(df):
    # Calculate HLC3 (High, Low, Close average)
    hlc3 = (df['High'] + df['Low'] + df['Close']) / 3
    
    # Calculate 5-day SMA of Volume
    average_volume = df['Volume'].rolling(window=5).mean()

    # Calculate Price Volume (HLC3 * Volume) and its 5-day SMA
    price_volume = hlc3 * df['Volume']
    average_price_volume = price_volume.rolling(window=5).mean()

    df['HLC3'] = hlc3
    df['Average_Volume'] = average_volume
    df['Price_Volume'] = price_volume
    df['Average_Price_Volume'] = average_price_volume   

    # Calculate WVWAP (Weighted Volume Weighted Average Price)
    df['WVWAP'] = df['Average_Price_Volume'] / df['Average_Volume']
    
    # Calculate 9-day SMA of WVWAP
    df['Smooth_WVWAP'] = df['WVWAP'].rolling(window=9).mean()
    
    # Calculate entry and exit criteria - fixing the comparison logic
    df['Entry_Signal'] = ((df['WVWAP'] > df['Smooth_WVWAP']).astype(int) & 
                         (df['WVWAP'].shift(1) <= df['Smooth_WVWAP'].shift(1)).astype(int))
    df['Exit_Signal'] = ((df['WVWAP'] <= df['Smooth_WVWAP']).astype(int) & 
                        (df['WVWAP'].shift(1) > df['Smooth_WVWAP'].shift(1)).astype(int))

    return df

@app.route('/api/stock-trades/<ticker>', methods=['GET'])
def get_stock_trades(ticker):
    try:
        # Fetch data for the specified ticker
        stock_data = fetch_stock_data(ticker)
        # filename = f"stock_data_{ticker.replace('.', '_')}_{datetime.now().strftime('%Y%m%d')}.csv"
        # stock_data.to_csv(f"stock_data/{filename}")

        if stock_data.empty:
            return jsonify({
                'status': 'error',
                'message': f'No data found for ticker {ticker}'
            }), 404
            
        # Calculate indicators using existing function
        result_df = calculate_indicators(stock_data)
        
        # Create a list to store trade periods
        trades = []
        in_position = False
        entry_date = None
        
        # Convert signals to numpy for iteration
        entry_signals = result_df['Entry_Signal'].values
        exit_signals = result_df['Exit_Signal'].values
        dates = result_df.index
        
        # Access signals
        for i in range(len(result_df)):
            if entry_signals[i] == 1 and not in_position:
                entry_date = dates[i]
                in_position = True
            elif exit_signals[i] == 1 and in_position:
                trades.append({
                    'entry': entry_date.strftime('%Y-%m-%d'),
                    'exit': dates[i].strftime('%Y-%m-%d')
                })
                in_position = False
        
        return jsonify({
            'status': 'success',
            'ticker': ticker,
            'total_trades': len(trades),
            'trades': trades
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/historical-data/<ticker>', methods=['GET'])
def get_historical_data(ticker):
    try:
        # Fetch data for the specified ticker
        stock_data = fetch_stock_data(ticker)
        
        if stock_data.empty:
            return jsonify({
                'status': 'error',
                'message': f'No data found for ticker {ticker}'
            }), 404
        
        # Calculate indicators
        result_df = calculate_indicators(stock_data)
        
        # Convert DataFrame to dictionary format
        historical_data = []
        for date, row in result_df.iterrows():
            historical_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': float(row['Volume']),
                'hlc3': float(row['HLC3']),
                'wvwap': float(row['WVWAP']),
                'smooth_wvwap': float(row['Smooth_WVWAP']),
                'entry_signal': bool(row['Entry_Signal']),
                'exit_signal': bool(row['Exit_Signal'])
            })
        
        return jsonify({
            'status': 'success',
            'ticker': ticker,
            'total_records': len(historical_data),
            'data': historical_data
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
