
import time
import hmac
import hashlib
import base64
import requests
import json
from flask import Flask, request
import threading
import logging

# === НАСТРОЙКИ ===
KUCOIN_API_KEY = "687d0016c714e80001eecdbe"
KUCOIN_API_SECRET = "d954b08b-7fbd-408e-a117-4e358a8a764d"
KUCOIN_API_PASSPHRASE = "Evgeniy@84"

BITGET_API_KEY = "b8c00194-cd2e-4196-9442-538774c5d228"
BITGET_API_SECRET = "0b2aa92e-8e69-4f8f-a392-efcabd8a5f69"
BITGET_PASSPHRASE = "Evgeniy@84"

TELEGRAM_TOKEN = "7630671081:AAG17gVyITruoH_CYreudyTBm5RTpvNgwMA"
TELEGRAM_CHAT_ID = "5723086631"

TRADE_AMOUNT = 100
ARBITRAGE_THRESHOLD = 0.35  # минимальная разница в % для запуска сделки
COOLDOWN = 60 * 60 * 3  # 3 часа между сделками по одному символу
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
