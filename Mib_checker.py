import os
import json
import requests
import pandas as pd
from datetime import datetime
import pytz

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TIMEZONE = pytz.timezone("Europe/Rome")
STATE_FILE = "mib_state.json"

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenziali Telegram mancanti.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Errore nell'invio Telegram: {e}")

def get_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                return data.get("signal")
        except:
            pass
    return None

def save_state(signal):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"signal": signal, "updated_at": datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}, f)
    except Exception as e:
        print(f"Errore salvataggio stato MIB: {e}")

def fetch_stooq_data(symbol="mib", interval="15m"):
    """Scarica i dati da Stooq in modo pulito via CSV."""
    if interval == "15m":
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=15m"
    else:
        url = f"https://stooq.com/q/d/l/?s={symbol}&i=d"
        
    try:
        df = pd.read_csv(url)
        if df.empty or 'Close' not in df.columns:
            return pd.DataFrame()
            
        if 'Time' in df.columns:
            df['Date'] = pd.to_datetime(df['Date'] + ' ' + df['Time'], errors='coerce')
        else:
            df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
            
        df = df.dropna(subset=['Date'])
        df.set_index('Date', inplace=True)
        # Conversione numerica per sicurezza
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df.dropna()
    except Exception as e:
        print(f"Errore download Stooq ({symbol}): {e}")
        return pd.DataFrame()

def run_mib_check():
    # 1. Filtro orario: Borsa Italiana aperta (Lun-Ven, 09:00 - 17:30)
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: 
        print("MIB: Mercato chiuso (weekend).")
        return
        
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=17, minute=30, second=0, microsecond=0)
    
    if not (market_open <= now <= market_close):
        print("MIB: Fuori orario di borsa.")
        return

    try:
        print("Analisi FTSE MIB / Minifib in corso (via Stooq)...")
        
        # Download dati 15m e Daily da Stooq
        df_15m = fetch_stooq_data("mib", interval="15m")
        df_daily = fetch_stooq_data("mib", interval="d")
        
        
