import os
import argparse
import requests
from datetime import datetime
import pytz

# --- CREDENZIALI TELEGRAM ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Secret Telegram mancanti (TELEGRAM_TOKEN o CHAT_ID).")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Alert Telegram inviato con successo!")
        else:
            print(f"❌ Errore API Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Errore connessione Telegram: {e}")

def process_signal(action, price, sl, tp, orb_high=None, orb_low=None, ema=None):
    tz = pytz.timezone("Europe/Rome")
    now_eu = datetime.now(tz)
    latest_time = now_eu.strftime('%H:%M')

    act_upper = action.upper()
    
    # Gestione Segnale LONG / BUY
    if act_upper in ["LONG", "BUY"]:
        delta_tp = ((tp - price) / price) * 100
        delta_sl = ((price - sl) / price) * 100
        
        orb_str = f"`{orb_low:.2f}` — `{orb_high:.2f}`" if (orb_low and orb_high) else "Registrato TV"
        ema_str = f"`{ema:.2f}`" if ema else "Superata (OK)"

        msg = (f"🚨 *BREAKOUT CAC 40 — LONG (REAL-TIME)*\n\n"
               f"⏰ Candela: {latest_time} CET\n"
               f"📈 Ingresso Spot: `{price:.2f}`\n"
               f"🎯 Target Profit: `{tp:.2f}` (+{delta_tp:.2f}%)\n"
               f"🛑 Stop Loss: `{sl:.2f}` (-{delta_sl:.2f}%)\n\n"
               f"📊 Range ORB 09:00: {orb_str}\n"
               f"📈 EMA 200: {ema_str}")

    # Gestione Segnale SHORT / SELL
    elif act_upper in ["SHORT", "SELL"]:
        delta_tp = ((price - tp) / price) * 100
        delta_sl = ((sl - price) / price) * 100

        orb_str = f"`{orb_low:.2f}` — `{orb_high:.2f}`" if (orb_low and orb_high) else "Registrato TV"
        ema_str = f"`{ema:.2f}`" if ema else "Sotto (OK)"

        msg = (f"🚨 *BREAKOUT CAC 40 — SHORT (REAL-TIME)*\n\n"
               f"⏰ Candela: {latest_time} CET\n"
               f"📉 Ingresso Spot: `{price:.2f}`\n"
               f"🎯 Target Profit: `{tp:.2f}` (-{delta_tp:.2f}%)\n"
               f"🛑 Stop Loss: `{sl:.2f}` (+{delta_sl:.2f}%)\n\n"
               f"📊 Range ORB 09:00: {orb_str}\n"
               f"📉 EMA 200: {ema_str}")
    else:
        print(f"⚠️ Azione non riconosciuta: {action}")
        return

    send_telegram(msg)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CAC40 Signal Receiver via Webhook")
    parser.add_argument("--action", type=str, required=True, help="BUY/LONG o SELL/SHORT")
    parser.add_argument("--price", type=float, required=True, help="Prezzo di ingresso")
    parser.add_argument("--sl", type=float, required=True, help="Stop Loss")
    parser.add_argument("--tp", type=float, required=True, help="Take Profit")
    parser.add_argument("--orb_high", type=float, default=None, help="Massimo ORB 09:00")
    parser.add_argument("--orb_low", type=float, default=None, help="Minimo ORB 09:00")
    parser.add_argument("--ema", type=float, default=None, help="Valore EMA 200")

    args = parser.parse_args()
    
    process_signal(
        action=args.action,
        price=args.price,
        sl=args.sl,
        tp=args.tp,
        orb_high=args.orb_high,
        orb_low=args.orb_low,
        ema=args.ema
    )
