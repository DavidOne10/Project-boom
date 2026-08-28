import os
import requests
import pandas as pd
from datetime import datetime
import pytz
from tvdatafeed import TvDatafeed, Interval

# Recupera i Secret configurati su GitHub
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
    tv = TvDatafeed()
    df = tv.get_hist(symbol='PX1', exchange='EURONEXT', interval=Interval.in_15_minute, n_bars=40)
    
    if df is None or df.empty:
        return

    df.index = df.index.tz_localize('UTC').tz_convert('Europe/Rome')
    today = datetime.now(pytz.timezone('Europe/Rome')).date()
    df_today = df[df.index.date == today]
    
    if df_today.empty:
        return

    # Range prima candela (09:00 - 09:15 CET)
    orb_bar = df_today[df_today.index.time == pd.to_datetime('09:00').time()]
    if orb_bar.empty:
        return
        
    orb_high = orb_bar['high'].iloc[0]
    orb_low = orb_bar['low'].iloc[0]
    orb_range = orb_high - orb_low
    
    latest_bar = df_today.iloc[-1]
    latest_close = latest_bar['close']
    latest_time = df_today.index[-1].strftime('%H:%M')
    
    if df_today.index[-1].time() <= pd.to_datetime('09:00').time():
        return

    # Segnale Long
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
        
    # Segnale Short
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

if __name__ == "__main__":
    check_cac40_orb()
