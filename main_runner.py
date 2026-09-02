import os
import time
import threading
from datetime import datetime
from zoneinfo import ZoneInfo
from flask import Flask
import requests
import pandas as pd
import numpy as np
import yfinance as yf

# --- MICRO SERVER FLASK (Per tenere sveglio Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "🟢 Bot ORB Trading Attivo 24/7", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- CREDENZIALI ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://data.alpaca.markets/v2"

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Credenziali Telegram mancanti. Messaggio:\n{message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

# --- SCANSIONE CAC 40 (EUROPA) ---
def check_cac40():
    now_cet = datetime.now(ZoneInfo("Europe/Paris"))
    if now_cet.weekday() >= 5 or not (9 <= now_cet.hour < 18):
        return

    try:
        df = yf.download("^FCHI", period="5d", interval="15m", progress=False)
        if df.empty: return
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        df.index = df.index.tz_convert("Europe/Paris")
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()

        today_bars = df[df.index.date == df.index.date.max()]
        orb_candle = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 0)]
        if orb_candle.empty: return

        orb_high, orb_low = float(orb_candle['High'].values[0]), float(orb_candle['Low'].values[0])
        orb_range, atr = orb_high - orb_low, float(orb_candle['ATR'].values[0])
        if pd.isna(atr) or orb_range < (0.25 * atr): return

        session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute > 0))]
        if session_bars.empty: return

        latest_bar = session_bars.iloc[-1]
        latest_close, latest_ema = float(latest_bar['Close']), float(latest_bar['EMA_200'])
        latest_time = session_bars.index[-1].strftime('%H:%M')

        if latest_time == "09:15":
            send_telegram(f"🟢 *Bot CAC 40 Attivo*\n\n📊 Range ORB 09:00: `{orb_low:.2f}` — `{orb_high:.2f}`")

        prev_close = float(session_bars.iloc[-2]['Close']) if len(session_bars) > 1 else float(orb_candle['Close'].values[0])

        if latest_close > orb_high and prev_close <= orb_high and latest_close > latest_ema:
            tp, sl = latest_close + (1.2 * orb_range), orb_low
            send_telegram(f"🚨 *SEGNALE CAC 40 — LONG*\nIngresso: `{latest_close:.2f}` | TP: `{tp:.2f}` | SL: `{sl:.2f}`")
        elif latest_close < orb_low and prev_close >= orb_low and latest_close < latest_ema:
            tp, sl = latest_close - (1.2 * orb_range), orb_high
            send_telegram(f"🚨 *SEGNALE CAC 40 — SHORT*\nIngresso: `{latest_close:.2f}` | TP: `{tp:.2f}` | SL: `{sl:.2f}`")
    except Exception as e:
        print(f"❌ Errore CAC40: {e}")

# --- SCANSIONE USA (ALPACA) ---
def check_usa():
    now_est = datetime.now(ZoneInfo("America/New_York"))
    if now_est.weekday() >= 5 or not (9 <= now_est.hour < 16 or (now_est.hour == 16 and now_est.minute == 0)):
        return

    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    assets = {"S&P 500 (SPY)": "SPY", "PETROLIO WTI (USO)": "USO", "ORO (GLD)": "GLD"}

    for name, symbol in assets.items():
        try:
            url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe=15Min&limit=500&feed=iex"
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code != 200: continue
            data = res.json().get("bars", {}).get(symbol, [])
            if not data: continue

            df = pd.DataFrame(data)
            df['t'] = pd.to_datetime(df['t'])
            df.set_index('t', inplace=True)
            df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
            df.index = df.index.tz_convert("America/New_York")

            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()

            today_bars = df[df.index.date == df.index.date.max()]
            orb_candle = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
            if orb_candle.empty: continue

            orb_high, orb_low = float(orb_candle['High'].values[0]), float(orb_candle['Low'].values[0])
            orb_range, atr = orb_high - orb_low, float(orb_candle['ATR'].values[0])
            if pd.isna(atr) or orb_range < (0.25 * atr): continue

            session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute > 30))]
            if session_bars.empty: continue

            latest_bar = session_bars.iloc[-1]
            latest_close, latest_ema = float(latest_bar['Close']), float(latest_bar['EMA_200'])
            latest_time = session_bars.index[-1].strftime('%H:%M')

            if latest_time == "09:45" and symbol == "SPY":
                send_telegram("🟢 *Bot USA Attivo (SPY, USO, GLD)*\n\n📊 Candela 09:30 EST registrata.")

            prev_close = float(session_bars.iloc[-2]['Close']) if len(session_bars) > 1 else float(orb_candle['Close'].values[0])

            if latest_close > orb_high and prev_close <= orb_high and latest_close > latest_ema:
                tp, sl = latest_close + (1.2 * orb_range), orb_low
                send_telegram(f"🚨 *SEGNALE USA ({name}) — LONG*\nIngresso: `{latest_close:.2f}` | TP: `{tp:.2f}` | SL: `{sl:.2f}`")
            elif latest_close < orb_low and prev_close >= orb_low and latest_close < latest_ema:
                tp, sl = latest_close - (1.2 * orb_range), orb_high
                send_telegram(f"🚨 *SEGNALE USA ({name}) — SHORT*\nIngresso: `{latest_close:.2f}` | TP: `{tp:.2f}` | SL: `{sl:.2f}`")
        except Exception as e:
            print(f"❌ Errore {symbol}: {e}")

# --- LOOP DI PRECISIONE (Sincronizzato ogni 15 minuti) ---
def strategy_loop():
    send_telegram("🚀 *Bot ORB avviato con successo su Render! (Precisione 15m)*")
    while True:
        now = datetime.now()
        # Calcola i secondi al prossimo blocco di 15 min + 10 sec di tolleranza dati
        next_minute = (now.minute // 15 + 1) * 15
        if next_minute == 60:
            next_time = now.replace(hour=(now.hour + 1) % 24, minute=0, second=10, microsecond=0)
        else:
            next_time = now.replace(minute=next_minute, second=10, microsecond=0)

        sleep_seconds = (next_time - now).total_seconds()
        print(f"⏰ Prossima scansione alle {next_time.strftime('%H:%M:%S')} (attesa: {int(sleep_seconds)}s)")
        time.sleep(sleep_seconds)

        print("🔍 Esecuzione scansione di mercato...")
        check_cac40()
        check_usa()

if __name__ == "__main__":
    # Avvia Flask in un thread secondario
    threading.Thread(target=run_flask, daemon=True).start()
    # Avvia il loop di trading nel thread principale
    strategy_loop()
