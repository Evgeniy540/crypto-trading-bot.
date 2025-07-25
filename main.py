
import time
import hmac
import hashlib
import base64
import requests
import json
import threading
import logging
from flask import Flask

# === НАСТРОЙКИ ===
KUCOIN_API_KEY = "687d0016c714e80001eecdbe"
KUCOIN_API_SECRET = "d954b08b-7fbd-408e-a117-4e358a8a764d"
KUCOIN_API_PASSPHRASE = "Evgeniy@84"

BITGET_API_KEY = "bg_ec8a64de58248985f9817cbd3db16977"
BITGET_API_SECRET = "b56b8e53af502bee4ba48c7e5eedcf67784526c53075bd1734b7f8ef3381c018"
BITGET_API_PASSPHRASE = "Evgeniy@84"

TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"
TRADE_AMOUNT = 100
ARBITRAGE_THRESHOLD = 0.35
COOLDOWN = 60 * 60 * 3

last_trade_time = {}
SYMBOLS = ["TRX/USDT", "XRP/USDT", "SOL/USDT", "BTC/USDT", "GALA/USDT"]

BITGET_SYMBOLS = {
    "BTC/USDT": "BTCUSDT_SPBL",
    "ETH/USDT": "ETHUSDT_SPBL",
    "SOL/USDT": "SOLUSDT_SPBL",
    "TRX/USDT": "TRXUSDT_SPBL",
    "XRP/USDT": "XRPUSDT_SPBL",
    "GALA/USDT": "GALAUSDT_SPBL"
}

BITGET_WALLETS = {
    "BTC": "bitget_btc_wallet_address",
    "ETH": "bitget_eth_wallet_address",
    "SOL": "bitget_sol_wallet_address",
    "TRX": "bitget_trx_wallet_address",
    "XRP": "bitget_xrp_wallet_address",
    "GALA": "bitget_gala_wallet_address"
}

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

def send_telegram(msg):
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})
    except Exception as e:
        logging.error(f"Telegram Error: {e}")

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
    try:
        s = symbol.replace("/", "-")
        r = requests.get(f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={s}")
        data = r.json().get("data")
        if not data or "price" not in data:
            raise ValueError("Цена KuCoin не получена")
        return float(data["price"])
    except Exception as e:
        logging.error(f"KuCoin Price Error ({symbol}): {e}")
        return None

def kucoin_buy(symbol, amount):
    try:
        s = symbol.replace("/", "-")
        url = "https://api.kucoin.com/api/v1/orders"
        body = {
            "clientOid": str(time.time()),
            "side": "buy",
            "symbol": s,
            "type": "market",
            "funds": str(amount)
        }
        r = requests.post(url, headers=kucoin_headers("POST", "/api/v1/orders"), json=body)
        return r.json()
    except Exception as e:
        logging.error(f"KuCoin Buy Error ({symbol}): {e}")
        return {}

def kucoin_withdraw(symbol, amount_coin):
    coin = symbol.split("/")[0]
    address = BITGET_WALLETS.get(coin)
    if not address:
        send_telegram(f"❌ Нет адреса Bitget для {coin}")
        return
    try:
        url = "https://api.kucoin.com/api/v1/withdrawals"
        body = {
            "currency": coin,
            "address": address,
            "amount": str(round(amount_coin, 6)),
            "chain": "Main",
            "remark": "To Bitget"
        }
        r = requests.post(url, headers=kucoin_headers("POST", "/api/v1/withdrawals"), json=body)
        send_telegram(f"📤 Перевод {amount_coin} {coin} на Bitget: {r.text}")
    except Exception as e:
        logging.error(f"KuCoin Withdraw Error ({coin}): {e}")

def bitget_headers(method, request_path, body=''):
    timestamp = str(int(time.time() * 1000))
    message = timestamp + method + request_path + body
    signature = base64.b64encode(
        hmac.new(BITGET_API_SECRET.encode(), message.encode(), hashlib.sha256).digest()
    ).decode()
    return {
        'Content-Type': 'application/json',
        'ACCESS-KEY': BITGET_API_KEY,
        'ACCESS-SIGN': signature,
        'ACCESS-TIMESTAMP': timestamp,
        'ACCESS-PASSPHRASE': BITGET_API_PASSPHRASE
    }

def bitget_get_price(symbol):
    try:
        s = BITGET_SYMBOLS.get(symbol)
        r = requests.get(f"https://api.bitget.com/api/spot/v1/market/ticker?symbol={s}")
        return float(r.json()["data"]["close"])
    except Exception as e:
        logging.error(f"Bitget Price Error ({symbol}): {e}")
        return None

def bitget_sell(symbol, amount_coin):
    s = BITGET_SYMBOLS.get(symbol)
    if not s:
        send_telegram(f"❌ Символ не найден для Bitget: {symbol}")
        return 0
    url = "https://api.bitget.com/api/spot/v1/trade/orders"
    price = bitget_get_price(symbol)
    if not price:
        send_telegram("❌ Не удалось получить цену для продажи")
        return 0

    body = {
        "symbol": s,
        "side": "sell",
        "orderType": "market",
        "force": "gtc",
        "size": str(amount_coin)
    }
    body_json = json.dumps(body)
    headers = bitget_headers("POST", "/api/spot/v1/trade/orders", body_json)
    r = requests.post(url, headers=headers, data=body_json)
    try:
        res = r.json()
        send_telegram(f"💸 Продажа {amount_coin} {symbol.split('/')[0]} на Bitget: {res}")
        return round(price * amount_coin, 2)
    except:
        send_telegram("❌ Ошибка продажи на Bitget")
        return 0

def arbitrage_loop():
    global TRADE_AMOUNT
    logging.info("🔁 arbitrage_loop запущен")
    send_telegram("🤖 Бот запущен. Ожидает выгодный арбитраж...")
    while True:
        for symbol in SYMBOLS:
            now = time.time()
            if symbol in last_trade_time and now - last_trade_time[symbol] < COOLDOWN:
                continue
            kucoin_price = kucoin_get_price(symbol)
            bitget_price = bitget_get_price(symbol)
            if kucoin_price and bitget_price:
                diff = (bitget_price - kucoin_price) / kucoin_price * 100
                logging.info(f"{symbol}: KuCoin={kucoin_price}, Bitget={bitget_price}, Разница={diff:.2f}%")
                if diff >= ARBITRAGE_THRESHOLD:
                    result = kucoin_buy(symbol, TRADE_AMOUNT)
                    send_telegram(f"✅ Куплено {symbol} на KuCoin за {TRADE_AMOUNT} USDT")
                    amount_coin = round(TRADE_AMOUNT / kucoin_price * 0.98, 6)
                    kucoin_withdraw(symbol, amount_coin)
                    time.sleep(30)
                    earned = bitget_sell(symbol, amount_coin)
                    profit = earned - TRADE_AMOUNT
                    send_telegram(f"📈 Прибыль: {profit:.2f} USDT")
                    TRADE_AMOUNT += profit if profit > 0 else 0
                    last_trade_time[symbol] = now
        time.sleep(60)

@app.route("/")
def home():
    return "✅ Arbitrage bot is running"

@app.route("/status")
def status():
    return json.dumps({"status": "running", "balance": TRADE_AMOUNT}), 200

if __name__ == "__main__":
    threading.Thread(target=arbitrage_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
