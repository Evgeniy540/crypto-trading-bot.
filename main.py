import os
import time
import requests
import hmac
import base64
import hashlib
import json
from flask import Flask
from threading import Thread
from datetime import datetime
from kucoin.client import Trade
from kucoin.client import Market

# === Настройки ===
API_KEY = "687a46d91cad950001b63f47"
API_SECRET = "3c7fad47-f000-4336-8162-3e2132b6372a"
API_PASSPHRASE = "198484"
TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"
SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT", "GALA-USDT"]
TRADE_AMOUNT = 100
COOLDOWN = {}

# === Telegram уведомление ===
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Ошибка Telegram: {e}")

# === Стратегия на основе EMA ===
def get_ema_signal(symbol):
    client = Market()
    klines = client.get_kline(symbol=symbol, kline_type="1hour", size=30)
    closes = [float(k[2]) for k in klines]
    ema9 = sum(closes[-9:]) / 9
    ema21 = sum(closes[-21:]) / 21
    return "buy" if ema9 > ema21 else "hold"

# === Торговля ===
def execute_trade(symbol, action):
    if COOLDOWN.get(symbol) and time.time() - COOLDOWN[symbol] < 21600:
        return

    client = Trade(key=API_KEY, secret=API_SECRET, passphrase=API_PASSPHRASE, is_sandbox=False)
    try:
        order = client.create_market_order(symbol=symbol, side='buy', size=None, funds=str(TRADE_AMOUNT))
        COOLDOWN[symbol] = time.time()
        send_telegram(f"✅ Покупка {symbol} на {TRADE_AMOUNT} USDT. Ордер: {order['orderId']}")
    except Exception as e:
        send_telegram(f"❌ Ошибка покупки {symbol}: {e}")

# === Основной цикл ===
def trade_loop():
    while True:
        for symbol in SYMBOLS:
            try:
                signal = get_ema_signal(symbol)
                if signal == "buy":
                    execute_trade(symbol, signal)
            except Exception as e:
                print(f"Ошибка по {symbol}: {e}")
        time.sleep(3600)

# === Flask для Railway / UptimeRobot ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Бот работает!"

# === Запуск ===
def start():
    Thread(target=trade_loop).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    send_telegram("🤖 Бот запущен на Railway!")
    start()
