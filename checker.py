import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# --- 1. CONFIGURAZIONE CREDENZIALI & TELEGRAM ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")

# --- 2. CACHE ANTI-SPAM TELEGRAM ---
CACHE_FILE = "sent_alerts.json"
sent_alerts = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r") as f:
            sent_alerts = json.load(f)
    except Exception:
        sent_alerts = {}

now_rome = datetime.now(ZoneInfo("Europe/Rome"))
today_str = now_rome.strftime("%Y-%m-%d")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"⚠️ Credenziali Telegram non trovate. Messaggio simulato:\n{message}")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("✅ Messaggio Telegram inviato!")
        else:
            print(f"❌ Errore Telegram: {res.text}")
    except Exception as e:
        print(f"❌ Errore connessione Telegram: {e}")

if len(sys.argv) > 1 and sys.argv[1] == "--test":
    send_telegram("🧪 *TEST CHECKER — TELEGRAM OPERATIVO*")
    sys.exit(0)

# Importazione Alpaca SDK per Mercati US
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.data.enums import DataFeed
    ALPACA_KEY = os.environ.get("ALPACA_API_KEY") or os.environ.get("API_KEY")
    ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("SECRET_KEY")
    alpaca_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET) if ALPACA_KEY and ALPACA_SECRET else None
except Exception:
    alpaca_client = None

# ==========================================
# 3. SCANSIONE CRYPTO 24/7 (15M Crossover + Donchian 20G + Trailing SL)
# ==========================================
def check_crypto():
    print(f"\n🪙 [{now_rome.strftime('%H:%M CEST')}] Avvio scansione Crypto 24/7...")
    crypto_symbols = {"BTC-USD": "Bitcoin ₿", "ETH-USD": "Ethereum 🔷"}

    for ticker, name in crypto_symbols.items():
        try:
            # 1. Livelli giornalieri (Donchian 20G, EMA50, Trailing SL 10G)
            df_daily = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(df_daily.columns, pd.MultiIndex):
                df_daily.columns = df_daily.columns.get_level_values(0)

            if df_daily.empty or len(df_daily) < 25:
                print(f"⚠️ Dati giornalieri non disponibili per {name}")
                continue

            df_daily['EMA_50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()
            df_daily['Donchian_H'] = df_daily['High'].shift(1).rolling(20).max()
            df_daily['Donchian_L'] = df_daily['Low'].shift(1).rolling(20).min()
            df_daily['Trailing_SL_L'] = df_daily['Low'].shift(1).rolling(10).min()
            df_daily['Trailing_SL_H'] = df_daily['High'].shift(1).rolling(10).max()

            last_daily = df_daily.iloc[-1]
            ema = float(last_daily['EMA_50'])
            d_high, d_low = float(last_daily['Donchian_H']), float(last_daily['Donchian_L'])

            # 2. Controllo incrocio su candela 15m
            df_intra = yf.download(ticker, period="5d", interval="15m", progress=False, auto_adjust=True)
            if isinstance(df_intra.columns, pd.MultiIndex):
                df_intra.columns = df_intra.columns.get_level_values(0)

            if df_intra.empty or len(df_intra) < 2:
                print(f"⚠️ Dati intraday 15m non disponibili per {name}")
                continue

            c = float(df_intra['Close'].iloc[-1])       # Prezzo 15m attuale
            prev_c = float(df_intra['Close'].iloc[-2])  # Prezzo 15m precedente

            is_long = (c > d_high) and (prev_c <= d_high) and (c > ema)
            is_short = (c < d_low) and (prev_c >= d_low) and (c < ema)

            print(f"📊 {name}: Prezzo {c:,.2f} | EMA50: {ema:,.2f} | Donchian H20: {d_high:,.2f} | Donchian L20: {d_low:,.2f}")

            if is_long or is_short:
                direction = "LONG" if is_long else "SHORT"
                alert_key = f"{ticker}_{direction}"

                if sent_alerts.get(alert_key) == today_str:
                    print(f"ℹ️ Segnale {direction} per {name} già inviato oggi. Saltato.")
                    continue

                azione = "COMPRA (Long) 📈" if is_long else "VENDI (Short) 📉"
                trail_sl = float(last_daily['Trailing_SL_L']) if is_long else float(last_daily['Trailing_SL_H'])
                sl_pct = (abs(c - trail_sl) / c) * 100

                msg = (
                    f"🚨 *SEGNALE CRYPTO TREND — {name}*\n\n"
                    f"🎯 *Azione:* {azione}\n"
                    f"📌 *Prezzo Attuale:* `${c:,.2f}`\n"
                    f"🛡️ *Trailing Stop Dinamico (10g):* `${trail_sl:,.2f}` (-{sl_pct:.2f}%)\n\n"
                    f"ℹ️ *Exit:* Mantieni finché il prezzo non infrange il Trailing Stop a 10 giorni."
                )
                send_telegram(msg)
                
                sent_alerts[alert_key] = today_str
                with open(CACHE_FILE, "w") as f:
                    json.dump(sent_alerts, f)
            else:
                print(f"⚖️ {name}: Nessun nuovo incrocio sui 15m.")

        except Exception as e:
            print(f"⚠️ Errore temporaneo per {name}: {e}")

# ==========================================
# 4. SCANSIONE STOCK US (Alpaca API ORB 15M)
# ==========================================
def check_us_stocks():
    now_ny = datetime.now(ZoneInfo("America/New_York"))
    print(f"\n🇺🇸 [{now_ny.strftime('%H:%M EST')}] Controllo orario Wall Street...")
    
    is_market_open = (now_ny.weekday() < 5) and (
        (now_ny.hour == 9 and now_ny.minute >= 30) or (10 <= now_ny.hour < 16)
    )

    if not is_market_open:
        print(f"🌙 Mercati US chiusi ({now_ny.strftime('%H:%M EST')}). Scansione Stock US saltata.")
        return

    if not alpaca_client:
        print("❌ Alpaca API Keys mancanti. Scansione US saltata.")
        return

    symbols = ["SPY", "USO", "GLD"]
    print(f"📈 Avvio scansione ORB 15m su {symbols} via Alpaca API...")
    start_date = now_ny - timedelta(days=7)

    for sym in symbols:
        try:
            request_params = StockBarsRequest(
                symbol_or_symbols=sym,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=start_date,
                feed=DataFeed.IEX
            )
            bars = alpaca_client.get_stock_bars(request_params)
            df = bars.df

            if isinstance(df.index, pd.MultiIndex):
                if sym in df.index.get_level_values(0):
                    df = df.xs(sym)
                else:
                    continue

            if df.empty or len(df) < 30:
                print(f"⚠️ Dati insufficienti per {sym} su Alpaca.")
                continue

            df['date_est'] = df.index.tz_convert("America/New_York")
            today_df = df[df['date_est'].dt.date == now_ny.date()]

            if today_df.empty:
                print(f"⏳ Nessuna candela per oggi su {sym}.")
                continue

            orb_first_bar = today_df[(today_df['date_est'].dt.hour == 9) & (today_df['date_est'].dt.minute == 30)]
            if orb_first_bar.empty:
                print(f"⏳ Candela di apertura 09:30 non ancora disponibile per {sym}.")
                continue

            orb_high = float(orb_first_bar['high'].iloc[0])
            orb_low = float(orb_first_bar['low'].iloc[0])

            df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()
            df['SMA50'] = df['close'].rolling(50).mean()
            
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))

            bar = df.iloc[-1]
            prev_bar = df.iloc[-2]

            c = float(bar['close'])
            prev_c = float(prev_bar['close'])
            ema200 = float(bar['EMA200'])
            sma50 = float(bar['SMA50'])
            rsi = float(bar['RSI'])

            rsi_valid = 25 <= rsi <= 75

            is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema200) and (c > sma50) and rsi_valid
            is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema200) and (c < sma50) and rsi_valid

            print(f"📊 {sym}: Prezzo {c:.2f} | ORB High: {orb_high:.2f} | ORB Low: {orb_low:.2f} | EMA200: {ema200:.2f} | RSI: {rsi:.1f}")

            if is_long or is_short:
                direction = "LONG" if is_long else "SHORT"
                alert_key = f"{sym}_{direction}"

                if sent_alerts.get(alert_key) == today_str:
                    print(f"ℹ️ Segnale {direction} per {sym} già inviato oggi. Saltato.")
                    continue

                azione = "LONG 📈" if is_long else "SHORT 📉"
                msg = (
                    f"🚨 *SEGNALE US ORB 15M*\n\n"
                    f"🇺🇸 *Ticker:* {sym}\n"
                    f"🎯 *Azione:* {azione}\n"
                    f"📌 *Prezzo Attuale:* `${c:.2f}`\n"
                    f"📐 *Livello ORB:* `${orb_high if is_long else orb_low:.2f}`\n"
                    f"📊 *EMA200:* `${ema200:.2f}` | *SMA50:* `${sma50:.2f}`\n"
                    f"📈 *RSI(14):* `{rsi:.1f}`\n"
                )
                send_telegram(msg)

                sent_alerts[alert_key] = today_str
                with open(CACHE_FILE, "w") as f:
                    json.dump(sent_alerts, f)
            else:
                print(f"⚖️ {sym}: Nessun nuovo breakout prioritario.")

        except Exception as e:
            print(f"❌ Errore durante la scansione Alpaca per {sym}: {e}")

# ==========================================
# 5. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    check_crypto()
    check_us_stocks()
