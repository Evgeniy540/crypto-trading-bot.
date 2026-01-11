import time, hmac, hashlib, json, requests, threading, os, schedule
from flask import Flask, request
from datetime import datetime
import numpy as np
import pandas as pd

# === КЛЮЧИ ===
API_KEY = "bg_7bd202760f36727cedf11a481dbca611"
API_SECRET = "b6bd206dfbe827ee5b290604f6097d781ce5adabc3f215bba2380fb39c0e9711"
API_PASSPHRASE = "Evgeniy84"
TELEGRAM_TOKEN = "8377721363:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"

# === НАСТРОЙКИ ===
TRADE_AMOUNT = 10.0
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "TRXUSDT", "PEPEUSDT", "BGBUSDT"]
INTERVAL = "1m"
TP_PERCENT = 1.5
SL_PERCENT = 1.0

app = Flask(__name__)
positions_file = "short_positions.json"
profit_file = "short_profit.json"

# === Bitget API ===
def bitget_request(method, path, params=None, body=""):
    timestamp = str(int(time.time() * 1000))
    query = "" if not params else "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    pre_hash = timestamp + method + path + query + body
    sign = hmac.new(API_SECRET.encode(), pre_hash.encode(), hashlib.sha256).hexdigest()
    headers = {
        "ACCESS-KEY": API_KEY,
        "ACCESS-SIGN": sign,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": API_PASSPHRASE,
        "Content-Type": "application/json"
    }
    url = "https://api.bitget.com" + path
    if method == "GET":
        r = requests.get(url, headers=headers, params=params)
    elif method == "POST":
        r = requests.post(url, headers=headers, data=body)
    else:
        return None
    return r.json()

def get_candles(symbol):
    try:
        params = {"symbol": symbol, "granularity": "1m", "limit": "100"}
        res = bitget_request("GET", "/api/spot/v1/market/candles", params)
        candles = res["data"]
        close_prices = [float(c[4]) for c in candles][::-1]
        return close_prices
    except:
        return []

def calculate_ema(prices, period):
    return list(np.array(pd.Series(prices).ewm(span=period, adjust=False).mean()))

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

def load_positions():
    try:
        with open(positions_file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_positions(data):
    with open(positions_file, "w") as f:
        json.dump(data, f, indent=2)

def load_profit():
    try:
        with open(profit_file, "r") as f:
            return json.load(f)
    except:
        return {"total_profit": 0}

def save_profit(data):
    with open(profit_file, "w") as f:
        json.dump(data, f, indent=2)

def get_balance(symbol="USDT"):
    res = bitget_request("GET", "/api/spot/v1/account/assets", {})
    for item in res["data"]:
        if item["coinName"] == symbol:
            return float(item["available"])
    return 0.0

def place_order(symbol, side, size):
    body = json.dumps({
        "symbol": symbol,
        "side": side,
        "orderType": "market",
        "force": "gtc",
        "size": str(size)
    })
    return bitget_request("POST", "/api/spot/v1/trade/orders", body=body)

def monitor():
    global TRADE_AMOUNT
    while True:
        positions = load_positions()
        profit_data = load_profit()
        for symbol in SYMBOLS:
            try:
                if symbol in positions:
                    entry = positions[symbol]["entry"]
                    amount = float(positions[symbol]["amount"])
                    balance = get_balance(symbol.replace("USDT", ""))
                    current_price = float(get_candles(symbol)[-1])

                    tp_price = entry * (1 - TP_PERCENT / 100)
                    sl_price = entry * (1 + SL_PERCENT / 100)

                    if current_price <= tp_price or current_price >= sl_price:
                        cost = amount * current_price
                        result = (entry - current_price) * amount
                        profit_data["total_profit"] += result
                        save_profit(profit_data)
                        place_order(symbol, "buy", amount)
                        send_telegram(f"✅ Закрыт SHORT {symbol} по {'TP' if current_price <= tp_price else 'SL'}\nПрибыль: {result:.4f} USDT")
                        del positions[symbol]
                        save_positions(positions)
                        if result > 0:
                            TRADE_AMOUNT += result
                    continue

                prices = get_candles(symbol)
                if len(prices) < 21:
                    continue
                ema9 = calculate_ema(prices, 9)[-1]
                ema21 = calculate_ema(prices, 21)[-1]

                if ema9 < ema21:
                    coin = symbol.replace("USDT", "")
                    balance = get_balance(coin)
                    if balance * prices[-1] < TRADE_AMOUNT:
                        continue

                    qty = round(TRADE_AMOUNT / prices[-1], 5)
                    place_order(symbol, "sell", qty)
                    positions[symbol] = {"entry": prices[-1], "amount": qty}
                    save_positions(positions)
                    send_telegram(f"🔻 SHORT {symbol} по цене {prices[-1]} на сумму {TRADE_AMOUNT} USDT")
            except Exception as e:
                send_telegram(f"Ошибка по {symbol}: {e}")
        time.sleep(30)

@app.route('/')
def home():
    return "Short bot is running!"

@app.route('/profit', methods=["GET", "POST"])
def profit():
    data = load_profit()
    return f"📊 Текущая прибыль: {data['total_profit']:.4f} USDT"

def start():
    threading.Thread(target=monitor).start()
    schedule.every().day.at("20:47").do(lambda: send_telegram(f"📊 Ежедневная прибыль: {load_profit()['total_profit']:.4f} USDT"))
    threading.Thread(target=lambda: schedule.run_pending()).start()
    send_telegram("🤖 Short бот успешно запущен на Render!")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    start()
