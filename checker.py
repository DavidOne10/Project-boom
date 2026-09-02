import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CONTROLLO ORARIO DI MERCATO (Wall Street 09:30 - 16:00 EST / 15:30 - 22:00 IT) ---
now_est = datetime.now(ZoneInfo("America/New_York"))
is_weekday = now_est.weekday() < 5  # Lunedì - Venerdì
market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)

# Scansione saltata se fuori orario (tranne se in modalità --test)
if len(sys.argv) == 1 and (not is_weekday or not (market_open <= now_est <= market_close)):
    print(f"🌙 Mercati US chiusi ({now_est.strftime('%H:%M EST')}). Scansione saltata.")
    sys.exit(0)

# --- CREDENZIALI DA GITHUB SECRETS ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

ALPACA_BASE_URL = "https://data.alpaca.markets/v2"

def send_telegram(message):
    """Invia un messaggio formattato su Telegram."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Credenziali Telegram non trovate. Messaggio simulato:\n{message}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Messaggio Telegram inviato!")
        else:
            print(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Errore connessione Telegram: {e}")

# --- TEST CONNETTIVITÀ ---
if len(sys.argv) > 1 and sys.argv[1] == "--test":
    test_msg = (
        "🧪 *TEST TELEGRAM & ALPACA COMPLETO*\n\n"
        "✅ Telegram Token & Chat ID collegati correttamente!\n"
        "🚀 *Sistema ORB 15m pronto su GitHub Actions.*"
    )
    send_telegram(test_msg)
    sys.exit(0)

def get_alpaca_bars(symbol, timeframe="15Min", limit=500):
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("❌ Mancano le API Keys nei Secrets di GitHub!")
        return pd.DataFrame()

    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }
    url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=iex"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ Errore download Alpaca per {symbol}: {response.text}")
            return pd.DataFrame()

        data = response.json().get("bars", {}).get(symbol, [])
        if not data:
            print(f"⚠️ Nessun dato da Alpaca per {symbol}.")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'])
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception as e:
        print(f"❌ Eccezione recupero dati per {symbol}: {e}")
        return pd.DataFrame()

ASSETS = {
    "S&P 500 (SPY)": "SPY",
    "PETROLIO WTI (USO)": "USO",
    "ORO (GLD)": "GLD"
}

print("1. Avvio scansione REAL-TIME tramite Alpaca Data API...")

for asset_name, symbol in ASSETS.items():
    df = get_alpaca_bars(symbol, timeframe="15Min", limit=500)
    if df.empty:
        continue

    df.index = df.index.tz_convert("America/New_York")

    # Calcolo Indicatori
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14, min_periods=1).mean()

    today_date = df.index.date.max()
    today_bars = df[df.index.date == today_date]

    # Candela ORB esatta di apertura (09:30 New York)
    orb_candle = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
    
    if orb_candle.empty:
        print(f"🕒 [{asset_name}] Candela ORB 09:30 EST non ancora presente.")
        continue

    orb_high = float(orb_candle['High'].values[0])
    orb_low = float(orb_candle['Low'].values[0])
    orb_range = orb_high - orb_low
    atr = float(orb_candle['ATR'].values[0])

    if pd.isna(atr) or orb_range < (0.25 * atr):
        print(f"⚠️ [{asset_name}] Volatilità dell'ORB contenuta ({orb_range:.2f} < 25% ATR {atr:.2f}). Sessione scartata.")
        continue

    session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute > 30))]
    if session_bars.empty:
        continue

    latest_bar = session_bars.iloc[-1]
    latest_close = float(latest_bar['Close'])
    latest_ema = float(latest_bar['EMA_200'])
    latest_time = session_bars.index[-1].strftime('%H:%M')

    # 🟢 HEARTBEAT: Notifica di avvio alla prima scansione utile (09:45 EST / 15:45 IT)
    if latest_time == "09:45" and symbol == "SPY":
        print("🟢 Invio heartbeat di avvio sessione USA...")
        send_telegram("🟢 *Bot USA Attivo (SPY, USO, GLD)*\n\n"
                      "📊 Candela d'apertura 09:30 EST registrata.\n"
                      "⚡ Scansione in corso per la sessione americana.")

    prev_close = float(session_bars.iloc[-2]['Close']) if len(session_bars) > 1 else float(orb_candle['Close'].values[0])

    # SEGNALE LONG
    if latest_close > orb_high and prev_close <= orb_high:
        if latest_close > latest_ema:
            entry = latest_close
            tp = entry + (1.2 * orb_range)
            sl = orb_low
            
            tp_pct = ((tp - entry) / entry) * 100
            sl_pct = ((entry - sl) / entry) * 100
            
            msg = (
                f"🚨 *SEGNALE REAL-TIME (ALPACA) — {asset_name}*\n\n"
                f"📈 *Azione:* COMPRA (Breakout ORB Confermato)\n"
                f"📌 *Prezzo Ingresso:* `{entry:.2f}`\n"
                f"🎯 *Take Profit (1.2x):* `{tp:.2f}` (+{tp_pct:.2f}%)\n"
                f"🛡️ *Stop Loss:* `{sl:.2f}` (-{sl_pct:.2f}%)\n\n"
                f"📊 *Dati Real-time:* Chiusura sopra Max ORB ({orb_high:.2f}) e sopra EMA200 ({latest_ema:.2f})."
            )
            send_telegram(msg)
        else:
            print(f"❌ [{asset_name}] Breakout LONG bloccato da EMA200.")

    # SEGNALE SHORT
    elif latest_close < orb_low and prev_close >= orb_low:
        if latest_close < latest_ema:
            entry = latest_close
            tp = entry - (1.2 * orb_range)
            sl = orb_high

            tp_pct = ((entry - tp) / entry) * 100
            sl_pct = ((sl - entry) / entry) * 100

            msg = (
                f"🚨 *SEGNALE REAL-TIME (ALPACA) — {asset_name}*\n\n"
                f"📉 *Azione:* VENDI (Breakdown ORB Confermato)\n"
                f"📌 *Prezzo Ingresso:* `{entry:.2f}`\n"
                f"🎯 *Take Profit (1.2x):* `{tp:.2f}` (-{tp_pct:.2f}%)\n"
                f"🛡️ *Stop Loss:* `{sl:.2f}` (+{sl_pct:.2f}%)\n\n"
                f"📊 *Dati Real-time:* Chiusura sotto Min ORB ({orb_low:.2f}) e sotto EMA200 ({latest_ema:.2f})."
            )
            send_telegram(msg)
        else:
            print(f"❌ [{asset_name}] Breakdown SHORT bloccato da EMA200.")
    else:
        print(f"😴 [{asset_name}] Nessun nuovo segnale alle {latest_time} EST.") 

print("Scansione Real-Time completata.")
