import os
import requests
import pandas as pd
from datetime import datetime
import pytz

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

def check_cac40():
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz)
    
    # Esegui solo in orario di mercato EU (09:00 - 17:30)
    if not (9 <= now.hour < 17 or (now.hour == 17 and now.minute <= 30)):
        print("🌙 Mercato CAC 40 chiuso. Scansione saltata.", flush=True)
        return

    print("🔎 Check CAC 40 Real-Time via Euronext...", flush=True)
    
    try:
        # Feed ufficiale Euronext CAC 40 (FR0003500008-XPAR)
        url = "https://live.euronext.com/intraday_chart/getChartData/FR0003500008-XPAR/15m"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers).json()
        
        if not res:
            print("❌ Dati Euronext non disponibili.", flush=True)
            return

        df = pd.DataFrame(res)
        df['time'] = pd.to_datetime(df['time'])
        df['time_str'] = df['time'].dt.strftime('%H:%M')
        
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        # Candela ORB (09:00)
        orb_candle = df[df['time_str'] == '09:00']

        if orb_candle.empty:
            print("⏳ Candela ORB (09:00) non ancora disponibile.", flush=True)
            return

        orb_high = orb_candle.iloc[0]["high"]
        orb_low = orb_candle.iloc[0]["low"]
        
        last_candle = df.iloc[-1]
        close_price = last_candle["close"]

        # Logica Breakout ORB
        if close_price > orb_high:
            sl = orb_low
            tp = close_price + (close_price - sl) * 1.5
            send_telegram_msg(f"🚀 *SEGNALE LONG CAC 40*\n\nPrezzo: `{close_price:.2f}`\nSL: `{sl:.2f}`\nTP: `{tp:.2f}`\nORB High: `{orb_high:.2f}`")
            print("✅ Segnale LONG inviato a Telegram!", flush=True)
        elif close_price < orb_low:
            sl = orb_high
            tp = close_price - (sl - close_price) * 1.5
            send_telegram_msg(f"🔻 *SEGNALE SHORT CAC 40*\n\nPrezzo: `{close_price:.2f}`\nSL: `{sl:.2f}`\nTP: `{tp:.2f}`\nORB Low: `{orb_low:.2f}`")
            print("✅ Segnale SHORT inviato a Telegram!", flush=True)
        else:
            print(f"📊 CAC 40 Real-Time: {close_price:.2f} | ORB: [{orb_low:.2f} - {orb_high:.2f}]", flush=True)

    except Exception as e:
        print(f"❌ Errore Euronext: {e}", flush=True)

if __name__ == "__main__":
    check_cac40()
