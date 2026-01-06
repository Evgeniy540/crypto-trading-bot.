import time
import hmac
import hashlib
import requests
import threading
import os
from flask import Flask

# === НАСТРОЙКИ ===
TELEGRAM_TOKEN = "AAEnqRYtbaNHX8V5LtrST5e-SZh6iGkPi1Y"
TELEGRAM_CHAT_ID = "8377721363"
CHECK_INTERVAL = 30  # секунд
ARBITRAGE_THRESHOLD = 0.25  # в процентах

# ХОДОВЫЕ МОНЕТЫ
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "TRXUSDT",
    "LTCUSDT", "DOGEUSDT", "MATICUSDT", "ADAUSDT", "SHIBUSDT",
    "APTUSDT", "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "SUIUSDT", "ARBUSDT", "PEPEUSDT"
]

app = Flask(__name__)

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

# === KUCOIN ===
def get_kucoin_price(symbol):
    try:
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol.replace('USDT', '-USDT')}"
        res = requests.get(url).json()
        return float(res["data"]["price"])
    except:
        return None

# === BITGET ===
def get_bitget_price(symbol):
    try:
        url = f"https://api.bitget.com/api/spot/v1/market/ticker?symbol={symbol}"
        res = requests.get(url).json()
        return float(res["data"]["close"])
    except:
        return None

# === ПРОВЕРКА АРБИТРАЖА ===
def check_arbitrage():
    while True:
        for symbol in SYMBOLS:
            try:
                price_kucoin = get_kucoin_price(symbol)
                price_bitget = get_bitget_price(symbol)
                if price_kucoin is None or price_bitget is None:
                    continue

                diff = abs(price_kucoin - price_bitget)
                avg_price = (price_kucoin + price_bitget) / 2
                percent_diff = (diff / avg_price) * 100

                if percent_diff >= ARBITRAGE_THRESHOLD:
                    direction = "🟢 Bitget дороже" if price_bitget > price_kucoin else "🔴 KuCoin дороже"
                    message = (
                        f"📊 Арбитраж по {symbol}:\n"
                        f"{direction}\n"
                        f"KuCoin: {price_kucoin:.4f} USDT\n"
                        f"Bitget: {price_bitget:.4f} USDT\n"
                        f"Разница: {percent_diff:.2f}%"
                    )
                    send_telegram(message)
            except Exception as e:
                send_telegram(f"⚠️ Ошибка при проверке {symbol}: {e}")
        time.sleep(CHECK_INTERVAL)

# === FLASK ДЛЯ RENDER ===
@app.route("/")
def home():
    return "🟢 Arbitrage signal bot is running!"

# === СТАРТ ===
def run_bot():
    send_telegram("🤖 Арбитражный бот запущен и следит за рынком!")
    threading.Thread(target=check_arbitrage).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

if __name__ == "__main__":
    run_bot()
