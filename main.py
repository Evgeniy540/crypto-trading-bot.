# ================== ВЕРСИЯ С /status ==================
# Все как раньше, но добавлена обработка команд Telegram
# включая /status

import os
import time
import threading
from datetime import datetime, timezone
from collections import defaultdict
from typing import Tuple, Optional, List

import requests
from flask import Flask

# ========== ТВОИ ДАННЫЕ ==========
TELEGRAM_BOT_TOKEN = "AAEnqRYtbaNHX8V5LtrST5e-SZh6iGkPi1Y"  # вставь свой токен
TELEGRAM_CHAT_ID   = os.environ.get("TG_CHAT_ID", "auto")   # оставь "auto" или укажи chat_id
# =================================

DEFAULT_SYMBOLS = [
    "BTC-USDT","ETH-USDT","BNB-USDT","SOL-USDT","XRP-USDT","ADA-USDT","DOGE-USDT","TRX-USDT",
    "TON-USDT","LINK-USDT","LTC-USDT","DOT-USDT","ARB-USDT","OP-USDT","PEPE-USDT","SHIB-USDT"
]

BASE_TF_HUMAN     = "5m"
FALLBACK_TF_HUMAN = "1m"

EMA_FAST, EMA_SLOW = 9, 21
CANDLES_NEED       = 100
CHECK_INTERVAL_S   = 180
COOLDOWN_S         = 180
SEND_NOSIG_EVERY   = 3600
THROTTLE_PER_SYMBOL_S = 0.25

MODE          = "both"
EPS_PCT       = 0.10/100
REPORT_SUMMARY_EVERY = 30*60
KUCOIN_BASE = "https://api.kucoin.com"

app = Flask(__name__)

last_signal_ts = defaultdict(lambda: 0)
last_nosig_ts  = defaultdict(lambda: 0)
last_cross_dir = defaultdict(lambda: None)
last_summary_ts = 0
SETTINGS = {"symbols": sorted(DEFAULT_SYMBOLS)}

# ========== УТИЛИТЫ ==========
def now_ts() -> int:
    return int(time.time())

def ts_utc_str(ts: Optional[int] = None) -> str:
    ts = ts if ts is not None else now_ts()
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def tg_send(text: str) -> None:
    if TELEGRAM_CHAT_ID in ("", None, "auto"):
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10
        )
    except Exception:
        pass

def tg_delete_webhook():
    try:
        requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": True},
            timeout=10
        )
    except Exception:
        pass

def tg_get_updates(offset=None):
    try:
        params = {"timeout": 0}
        if offset: params["offset"] = offset
        r = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
                         params=params, timeout=10)
        return r.json().get("result", [])
    except Exception:
        return []

def tf_human_to_kucoin(tf: str) -> str:
    _TF_MAP = {
        "1m":"1min","3m":"3min","5m":"5min","15m":"15min","30m":"30min",
        "1h":"1hour","2h":"2hour","4h":"4hour","6h":"6hour","8h":"8hour","12h":"12hour",
        "1d":"1day","1w":"1week"
    }
    tf = tf.strip().lower()
    if tf in _TF_MAP.values():
        return tf
    return _TF_MAP.get(tf, "5min")

def kucoin_candles(symbol: str, tf_kucoin: str, need: int, max_retries: int = 3) -> Tuple[List[float], List[float], List[float]]:
    url = f"{KUCOIN_BASE}/api/v1/market/candles"
    params = {"type": tf_kucoin, "symbol": symbol}
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, timeout=12)
            if r.status_code in (429, 503):
                time.sleep(0.5 * attempt)
                continue
            r.raise_for_status()
            data = r.json().get("data", [])
            if not isinstance(data, list) or not data:
                time.sleep(0.25 * attempt)
                continue
            arr = list(reversed(data))[-max(need, EMA_SLOW + 3):]
            closes = [float(x[2]) for x in arr]
            highs  = [float(x[3]) for x in arr]
            lows   = [float(x[4]) for x in arr]
            return closes, highs, lows
        except Exception:
            time.sleep(0.4 * attempt)
    return [], [], []

def ema(series: List[float], period: int) -> List[Optional[float]]:
    if len(series) < period:
        return []
    k = 2.0 / (period + 1)
    out: List[Optional[float]] = [None] * (period - 1)
    ema_val = sum(series[:period]) / period
    out.append(ema_val)
    for x in series[period:]:
        ema_val = x * k + ema_val * (1 - k)
        out.append(ema_val)
    return out

def pct(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return (a - b) / b

def analyze_symbol(symbol: str, tf_human: str, need: int) -> Tuple[Optional[str], Optional[str], str]:
    tf_kucoin = tf_human_to_kucoin(tf_human)
    closes, highs, lows = kucoin_candles(symbol, tf_kucoin, need)
    tf_used = tf_kucoin

    if len(closes) < max(EMA_SLOW + 2, 30):
        fb_kucoin = tf_human_to_kucoin(FALLBACK_TF_HUMAN)
        closes, highs, lows = kucoin_candles(symbol, fb_kucoin, need)
        tf_used = fb_kucoin

    if len(closes) < max(EMA_SLOW + 2, 30):
        return None, None, f"Недостаточно данных ({len(closes)})"

    ema_fast = ema(closes, EMA_FAST)
    ema_slow = ema(closes, EMA_SLOW)
    if not ema_fast or not ema_slow:
        return None, None, "EMA not ready"

    f1, f2 = ema_fast[-2], ema_fast[-1]
    s1, s2 = ema_slow[-2], ema_slow[-1]

    crossed_up   = f1 <= s1 and f2 > s2
    crossed_down = f1 >= s1 and f2 < s2

    dist_pct = abs(pct(f2, s2))
    near_cross = dist_pct <= EPS_PCT

    strong_dir = None
    if crossed_up:
        strong_dir = "up"
    elif crossed_down:
        strong_dir = "down"

    if strong_dir:
        last_cross_dir[symbol] = strong_dir
        return "STRONG", strong_dir, f"cross {strong_dir}, tf={tf_used}"

    if MODE == "both":
        if near_cross:
            direction = "up" if f2 >= s2 else "down"
            return "WEAK", direction, f"near-cross Δ≈{dist_pct*100:.3f}%, tf={tf_used}"
        if last_cross_dir[symbol] in ("up", "down"):
            dir_ = last_cross_dir[symbol]
            if dir_ == "up" and f2 > s2 and dist_pct <= (EPS_PCT * 1.2):
                return "WEAK", "up", f"retest↑ Δ≈{dist_pct*100:.3f}%, tf={tf_used}"
            if dir_ == "down" and f2 < s2 and dist_pct <= (EPS_PCT * 1.2):
                return "WEAK", "down", f"retest↓ Δ≈{dist_pct*100:.3f}%, tf={tf_used}"

    return None, None, f"Нет сигнала (tf={tf_used}, свечей={len(closes)})"

def format_signal(symbol: str, kind: str, direction: str, reason: str) -> str:
    arrow = "🟢BUY" if direction == "up" else "🔴SELL"
    tag = "STRONG" if kind == "STRONG" else "weak"
    return (
        f"⚡ {symbol}: {arrow} <b>{tag}</b>\n"
        f"• EMA9/21: {reason}\n"
        f"• UTC: {ts_utc_str()}"
    )

# ========== TELEGRAM /status ==========
def process_updates():
    global TELEGRAM_CHAT_ID
    last_update_id = None
    while True:
        for upd in tg_get_updates(last_update_id + 1 if last_update_id else None):
            last_update_id = upd["update_id"]
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat", {})
            chat_id = str(chat.get("id"))
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            if TELEGRAM_CHAT_ID in ("", "auto", None):
                TELEGRAM_CHAT_ID = chat_id
                tg_send(f"🔗 Привязал этот чат: <code>{TELEGRAM_CHAT_ID}</code>")
            if TELEGRAM_CHAT_ID and chat_id != str(TELEGRAM_CHAT_ID):
                continue
            cmd = text.strip().lower()
            if cmd == "/status":
                tg_send(
                    f"Символов={len(SETTINGS['symbols'])}, tf={BASE_TF_HUMAN}→{FALLBACK_TF_HUMAN}, "
                    f"cooldown={COOLDOWN_S}s, режим={MODE}\n"
                    f"UTC: {ts_utc_str()}\n"
                    f"{', '.join(SETTINGS['symbols'])}"
                )
        time.sleep(1)

# ========== РАБОЧИЙ ПОТОК ==========
def worker():
    global last_summary_ts
    while True:
        round_started = now_ts()
        for sym in SETTINGS["symbols"]:
            kind, direction, reason = analyze_symbol(sym, BASE_TF_HUMAN, CANDLES_NEED)
            if kind in ("STRONG", "WEAK"):
                if now_ts() - last_signal_ts[sym] >= COOLDOWN_S:
                    last_signal_ts[sym] = now_ts()
                    tg_send(format_signal(sym, kind, direction, reason))
            else:
                if now_ts() - last_nosig_ts[sym] >= SEND_NOSIG_EVERY:
                    last_nosig_ts[sym] = now_ts()
                    tg_send(f"ℹ️ {sym}: {reason}\nUTC: {ts_utc_str()}")
            time.sleep(THROTTLE_PER_SYMBOL_S)
        if now_ts() - last_summary_ts >= REPORT_SUMMARY_EVERY:
            last_summary_ts = now_ts()
            tg_send(
                f"✂️ Отчёт: символов={len(SETTINGS['symbols'])}, "
                f"tf={BASE_TF_HUMAN}→{FALLBACK_TF_HUMAN}, cooldown={COOLDOWN_S}s, режим={MODE}\n"
                f"UTC: {ts_utc_str()}"
            )
        elapsed = now_ts() - round_started
        sleep_left = max(1, CHECK_INTERVAL_S - elapsed)
        time.sleep(sleep_left)

@app.route("/")
def root():
    return "OK"

def main():
    tg_delete_webhook()
    threading.Thread(target=process_updates, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    port = int(os.environ.get("PORT", "7860"))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
