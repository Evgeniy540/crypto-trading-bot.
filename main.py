import time
import hmac
import base64
import hashlib
import requests
import json
import threading
from flask import Flask

# === CONFIG ===
API_KEY = "687a46d91cad950001b63f47"
API_SECRET = "3c7fad47-f000-4336-8162-3e2132b6372a"
API_PASSPHRASE = "198483"
TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"
TRADE_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "GALA-USDT"]
TRADE_AMOUNT = 28
COOLDOWN_SECONDS = 6 * 60 * 60

cooldown = {}

# === UTILS ===

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=payload)
    except:
        pass

def kucoin_headers(endpoint, method="GET", body=""):
    now = str(int(time.time() * 1000))
    str_to_sign = now + method + endpoint + body
    signature = base64.b64encode(hmac.new(API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest())
    passphrase = base64.b64encode(hmac.new(API_SECRET.encode(), API_PASSPHRASE.encode(), hashlib.sha256).digest())
    return {
        "KC-API-KEY": 687a46d91cad950001b63f47,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": now,
        "KC-API-PASSPHRASE": 198483,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

def get_price(symbol):
    url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
    response = requests.get(url)
    return float(response.json()["data"]["price"])

def get_ema(symbol, span):
    url = f"https://api.kucoin.com/api/v1/market/candles?type=1hour&symbol={symbol}"
    res = requests.get(url).json()
    closes = [float(c[2]) for c in res["data"]][-span:]
    return sum(closes) / len(closes)

def place_order(symbol, side, size):
    endpoint = "/api/v1/orders"
    url = "https://api.kucoin.com" + endpoint
    data = {
        "clientOid": str(int(time.time() * 1000)),
        "side": side,
        "symbol": symbol,
        "type": "market",
        "funds": str(size)
    }
    headers = kucoin_headers(endpoint, "POST", json.dumps(data))
    res = requests.post(url, headers=headers, json=data)
    return res.json()

# === TRADING LOOP ===

def trade_loop():
    while True:
        for symbol in TRADE_SYMBOLS:
            now = time.time()
            if cooldown.get(symbol, 0) > now:
                continue

            try:
                ema9 = get_ema(symbol, 9)
                ema21 = get_ema(symbol, 21)
                price = get_price(symbol)

                if ema9 > ema21:
                    order = place_order(symbol, "buy", TRADE_AMOUNT)
                    if order.get("code") == "200000":
                        send_telegram(f"✅ Куплено {symbol} по {price}\nEMA9={ema9:.2f} > EMA21={ema21:.2f}")
                        cooldown[symbol] = now + COOLDOWN_SECONDS
                    else:
                        send_telegram(f"❌ Ошибка покупки {symbol}: {order}")
                else:
                    print(f"{symbol}: EMA9={ema9:.2f}, EMA21={ema21:.2f} — сигналов нет")
            except Exception as e:
                send_telegram(f"⚠️ Ошибка по {symbol}: {str(e)}")

        time.sleep(300)  # Проверять каждые 5 минут

# === FLASK KEEP-ALIVE ===

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Бот работает"

# === START ===

if __name__ == '__main__':
    threading.Thread(target=trade_loop).start()
    app.run(host='0.0.0.0', port=3000)
