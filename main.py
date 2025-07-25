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
TRADE_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "GALA-USDT", "TRX-USDT", "XRP-USDT"]
TRADE_AMOUNT = 50
COOLDOWN_SECONDS = 3 * 60 * 60  # 3 часа
PRICE_DROP_THRESHOLD = 0.01     # 1%
TAKE_PROFIT = 0.015             # 1.5%
STOP_LOSS = 0.01                # 1%
CHECK_INTERVAL = 30             # секунд

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
        res = requests.get(url, timeout=10).json()
        return float(res["data"]["price"])
    except Exception as e:
        print(f"❌ Ошибка цены {symbol}:", e)
        return None

# === EMA ===
def get_ema(symbol, span):
    try:
        url = f"https://api.kucoin.com/api/v1/market/candles?type=1hour&symbol={symbol}"
        res = requests.get(url, timeout=10).json()
        closes = [float(c[2]) for c in res["data"]][-span:]
        return sum(closes) / len(closes)
    except Exception as e:
        print(f"❌ Ошибка EMA {symbol}:", e)
        return None

# === ОРДЕР ===
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
        r = requests.post(url, headers=headers, data=body_json, timeout=10)
        return r.json()
    except Exception as e:
        print(f"❌ Ошибка ордера {symbol}:", e)
        return None

# === ЦИКЛ ТОРГОВЛИ ===
def trading_loop():
    while True:
        for symbol in TRADE_SYMBOLS:
            now = time.time()
            if cooldown.get(symbol, 0) > now:
                continue

            price = get_price(symbol)
            if not price:
                continue

            # Обновление истории
            history = price_history.setdefault(symbol, [])
            history.append((now, price))
            history = [p for p in history if now - p[0] <= 600]
            price_history[symbol] = history

            try:
                ema9 = get_ema(symbol, 9)
                ema21 = get_ema(symbol, 21)

                if ema9 and ema21 and ema9 > ema21:
                    size = round(TRADE_AMOUNT / price, 6)
                    order = place_order(symbol, "buy", str(size))
                    if order and order.get("code") == "200000":
                        send_telegram(f"🟢 Куплено {symbol} по цене {price:.2f}")
                        active_trades[symbol] = price
                        cooldown[symbol] = now + COOLDOWN_SECONDS
                    else:
                        send_telegram(f"❌ Ошибка покупки {symbol}: {order}")
                    continue

                # Проверка падения цены
                min_price = min([p[1] for p in history])
                price_drop = (min_price - price) / min_price if min_price else 0
                if price_drop >= PRICE_DROP_THRESHOLD:
                    size = round(TRADE_AMOUNT / price, 6)
                    order = place_order(symbol, "buy", str(size))
                    if order and order.get("code") == "200000":
                        send_telegram(f"🟢 Куплено (падение) {symbol} по {price:.2f}")
                        active_trades[symbol] = price
                        cooldown[symbol] = now + COOLDOWN_SECONDS
                    continue

                # TP / SL
                if symbol in active_trades:
                    entry = active_trades[symbol]
                    change = (price - entry) / entry
                    if change >= TAKE_PROFIT:
                        send_telegram(f"✅ TP {symbol} {change*100:.2f}%")
                        del active_trades[symbol]
                    elif change <= -STOP_LOSS:
                        send_telegram(f"⚠️ SL {symbol} {change*100:.2f}%")
                        del active_trades[symbol]

            except Exception as e:
                send_telegram(f"❌ Ошибка по {symbol}: {str(e)}")

        time.sleep(CHECK_INTERVAL)

# === FLASK SERVER ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ KuCoin Auto-Trader is running!"

# === ЗАПУСК ===
threading.Thread(target=trading_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
