import os
from datetime import datetime
import pandas as pd
import requests
import yfinance as yf


def send_telegram(message):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("CHAT_ID")
    if token and chat_id:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload)


# 1. PARAMETRI DEFINITIVI ESTRATTI DAL BACKTEST (R/R 1:3)
SL_PCT = 0.0500  # Stop Loss: -5.00%
TP_PCT = 0.1500  # Take Profit: +15.00%
MAX_DAYS = 6  # Time Stop: 6 Sessioni
LOOKBACK_DAYS = 20  # Breakout a 20 Giorni

# 2. Download Dati e Patch Candela Odierna
df = yf.download(
    "^GDAXI", period="3mo", interval="1d", progress=False, auto_adjust=True
)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df = df.reset_index()

today_str = datetime.now().strftime("%Y-%m-%d")
last_date_str = df["Date"].dt.strftime("%Y-%m-%d").iloc[-1]

# Se la candela odierna manca, viene ricostruita dai dati intraday a 5m
if last_date_str != today_str:
    df_intra = yf.download(
        "^GDAXI", period="1d", interval="5m", progress=False, auto_adjust=True
    )
    if isinstance(df_intra.columns, pd.MultiIndex):
        df_intra.columns = df_intra.columns.get_level_values(0)
    if not df_intra.empty:
        new_row = pd.DataFrame([{
            "Date": pd.to_datetime(today_str),
            "Open": df_intra["Open"].iloc[0],
            "High": df_intra["High"].max(),
            "Low": df_intra["Low"].min(),
            "Close": df_intra["Close"].iloc[-1],
        }])
        df = pd.concat([df, new_row], ignore_index=True)

# 3. Calcolo Indicatori Tecnici
df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
df["high_20"] = df["Close"].shift(1).rolling(LOOKBACK_DAYS).max()

last_row = df.iloc[-1]
signal_today = (last_row["Close"] > last_row["ema50"]) and (
    last_row["Close"] > last_row["high_20"]
)

# 4. Invio Notifica Telegram Solo su Segnale Valido
if signal_today:
    msg = (
        f"🚨 *SEGNALE STRATEGIA DAX 3X (OTTIMIZZATO)*\n\n"
        f"📅 Data: {today_str}\n"
        f"📈 Chiusura Spot: {last_row['Close']:.2f}\n"
        f"📊 EMA50: {last_row['ema50']:.2f} | Max 20g: {last_row['high_20']:.2f}\n\n"
        f"🟢 *AZIONE DOMANI:* Comprare in APERTURA (09:00)\n"
        f"🎯 *Take Profit:* +{TP_PCT*100:.1f}%\n"
        f"🛡️ *Stop Loss:* -{SL_PCT*100:.1f}%\n"
        f"⏱️ *Time Stop:* {MAX_DAYS} Sessioni"
    )
    send_telegram(msg)
