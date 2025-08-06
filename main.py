import time, hmac, hashlib, json, requests, threading, os
import numpy as np
import pandas as pd
from flask import Flask
from datetime import datetime

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "TRXUSDT", "PEPEUSDT", "BGBUSDT"]
CHECK_INTERVAL = 30  # секунд

app = Flask(__name__)

# === Bitget API ===
def bitget_request(method, path, params=None):
    timestamp = str(int(time.time() * 1000))
    query = "" if not params else "&".join([f"{k}={v}" for k, v in sorted(params.items())])
    body = ""
    pre_hash = timestamp + method + path + query + body
    sign = hmac.new(
        "b6bd206dfbe827ee5b290604f6097d781ce5adabc3f215bba2380fb39c0e9711".encode(),
        pre_hash.encode(),
        hashlib.sha256
    ).hexdigest()
    headers = {
        "ACCESS-KEY": "bg_7bd202760f36727cedf11a481dbca611",
        "ACCESS-SIGN": sign,
        "ACCESS-TIMESTAMP": timestamp,
        "ACCESS-PASSPHRASE": "Evgeniy84",
        "Content-Type": "application/json"
    }
    url = "https://api.bitget.com" + path
    if method == "GET":
        r = requests.get(url, headers=headers, params=params)
        return r.json()
    return None

def get_candles(symbol):
    try:
        params = {"symbol": symbol, "granularity": "1m", "limit": "100"}
        res = bitget_request("GET", "/api/spot/v1/market/candles", params)
        candles = res.get("data", [])
        closes = [float(c[4]) for c in candles][::-1]
        return closes
    except:
        return []

def calculate_ema(prices, period):
    return pd.Series(prices).ewm(span=period, adjust=False).mean().tolist()

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text})

def signal_monitor():
    last_signals = {}
    while True:
        for symbol in SYMBOLS:
            try:
                closes = get_candles(symbol)
                if len(closes) < 21:
                    continue
                ema9 = calculate_ema(closes, 9)[-1]
                ema21 = calculate_ema(closes, 21)[-1]
                previous = last_signals.get(symbol, "")

                if ema9 > ema21 and previous != "long":
                    send_telegram(f"🟢 [SIGNAL] LONG по {symbol}\nEMA9: {ema9:.2f} > EMA21: {ema21:.2f}")
                    last_signals[symbol] = "long"
                elif ema9 < ema21 and previous != "short":
                    send_telegram(f"🔴 [SIGNAL] SHORT по {symbol}\nEMA9: {ema9:.2f} < EMA21: {ema21:.2f}")
                    last_signals[symbol] = "short"
                else:
                    pass  # нет нового сигнала
            except Exception as e:
                send_telegram(f"⚠️ Ошибка {symbol}: {e}")
        time.sleep(CHECK_INTERVAL)

@app.route("/")
def home():
    return "Signal bot is running!"

def start():
    send_telegram("📡 Сигнальный бот запущен и отслеживает сигналы по EMA (9/21)")
    threading.Thread(target=signal_monitor).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    start()
