import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import pytz

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

def check_cac40_orb():
    df = yf.download("^FCHI", period="5d", interval="15m", progress=False)
    if df.empty:
        print("❌ Nessun dato scaricato.")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.dropna(inplace=True)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert("Europe/Rome")
    else:
        df.index = df.index.tz_convert("Europe/Rome")

    today = datetime.now(pytz.timezone('Europe/Rome')).date()
    df_today = df[df.index.date == today].copy()
    
    if df_today.empty:
        print("⚠️ Nessun dato per la giornata odierna.")
        return

    df_today["Time"] = df_today.index.time

    # Range candela ORB 09:00 CET
    orb_bar = df_today[df_today["Time"] == pd.to_datetime('09:00').time()]
    if orb_bar.empty:
        print("⏳ Candela d'apertura delle 09:00 non ancora registrata.")
        return
        
    orb_high = orb_bar['High'].iloc[0]
    orb_low = orb_bar['Low'].iloc[0]
    orb_range = orb_high - orb_low
    
    latest_bar = df_today.iloc[-1]
    latest_close = latest_bar['Close']
    latest_time = df_today.index[-1].strftime('%H:%M')
    
    if df_today.index[-1].time() <= pd.to_datetime('09:00').time():
        print("ℹ️ ORB appena formato, in attesa di breakout.")
        return

    if latest_close > orb_high:
        tp = latest_close + (1.2 * orb_range)
        sl = orb_low
        delta_tp = ((tp - latest_close) / latest_close) * 100
        delta_sl = ((latest_close - sl) / latest_close) * 100
        msg = (f"🚨 *BREAKOUT CAC 40 — LONG*\n\n"
               f"⏰ Candela: {latest_time} CET\n"
               f"📈 Ingresso Spot: `{latest_close:.2f}`\n"
               f"🎯 Target Profit (1.2x): `{tp:.2f}` (+{delta_tp:.2f}%)\n"
               f"🛑 Stop Loss: `{sl:.2f}` (-{delta_sl:.2f}%)\n\n"
               f"📊 Range ORB 09:00: {orb_low:.2f} — {orb_high:.2f}")
        send_telegram(msg)
        
    elif latest_close < orb_low:
        tp = latest_close - (1.2 * orb_range)
        sl = orb_high
        delta_tp = ((latest_close - tp) / latest_close) * 100
        delta_sl = ((sl - latest_close) / latest_close) * 100
        msg = (f"🚨 *BREAKOUT CAC 40 — SHORT*\n\n"
               f"⏰ Candela: {latest_time} CET\n"
               f"📉 Ingresso Spot: `{latest_close:.2f}`\n"
               f"🎯 Target Profit (1.2x): `{tp:.2f}` (+{delta_tp:.2f}%)\n"
               f"🛑 Stop Loss: `{sl:.2f}` (-{delta_sl:.2f}%)\n\n"
               f"📊 Range ORB 09:00: {orb_low:.2f} — {orb_high:.2f}")
        send_telegram(msg)
    else:
        print(f"😴 Prezzo ({latest_close:.2f}) compreso nel range ORB ({orb_low:.2f} - {orb_high:.2f}). Nessun segnale.")

if __name__ == "__main__":
    check_cac40_orb()
