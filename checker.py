import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CONTROLLO ORARIO DI MERCATO ---
now_est = datetime.now(ZoneInfo("America/New_York"))
is_weekday = now_est.weekday() < 5  
market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)

if len(sys.argv) == 1 and (not is_weekday or not (market_open <= now_est <= market_close)):
    print(f"🌙 Mercati US chiusi ({now_est.strftime('%H:%M EST')}). Scansione saltata.")
    sys.exit(0)

# --- CREDENZIALI GITHUB SECRETS ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

ALPACA_BASE_URL = "https://data.alpaca.markets/v2"

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Credenziali Telegram non trovate. Messaggio simulato:\n{message}")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Messaggio Telegram inviato!")
        else:
            print(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Errore connessione Telegram: {e}")

if len(sys.argv) > 1 and sys.argv[1] == "--test":
    send_telegram("🧪 *TEST SYSTEM OK — FILTRO S/R + TP 1.3x ATTIVI*")
    sys.exit(0)

def get_alpaca_bars(symbol, timeframe="15Min", limit=500):
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        print("❌ Mancano le API Keys nei Secrets di GitHub!")
        return pd.DataFrame()

    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=iex"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return pd.DataFrame()
        data = response.json().get("bars", {}).get(symbol, [])
        if not data: return pd.DataFrame()

        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'])
        df['timestamp'] = df['t']
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception as e:
        print(f"❌ Errore dati {symbol}: {e}")
        return pd.DataFrame()

ASSETS = {"S&P 500 (SPY)": "SPY", "PETROLIO WTI (USO)": "USO", "ORO (GLD)": "GLD"}

print("1. Avvio scansione REAL-TIME (Modello 1.3x - Win Rate 58.06%)...")

for asset_name, symbol in ASSETS.items():
    df = get_alpaca_bars(symbol, timeframe="15Min", limit=500)
    if df.empty: continue

    df.index = df.index.tz_convert("America/New_York")
    df['date'] = df.index.date

    # --- CALCOLO PIVOT POINTS (Filtro Ostacoli) ---
    daily = df.groupby('date').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
    daily['pivot'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
    daily['R1'] = (2 * daily['pivot']) - daily['Low']
    daily['S1'] = (2 * daily['pivot']) - daily['High']
    
    # Unione con shift(1) per usare S/R del giorno precedente
    df = df.merge(daily[['R1', 'S1']].shift(1), left_on='date', right_index=True, how='left')

    # --- INDICATORI ---
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14, min_periods=1).mean()

    today_date = df.index.date.max()
    today_bars = df[df.index.date == today_date]

    orb_candle = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
    if orb_candle.empty: continue

    orb_high, orb_low = float(orb_candle['High'].values[0]), float(orb_candle['Low'].values[0])
    orb_range, atr = orb_high - orb_low, float(orb_candle['ATR'].values[0])

    if pd.isna(atr) or orb_range < (0.25 * atr): continue

    # Scansione operazioni dalle 09:45 in poi
    session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute >= 45))]
    if session_bars.empty: continue

    first_signal_bar_idx, signal_type = None, None

    # Ricerca del primo breakout pulito della giornata
    for i in range(len(session_bars)):
        bar = session_bars.iloc[i]
        c = float(bar['Close'])
        prev_c = float(session_bars.iloc[i-1]['Close']) if i > 0 else float(orb_candle['Close'].values[0])
        ema, sma = float(bar['EMA_200']), float(bar['SMA_50']) if not pd.isna(bar['SMA_50']) else c
        rsi = float(bar['RSI']) if not pd.isna(bar['RSI']) else 50

        is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema) and (c > sma) and (45 <= rsi <= 75)
        is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema) and (c < sma) and (25 <= rsi <= 55)

        if is_long or is_short:
            # Recupero livelli S/R
            r1, s1 = float(bar['R1']), float(bar['S1'])
            sl = orb_low if is_long else orb_high
            risk = (c - sl) if is_long else (sl - c)
            
            # Controllo matematica per evitare errori
            if risk <= 0: continue
            
            # Calcolo TP dinamico a 1.3x Rischio Reale
            tp = c + (1.3 * risk) if is_long else c - (1.3 * risk)

            # Controllo Ostruzione Statica (Il livello R1/S1 spezza il trade a metà?)
            blocked = False
            if is_long and not pd.isna(r1) and (c < r1 < tp): blocked = True
            if is_short and not pd.isna(s1) and (tp < s1 < c): blocked = True

            if not blocked:
                first_signal_bar_idx = i
                signal_type = "LONG" if is_long else "SHORT"
                break

    # Se c'è un segnale e corrisponde esattamente all'ULTIMA candela chiusa -> INVIA MESSAGGIO
    if first_signal_bar_idx == len(session_bars) - 1:
        latest_bar = session_bars.iloc[-1]
        entry = float(latest_bar['Close'])
        latest_time = session_bars.index[-1].strftime('%H:%M')
        
        sl = orb_low if signal_type == "LONG" else orb_high
        risk = (entry - sl) if signal_type == "LONG" else (sl - entry)
        tp = entry + (1.3 * risk) if signal_type == "LONG" else entry - (1.3 * risk)
        
        # Formattazione per Telegram
        tp_pct = (abs(tp - entry) / entry) * 100
        sl_pct = (abs(entry - sl) / entry) * 100
        
        azione_txt = "COMPRA (Long) 📈" if signal_type == "LONG" else "VENDI (Short) 📉"
        muro_txt = "R1 (Resistenza)" if signal_type == "LONG" else "S1 (Supporto)"

        msg = (
            f"🚨 *SEGNALE ORB 15m VALIDATO — {asset_name}*\n\n"
            f"🎯 *Azione:* {azione_txt}\n"
            f"📌 *Prezzo Ingresso:* `{entry:.2f}`\n"
            f"💰 *Take Profit (1.3x):* `{tp:.2f}` (+{tp_pct:.2f}%)\n"
            f"🛡️ *Stop Loss:* `{sl:.2f}` (-{sl_pct:.2f}%)\n\n"
            f"✅ *Controllo Sicurezza:* Strada libera fino a {muro_txt}.\n"
            f"📊 *Orario:* {latest_time} EST | RSI: `{latest_bar['RSI']:.1f}`"
        )
        send_telegram(msg)
    else:
        print(f"😴 [{asset_name}] Nessun nuovo segnale prioritario (o segnale già passato) alle {session_bars.index[-1].strftime('%H:%M')} EST.")

print("Scansione Real-Time completata.")
