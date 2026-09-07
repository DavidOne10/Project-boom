import os
import requests
import pandas as pd
import yfinance as yf

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

STATE_FILE = "cac40_sent.txt"
ISIN_CAC = "IE00B7V0GB87"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Errore invio Telegram: {e}")

def check_cac40_strategy():
    df = yf.download("^FCHI", period="1y", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    
    daily_ret = df['Close'].pct_change()
    lev_ret = (daily_ret * 3.0) - (0.0075 / 252)
    df['lev_price'] = (1 + lev_ret.fillna(0)).cumprod() * 100
    
    df_w = df.set_index('Date').resample('W').agg({'lev_price': 'last'}).dropna().reset_index()
    df_w['sma20'] = df_w['lev_price'].rolling(window=20).mean()
    
    delta = df_w['lev_price'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df_w['rsi'] = 100 - (100 / (1 + (gain / loss)))
    df_w['is_down'] = df_w['lev_price'].diff() < 0
    
    last_row = df_w.iloc[-2]
    close = last_row['lev_price']
    sma20 = last_row['sma20']
    rsi = last_row['rsi']
    is_down = last_row['is_down']
    date_str = str(last_row['Date'])[:10]
    
    if close < sma20 and rsi < 35 and is_down:
        last_sent_date = ""
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                last_sent_date = f.read().strip()
                
        if last_sent_date == date_str:
            print(f"[{date_str}] CAC40: Segnale già notificato in precedenza per questa settimana.")
            return

        stop_loss = close * 0.95
        take_profit = close * 1.09

        msg = (
            f"🇫🇷 **SEGNALE LONG CAC 40 3X** 🇫🇷\n\n"
            f"📌 *ISIN:* `{ISIN_CAC}`\n"
            f"📅 Data Chiusura: {date_str}\n"
            f"💰 Prezzo Simula 3x: {close:.2f}\n"
            f"📊 SMA20: {sma20:.2f} | RSI: {rsi:.2f}\n\n"
            f"🎯 *Parametri:* Stop Loss -5% (`{stop_loss:.2f}`) | Take Profit +9% (`{take_profit:.2f}`)"
        )
        send_telegram_message(msg)
        
        with open(STATE_FILE, "w") as f:
            f.write(date_str)
    else:
        print(f"[{date_str}] CAC40: Nessun segnale attivo.")

if __name__ == "__main__":
    check_cac40_strategy()
