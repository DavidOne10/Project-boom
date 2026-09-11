import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

# --- 1. CONTROLLO FINESTRA OPERATIVA LOCALE (09:00 - 22:00 Italia) ---
now_rome = datetime.now(ZoneInfo("Europe/Rome"))
if len(sys.argv) == 1 and not (9 <= now_rome.hour < 22):
    print(f"🌙 Fuori orario operativo ({now_rome.strftime('%H:%M %Z')}). Scansione saltata.")
    sys.exit(0)

# --- 2. SECRETS E CREDENZIALI ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY")

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

# --- 3. FETCH DATI REAL-TIME DA ALPACA API ---
def get_alpaca_stock_bars(symbol, timeframe="15Min", limit=500):
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_DATA_URL}/v2/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=iex"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return pd.DataFrame()
        data = res.json().get("bars", {}).get(symbol, [])
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'])
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception as e:
        print(f"❌ Errore Alpaca Stock {symbol}: {e}")
        return pd.DataFrame()

def get_alpaca_crypto_bars(symbol, timeframe="15Min", limit=500):
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_DATA_URL}/v1beta3/crypto/us/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return pd.DataFrame()
        data = res.json().get("bars", {}).get(symbol, [])
        if not data: return pd.DataFrame()
        
        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'])
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception as e:
        print(f"❌ Errore Alpaca Crypto {symbol}: {e}")
        return pd.DataFrame()

# Mappatura Asset
ASSETS = {
    "S&P 500 (SPY)":  {"symbol": "SPY",      "type": "STOCK_ORB"},
    "PETROLIO (USO)": {"symbol": "USO",      "type": "STOCK_ORB"},
    "ORO (GLD)":      {"symbol": "GLD",      "type": "STOCK_ORB"},
    "BITCOIN":        {"symbol": "BTC/USD",  "type": "CRYPTO_TRAILING"},
    "ETHEREUM":       {"symbol": "ETH/USD",  "type": "CRYPTO_TRAILING"}
}

now_est = datetime.now(ZoneInfo("America/New_York"))
is_us_market_open = (now_est.weekday() < 5) and (
    now_est.replace(hour=9, minute=30, second=0) <= now_est <= now_est.replace(hour=16, minute=0, second=0)
)

print(f"🚀 Avvio scansione Real-Time Alpaca ({now_rome.strftime('%H:%M CEST')})...")

for asset_name, config in ASSETS.items():
    symbol = config["symbol"]
    strat_type = config["type"]

    if strat_type == "STOCK_ORB" and not is_us_market_open:
        print(f"🌙 [{asset_name}] Mercato US chiuso. Scansione saltata.")
        continue

    # Download dati da Alpaca
    if strat_type == "STOCK_ORB":
        df = get_alpaca_stock_bars(symbol)
    else:
        df = get_alpaca_crypto_bars(symbol)

    if df.empty: continue

    df.index = df.index.tz_convert("America/New_York")
    df['date'] = df.index.date
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()

    # --- STRATEGIA 1: STOCK/COMMODITIES ORB 15M + PIVOTS ---
    if strat_type == "STOCK_ORB":
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

        orb_high, orb_low = float(orb_bar['High'].values[0]), float(orb_bar['Low'].values[0])
        session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute >= 45))]
        if session_bars.empty: continue

        # Verifica segnale prioritario sulla candela più recente
        bar = session_bars.iloc[-1]
        c = float(bar['Close'])
        prev_c = float(session_bars.iloc[-2]['Close']) if len(session_bars) > 1 else float(orb_bar['Close'].values[0])
        ema, sma = float(bar['EMA_200']), float(bar['SMA_50']) if not pd.isna(bar['SMA_50']) else c
        rsi = float(bar['RSI']) if not pd.isna(bar['RSI']) else 50

        is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema) and (c > sma) and (45 <= rsi <= 75)
        is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema) and (c < sma) and (25 <= rsi <= 55)

        if is_long or is_short:
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

    # --- STRATEGIA 2: CRYPTO DONCHIAN + TRAILING EXIT ---
    elif strat_type == "CRYPTO_TRAILING":
        df['Donchian_H'] = df['High'].shift(1).rolling(20).max()
        df['Donchian_L'] = df['Low'].shift(1).rolling(20).min()
        df['Trailing_SL_L'] = df['Low'].shift(1).rolling(10).min()
        df['Trailing_SL_H'] = df['High'].shift(1).rolling(10).max()

        bar = df.iloc[-1]
        c, ema = float(bar['Close']), float(bar['EMA_200'])
        d_high, d_low = float(bar['Donchian_H']), float(bar['Donchian_L'])

        is_long = (c > d_high) and (c > ema)
        is_short = (c < d_low) and (c < ema)

        if is_long or is_short:
            trail_sl = float(bar['Trailing_SL_L']) if is_long else float(bar['Trailing_SL_H'])
            sl_pct = (abs(c - trail_sl) / c) * 100
            azione = "COMPRA (Long) 📈" if is_long else "VENDI (Short) 📉"

            msg = (
                f"🚨 *SEGNALE CRYPTO TREND — {asset_name}*\n\n"
                f"🎯 *Azione:* {azione}\n"
                f"📌 *Prezzo Attuale:* `{c:.2f}`\n"
                f"🛡️ *Trailing Stop Dinamico (10p):* `{trail_sl:.2f}` (-{sl_pct:.2f}%)\n\n"
                f"ℹ️ *Gestione Exit:* Mantieni la posizione finché il prezzo non infrange il Trailing Stop a 10 candele."
            )
            send_telegram(msg)

print("Scansione completata.")

