from flask import Flask, jsonify
from nselib import capital_market as cm
from nselib import indices
import pandas as pd
from datetime import datetime, timedelta

app = Flask(__name__)

def fetch_nifty_data():
    # Fetch Nifty 50 data
    nifty_data = indices.get_index_data('NIFTY 50')
    return pd.DataFrame(nifty_data)

def fetch_stock_data(symbol):
    """
    Fetch historical data for a given stock symbol
    """
    # Get historical data
    hist_data = cm.get_price_volume_data(symbol)
    
    if not hist_data or 'data' not in hist_data:
        raise ValueError(f"No data found for {symbol}")
    
    # Convert to DataFrame
    df = pd.DataFrame(hist_data['data'])
    
    # Rename columns to match our indicator calculations
    df = df.rename(columns={
        'CH_TIMESTAMP': 'Date',
        'CH_OPENING_PRICE': 'Open',
        'CH_TRADE_HIGH_PRICE': 'High',
        'CH_TRADE_LOW_PRICE': 'Low',
        'CH_CLOSING_PRICE': 'Close',
        'CH_TOT_TRADED_QTY': 'Volume'
    })
    
    # Convert date string to datetime
    df['Date'] = pd.to_datetime(df['Date'])
    df.set_index('Date', inplace=True)
    
    # Convert price and volume columns to numeric
    price_columns = ['Open', 'High', 'Low', 'Close']
    df[price_columns] = df[price_columns].apply(pd.to_numeric)
    df['Volume'] = pd.to_numeric(df['Volume'])
    
    return df.sort_index()

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

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0')
