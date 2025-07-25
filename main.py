import time
import requests
import hmac
import base64
import hashlib
import json
import threading
from datetime import datetime
from flask import Flask

# === КЛЮЧИ KuCoin ===
API_KEY = "687d0016c714e80001eecdbe"
API_SECRET = "d954b08b-7fbd-408e-a117-4e358a8a764d"
API_PASSPHRASE = "Evgeniy@84"

# === TELEGRAM ===
TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"

# === НАСТРОЙКИ ТОРГОВЛИ ===
TRADE_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
TRADE_AMOUNT = 50
COOLDOWN_SECONDS = 3 * 60 * 60  # 3 часа
PRICE_DROP_THRESHOLD = 0.01    # 1%
TAKE_PROFIT = 0.015            # 1.5%
STOP_LOSS = 0.01               # 1%
CHECK_INTERVAL = 30            # секунд

cooldown = {}
price_history = {}
active_trades = {}

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})
    except Exception as e:
        print("❌ Ошибка Telegram:", e)

# === ЗАГОЛОВКИ KuCoin ===
def kucoin_headers(method, endpoint, body=""):
    now = str(int(time.time() * 1000))
    str_to_sign = now + method + endpoint + body
    signature = base64.b64encode(hmac.new(API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()).decode()
    passphrase = base64.b64encode(hmac.new(API_SECRET.encode(), API_PASSPHRASE.encode(), hashlib.sha256).digest()).decode()
    return {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": now,
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

# === ЦЕНА ===
def get_price(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
        response = requests.get(url)
        return float(response.json()["data"]["price"])
    except:
        return None

# === ПОКУПКА ===
def place_order(symbol, side, size):
    url = "https://api.kucoin.com/api/v1/orders"
    body = {
        "clientOid": str(int(time.time() * 1000)),
        "side": side,
        "symbol": symbol,
        "type": "market",
        "size": str(size)
    }
    headers = kucoin_headers("POST", "/api/v1/orders", json.dumps(body))
    response = requests.post(url, headers=headers, json=body)
    return response.json()

# === ОСНОВНАЯ ЛОГИКА ===
def check_market():
    while True:
        for symbol in TRADE_SYMBOLS:
            now = time.time()
            if symbol in cooldown and now - cooldown[symbol] < COOLDOWN_SECONDS:
                continue

            price = get_price(symbol)
            if not price:
                continue

            if symbol not in price_history:
                price_history[symbol] = price
                continue

            change = (price - price_history[symbol]) / price_history[symbol]
            if change <= -PRICE_DROP_THRESHOLD:
                size = round(TRADE_AMOUNT / price, 6)
                result = place_order(symbol, "buy", size)
                send_telegram(f"✅ Куплено {symbol} по {price}, объем: {size}")
                active_trades[symbol] = {
                    "buy_price": price,
                    "size": size,
                    "time": now
                }
                cooldown[symbol] = now
                price_history[symbol] = price
            elif symbol in active_trades:
                buy_price = active_trades[symbol]["buy_price"]
                if price >= buy_price * (1 + TAKE_PROFIT):
                    size = active_trades[symbol]["size"]
                    result = place_order(symbol, "sell", size)
                    send_telegram(f"📈 Продано {symbol} по {price}, профит ✅")
                    del active_trades[symbol]
                elif price <= buy_price * (1 - STOP_LOSS):
                    size = active_trades[symbol]["size"]
                    result = place_order(symbol, "sell", size)
                    send_telegram(f"📉 Продано {symbol} по {price}, стоп-лосс ❌")
                    del active_trades[symbol]

        time.sleep(CHECK_INTERVAL)

# === FLASK Keep-Alive ===
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Бот запущен и работает"

if __name__ == "__main__":
    threading.Thread(target=check_market).start()
    app.run(host="0.0.0.0", port=8080)
