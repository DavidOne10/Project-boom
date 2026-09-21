import os
import sys
import json
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from zoneinfo import ZoneInfo

# --- CACHE ANTI-SPAM TELEGRAM ---
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

# --- 1. CONTROLLO FINESTRA OPERATIVA LOCALE (09:00 - 22:00 Italia) ---
if len(sys.argv) == 1 and not (9 <= now_rome.hour < 22):
    print(f"🌙 Fuori orario operativo ({now_rome.strftime('%H:%M %Z')}). Scansione saltata.")
    sys.exit(0)

# --- 2. SECRETS E CREDENZIALI ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY") or os.environ.get("API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY") or os.environ.get("SECRET_KEY")

ALPACA_DATA_URL = "https://data.alpaca.markets"

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
    send_telegram("🧪 *TEST SYSTEM OK — ALPACA + TELEGRAM OPERATIVI (09:00-22:00)*")
    sys.exit(0)

# --- 3. FETCH DATI STOCKS (ALPACA REAL-TIME 15M) ---
def get_alpaca_stock_bars(symbol, timeframe="15Min", limit=500):
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_DATA_URL}/v2/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=iex"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return pd.DataFrame()
        data = res.json().get("bars", {}).get(symbol, [])
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'], utc=True)
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception as e:
        print(f"❌ Errore Alpaca Stock {symbol}: {e}")
        return pd.DataFrame()

# --- 4. FETCH DATI CRYPTO (YFINANCE DAILY PER DONCHIAN 20G REALE) ---
def get_crypto_daily_yf(yf_symbol):
    try:
        df = yf.download(yf_symbol, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty: return pd.DataFrame()
        return df[['Open', 'High', 'Low', 'Close']]
    except Exception as e:
        print(f"❌ Errore Crypto YFinance {yf_symbol}: {e}")
        return pd.DataFrame()

# Mappatura Asset
ASSETS = {
    "S&P 500 (SPY)":  {"symbol": "SPY",      "yf_symbol": "SPY",     "type": "STOCK_ORB"},
    "PETROLIO (USO)": {"symbol": "USO",      "yf_symbol": "USO",     "type": "STOCK_ORB"},
    "ORO (GLD)":      {"symbol": "GLD",      "yf_symbol": "GLD",     "type": "STOCK_ORB"},
    "BITCOIN":        {"symbol": "BTC/USD",  "yf_symbol": "BTC-USD", "type": "CRYPTO_TRAILING"},
    "ETHEREUM":       {"symbol": "ETH/USD",  "yf_symbol": "ETH-USD", "type": "CRYPTO_TRAILING"}
}

now_est = datetime.now(ZoneInfo("America/New_York"))
is_us_market_open = (now_est.weekday() < 5) and (
    now_est.replace(hour=9, minute=30, second=0) <= now_est <= now_est.replace(hour=16, minute=0, second=0)
)

print(f"🚀 Avvio scansione Real-Time ({now_rome.strftime('%H:%M CEST')})...")

for asset_name, config in ASSETS.items():
    symbol = config["symbol"]
    yf_sym = config["yf_symbol"]
    strat_type = config["type"]

    # --- STRATEGIA 1: STOCK/COMMODITIES ORB 15M + PIVOTS ---
    if strat_type == "STOCK_ORB":
        if not is_us_market_open:
            print(f"🌙 [{asset_name}] Mercato US chiuso. Scansione saltata.")
            continue

        df = get_alpaca_stock_bars(symbol)
        if df.empty: continue

        df.index = df.index.tz_convert("America/New_York")
        df['date'] = df.index.date
        df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

        daily = df.groupby('date').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
        daily['pivot'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
        daily['R1'] = (2 * daily['pivot']) - daily['Low']
        daily['S1'] = (2 * daily['pivot']) - daily['High']
        df = df.merge(daily[['R1', 'S1']].shift(1), left_on='date', right_index=True, how='left')

        df['SMA_50'] = df['Close'].rolling(window=50).mean()
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))

        today_bars = df[df.index.date == df.index.date.max()]
        orb_bar = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
        if orb_bar.empty: continue

        orb_high, orb_low = float(orb_bar['High'].iloc[0]), float(orb_bar['Low'].iloc[0])
        session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute >= 45))]
        if session_bars.empty: continue

        bar = session_bars.iloc[-1]
        c = float(bar['Close'])
        prev_c = float(session_bars.iloc[-2]['Close']) if len(session_bars) > 1 else float(orb_bar['Close'].iloc[0])
        ema = float(bar['EMA_200'])
        sma = float(bar['SMA_50']) if not pd.isna(bar['SMA_50']) else c
        rsi = float(bar['RSI']) if not pd.isna(bar['RSI']) else 50

        is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema) and (c > sma) and (45 <= rsi <= 75)
        is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema) and (c < sma) and (25 <= rsi <= 55)

        if is_long or is_short:
            direction = "LONG" if is_long else "SHORT"
            alert_key = f"{asset_name}_{direction}"

            if sent_alerts.get(alert_key) == today_str:
                print(f"ℹ️ Segnale {direction} per {asset_name} già notificato oggi ({today_str}). Saltato.")
                continue

            sl = orb_low if is_long else orb_high
            risk = abs(c - sl)
            if risk > 0:
                tp = c + (1.3 * risk) if is_long else c - (1.3 * risk)
                r1, s1 = float(bar['R1']), float(bar['S1'])
                
                blocked = (is_long and not pd.isna(r1) and c < r1 < tp) or (is_short and not pd.isna(s1) and tp < s1 < c)
                if not blocked:
                    tp_pct = (abs(tp - c) / c) * 100
                    sl_pct = (abs(c - sl) / c) * 100
                    azione = "COMPRA (Long) 📈" if is_long else "VENDI (Short) 📉"
                    muro = "R1 (Resistenza)" if is_long else "S1 (Supporto)"

                    msg = (
                        f"🚨 *SEGNALE NY ORB 15M — {asset_name}*\n\n"
                        f"🎯 *Azione:* {azione}\n"
                        f"📌 *Prezzo Ingresso:* `{c:.2f}`\n"
                        f"💰 *Take Profit (1.3x):* `{tp:.2f}` (+{tp_pct:.2f}%)\n"
                        f"🛡️ *Stop Loss:* `{sl:.2f}` (-{sl_pct:.2f}%)\n\n"
                        f"✅ *Controllo Sicurezza:* Strada libera fino a {muro}.\n"
                        f"📊 *Orario:* {session_bars.index[-1].strftime('%H:%M')} EST | RSI: `{rsi:.1f}`"
                    )
                    send_telegram(msg)
                    sent_alerts[alert_key] = today_str
                    with open(CACHE_FILE, "w") as f:
                        json.dump(sent_alerts, f)

        # --- STRATEGIA 2: CRYPTO DONCHIAN 20G REALE + CROSSOVER ---
    elif strat_type == "CRYPTO_TRAILING":
        # 1. Livelli giornalieri reali (Donchian 20G, EMA50, Trailing SL 10G)
        df_daily = get_crypto_daily_yf(yf_sym)
        if df_daily.empty or len(df_daily) < 25: continue

        df_daily['EMA_50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()
        df_daily['Donchian_H'] = df_daily['High'].shift(1).rolling(20).max()
        df_daily['Donchian_L'] = df_daily['Low'].shift(1).rolling(20).min()
        df_daily['Trailing_SL_L'] = df_daily['Low'].shift(1).rolling(10).min()
        df_daily['Trailing_SL_H'] = df_daily['High'].shift(1).rolling(10).max()

        last_daily = df_daily.iloc[-1]
        ema = float(last_daily['EMA_50'])
        d_high, d_low = float(last_daily['Donchian_H']), float(last_daily['Donchian_L'])

        # 2. Controllo incrocio sulla candela a 15 minuti (scatta 1 sola volta)
        df_intra = yf.download(yf_sym, period="5d", interval="15m", progress=False, auto_adjust=True)
        if isinstance(df_intra.columns, pd.MultiIndex):
            df_intra.columns = df_intra.columns.get_level_values(0)
        if df_intra.empty or len(df_intra) < 2: continue

        c = float(df_intra['Close'].iloc[-1])       # Prezzo 15m attuale
        prev_c = float(df_intra['Close'].iloc[-2])  # Prezzo 15m di 15 min fa

        is_long = (c > d_high) and (prev_c <= d_high) and (c > ema)
        is_short = (c < d_low) and (prev_c >= d_low) and (c < ema)

        if is_long or is_short:
            direction = "LONG" if is_long else "SHORT"
            trail_sl = float(last_daily['Trailing_SL_L']) if is_long else float(last_daily['Trailing_SL_H'])
            sl_pct = (abs(c - trail_sl) / c) * 100
            azione = "COMPRA (Long) 📈" if is_long else "VENDI (Short) 📉"

            msg = (
                f"🚨 *SEGNALE CRYPTO TREND — {asset_name}*\n\n"
                f"🎯 *Azione:* {azione}\n"
                f"📌 *Prezzo Attuale:* `{c:.2f}`\n"
                f"🛡️ *Trailing Stop Dinamico (10g):* `{trail_sl:.2f}` (-{sl_pct:.2f}%)\n\n"
                f"ℹ️ *Gestione Exit:* Mantieni la posizione finché il prezzo non infrange il Trailing Stop a 10 giorni."
            )
            send_telegram(msg)
