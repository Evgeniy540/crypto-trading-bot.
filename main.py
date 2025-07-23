import time
import hmac
import hashlib
import base64
import requests
import json
from flask import Flask
import threading
from datetime import datetime
import logging

# === НАСТРОЙКИ ===
KUCOIN_API_KEY = "687d0016c714e80001eecdbe"
KUCOIN_API_SECRET = "d954b08b-7fbd-408e-a117-4e358a8a764d"
KUCOIN_API_PASSPHRASE = "Evgeniy@84"
TRADE_PASSWORD = "198483"

TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"

TRADE_AMOUNT = 100  # USDT
SYMBOLS = ["TRX/USDT", "XRP/USDT", "SOL/USDT", "BTC/USDT"]
ARBITRAGE_THRESHOLD = 0.8  # %
COOLDOWN = 60 * 60 * 3  # 3 часа
last_trade_time = {}

# === Bitget пары ===
BITGET_SYMBOLS = {
    "BTC/USDT": "BTCUSDT_SPBL",
    "ETH/USDT": "ETHUSDT_SPBL",
    "SOL/USDT": "SOLUSDT_SPBL",
    "TRX/USDT": "TRXUSDT_SPBL",
    "XRP/USDT": "XRPUSDT_SPBL"
}

# === TELEGRAM ===
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message})

# === KUCOIN ===
def kucoin_headers(method, endpoint):
    now = int(time.time() * 1000)
    str_to_sign = f'{now}{method}{endpoint}'
    signature = base64.b64encode(hmac.new(KUCOIN_API_SECRET.encode(), str_to_sign.encode(), hashlib.sha256).digest()).decode()
    passphrase = base64.b64encode(hmac.new(KUCOIN_API_SECRET.encode(), KUCOIN_API_PASSPHRASE.encode(), hashlib.sha256).digest()).decode()
    return {
        "KC-API-KEY": KUCOIN_API_KEY,
        "KC-API-SIGN": signature,
        "KC-API-TIMESTAMP": str(now),
        "KC-API-PASSPHRASE": passphrase,
        "KC-API-KEY-VERSION": "2",
        "Content-Type": "application/json"
    }

def kucoin_get_price(symbol):
    symbol_clean = symbol.replace("/", "-")
    url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={symbol_clean}"
    r = requests.get(url)
    result = r.json()

    if "data" in result and result["data"] and "price" in result["data"]:
        return float(result["data"]["price"])
    else:
        send_telegram(f"❌ KuCoin не вернул цену для {symbol}: {result}")
        return None

def kucoin_buy(symbol, amount_usdt):
    symbol_clean = symbol.replace("/", "-")
    url = "https://api.kucoin.com/api/v1/orders"
    data = {
        "clientOid": str(time.time()),
        "side": "buy",
        "symbol": symbol_clean,
        "type": "market",
        "funds": str(amount_usdt)
    }
    r = requests.post(url, headers=kucoin_headers("POST", "/api/v1/orders"), json=data)
    return r.json()

def kucoin_get_address(symbol):
    coin = symbol.split("/")[0]
    url = f"https://api.kucoin.com/api/v2/wallet/addresses?currency={coin}&chain=Main"
    r = requests.get(url, headers=kucoin_headers("GET", f"/api/v2/wallet/addresses?currency={coin}&chain=Main"))
    addresses = r.json().get("data", [])
    if not addresses:
        return None
    return addresses[0]["address"]

def kucoin_withdraw(symbol, amount):
    coin = symbol.split("/")[0]
    address = kucoin_get_address(symbol)
    if not address:
        send_telegram(f"❌ Не удалось получить адрес для перевода {coin}")
        return

    url = "https://api.kucoin.com/api/v1/withdrawals"
    data = {
        "currency": coin,
        "address": address,
        "amount": str(amount),
        "chain": "Main",
        "remark": "Transfer to Bitget",
        "tradePassword": TRADE_PASSWORD
    }
    r = requests.post(url, headers=kucoin_headers("POST", "/api/v1/withdrawals"), json=data)
    if r.status_code == 200 and r.json()["code"] == "200000":
        send_telegram(f"🚀 Перевод {amount} {coin} на Bitget отправлен!")
    else:
        send_telegram(f"⚠️ Ошибка перевода {coin}: {r.text}")

# === BITGET ===
def bitget_get_price(symbol):
    bitget_symbol = BITGET_SYMBOLS.get(symbol)
    if not bitget_symbol:
        send_telegram(f"❌ Неизвестная пара для Bitget: {symbol}")
        return None

    url = f"https://api.bitget.com/api/spot/v1/market/ticker?symbol={bitget_symbol}"
    r = requests.get(url)
    result = r.json()
    if "data" in result and result["data"] and "close" in result["data"]:
        return float(result["data"]["close"])
    else:
        send_telegram(f"❌ Bitget не вернул цену для {symbol}: {result}")
        return None

# === АРБИТРАЖ ===
def arbitrage():
    while True:
        for symbol in SYMBOLS:
            try:
                now = time.time()
                if symbol in last_trade_time and now - last_trade_time[symbol] < COOLDOWN:
                    continue

                kucoin_price = kucoin_get_price(symbol)
                bitget_price = bitget_get_price(symbol)

                if kucoin_price is None or bitget_price is None:
                    continue

                diff_percent = ((bitget_price - kucoin_price) / kucoin_price) * 100
                if diff_percent >= ARBITRAGE_THRESHOLD:
                    buy_result = kucoin_buy(symbol, TRADE_AMOUNT)
                    last_trade_time[symbol] = now
                    send_telegram(f"✅ Куплено {symbol} на KuCoin по {kucoin_price:.4f} | Профит: {diff_percent:.2f}%")

                    time.sleep(10)

                    coin = symbol.split("/")[0]
                    amount_coin = TRADE_AMOUNT / kucoin_price
                    kucoin_withdraw(symbol, round(amount_coin * 0.98, 6))

                else:
                    print(f"{symbol}: разница {diff_percent:.2f}% — недостаточно")

            except Exception as e:
                send_telegram(f"⚠️ Ошибка в арбитраже {symbol}: {e}")
        time.sleep(60)

# === KEEP-ALIVE ===
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Arbitrage Bot is running!"

# === ЗАПУСК ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    threading.Thread(target=arbitrage, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
