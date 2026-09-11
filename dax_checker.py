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


# 1. Download dati e patch candela odierna
df = yf.download(
    "^GDAXI", period="3mo", interval="1d", progress=False, auto_adjust=True
)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df = df.reset_index()

today_str = datetime.now().strftime("%Y-%m-%d")
last_date_str = df["Date"].dt.strftime("%Y-%m-%d").iloc[-1]

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
        df = pd.concat([df, new_row], ignore_ignore=True)

# 2. Calcolo Indicatori
df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
df["high_10"] = df["Close"].shift(1).rolling(10).max()

last_row = df.iloc[-1]
signal_today = (last_row["Close"] > last_row["ema50"]) and (
    last_row["Close"] > last_row["high_10"]
)

# 3. Notifica Telegram
if signal_today:
    msg = (
        f"🚨 *SEGNALE STRATEGIA DAX 3X*\n\n"
        f"Data: {today_str}\n"
        f"Chiusura Spot: {last_row['Close']:.2f}\n"
        f"EMA50: {last_row['ema50']:.2f} | Max 10g: {last_row['high_10']:.2f}\n\n"
        f"🟢 *AZIONE DOMANI:* Comprare in APERTURA (09:00)\n"
        f"🎯 *Take Profit:* +11.25%\n"
        f"🛡️ *Stop Loss:* -3.75%\n"
        f"⏱️ *Time Stop:* 6 Sessioni"
    )
    send_telegram(msg)
