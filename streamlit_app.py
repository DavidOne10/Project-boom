import os
import requests
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
import pytz

# =============================================================================
# SETUP PAGINA & CREDENZIALI
# =============================================================================
st.set_page_config(page_title="Trading Dashboard PRO", page_icon="📈", layout="wide")

# Recupero credenziali in modo sicuro
API_KEY = os.environ.get("API_KEY") or st.secrets.get("API_KEY", "")
SECRET_KEY = os.environ.get("SECRET_KEY") or st.secrets.get("SECRET_KEY", "")

ALPACA_TRADING_URL = "https://paper-api.alpaca.markets/v2"
ALPACA_DATA_URL = "https://data.alpaca.markets/v2"

HEADERS = {"APCA-API-KEY-ID": API_KEY, "APCA-API-SECRET-KEY": SECRET_KEY}

# Raccoglitore globale per i segnali attivi (utilizzato poi nel terminale ordini)
global_signals = {}

# =============================================================================
# 🎛️ SIDEBAR: CENTRO DI CONTROLLO & STATO
# =============================================================================
st.sidebar.title("🤖 System Status")
st.sidebar.divider()

now_utc = datetime.now(pytz.utc)
st.sidebar.metric("Orario Server (UTC)", now_utc.strftime("%H:%M:%S"))

st.sidebar.subheader("🔌 Connessione Broker")
if API_KEY and SECRET_KEY:
    try:
        r = requests.get(f"{ALPACA_TRADING_URL}/account", headers=HEADERS, timeout=3)
        if r.status_code == 200:
            st.sidebar.success("✅ Alpaca API: OK")
            st.sidebar.text(f"Cash: ${float(r.json().get('cash', 0)):,.2f}")
        else:
            st.sidebar.error("❌ Alpaca API: Errore Auth")
    except Exception:
        st.sidebar.error("❌ Alpaca API: Offline")
else:
    st.sidebar.warning("⚠️ Chiavi Alpaca Mancanti")

st.sidebar.divider()
st.sidebar.subheader("🏛️ Stato Mercati")
# Wall Street: 13:30 - 20:00 UTC (15:30 - 22:00 CET)
is_us_open = 13 <= now_utc.hour < 20
# Europa (DAX): 07:00 - 15:30 UTC (09:00 - 17:30 CET)
is_eu_open = 7 <= now_utc.hour < 15

st.sidebar.write(f"🇺🇸 Wall Street: {'🟢 APERTA' if is_us_open else '🔴 CHIUSA'}")
st.sidebar.write(f"🇪🇺 Europa (DAX): {'🟢 APERTA' if is_eu_open else '🔴 CHIUSA'}")
st.sidebar.write("🪙 Crypto (BTC/ETH): 🟢 24/7")

# =============================================================================
# INTRODUZIONE DASHBOARD
# =============================================================================
st.title("📈 Trading Dashboard — Multi-Asset PRO")
st.write("Monitoraggio segnali, diagnostica filtri ed esecuzione ordini in tempo reale.")

# =============================================================================
# FUNZIONI HELPERS PER IL DOWNLOAD DATI
# =============================================================================
@st.cache_data(ttl=60)
def fetch_yf_data(ticker, period="6mo", interval="1d"):
    """Scarica dati storici da Yahoo Finance pulendo l'eventuale MultiIndex delle colonne."""
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty:
            return pd.DataFrame()
        return df[['Open', 'High', 'Low', 'Close']]
    except Exception:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_us_intraday_alpaca(symbol):
    """Scarica candele 15M da Alpaca IEX per la strategia US ORB."""
    if not API_KEY or not SECRET_KEY:
        return pd.DataFrame()
    url = f"{ALPACA_DATA_URL}/stocks/bars?symbols={symbol}&timeframe=15Min&limit=100&feed=iex"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            bars = res.json().get("bars", {}).get(symbol, [])
            if not bars:
                return pd.DataFrame()
            df = pd.DataFrame(bars)
            df['t'] = pd.to_datetime(df['t']).dt.tz_convert("America/New_York")
            df.set_index('t', inplace=True)
            df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
            return df[['Open', 'High', 'Low', 'Close']]
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

# =============================================================================
# 🇺🇸 SEZIONE 1: MERCATI USA (ORB 15M & TREND)
# =============================================================================
st.header("🇺🇸 Mercati USA — Breakout ORB 15m")

usa_assets = {
    "S&P 500": ("SPY", "SPY"),
    "WTI Oil": ("USO", "USO"),
    "Gold": ("GLD", "GLD")
}

with st.expander("🔍 Diagnostica Mercati USA", expanded=True):
    usa_cols = st.columns(len(usa_assets))
    for idx, (name, (alpaca_sym, yf_sym)) in enumerate(usa_assets.items()):
        with usa_cols[idx]:
            st.subheader(f"{name} ({alpaca_sym})")
            
            # Durante la sessione usa Alpaca Intraday, altrimenti fallback su Yahoo Finance
            df_intra = fetch_us_intraday_alpaca(alpaca_sym) if is_us_open else pd.DataFrame()
            
            if not df_intra.empty:
                df_intra['EMA_200'] = df_intra['Close'].ewm(span=200, adjust=False).mean()
                curr_p = float(df_intra['Close'].iloc[-1])
                ema = float(df_intra['EMA_200'].iloc[-1])
                
                today_bars = df_intra[df_intra.index.date == df_intra.index.max().date()]
                orb = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
                
                st.metric("Prezzo Live 15m", f"${curr_p:.2f}")
                
                if not orb.empty:
                    orb_h, orb_l = float(orb['High'].iloc[0]), float(orb['Low'].iloc[0])
                    st.write(f"**ORB High:** ${orb_h:.2f} | **ORB Low:** ${orb_l:.2f}")
                    
                    cond_long = curr_p > orb_h and curr_p > ema
                    cond_short = curr_p < orb_l and curr_p < ema
                    
                    st.write("### Esito Filtri:")
                    st.write(f"- **Trend (Prezzo > EMA200):** {'✅' if curr_p > ema else '❌'}")
                    st.write(f"- **Breakout High:** {'✅' if curr_p > orb_h else '❌'}")
                    
                    if cond_long:
                        st.success("🟢 SEGNALE LONG VALIDO")
                        global_signals[alpaca_sym] = {"dir": "LONG", "entry": curr_p}
                    elif cond_short:
                        st.error("🔴 SEGNALE SHORT VALIDO")
                        global_signals[alpaca_sym] = {"dir": "SHORT", "entry": curr_p}
                    else:
                        st.info("⚖️ Nessun setup confermato.")
                else:
                    st.write("⏳ In attesa della candela ORB (09:30 EST).")
            else:
                # Se la sessione intraday è chiusa, mostriamo lo stato Daily via yfinance
                df_daily = fetch_yf_data(yf_sym, period="6mo", interval="1d")
                if not df_daily.empty and len(df_daily) >= 20:
                    df_daily['EMA_50'] = df_daily['Close'].ewm(span=50, adjust=False).mean()
                    df_daily['High_20'] = df_daily['Close'].shift(1).rolling(20).max()
                    
                    last = df_daily.iloc[-1]
                    curr_p = float(last['Close'])
                    ema = float(df_daily['EMA_50'].iloc[-1])
                    h20 = float(df_daily['High_20'].iloc[-1])
                    
                    st.metric("Ultimo Chiusura", f"${curr_p:.2f}")
                    st.write(f"**EMA 50:** ${ema:.2f} | **Max 20g:** ${h20:.2f}")
                    st.info("🌙 Mercato Chiuso. Attesa sessione 15:30 CET.")
                else:
                    st.warning("Dati non disponibili.")

# =============================================================================
# 🪙 SEZIONE 2: CRYPTO (TREND FOLLOWING 24/7)
# =============================================================================
st.divider()
st.header("🪙 Crypto — Donchian Breakout & Trend Following")

crypto_assets = {
    "Bitcoin": ("BTC/USD", "BTC-USD"),
    "Ethereum": ("ETH/USD", "ETH-USD")
}

with st.expander("🔍 Diagnostica Crypto", expanded=True):
    cry_cols = st.columns(len(crypto_assets))
    for idx, (name, (alpaca_sym, yf_sym)) in enumerate(crypto_assets.items()):
        df = fetch_yf_data(yf_sym, period="6mo", interval="1d")
        with cry_cols[idx]:
            st.subheader(f"{name} ({alpaca_sym})")
            if df.empty or len(df) < 25:
                st.warning("Dati Crypto in caricamento o non disponibili.")
                continue
            
            df['EMA_50'] = df['Close'].ewm(span=50, adjust=False).mean()
            df['High_20'] = df['Close'].shift(1).rolling(20).max()
            
            last = df.iloc[-1]
            c = float(last['Close'])
            e50 = float(df['EMA_50'].iloc[-1])
            h20 = float(df['High_20'].iloc[-1])
            
            st.metric("Prezzo Attuale", f"${c:,.2f}")
            st.write(f"**EMA 50:** ${e50:,.2f} | **Max 20g:** ${h20:,.2f}")
            
            cond_ema = c > e50
            cond_brk = c > h20
            
            st.write("### Esito Filtri:")
            st.write(f"- **Trend (Prezzo > EMA50):** {'✅' if cond_ema else '❌'}")
            st.write(f"- **Breakout (Prezzo > Max 20g):** {'✅' if cond_brk else '❌'}")
            
            if cond_ema and cond_brk:
                st.success("🚀 SEGNALE LONG VALIDO")
                global_signals[alpaca_sym] = {"dir": "LONG", "entry": c}
            else:
                st.info("⚖️ In accumulazione / Nessun breakout.")

# =============================================================================
# 🇪🇺 SEZIONE 3: EUROPA (DAX SWING 3X)
# =============================================================================
st.divider()
st.header("🇪🇺 Mercati Europei — DAX Swing 3X")

with st.expander("🔍 Diagnostica Europa", expanded=True):
    df_dax = fetch_yf_data("^GDAXI", period="6mo", interval="1d")
    if not df_dax.empty and len(df_dax) >= 25:
        df_dax['EMA_50'] = df_dax['Close'].ewm(span=50, adjust=False).mean()
        df_dax['High_20'] = df_dax['Close'].shift(1).rolling(20).max()
        
        l_dax = df_dax.iloc[-1]
        c_dax = float(l_dax['Close'])
        ema_dax = float(df_dax['EMA_50'].iloc[-1])
        h20_dax = float(df_dax['High_20'].iloc[-1])
        
        st.metric("DAX Spot (^GDAXI)", f"{c_dax:,.2f}")
        st.write(f"**EMA 50:** {ema_dax:,.2f} | **Max 20g:** {h20_dax:,.2f}")
        
        c1, c2 = st.columns(2)
        c1.write(f"- **Trend (Prezzo > EMA50):** {'✅' if c_dax > ema_dax else '❌'}")
        c2.write(f"- **Breakout (Prezzo > Max 20g):** {'✅' if c_dax > h20_dax else '❌'}")
        
        if c_dax > ema_dax and c_dax > h20_dax:
            st.success("🟢 SEGNALE LONG DAX ATTIVO (Applica su ETF 3X)")
            global_signals["^GDAXI"] = {"dir": "LONG", "entry": c_dax}
        else:
            st.info("⚖️ Nessun segnale confermato.")
    else:
        st.warning("Dati DAX non disponibili.")

# =============================================================================
# 🎯 TERMINALE ORDINI (FINECO & ALPACA)
# =============================================================================
st.divider()
st.header("🚀 Terminale Operativo & Convertitore")

all_assets = ["SPY", "USO", "GLD", "BTC/USD", "ETH/USD"]
sel_asset = st.selectbox("Seleziona Asset da gestire:", all_assets)

res = global_signals.get(sel_asset, {"dir": "N/D", "entry": 100.0})

col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    fineco_val = st.number_input("Prezzo Fineco / Piattaforma:", value=float(res['entry']), step=0.1)
with col_f2:
    qty_val = st.number_input("Quantità / Size:", value=1.0, min_value=0.01)
with col_f3:
    if res['dir'] != "N/D":
        st.success(f"Direzione Suggerita: **{res['dir']}**")
        dir_val = res['dir']
    else:
        dir_val = st.radio("Direzione Manuale:", ["LONG", "SHORT"], horizontal=True)

f_tp = fineco_val * 1.015 if dir_val == "LONG" else fineco_val * 0.985
f_sl = fineco_val * 0.995 if dir_val == "LONG" else fineco_val * 1.005

m1, m2, m3 = st.columns(3)
m1.metric("Ingresso", f"{fineco_val:.2f}")
m2.metric("🎯 TAKE PROFIT (+1.5%)", f"{f_tp:.2f}")
m3.metric("🔴 STOP LOSS (-0.5%)", f"{f_sl:.2f}")

if st.button(f"⚡ Esegui Ordine {dir_val} su Alpaca", type="primary"):
    if not API_KEY:
        st.error("Inserisci le API Keys di Alpaca nei Secrets per eseguire l'ordine.")
    else:
        side = "buy" if dir_val == "LONG" else "sell"
        order_data = {
            "symbol": sel_asset,
            "qty": str(qty_val),
            "side": side,
            "type": "market",
            "time_in_force": "gtc"
        }
        try:
            r = requests.post(f"{ALPACA_TRADING_URL}/orders", json=order_data, headers=HEADERS)
            if r.status_code in [200, 201]:
                st.success(f"✅ Ordine piazzato con successo! ID: {r.json().get('id')}")
            else:
                st.error(f"❌ Errore Alpaca: {r.text}")
        except Exception as e:
            st.error(f"Errore di rete: {e}")
