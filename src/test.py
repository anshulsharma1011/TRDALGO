import webbrowser
from fyers_apiv3 import fyersModel

client_id = "VDSQ7JWF9Q-100"
secret_key = "QUHM6D1089"
redirect_uri = "http://127.0.0.1:5000/auth"
response_type = "code"
grant_type = "authorization_code"
state = "sample"


appSession = fyersModel.SessionModel(client_id = client_id, redirect_uri = redirect_uri,response_type=response_type,state=state,secret_key=secret_key,grant_type=grant_type)

generateTokenUrl = appSession.generate_authcode()
print((generateTokenUrl))
webbrowser.open(generateTokenUrl,new=1)



auth_code = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJhcGkubG9naW4uZnllcnMuaW4iLCJpYXQiOjE3MzQ4MDkyOTEsImV4cCI6MTczNDgzOTI5MSwibmJmIjoxNzM0ODA4NjkxLCJhdWQiOiJbXCJ4OjBcIiwgXCJ4OjFcIiwgXCJkOjFcIiwgXCJkOjJcIiwgXCJ4OjBcIl0iLCJzdWIiOiJhdXRoX2NvZGUiLCJkaXNwbGF5X25hbWUiOiJYQzA5MzI5Iiwib21zIjoiSzEiLCJoc21fa2V5IjoiYTI4NDNjYTI1ZWQ4ZDgwMWZlNDcyMjE2ZTlhOTdlODA2NTQzZmYzMTI4ZjY2MzY4YjllYmE5ZGQiLCJub25jZSI6IiIsImFwcF9pZCI6IlZEU1E3SldGOVEiLCJ1dWlkIjoiMzhjYWI3YzBiYTA2NDgzZDgwNmY0MmY2OWJkMDUwYmEiLCJpcEFkZHIiOiIwLjAuMC4wIiwic2NvcGUiOiIifQ.BAhAXkn2WEdZgRs0Llm51_U1e8huUn9NXgGGf_qWFEE"
appSession.set_token(auth_code)
response = appSession.generate_token()


try: 
    access_token = response["access_token"]
except Exception as e:
    print(e,response)


fyers = fyersModel.FyersModel(token=access_token,is_async=False,client_id=client_id,log_path="")
# data = {"symbol":"NSE:SBIN-EQ","resolution":"D","date_format":"0","range_from":"1622097600","range_to":"1622097685","cont_flag":"1"}
data = {'symbol': 'NSE:SBIN-EQ', 'resolution': 'D', 'date_format': '0', 'range_from': '1732213800', 'range_to': '1734805800', 'cont_flag': '1'}
print(data)
print(fyers.history(data))

# from datetime import datetime, timedelta

# start_date = datetime(2024, 6, 25)
# end_date = datetime(2024, 8, 1)

# print(start_date,end_date)

# sd_timestamp = int(datetime.strptime('2024-08-01', "%Y-%m-%d").timestamp())
# ed_timestamp = int(datetime.strptime('2024-09-01', "%Y-%m-%d").timestamp())
# print(sd_timestamp,ed_timestamp)