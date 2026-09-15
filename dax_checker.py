import os
import sys
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# --- 1. CONTROLLO FINESTRA OPERATIVA EUROPA (09:00 - 18:00 Italia) ---
now_rome = datetime.now(ZoneInfo("Europe/Rome"))
if len(sys.argv) == 1 and not (9 <= now_rome.hour < 18):
    print(f"🌙 Fuori orario Europa ({now_rome.strftime('%H:%M %Z')}). Scansione saltata.")
    sys.exit(0)

# --- 2. CREDENZIALI TELEGRAM ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")

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
    send_telegram("🧪 *TEST DAX 3X CHECKER — TELEGRAM OPERATIVO*")
    sys.exit(0)

# --- 3. PARAMETRI DEFINITIVI ESTRATTI DAL BACKTEST (R/R 1:3) ---
SL_PCT = 0.0500       # Stop Loss: -5.00%
TP_PCT = 0.1500       # Take Profit: +15.00%
MAX_DAYS = 6          # Time Stop: 6 Sessioni
LOOKBACK_DAYS = 20    # Breakout a 20 Giorni di CHIUSURA

print(f"🔍 Avvio controllo DAX 3X ({now_rome.strftime('%H:%M CEST')})...")

try:
    # Download Dati Giornalieri
    df = yf.download("^GDAXI", period="4mo", interval="1d", progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if df.empty or len(df) < 25:
        print("⚠️ Dati DAX non disponibili.")
        sys.exit(0)

    df.index = pd.to_datetime(df.index)
    today_str = now_rome.strftime("%Y-%m-%d")
    last_date_str = df.index[-1].strftime("%Y-%m-%d")

    # Patch: Se la candela odierna manca, viene ricostruita dai dati intraday a 5m
    if last_date_str != today_str:
        df_intra = yf.download("^GDAXI", period="1d", interval="5m", progress=False, auto_adjust=True)
        if isinstance(df_intra.columns, pd.MultiIndex):
            df_intra.columns = df_intra.columns.get_level_values(0)
            
        if not df_intra.empty:
            new_row = pd.DataFrame([{
                "Open": float(df_intra["Open"].iloc[0]),
                "High": float(df_intra["High"].max()),
                "Low": float(df_intra["Low"].min()),
                "Close": float(df_intra["Close"].iloc[-1])
            }], index=[pd.to_datetime(today_str)])
            df = pd.concat([df, new_row])

    # --- 4. CALCOLO INDICATORI TECNICI (ESATTI DAL TUO BACKTEST) ---
    df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()
    df['high_20'] = df['Close'].shift(1).rolling(LOOKBACK_DAYS).max()

    last_row = df.iloc[-1]
    prev_row = df.iloc[-2]

    c = float(last_row['Close'])
    prev_c = float(prev_row['Close'])
    ema50 = float(last_row['ema50'])
    h20 = float(last_row['high_20'])
    prev_h20 = float(prev_row['high_20'])

    # Crossover: il breakout deve avvenire OGGI (evita notifiche ripetute durante il giorno)
    is_breakout = (c > h20) and (prev_c <= prev_h20)
    signal_today = is_breakout and (c > ema50)

    print(f"📊 DAX Spot: {c:.2f} | EMA50: {ema50:.2f} | Max 20g (Close): {h20:.2f}")

    # --- 5. INVIO NOTIFICA TELEGRAM ---
    if signal_today:
        msg = (
            f"🚨 *SEGNALE STRATEGIA DAX 3X (OTTIMIZZATO)*\n\n"
            f"📅 Data: `{today_str}`\n"
            f"📈 Chiusura Spot: `{c:.2f}`\n"
            f"📊 EMA50: `{ema50:.2f}` | Max 20g: `{h20:.2f}`\n\n"
            f"🟢 *AZIONE DOMANI:* Comprare in APERTURA (09:00)\n"
            f"🎯 *Take Profit:* +{TP_PCT*100:.1f}%\n"
            f"🛡️ *Stop Loss:* -{SL_PCT*100:.1f}%\n"
            f"⏱️ *Time Stop:* {MAX_DAYS} Sessioni"
        )
        send_telegram(msg)
        print("✅ Alert DAX inviato!")
    else:
        print("⚖️ DAX: Nessun nuovo breakout confermato.")

except Exception as e:
    print(f"❌ Errore DAX: {e}")
