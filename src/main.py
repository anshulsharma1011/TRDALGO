from flask import Flask, jsonify, request
from fyers_apiv3 import fyersModel
import pandas as pd
from datetime import datetime, timedelta
import os
import time
import threading
from functools import wraps

app = Flask(__name__)

# Fyers API credentials
client_id = "VDSQ7JWF9Q-100"
secret_key = "QUHM6D1089"
redirect_uri = "http://127.0.0.1:5000/auth"
response_type = "code"
grant_type = "authorization_code"
state = "sample"

# Initialize Fyers session
session = fyersModel.SessionModel(
    client_id=client_id,
    redirect_uri=redirect_uri,
    response_type=response_type,
    state=state,
    secret_key=secret_key,
    grant_type=grant_type
)

# Add a global variable to store the access token
access_token = None

# Add these global variables
TOKEN_FILE = "access_token.txt"
token_expiry = None
auth_lock = threading.Lock()

def refresh_token_background():
    """Background task to refresh the token"""
    global access_token, token_expiry
    
    while True:
        try:
            with auth_lock:
                if not access_token or (token_expiry and time.time() >= token_expiry - 300):  # Refresh 5 mins before expiry
                    # Generate new token
                    auth_url = session.generate_authcode()
                    print(f"Please visit this URL to authenticate: {auth_url}")
                    print("After authentication, the service will automatically use the new token")
                    
                    # Wait for some time to allow authentication
                    time.sleep(30)  # Wait 30 seconds for manual authentication
                    
                    # Check if token was updated by auth endpoint
                    if not access_token:
                        print("Authentication pending... Service may not work until authenticated")
            
            # Sleep for 5 minutes before next check
            time.sleep(300)
            
        except Exception as e:
            print(f"Token refresh error: {str(e)}")
            time.sleep(60)  # Wait a minute before retrying on error

def require_authentication(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global access_token
        
        if not access_token:
            return jsonify({
                'status': 'error',
                'message': 'Service not authenticated. Please check server logs for authentication URL.'
            }), 401
                
        return f(*args, **kwargs)
    return decorated_function

# Keep the auth endpoint for initial setup
@app.route('/auth')
def auth():
    global access_token, token_expiry
    auth_code = request.args.get('auth_code')
    if auth_code:
        session.set_token(auth_code)
        try:
            with auth_lock:
                token_response = session.generate_token()
                access_token = token_response["access_token"]
                token_expiry = time.time() + 86400  # Set expiry to 24 hours
                
                # Save token to file
                with open(TOKEN_FILE, 'w') as file:
                    file.write(access_token)
                    
                return jsonify({
                    'status': 'success',
                    'message': 'Authorization successful'
                })
        except Exception as e:
            return jsonify({
                'status': 'error',
                'message': f'Error generating token: {str(e)}'
            }), 500
    return jsonify({
        'status': 'error',
        'message': 'No auth code received'
    }), 400

# Initialize Fyers model (move this inside your API routes)
def get_fyers_model():
    global access_token
    if access_token:
        return fyersModel.FyersModel(token=access_token, is_async=False, client_id=client_id, log_path="")
    raise ValueError("Not authenticated. Please visit the authorization URL and complete the authentication process.")


def historical_bydate(symbol, start_date, end_date, interval="3"):
    # Convert datetime strings to Unix timestamps
    fyers = get_fyers_model()  # Get authenticated model
    sd_timestamp = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
    ed_timestamp = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
    # print(sd_timestamp,ed_timestamp)
    data = {
        "symbol": f"NSE:{symbol}-EQ",
        "resolution": "D",
        "date_format": "0",
        "range_from": str(sd_timestamp),  # Convert to string as required by API
        "range_to": str(ed_timestamp),    # Convert to string as required by API
        "cont_flag": "1"
    }
    # print(data)
    nx = fyers.history(data)
    # print(nx)
    cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    df = pd.DataFrame.from_dict(nx['candles'])
    df.columns = cols
    df['date'] = pd.to_datetime(df['date'], unit="s")
    df['date'] = df['date'].dt.tz_localize('utc').dt.tz_convert('Asia/Kolkata')
    df['date'] = df['date'].dt.tz_localize(None)
    return df

def fetch_historical_data(symbol, start_date, end_date, interval="3"):
    dfs = []
    n = abs((start_date - end_date).days)
    ab = None

    while ab is None:
        # Start from the end date and work backwards
        sd = (end_date - timedelta(days=n))
        ed = (sd + timedelta(days=99 if n > 100 else n)).strftime("%Y-%m-%d")
        sd = sd.strftime("%Y-%m-%d")
        
        dx = historical_bydate(symbol, sd, ed, interval)
        dfs.append(dx)
        n = n - 100 if n > 100 else 0
        print(n)
        if n == 0:
            ab = "done"

    df = pd.concat(dfs, ignore_index=True)
    return df

def fetch_stock_data(symbol):
    # Change to use past dates instead of future dates
    end_date = datetime.now()  # Use current date as end date
    start_date = end_date - timedelta(days=365*20)  # Get last 30 days of data
    return fetch_historical_data(symbol, start_date, end_date)

def calculate_indicators(df):
    # Calculate HLC3 (High, Low, Close average)
    hlc3 = (df['high'] + df['low'] + df['close']) / 3
    
    # Calculate 5-day SMA of Volume
    average_volume = df['volume'].rolling(window=5).mean()

    # Calculate Price Volume (HLC3 * Volume) and its 5-day SMA
    price_volume = hlc3 * df['volume']
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
@require_authentication
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
        result_df.to_csv(f"stock_data/{ticker}.csv")
        
        # Create a list to store trade periods
        trades = []
        in_position = False
        entry_date = None
        
        # Convert signals to numpy for iteration
        entry_signals = result_df['Entry_Signal'].values
        exit_signals = result_df['Exit_Signal'].values
        dates = result_df['date'].values  # Changed from index to 'date' column
        
        # Access signals
        for i in range(len(result_df)):
            if entry_signals[i] == 1 and not in_position:
                entry_date = dates[i]
                in_position = True
            elif exit_signals[i] == 1 and in_position:
                trades.append({
                    'entry': pd.Timestamp(entry_date).strftime('%Y-%m-%d'),  # Convert to Timestamp
                    'exit': pd.Timestamp(dates[i]).strftime('%Y-%m-%d')      # Convert to Timestamp
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
@require_authentication
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
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']),
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

# Add a new route to check authentication status
@app.route('/auth-status')
def auth_status():
    global access_token
    if access_token:
        return jsonify({
            'status': 'authenticated',
            'message': 'Authentication successful'
        })
    auth_url = session.generate_authcode()
    return jsonify({
        'status': 'not_authenticated',
        'message': 'Please complete authentication',
        'auth_url': auth_url
    })

@app.route('/test-connection')
def test_connection():
    try:
        fyers = get_fyers_model()
        profile = fyers.get_profile()
        return jsonify({
            'status': 'success',
            'message': 'Connection successful',
            'profile': profile
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Connection failed: {str(e)}'
        }), 500

if __name__ == "__main__":
    # Try to load existing token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as file:
            stored_token = file.read().strip()
            if stored_token:
                access_token = stored_token
                token_expiry = time.time() + 86400

    # Start the background token refresh thread
    refresh_thread = threading.Thread(target=refresh_token_background, daemon=True)
    refresh_thread.start()
    
    # Start the Flask server
    app.run(debug=True, host='0.0.0.0')
