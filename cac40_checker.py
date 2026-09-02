import os
import requests
import pandas as pd
import numpy as np
import yfinance as yf
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

def check_cac40_orb():
    tz = pytz.timezone("Europe/Rome")
    now_eu = datetime.now(tz)
    is_weekday = now_eu.weekday() < 5
    market_open = now_eu.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now_eu.replace(hour=17, minute=30, second=0, microsecond=0)

    # Scansione saltata se fuori orario (09:00 - 17:30 CET) o nel weekend
    if not is_weekday or not (market_open <= now_eu <= market_close):
        print(f"🌙 Mercati EU chiusi ({now_eu.strftime('%H:%M CET')}). Scansione saltata.")
        return

    # Estensione a 60 giorni per garantire oltre 200 candele per la EMA200
    df = yf.download("^FCHI", period="60d", interval="15m", progress=False)
    if df.empty:
        print("❌ Nessun dato scaricato da Yahoo Finance.")
        return

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df.dropna(inplace=True)

    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC").tz_convert(tz)
    else:
        df.index = df.index.tz_convert(tz)

    # Calcolo Indicatori EMA 200 e ATR 14 (con min_periods=1 per evitare NaN)
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14, min_periods=1).mean()

    today = now_eu.date()
    df_today = df[df.index.date == today].copy()
    
    if len(df_today) < 2:
        print("⚠️ Candele odierne insufficienti.")
        return

    df_today["Time"] = df_today.index.time

    # Range candela ORB 09:00 CET
    orb_bar = df_today[df_today["Time"] == pd.to_datetime('09:00').time()]
    if orb_bar.empty:
        print("⏳ Candela d'apertura delle 09:00 non ancora registrata.")
        return
        
    orb_high = float(orb_bar['High'].iloc[0])
    orb_low = float(orb_bar['Low'].iloc[0])
    orb_range = orb_high - orb_low
    atr_val = float(orb_bar['ATR'].iloc[0])

    # Filtro Volatilità (Range ORB > 25% ATR)
    if pd.isna(atr_val) or orb_range < (0.25 * atr_val):
        print(f"⚠️ Sessione scartata: Range ORB ({orb_range:.2f}) < 25% ATR ({atr_val:.2f}).")
        return

    latest_bar = df_today.iloc[-1]
    prev_bar = df_today.iloc[-2]
    
    latest_close = float(latest_bar['Close'])
    prev_close = float(prev_bar['Close'])
    latest_ema = float(latest_bar['EMA_200'])
    latest_time = df_today.index[-1].strftime('%H:%M')

    # 🟢 HEARTBEAT: Notifica di avvio alla prima scansione utile (09:15 CET)
    if latest_time == "09:15":
        print("🟢 Invio heartbeat di avvio sessione Europa...")
        send_telegram(f"🟢 *Bot CAC 40 Attivo*\n\n"
                      f"📊 Range ORB 09:00 registrato: `{orb_low:.2f}` — `{orb_high:.2f}`\n"
                      f"⚡ In ascolto per eventuali breakout.")

    if df_today.index[-1].time() <= pd.to_datetime('09:00').time():
        print("ℹ️ ORB appena formato, in attesa di breakout.")
        return

    # --- LOGICA BREAKOUT CON DEDUPLICAZIONE E FILTRO EMA 200 ---

    # Breakout LONG
    if latest_close > orb_high and prev_close <= orb_high:
        if latest_close > latest_ema:
            tp = latest_close + (1.2 * orb_range)
            sl = orb_low
            delta_tp = ((tp - latest_close) / latest_close) * 100
            delta_sl = ((latest_close - sl) / latest_close) * 100
            msg = (f"🚨 *BREAKOUT CAC 40 — LONG*\n\n"
                   f"⏰ Candela: {latest_time} CET\n"
                   f"📈 Ingresso Spot: `{latest_close:.2f}`\n"
                   f"🎯 Target Profit (1.2x): `{tp:.2f}` (+{delta_tp:.2f}%)\n"
                   f"🛑 Stop Loss: `{sl:.2f}` (-{delta_sl:.2f}%)\n\n"
                   f"📊 Range ORB 09:00: {orb_low:.2f} — {orb_high:.2f}\n"
                   f"📈 EMA 200: {latest_ema:.2f}")
            send_telegram(msg)
        else:
            print(f"❌ Breakout LONG bloccato: Prezzo ({latest_close:.2f}) sotto EMA200 ({latest_ema:.2f}).")

    # Breakdown SHORT
    elif latest_close < orb_low and prev_close >= orb_low:
        if latest_close < latest_ema:
            tp = latest_close - (1.2 * orb_range)
            sl = orb_high
            delta_tp = ((latest_close - tp) / latest_close) * 100
            delta_sl = ((sl - latest_close) / latest_close) * 100
            msg = (f"🚨 *BREAKOUT CAC 40 — SHORT*\n\n"
                   f"⏰ Candela: {latest_time} CET\n"
                   f"📉 Ingresso Spot: `{latest_close:.2f}`\n"
                   f"🎯 Target Profit (1.2x): `{tp:.2f}` (-{delta_tp:.2f}%)\n"
                   f"🛑 Stop Loss: `{sl:.2f}` (+{delta_sl:.2f}%)\n\n"
                   f"📊 Range ORB 09:00: {orb_low:.2f} — {orb_high:.2f}\n"
                   f"📉 EMA 200: {latest_ema:.2f}")
            send_telegram(msg)
        else:
            print(f"❌ Breakdown SHORT bloccato: Prezzo ({latest_close:.2f}) sopra EMA200 ({latest_ema:.2f}).")
            
    else:
        print(f"😴 Nessun nuovo segnale alle {latest_time}. Prezzo ({latest_close:.2f}) dentro il range o breakout già notificato.")

if __name__ == "__main__":
    check_cac40_orb()
