import os
import json
import requests
import pandas as pd
from datetime import datetime
import pytz
import yfinance as yf

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
TIMEZONE = pytz.timezone("Europe/Rome")
STATE_FILE = "mib_state.json"
MIB_OFFSET = -523  # Differenza fissa per Plus500

def send_telegram(message):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("⚠️ Credenziali Telegram mancanti.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("✅ Messaggio Telegram inviato con successo!")
            return True
        else:
            print(f"❌ Errore Telegram ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"❌ Eccezione nell'invio Telegram: {e}")
        return False

def get_last_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                saved_date = data.get("date")
                today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
                if saved_date != today_str:
                    print("🔄 Nuovo giorno rilevato: reset dello stato precedente.")
                    return None
                return data.get("signal")
        except Exception:
            pass
    return None

def save_state(signal):
    try:
        today_str = datetime.now(TIMEZONE).strftime('%Y-%m-%d')
        with open(STATE_FILE, "w") as f:
            json.dump({
                "signal": signal,
                "date": today_str,
                "updated_at": datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')
            }, f)
    except Exception as e:
        print(f"Errore salvataggio stato MIB: {e}")

def run_mib_check():
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
        print("Analisi FTSE MIB / Minifib in corso (via Yahoo .MI)...")

        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })

        ticker = yf.Ticker("FTSEMIB.MI", session=session)
        df_15m = ticker.history(period="5d", interval="15m")
        df_daily = ticker.history(period="5d", interval="1d")

        if df_15m.empty or len(df_15m) < 40:
            ticker = yf.Ticker("EXXT.MI", session=session)
            df_15m = ticker.history(period="5d", interval="15m")
            df_daily = ticker.history(period="5d", interval="1d")

        if isinstance(df_15m.columns, pd.MultiIndex):
            df_15m.columns = df_15m.columns.get_level_values(0)
        if isinstance(df_daily.columns, pd.MultiIndex):
            df_daily.columns = df_daily.columns.get_level_values(0)

        if df_15m.empty or df_daily.empty or len(df_15m) < 40:
            print("MIB: Dati insufficienti da Yahoo (.MI).")
            return

        if df_15m.index.tz is None:
            df_15m.index = df_15m.index.tz_localize("UTC").tz_convert(TIMEZONE)
        else:
            df_15m.index = df_15m.index.tz_convert(TIMEZONE)

        if df_daily.index.tz is None:
            df_daily.index = df_daily.index.tz_localize("UTC").tz_convert(TIMEZONE)
        else:
            df_daily.index = df_daily.index.tz_convert(TIMEZONE)

        yesterday = df_daily.iloc[-2]
        y_high = yesterday['High']
        y_low = yesterday['Low']
        y_range = y_high - y_low

        df_closed = df_15m.iloc[:-1].copy()

        df_closed['EMA_9'] = df_closed['Close'].ewm(span=9, adjust=False).mean()
        df_closed['EMA_21'] = df_closed['Close'].ewm(span=21, adjust=False).mean()

        delta = df_closed['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df_closed['RSI'] = 100 - (100 / (1 + rs))

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

        sl_long = current_price - (1.2 * atr_val)
        tp_long = min(current_price + (3.0 * atr_val), y_high)

        sl_short = current_price + (1.2 * atr_val)
        tp_short = max(current_price - (3.0 * atr_val), y_low)

        print(f"📊 MIB Spot: {current_price:.2f} | EMA9: {last['EMA_9']:.2f} | EMA21: {last['EMA_21']:.2f} | RSI: {rsi_val:.1f}")
        print(f"🎯 Livelli in attesa -> LONG [SL: {sl_long:.2f} | TP: {tp_long:.2f}] | SHORT [SL: {sl_short:.2f} | TP: {tp_short:.2f}]")

        # --- ANALISI SEGNALI (Incrocio + Trend Following Avanzato con Pullback e Slope) ---
        signal = None
        tipo_segnale = "INCROCIO"

        ema9_slope = last['EMA_9'] - df_closed.iloc[-2]['EMA_9']

        # 1. Controllo INCROCIO INIZIALE
        if prev['EMA_9'] <= prev['EMA_21'] and last['EMA_9'] > last['EMA_21'] and rsi_val > 50:
            signal = "LONG"
            stop_loss = sl_long
            take_profit = tp_long

        elif prev['EMA_9'] >= prev['EMA_21'] and last['EMA_9'] < last['EMA_21'] and rsi_val < 50:
            signal = "SHORT"
            stop_loss = sl_short
            take_profit = tp_short

        else:
            # 2. CONTINUAZIONE DI TREND (Trend Following Avanzato sui Pullback)
            if last['EMA_9'] > last['EMA_21'] and ema9_slope > 0:
                tocca_ema = (df_closed.iloc[-3]['Low'] <= df_closed.iloc[-3]['EMA_9']) or (df_closed.iloc[-2]['Low'] <= df_closed.iloc[-2]['EMA_9'])
                rompe_massimo = last['Close'] > df_closed.iloc[-2]['High']

                if tocca_ema and rompe_massimo and rsi_val > 50:
                    signal = "LONG"
                    tipo_segnale = "CONTINUAZIONE (Pullback Pro)"
                    stop_loss = current_price - (1.2 * atr_val)
                    take_profit = min(current_price + (3.0 * atr_val), y_high)

            elif last['EMA_9'] < last['EMA_21'] and ema9_slope < 0:
                tocca_ema = (df_closed.iloc[-3]['High'] >= df_closed.iloc[-3]['EMA_9']) or (df_closed.iloc[-2]['High'] >= df_closed.iloc[-2]['EMA_9'])
                rompe_minimo = last['Close'] < df_closed.iloc[-2]['Low']

                if tocca_ema and rompe_minimo and rsi_val < 50:
                    signal = "SHORT"
                    tipo_segnale = "CONTINUAZIONE (Pullback Pro)"
                    stop_loss = current_price + (1.2 * atr_val)
                    take_profit = max(current_price - (3.0 * atr_val), y_low)

        last_sent_signal = get_last_state()

        if signal:
            if signal != last_sent_signal or tipo_segnale == "CONTINUAZIONE (Pullback Pro)":
                emoji = "🟢" if signal == "LONG" else "🔴"

                p_operativo = current_price + MIB_OFFSET
                sl_operativo = stop_loss + MIB_OFFSET
                tp_operativo = take_profit + MIB_OFFSET

                tolleranza = 0.3 * atr_val
                if signal == "LONG":
                    limite_ingresso = (current_price + tolleranza) + MIB_OFFSET
                    regola_tolleranza = f"• **Max Ingresso Consentito**: `{limite_ingresso:.2f}`"
                else:
                    limite_ingresso = (current_price - tolleranza) + MIB_OFFSET
                    regola_tolleranza = f"• **Min Ingresso Consentito**: `{limite_ingresso:.2f}`"

                message = (
                    f"🚨 *SEGNALE MINIFIB / MIB (15m)*\n"
                    f"• Tipo: *{tipo_segnale}*\n\n"
                    f"• Direzione: {emoji} *{signal}*\n"
                    f"• **Trigger (Ingresso)**: `{p_operativo:.2f}`\n"
                    f"{regola_tolleranza}\n"
                    f"• **Stop Loss (SL)**: `{sl_operativo:.2f}`\n"
                    f"• **Take Profit (TP)**: `{tp_operativo:.2f}`\n\n"
                    f"📊 *Metriche e Contesto:*\n"
                    f"• EMA 9/21: `{last['EMA_9']:.2f}` / `{last['EMA_21']:.2f}`\n"
                    f"• RSI: `{rsi_val:.1f}` | ATR: `{atr_val:.1f} pt`\n"
                    f"• Range Ieri (Daily): `{y_range:.1f} pt`\n"
                    f"• Orario candela: `{timestamp_candela}`"
                )

                if send_telegram(message):
                    save_state(signal)
                    print(f"✅ Segnale MIB {signal} ({tipo_segnale}) inviato correttamente!")
                else:
                    print(f"⚠️ Segnale MIB {signal} ({tipo_segnale}) NON inviato per problemi Telegram.")
            else:
                print(f"ℹ️ Segnale {signal} già registrato oggi.")
        else:
            print(f"MIB: Nessun nuovo segnale o pullback Pro rilevato (Ultimo stato: {last_sent_signal})")

    except Exception as e:
        print(f"❌ Errore esecuzione mib_checker: {e}")

if __name__ == "__main__":
    run_mib_check()
