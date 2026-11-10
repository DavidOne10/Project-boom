import os
import requests
import yfinance as yf
import pandas as pd
from flask import Flask, jsonify
from datetime import datetime
import pytz

app = Flask(__name__)

# Configurazioni Telegram e Fuso Orario
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TIMEZONE = pytz.timezone("Europe/Rome")

# Memoria di stato per evitare alert duplicati sullo stesso segnale
last_sent_signal = None

def send_telegram(message):
    """Invia l'alert formattato al bot Telegram."""
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("Credenziali Telegram mancanti.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Errore nell'invio Telegram: {e}")

@app.route("/")
def home():
    return "FTSE MIB / Minifib Checker (15m + Daily) attivo e operativo!", 200

@app.route("/check-mib", methods=["GET"])
def check_mib():
    global last_sent_signal
    
    # 1. Filtro orario: Borsa Italiana aperta (Lun-Ven, 09:00 - 17:30)
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5: 
        return jsonify({"status": "mercato chiuso (weekend)"}), 200
        
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=17, minute=30, second=0, microsecond=0)
    
    if not (market_open <= now <= market_close):
        return jsonify({"status": "fuori orario di borsa"}), 200

    try:
        ticker = yf.Ticker("^FTSEMIB")
        
        # 2. Download dati a 15 minuti (per la strategia) e Daily (per i confini)
        df_15m = ticker.history(period="5d", interval="15m")
        df_daily = ticker.history(period="5d", interval="1d")
        
        if df_15m.empty or df_daily.empty or len(df_15m) < 40:
            return jsonify({"status": "dati insufficienti"}), 400

        # Estraiamo i livelli chiave della seduta Daily precedente
        yesterday = df_daily.iloc[-2]
        y_high = yesterday['High']
        y_low = yesterday['Low']
        y_range = y_high - y_low

        # Lavoriamo rigorosamente sulla candela a 15m appena CHIUSA
        df_closed = df_15m.iloc[:-1].copy()

        # 3. Calcolo Indicatori Tecnici (EMA 9/21, RSI 14, ATR 14)
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
        
        # 4. Logica di Ingresso: Crossover EMA + Filtro RSI + Target Ibrido (ATR + Daily)
        signal = None
        if prev['EMA_9'] <= prev['EMA_21'] and last['EMA_9'] > last['EMA_21'] and rsi_val > 50:
            signal = "LONG"
            stop_loss = current_price - (1.2 * atr_val)
            take_profit = min(current_price + (3.0 * atr_val), y_high) # Limitato al massimo di ieri
            
        elif prev['EMA_9'] >= prev['EMA_21'] and last['EMA_9'] < last['EMA_21'] and rsi_val < 50:
            signal = "SHORT"
            stop_loss = current_price + (1.2 * atr_val)
            take_profit = max(current_price - (3.0 * atr_val), y_low) # Limitato al minimo di ieri
            
        # 5. Controllo Anti-Spam e Invio Notifica Telegram
        if signal and signal != last_sent_signal:
            last_sent_signal = signal
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
            return jsonify({"status": f"segnale inviato: {signal}"}), 200
        else:
            return jsonify({"status": "nessun nuovo segnale valido", "ultimo_segnale": last_sent_signal}), 200

    except Exception as e:
        print(f"Errore di elaborazione: {e}")
        return jsonify({"status": "errore", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
