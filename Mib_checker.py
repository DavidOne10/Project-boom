import os
import json
import requests
import yfinance as yf
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
        print("Analisi FTSE MIB / Minifib in corso...")
        
        # Sessione HTTP con User-Agent per evitare il blocco 401 di Yahoo Finance
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })
        
        ticker = yf.Ticker("^FTSEMIB", session=session)
        
        # Download dati 15m e Daily
        df_15m = ticker.history(period="5d", interval="15m")
        df_daily = ticker.history(period="5d", interval="1d")
        
        if df_15m.empty or df_daily.empty or len(df_15m) < 40:
            print("MIB: Dati insufficienti.")
            return

        # Livelli Daily della seduta precedente (per ancorare i target)
        yesterday = df_daily.iloc[-2]
        y_high = yesterday['High']
        y_low = yesterday['Low']
        y_range = y_high - y_low

        # Candela a 15m appena CHIUSA
        df_closed = df_15m.iloc[:-1].copy()

        # Indicatori Tecnici
        df_closed['EMA_9'] = df_closed['Close'].ewm(span=9, adjust=False).mean()
        df_closed['EMA_21'] = df_closed['Close'].ewm(span=21, adjust=False).mean()
        
        # RSI 14
        delta = df_closed['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_closed['RSI'] = 100 - (100 / (1 + rs))
        
        # ATR 14
        high_low = df_closed['High'] - df_closed['Low']
        high_close = (df_closed['High'] - df_closed['Close'].shift(1)).abs()
        low_close = (df_closed['Low'] - df_closed['Close'].shift(1)).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df_closed['ATR'] = true_range.rolling(window=14).mean()
        
        last = df_closed.iloc[-1]
        prev = df_closed.iloc[-2]
        
        current_price = last['Close']
        timestamp_candela = df_closed.index[-1].strftime('%H:%M - %d/%m/%Y')
        rsi_val = last['RSI']
        atr_val = last['ATR']
        
        # Logica di Ingresso: Crossover + Filtro RSI + Target ibrido (ATR + Daily)
        signal = None
        if prev['EMA_9'] <= prev['EMA_21'] and last['EMA_9'] > last['EMA_21'] and rsi_val > 50:
            signal = "LONG"
            stop_loss = current_price - (1.2 * atr_val)
            take_profit = min(current_price + (3.0 * atr_val), y_high)
            
        elif prev['EMA_9'] >= prev['EMA_21'] and last['EMA_9'] < last['EMA_21'] and rsi_val < 50:
            signal = "SHORT"
            stop_loss = current_price + (1.2 * atr_val)
            take_profit = max(current_price - (3.0 * atr_val), y_low)
            
        last_sent_signal = get_last_state()
        
        # Invio notifica solo in caso di cambio effettivo di stato
        if signal and signal != last_sent_signal:
            save_state(signal)
            emoji = "🟢" if signal == "LONG" else "🔴"
            
            message = (
                f"🚨 *SEGNALE MINIFIB / MIB (15m)*\n\n"
                f"• Direzione: {emoji} *{signal}*\n"
                f"• **Trigger (Ingresso)**: `{current_price:.2f}`\n"
                f"• **Stop Loss (SL)**: `{stop_loss:.2f}`\n"
                f"• **Take Profit (TP)**: `{take_profit:.2f}`\n\n"
                f"📊 *Metriche e Contesto:*\n"
                f"• EMA 9/21: `{last['EMA_9']:.2f}` / `{last['EMA_21']:.2f}`\n"
                f"• RSI: `{rsi_val:.1f}` | ATR: `{atr_val:.1f} pt`\n"
                f"• Range Ieri (Daily): `{y_range:.1f} pt`\n"
                f"• Orario candela: `{timestamp_candela}`"
            )
            send_telegram(message)
            print(f"Segnale MIB inviato: {signal}")
        else:
            print(f"MIB: Nessun nuovo segnale (Ultimo stato: {last_sent_signal})")

    except Exception as e:
        print(f"Errore esecuzione mib_checker: {e}")

if __name__ == "__main__":
    run_mib_check()
