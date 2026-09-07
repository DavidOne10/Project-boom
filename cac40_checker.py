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

def fetch_cac40_realtime():
    """Recupera le candele del CAC 40 in tempo reale via REST API Indici Boursorama."""
    # CORRETTO: da /action/ a /indices/cours/
    url = "https://www.boursorama.com/bourse/indices/cours/graph/ws/GetChart?symbol=1rPCAC&period=-1"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.boursorama.com/bourse/indices/cours/1rPCAC/"
    }
    
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            quote_list = data.get("d", {}).get("quote", [])
            
            if not quote_list:
                return None
                
            records = []
            tz = pytz.timezone("Europe/Paris")
            
            for q in quote_list:
                dt = datetime.fromtimestamp(q["d"] / 1000, tz=tz)
                records.append({
                    "datetime": dt,
                    "price": float(q["c"])
                })
                
            df = pd.DataFrame(records)
            df['date_str'] = df['datetime'].dt.strftime('%Y-%m-%d')
            
            today_str = datetime.now(tz).strftime('%Y-%m-%d')
            df_today = df[df['date_str'] == today_str].copy()
            
            if df_today.empty:
                return None

            # Resample sui 15 Minuti per costruire le candele OHLC reali
            df_15m = df_today.set_index('datetime').resample('15min').agg({
                'price': ['first', 'max', 'min', 'last']
            }).dropna()
            
            df_15m.columns = ['open', 'high', 'low', 'close']
            df_15m['time_str'] = df_15m.index.strftime('%H:%M')
            return df_15m.reset_index()
            
        else:
            print(f"⚠️ API risponde con stato: {res.status_code}", flush=True)
    except Exception as e:
        print(f"⚠️ Errore recupero REST CAC 40: {e}", flush=True)
        
    return None

def check_cac40():
    tz = pytz.timezone("Europe/Paris")
    now = datetime.now(tz)
    
    # Orario Mercato Parigi (09:00 - 17:30 CET)
    if not (9 <= now.hour < 17 or (now.hour == 17 and now.minute <= 30)):
        print(f"🌙 Mercato CAC 40 chiuso ({now.strftime('%H:%M')} CET). Scansione saltata.", flush=True)
        return

    print("⚡ Check CAC 40 Real-Time via REST API...", flush=True)
    
    df = fetch_cac40_realtime()
    
    if df is None or df.empty:
        print("❌ Impossibile recuperare i dati in tempo reale.", flush=True)
        return

    # Calcolo EMA 200
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()

    # Candela ORB delle 09:00 (apertura)
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

    # Notifica Apertura ORB (09:15 CET)
    if candle_time == "09:15" and now.minute < 20:
        msg_start = (
            f"🟢 *Bot CAC 40 Attivo (Real-Time)*\n\n"
            f"📊 Range ORB 09:00 registrato: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
            f"⚡ Monitoraggio breakout attivo."
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
            f"🚨 *BREAKOUT CAC 40 – LONG (REAL-TIME)*\n\n"
            f"⏰ Candela: {candle_time} CET\n"
            f"Ingresso Spot: `{close_price:.2f}`\n"
            f"🎯 Target Profit (1.2x): `{tp:.2f}` (+{tp_pct:.2f}%)\n"
            f"🛑 Stop Loss: `{sl:.2f}` (-{sl_pct:.2f}%)\n\n"
            f"📊 Range ORB 09:00: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
            f"📈 EMA 200: `{ema200_val:.2f}`"
        )
        send_telegram_msg(msg_long)
        print("✅ Segnale LONG REAL-TIME inviato a Telegram!", flush=True)

    # Breakout SHORT
    elif close_price < orb_low:
        sl = orb_high
        risk = sl - close_price
        tp = close_price - (risk * 1.2)
        tp_pct = ((close_price - tp) / close_price) * 100
        sl_pct = ((sl - close_price) / close_price) * 100
        
        msg_short = (
            f"🚨 *BREAKOUT CAC 40 – SHORT (REAL-TIME)*\n\n"
            f"⏰ Candela: {candle_time} CET\n"
            f"Ingresso Spot: `{close_price:.2f}`\n"
            f"🎯 Target Profit (1.2x): `{tp:.2f}` (-{tp_pct:.2f}%)\n"
            f"🛑 Stop Loss: `{sl:.2f}` (+{sl_pct:.2f}%)\n\n"
            f"📊 Range ORB 09:00: `{orb_low:.2f}` – `{orb_high:.2f}`\n"
            f"📉 EMA 200: `{ema200_val:.2f}`"
        )
        send_telegram_msg(msg_short)
        print("✅ Segnale SHORT REAL-TIME inviato a Telegram!", flush=True)

    else:
        print(f"📊 CAC 40 Live: {close_price:.2f} | ORB: [{orb_low:.2f} - {orb_high:.2f}] | Candela: {candle_time}", flush=True)

if __name__ == "__main__":
    check_cac40()
