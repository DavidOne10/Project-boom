import os
import sys
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# Importazione Alpaca SDK per Mercati US (Zero HTTP 429 Rate Limits)
try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    ALPACA_KEY = os.environ.get("ALPACA_API_KEY")
    ALPACA_SECRET = os.environ.get("ALPACA_SECRET_KEY")
    alpaca_client = StockHistoricalDataClient(ALPACA_KEY, ALPACA_SECRET) if ALPACA_KEY and ALPACA_SECRET else None
except Exception:
    alpaca_client = None

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")

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

# ==========================================
# 1. SCANSIONE CRYPTO 24/7 (Protezione Anti-429 Yahoo)
# ==========================================
def check_crypto():
    now_rome = datetime.now(ZoneInfo("Europe/Rome"))
    print(f"\n🪙 [{now_rome.strftime('%H:%M CEST')}] Avvio scansione Crypto 24/7...")
    crypto_symbols = {"BTC-USD": "Bitcoin ₿", "ETH-USD": "Ethereum 🔷"}

    for ticker, name in crypto_symbols.items():
        try:
            df = yf.download(ticker, period="4mo", interval="1d", progress=False, auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            if df.empty or len(df) < 25:
                print(f"⚠️ Dati non disponibili per {name}")
                continue

            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['High_20'] = df['High'].shift(1).rolling(20).max()
            df['Low_20'] = df['Low'].shift(1).rolling(20).min()

            bar = df.iloc[-1]
            prev_bar = df.iloc[-2]

            c = float(bar['Close'])
            prev_c = float(prev_bar['Close'])
            ema = float(bar['EMA_50'])
            h20, l20 = float(bar['High_20']), float(bar['Low_20'])
            prev_h20, prev_l20 = float(prev_bar['High_20']), float(prev_bar['Low_20'])

            is_long = (c > h20) and (prev_c <= prev_h20) and (c > ema)
            is_short = (c < l20) and (prev_c >= prev_l20) and (c < ema)

            print(f"📊 {name}: Prezzo {c:,.2f} | EMA50: {ema:,.2f} | High20: {h20:,.2f} | Low20: {l20:,.2f}")

            if is_long or is_short:
                azione = "COMPRA (Long) 📈" if is_long else "VENDI (Short) 📉"
                soglia = h20 if is_long else l20

                msg = (
                    f"🚨 *SEGNALE CRYPTO — BREAKOUT 20G*\n\n"
                    f"🪙 *Asset:* {name}\n"
                    f"🎯 *Azione:* {azione}\n"
                    f"📌 *Prezzo Attuale:* `${c:,.2f}`\n"
                    f"📐 *Livello Breakout (20g):* `${soglia:,.2f}`\n"
                    f"📊 *Filtro EMA50:* `${ema:,.2f}`\n"
                )
                send_telegram(msg)
            else:
                print(f"⚖️ {name}: Nessun breakout confermato.")

        except Exception as e:
            print(f"⚠️ Errore temporaneo Yahoo per {name}: {e}. Salto al prossimo asset.")

# ==========================================
# 2. SCANSIONE STOCK US (Alpaca API + Filtri Completi)
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
        print("❌ Alpaca API Keys mancanti. Impossibile eseguire la scansione US.")
        return

    symbols = ["SPY", "USO", "GLD"]
    print(f"📈 Avvio scansione ORB 15m su {symbols} via Alpaca API...")

    for sym in symbols:
        try:
            request_params = StockBarsRequest(
                symbol_or_symbols=sym,
                timeframe=TimeFrame.Minute15,
                limit=200
            )
            bars = alpaca_client.get_stock_bars(request_params)
            df = bars.df

            if isinstance(df.index, pd.MultiIndex):
                if sym in df.index.get_level_values(0):
                    df = df.xs(sym)
                else:
                    continue

            if df.empty or len(df) < 50:
                print(f"⚠️ Dati insufficienti per {sym} su Alpaca.")
                continue

            # Gestione Timezone EST
            df['date_est'] = df.index.tz_convert("America/New_York")
            today_df = df[df['date_est'].dt.date == now_ny.date()]

            if today_df.empty:
                print(f"⏳ Nessuna candela per oggi su {sym}.")
                continue

            # ORB 15m (Candela 09:30 EST)
            orb_first_bar = today_df[(today_df['date_est'].dt.hour == 9) & (today_df['date_est'].dt.minute == 30)]

            if orb_first_bar.empty:
                print(f"⏳ Candela di apertura 09:30 non ancora disponibile per {sym}.")
                continue

            orb_high = float(orb_first_bar['high'].iloc[0])
            orb_low = float(orb_first_bar['low'].iloc[0])

            # Indicatori: EMA200, SMA50 e RSI(14)
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

            # Filtro RSI (25 - 75)
            rsi_valid = 25 <= rsi <= 75

            # Condizione Crossover Breakout + Filtri Trend
            is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema200) and (c > sma50) and rsi_valid
            is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema200) and (c < sma50) and rsi_valid

            print(f"📊 {sym}: Prezzo {c:.2f} | ORB High: {orb_high:.2f} | ORB Low: {orb_low:.2f} | EMA200: {ema200:.2f} | RSI: {rsi:.1f}")

            if is_long or is_short:
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
            else:
                print(f"⚖️ {sym}: Nessun nuovo breakout prioritario.")

        except Exception as e:
            print(f"❌ Errore durante la scansione Alpaca per {sym}: {e}")

# ==========================================
# 3. MAIN EXECUTION
# ==========================================
if __name__ == "__main__":
    check_crypto()
    check_us_stocks()
