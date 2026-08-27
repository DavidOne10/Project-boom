import os
import sys
import requests
import pandas as pd
import numpy as np

# --- CREDENZIALI DA GITHUB SECRETS ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
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
            print("✅ Messaggio Telegram inviato con successo!")
        else:
            print(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Errore di connessione a Telegram: {e}")

# --- TEST CONNETTIVITÀ TELEGRAM ---
if len(sys.argv) > 1 and sys.argv[1] == "--test":
    test_msg = (
        "🧪 *TEST TELEGRAM & ALPACA COMPLETO*\n\n"
        "✅ Telegram Token & Chat ID collegati correttamente!\n"
        "🚀 *Sistema ORB 15m in Real-Time pronto su GitHub Actions.*"
    )
    send_telegram(test_msg)
    sys.exit(0)

def get_alpaca_bars(symbol, timeframe="15Min", limit=200):
    """Scarica barre in tempo reale da Alpaca Market Data API."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("❌ Manca Alpaca API Key o Secret Key nei Secrets!")
        return pd.DataFrame()

    headers = {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY
    }
    url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=sip"
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"❌ Errore download Alpaca per {symbol}: {response.text}")
        return pd.DataFrame()

    data = response.json().get("bars", {}).get(symbol, [])
    if not data:
        return pd.DataFrame()

    df = pd.DataFrame(data)
    df['t'] = pd.to_datetime(df['t'])
    df.set_index('t', inplace=True)
    df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
    return df

# --- MAPPA ASSET REAL-TIME (ETF liquidi per replicare Commodities su Alpaca) ---
ASSETS = {
    "PETROLIO WTI (USO)": "USO",
    "ORO (GLD)": "GLD"
}

print("1. Avvio scansione REAL-TIME tramite Alpaca Data API...")

for asset_name, symbol in ASSETS.items():
    df = get_alpaca_bars(symbol, timeframe="15Min", limit=150)
    if df.empty:
        continue

    # Calcolo Indicatori Tecnici
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()

    df['Date'] = df.index.date
    df['Hour'] = df.index.hour
    df['Minute'] = df.index.minute

    today_date = df['Date'].max()
    today_bars = df[df['Date'] == today_date]

    # Candela ORB 14:30 CET (13:30 UTC / 09:30 EST)
    orb_candle = today_bars[(today_bars['Hour'] == 13) & (today_bars['Minute'] == 30)]
    
    if orb_candle.empty:
        print(f"🕒 [{asset_name}] Candela ORB 14:30 CET non ancora presente.")
        continue

    orb_high = orb_candle['High'].values[0]
    orb_low = orb_candle['Low'].values[0]
    orb_range = orb_high - orb_low
    atr = orb_candle['ATR'].values[0]
    ema = orb_candle['EMA_200'].values[0]

    # Filtro volatilità minima
    if pd.isna(atr) or orb_range < (0.25 * atr):
        print(f"⚠️ [{asset_name}] Volatilità dell'ORB troppo contenuta. Sessione scartata.")
        continue

    session_bars = today_bars[(today_bars['Hour'] > 13) | ((today_bars['Hour'] == 13) & (today_bars['Minute'] > 30))]
    if session_bars.empty:
        continue

    latest_bar = session_bars.iloc[-1]

    # SEGNALE LONG CONFERMATO
    if latest_bar['Close'] > orb_high and latest_bar['Close'] > ema:
        entry = latest_bar['Close']
        tp = entry + (1.2 * orb_range)
        sl = orb_low
        
        msg = (
            f"🚨 *SEGNALE REAL-TIME (ALPACA) — {asset_name}*\n\n"
            f"📈 *Azione:* COMPRA (Breakout ORB Confermato)\n"
            f"📌 *Prezzo Ingresso:* `{entry:.2f}`\n"
            f"🎯 *Take Profit:* `{tp:.2f}`\n"
            f"🛡️ *Stop Loss:* `{sl:.2f}`\n\n"
            f"📊 *Dati Real-time:* Chiusura candela sopra Max ORB ({orb_high:.2f}) e sopra EMA200."
        )
        send_telegram(msg)

    # SEGNALE SHORT CONFERMATO
    elif latest_bar['Close'] < orb_low and latest_bar['Close'] < ema:
        entry = latest_bar['Close']
        tp = entry - (1.2 * orb_range)
        sl = orb_high

        msg = (
            f"🚨 *SEGNALE REAL-TIME (ALPACA) — {asset_name}*\n\n"
            f"📉 *Azione:* VENDI (Breakdown ORB Confermato)\n"
            f"📌 *Prezzo Ingresso:* `{entry:.2f}`\n"
            f"🎯 *Take Profit:* `{tp:.2f}`\n"
            f"🛡️ *Stop Loss:* `{sl:.2f}`\n\n"
            f"📊 *Dati Real-time:* Chiusura candela sotto Min ORB ({orb_low:.2f}) e sotto EMA200."
        )
        send_telegram(msg)

print("Scansione Real-Time completata.")
