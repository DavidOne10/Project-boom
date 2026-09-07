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
    
    # Orario di mercato EU (09:00 - 17:30)
    if not (9 <= now.hour < 17 or (now.hour == 17 and now.minute <= 30)):
        print("🌙 Mercato CAC 40 chiuso. Scansione saltata.", flush=True)
        return

    print("🔎 Check CAC 40 Real-Time via Euronext...", flush=True)
    
    try:
        url = "https://live.euronext.com/intraday_chart/getChartData/FR0003500008-XPAR/15m"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=10).json()
        
        if not res or not isinstance(res, list):
            print("❌ Dati Euronext non disponibili.", flush=True)
            return

        df = pd.DataFrame(res)
        df['time'] = pd.to_datetime(df['time'])
        df['time_str'] = df['time'].dt.strftime('%H:%M')
        
        for col in ["open", "high", "low", "close"]:
            df[col] = df[col].astype(float)

        # Calcolo EMA 200
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Candela ORB (09:00)
        orb_candle = df[df['time_str'] == '09:00']

        if orb_candle.empty:
            print("⏳ Candela ORB (09:00) non ancora disponibile.", flush=True)
            return

        orb_high = orb_candle.iloc[0]["high"]
        orb_low = orb_candle.iloc[0]["low"]
        
        last_candle = df.iloc[-1]
        close_price = last_candle["close"]
        ema200_val = last_candle["ema200"]
        candle_time = last_candle["time_str"]

        # Notifica di apertura ORB (scatta alla candela delle 09:15)
        if candle_time == "09:15" and now.minute < 30:
            msg_start = (
                f"🟢 *Bot CAC 40 Attivo*\n\n"
                f"📊 Range ORB 09:00 registrato: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
                f"⚡ In ascolto per eventuali breakout."
            )
            send_telegram_msg(msg_start)

        # Breakout LONG
        if close_price > orb_high:
            sl = orb_low
            risk = close_price - sl
            tp = close_price + (risk * 1.2)
            tp_pct = ((tp - close_price) / close_price) * 100
            sl_pct = ((close_price - sl) / close_price) * 100
            
            msg_long = (
                f"🚨 *BREAKOUT CAC 40 – LONG*\n\n"
                f"⏰ Candela: {candle_time} CET\n"
                f"Ingresso Spot: `{close_price:.2f}`\n"
                f"🎯 Target Profit (1.2x): `{tp:.2f}` (+{tp_pct:.2f}%)\n"
                f"🛑 Stop Loss: `{sl:.2f}` (-{sl_pct:.2f}%)\n\n"
                f"📊 Range ORB 09:00: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
                f"📈 EMA 200: `{ema200_val:.2f}`"
            )
            send_telegram_msg(msg_long)
            print("✅ Segnale LONG inviato a Telegram!", flush=True)

        # Breakout SHORT
        elif close_price < orb_low:
            sl = orb_high
            risk = sl - close_price
            tp = close_price - (risk * 1.2)
            tp_pct = ((close_price - tp) / close_price) * 100
            sl_pct = ((sl - close_price) / close_price) * 100
            
            msg_short = (
                f"🚨 *BREAKOUT CAC 40 – SHORT*\n\n"
                f"⏰ Candela: {candle_time} CET\n"
                f"Ingresso Spot: `{close_price:.2f}`\n"
                f"🎯 Target Profit (1.2x): `{tp:.2f}` (-{tp_pct:.2f}%)\n"
                f"🛑 Stop Loss: `{sl:.2f}` (+{sl_pct:.2f}%)\n\n"
                f"📊 Range ORB 09:00: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
                f"📉 EMA 200: `{ema200_val:.2f}`"
            )
            send_telegram_msg(msg_short)
            print("✅ Segnale SHORT inviato a Telegram!", flush=True)

        else:
            print(f"📊 CAC 40: {close_price:.2f} | ORB: [{orb_low:.2f} - {orb_high:.2f}] | EMA200: {ema200_val:.2f}", flush=True)

    except Exception as e:
        print(f"❌ Errore Euronext: {e}", flush=True)

if __name__ == "__main__":
    check_cac40()
