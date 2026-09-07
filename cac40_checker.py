import os
import requests
import pandas as pd
from datetime import datetime
import pytz

TWELVE_DATA_API_KEY = "37f7b0457f1847a390480b9d1dec5bc7"
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def check_cac40():
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz)
    
    if not (9 <= now.hour < 17 or (now.hour == 17 and now.minute <= 30)):
        print("🌙 Mercato CAC 40 chiuso. Scansione saltata.", flush=True)
        return

    print("🔎 Check CAC 40 via Twelve Data...", flush=True)
    
    # Ticker corretto CAC 40 su Twelve Data: FCHI
    url = f"https://api.twelvedata.com/time_series?symbol=FCHI&interval=15min&outputsize=30&apikey={TWELVE_DATA_API_KEY}"
    res = requests.get(url).json()

    if "values" not in res:
        print(f"❌ Errore API Twelve Data: {res.get('message', 'Risposta non valida')}", flush=True)
        return

    df = pd.DataFrame(res["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime").reset_index(drop=True)
    
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)

    df['time_str'] = df['datetime'].dt.strftime('%H:%M')
    orb_candle = df[df['time_str'] == '09:00']

    if orb_candle.empty:
        print("⏳ Candela ORB (09:00) non ancora disponibile.", flush=True)
        return

    orb_high = orb_candle.iloc[0]["high"]
    orb_low = orb_candle.iloc[0]["low"]
    
    last_candle = df.iloc[-1]
    close_price = last_candle["close"]

    if close_price > orb_high:
        sl = orb_low
        tp = close_price + (close_price - sl) * 1.5
        send_telegram_msg(f"🚀 *SEGNALE LONG CAC 40*\n\nPrezzo: `{close_price}`\nSL: `{sl:.2f}`\nTP: `{tp:.2f}`\nORB High: `{orb_high}`")
        print("✅ Segnale LONG inviato a Telegram!", flush=True)
    elif close_price < orb_low:
        sl = orb_high
        tp = close_price - (sl - close_price) * 1.5
        send_telegram_msg(f"🔻 *SEGNALE SHORT CAC 40*\n\nPrezzo: `{close_price}`\nSL: `{sl:.2f}`\nTP: `{tp:.2f}`\nORB Low: `{orb_low}`")
        print("✅ Segnale SHORT inviato a Telegram!", flush=True)
    else:
        print(f"📊 CAC 40 in range. Prezzo: {close_price} | ORB: [{orb_low} - {orb_high}]", flush=True)

if __name__ == "__main__":
    check_cac40()
