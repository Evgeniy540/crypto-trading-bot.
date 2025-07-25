import time
import requests
import hmac
import base64
import json
import hashlib
from datetime import datetime
import threading
from flask import Flask

# === КЛЮЧИ KuCoin ===
API_KEY = "687d0016c714e80001eecdbe"
API_SECRET = "d954b08b-7fbd-408e-a117-4e358a8a764d"
API_PASSPHRASE = "Evgeniy@84"

# === Настройки ===
TRADE_SYMBOLS = ["BTC-USDT", "ETH-USDT", "TRX-USDT", "SOL-USDT"]
TRADE_AMOUNT = 50
PRICE_DROP_THRESHOLD = 0.01  # 1%
TAKE_PROFIT = 0.015          # 1.5%
STOP_LOSS = 0.01             # 1%

price_history = {}
active_trades = {}

def kucoin_headers(method, endpoint, body=""):
    now = int(time.time() * 1000)
    str_to_sign = str(now) + method + endpoint + body
    signature = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), str_to_sign.encode('utf-8'), hashlib.sha256).digest()
    )
    passphrase = base64.b64encode(
        hmac.new(API_SECRET.encode('utf-8'), API_PASSPHRASE.encode('utf-8'), hashlib.sha256).digest()
    )
    return {
        "KC-API-KEY": API_KEY,
        "KC-API-SIGN": signature.decode(),
        "KC-API-TIMESTAMP": str(now),
        "KC-API-PASSPHRASE": passphrase.decode(),
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

def get_price(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol}"
        r = requests.get(url).json()
        return float(r["data"]["price"])
    except Exception as e:
        print(f"[{symbol}] ❌ Ошибка получения цены: {e}")
        return None

def place_order(symbol, side, size):
    url = "https://api.kucoin.com/api/v1/orders"
    body = {
        "clientOid": str(int(time.time()*1000)),
        "side": side,
        "symbol": symbol,
        "type": "market",
        "size": size
    }
    body_json = json.dumps(body)
    headers = kucoin_headers("POST", "/api/v1/orders", body_json)
    try:
        r = requests.post(url, headers=headers, data=body_json)
        return r.json()
    except Exception as e:
        print(f"[{symbol}] ❌ Ошибка размещения ордера: {e}")
        return None

def trading_loop():
    print("🟢 Бот запущен и работает!")
    while True:
        for symbol in TRADE_SYMBOLS:
            base = symbol.split("-")[0]
            price = get_price(symbol)
            if not price:
                print(f"[{symbol}] ⚠️ Цена не получена")
                continue

            history = price_history.setdefault(symbol, [])
            history.append((time.time(), price))
            history = [p for p in history if time.time() - p[0] <= 600]
            price_history[symbol] = history

            min_price = min([p[1] for p in history])
            price_drop = (min_price - price) / min_price if min_price else 0

            if symbol in active_trades:
                entry_price = active_trades[symbol]
                change = (price - entry_price) / entry_price

                if change >= TAKE_PROFIT:
                    print(f"[{symbol}] ✅ Продажа по TP: +{change*100:.2f}%")
                    del active_trades[symbol]
                elif change <= -STOP_LOSS:
                    print(f"[{symbol}] ⚠️ Продажа по SL: {change*100:.2f}%")
                    del active_trades[symbol]
                continue

            if price_drop >= PRICE_DROP_THRESHOLD:
                print(f"[{symbol}] 📉 Цена упала на {price_drop*100:.2f}% — покупаем...")
                usdt_price = price
                size = round(TRADE_AMOUNT / usdt_price, 6)
                order = place_order(symbol, "buy", str(size))
                print(f"[{symbol}] 🛒 Ордер: {order}")
                active_trades[symbol] = price

        time.sleep(30)

# === Flask keep-alive ===
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ KuCoin Bot работает!"

threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
