import os
import requests
import streamlit as st
import pandas as pd
import numpy as np
import pytz
import yfinance as yf
from datetime import datetime, timedelta

st.set_page_config(page_title="Dashboard Trading — USA & UE", page_icon="📈", layout="wide")

st.title("📈 Trading Dashboard — USA Real-Time & UE Swing 3X")

# =============================================================================
# CREDENZIALI (Compatibilità Sistema + Secrets)
# =============================================================================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY") or st.secrets.get("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY") or st.secrets.get("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL = "https://data.alpaca.markets/v2"

# =============================================================================
# 🇺🇸 SEZIONE 1: MERCATI USA (ORB 15M + S/R + PREVISIONE)
# =============================================================================
st.header("🇺🇸 Mercati USA — Breakout ORB 15m & Monitoraggio")

def get_alpaca_bars(symbol):
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return pd.DataFrame()
    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe=15Min&limit=500&feed=iex"
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code != 200: return pd.DataFrame()
        data = response.json().get("bars", {}).get(symbol, [])
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        df['t'] = pd.to_datetime(df['t'])
        df.set_index('t', inplace=True)
        df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close'}, inplace=True)
        return df
    except Exception:
        return pd.DataFrame()

usa_assets = {"S&P 500 (SPY)": "SPY", "PETROLIO WTI (USO)": "USO", "ORO (GLD)": "GLD"}
usa_results = {}
usa_table_rows = []

for name, symbol in usa_assets.items():
    df = get_alpaca_bars(symbol)
    if df.empty:
        usa_table_rows.append({"Asset": name, "Ticker": symbol, "Prezzo": "-", "Stato Segnale": "⚠️ No Dati", "Previsione / Monitoraggio": "Verificare chiavi Alpaca"})
        continue

    df.index = df.index.tz_convert("America/New_York")
    df['date'] = df.index.date

    # Pivot R1/S1 giorno precedente
    daily = df.groupby('date').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
    daily['pivot'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
    daily['R1'] = (2 * daily['pivot']) - daily['Low']
    daily['S1'] = (2 * daily['pivot']) - daily['High']
    df = df.merge(daily[['R1', 'S1']].shift(1), left_on='date', right_index=True, how='left')

    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    hl = df['High'] - df['Low']
    hc = np.abs(df['High'] - df['Close'].shift())
    lc = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([hl, hc, lc], axis=1), axis=1).rolling(14, min_periods=1).mean()

    today_date = df.index.date.max()
    today_bars = df[df.index.date == today_date]

    if today_bars.empty:
        usa_table_rows.append({"Asset": name, "Ticker": symbol, "Prezzo": "-", "Stato Segnale": "🕒 In Attesa", "Previsione / Monitoraggio": "Nessuna candela odierna"})
        continue

    orb_c = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
    if orb_c.empty:
        usa_table_rows.append({"Asset": name, "Ticker": symbol, "Prezzo": f"${today_bars.iloc[-1]['Close']:.2f}", "Stato Segnale": "🕒 Attesa ORB", "Candela 09:30 EST non chiusa": ""})
        continue

    orb_h, orb_l = float(orb_c['High'].values[0]), float(orb_c['Low'].values[0])
    orb_r, atr = orb_h - orb_l, float(orb_c['ATR'].values[0])
    curr_p = float(today_bars.iloc[-1]['Close'])

    if pd.isna(atr) or orb_r < (0.25 * atr):
        usa_table_rows.append({"Asset": name, "Ticker": symbol, "Prezzo": f"${curr_p:.2f}", "Stato Segnale": "⚠️ ATR Scarto", "Previsione / Monitoraggio": f"Range (${orb_r:.2f}) inferiore al 25% dell'ATR (${0.25*atr:.2f})"})
        continue

    session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute >= 45))]
    if session_bars.empty:
        usa_table_rows.append({"Asset": name, "Ticker": symbol, "Prezzo": f"${curr_p:.2f}", "Stato Segnale": "🕒 Attesa 09:45", "Previsione / Monitoraggio": "Mercato aperto, in attesa della finestra operativa"})
        continue

    signal_type = "NONE"
    entry_p, sl_p, tp_p, risk_pct, tp_pct = 0.0, 0.0, 0.0, 0.0, 0.0
    status_str = "⚖️ In Range"
    monitor_str = f"Prezzo a ${curr_p:.2f} | ORB High: ${orb_h:.2f} / Low: ${orb_l:.2f}"

    for i in range(len(session_bars)):
        bar = session_bars.iloc[i]
        c = float(bar['Close'])
        prev_c = float(session_bars.iloc[i-1]['Close']) if i > 0 else float(orb_c['Close'].values[0])
        ema, sma = float(bar['EMA_200']), float(bar['SMA_50']) if not pd.isna(bar['SMA_50']) else c
        rsi = float(bar['RSI']) if not pd.isna(bar['RSI']) else 50

        is_long = (c > orb_h) and (prev_c <= orb_h) and (c > ema) and (c > sma) and (45 <= rsi <= 75)
        is_short = (c < orb_l) and (prev_c >= orb_l) and (c < ema) and (c < sma) and (25 <= rsi <= 55)

        if is_long or is_short:
            r1, s1 = float(bar['R1']), float(bar['S1'])
            sl = orb_l if is_long else orb_h
            risk = (c - sl) if is_long else (sl - c)
            if risk <= 0: continue
            tp = c + (1.3 * risk) if is_long else c - (1.3 * risk)

            blocked = False
            if is_long and not pd.isna(r1) and (c < r1 < tp): blocked = True
            if is_short and not pd.isna(s1) and (tp < s1 < c): blocked = True

            if not blocked:
                signal_type = "LONG" if is_long else "SHORT"
                entry_p = c
                sl_p = sl
                tp_p = tp
                risk_pct = (risk / c) * 100
                tp_pct = risk_pct * 1.3
                status_str = f"🟢 {signal_type} ATTIVO" if i == len(session_bars)-1 else f"🔵 {signal_type} PASSATO"
                monitor_str = f"Segnale scattato a ${entry_p:.2f} (Target: ${tp_p:.2f})"
                break
            else:
                status_str = "❌ BLOCCATO"
                monitor_str = f"Ostacolato da R1/S1"

    # Se non c'è segnale, calcoliamo una previsione vicina
    if signal_type == "NONE":
        dist_long = orb_h - curr_p
        dist_short = curr_p - orb_l
        if curr_p > orb_h:
            monitor_str = f"Sopra ORB High (${orb_h:.2f}), in attesa filtri EMA/RSI"
        elif curr_p < orb_l:
            monitor_str = f"Sotto ORB Low (${orb_l:.2f}), in attesa filtri EMA/RSI"
        else:
            monitor_str = f"Manca ${dist_long:.2f} al breakout Long | Manca ${dist_short:.2f} al breakout Short"

    usa_results[symbol] = {
        "name": name,
        "signal": signal_type,
        "entry": entry_p if entry_p > 0 else curr_p,
        "sl": sl_p,
        "tp": tp_p,
        "risk_pct": risk_pct if risk_pct > 0 else 0.50,
        "tp_pct": tp_pct if tp_pct > 0 else 0.65,
        "status": status_str
    }

    usa_table_rows.append({
        "Asset": name,
        "Ticker": symbol,
        "Prezzo": f"${curr_p:.2f}",
        "Stato Segnale": status_str,
        "Previsione / Monitoraggio": monitor_str
    })

st.dataframe(pd.DataFrame(usa_table_rows), use_container_width=True)

# --- CONVERTITORE FINECO AUTOMATICO (USA) ---
st.divider()
st.subheader("🧮 Convertitore Prezzi Fineco (USA)")

sel_usa = st.radio("Seleziona Asset:", options=list(usa_assets.values()), format_func=lambda x: f"{[k for k,v in usa_assets.items() if v==x][0]} ({x})", horizontal=True)
res_u = usa_results.get(sel_usa, {"signal": "NONE", "risk_pct": 0.50, "tp_pct": 0.65})

col_f1, col_f2 = st.columns(2)
with col_f1:
    fineco_val = st.number_input(f"Inserisci Prezzo Reale Fineco ({sel_usa}):", value=5000.0 if sel_usa=="SPY" else 100.0, step=0.1, format="%.2f")

with col_f2:
    detected_dir = res_u['signal'] if res_u['signal'] in ["LONG", "SHORT"] else "LONG"
    if res_u['signal'] in ["LONG", "SHORT"]:
        st.success(f"Direzione rilevata automaticamente dal segnale: **{detected_dir}**")
    else:
        st.warning("Nessun segnale attivo. Direzione predefinita per simulazione:")
        detected_dir = st.radio("Seleziona verso:", ["LONG", "SHORT"], horizontal=True)

r_pct = res_u['risk_pct']
t_pct = res_u['tp_pct']

if detected_dir == "LONG":
    f_tp = fineco_val * (1 + (t_pct / 100))
    f_sl = fineco_val * (1 - (r_pct / 100))
else:
    f_tp = fineco_val * (1 - (t_pct / 100))
    f_sl = fineco_val * (1 + (r_pct / 100))

m1, m2, m3 = st.columns(3)
m1.metric("Prezzo Fineco", f"{fineco_val:.2f}")
m2.metric("🎯 TARGET PROFIT", f"{f_tp:.2f}", delta=f"{t_pct:.2f}%")
m3.metric("🔴 STOP LOSS", f"{f_sl:.2f}", delta=f"-{r_pct:.2f}%", delta_color="inverse")


# =============================================================================
# 🇪🇺 SEZIONE 2: MERCATI EUROPEI (SWING 3X + PREVISIONE)
# =============================================================================
st.divider()
st.header("🇪🇺 Mercati Europei — Strategy Swing Settimanale ETF 3X & Monitoraggio")

def check_eu_swing(ticker, fee_rate, isin):
    df = yf.download(ticker, period="1y", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.reset_index()
    
    daily_ret = df['Close'].pct_change()
    lev_ret = (daily_ret * 3.0) - (fee_rate / 252)
    df['lev_price'] = (1 + lev_ret.fillna(0)).cumprod() * 100
    
    df_w = df.set_index('Date').resample('W').agg({'lev_price': 'last'}).dropna().reset_index()
    df_w['sma20'] = df_w['lev_price'].rolling(window=20).mean()
    
    delta = df_w['lev_price'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df_w['rsi'] = 100 - (100 / (1 + (gain / loss)))
    df_w['is_down'] = df_w['lev_price'].diff() < 0
    
    last_row = df_w.iloc[-2]
    close = float(last_row['lev_price'])
    sma20 = float(last_row['sma20'])
    rsi = float(last_row['rsi'])
    is_down = bool(last_row['is_down'])
    date_str = str(last_row['Date'])[:10]
    
    is_signal = (close < sma20) and (rsi < 35) and is_down
    
    # Previsione / Monitoraggio
    conds_met = sum([close < sma20, rsi < 35, is_down])
    if is_signal:
        forecast = "Segnale Long attivo sulla chiusura settimanale."
    else:
        missing = []
        if not (close < sma20): missing.append(f"Prezzo ({close:.1f}) sopra SMA20 ({sma20:.1f})")
        if not (rsi < 35): missing.append(f"RSI ({rsi:.1f}) sopra 35")
        if not is_down: missing.append("Candela non ribassista")
        forecast = f"Mancano requisiti: {', '.join(missing)}"

    return {
        "date_str": date_str, "close": close, "sma20": sma20, "rsi": rsi, 
        "is_down": is_down, "is_signal": is_signal, "forecast": forecast, "isin": isin
    }

eu_configs = [
    {"Name": "CAC 40 3X", "Ticker": "^FCHI", "Fee": 0.0075, "ISIN": "IE00B7V0GB87"},
    {"Name": "DAX 40 3X", "Ticker": "^GDAXI", "Fee": 0.015, "ISIN": "N/D"}
]

eu_table_rows = []
for cfg in eu_configs:
    try:
        res = check_eu_swing(cfg["Ticker"], cfg["Fee"], cfg["ISIN"])
        status = "🟢 SEGNALE LONG 3X" if res["is_signal"] else "⚖️ In Attesa / Monitoraggio"
        
        eu_table_rows.append({
            "Asset": cfg["Name"],
            "Ticker": cfg["Ticker"],
            "Data Candela W": res["date_str"],
            "Prezzo 3x": f"{res['close']:.2f}",
            "SMA20 W": f"{res['sma20']:.2f}",
            "RSI(14) W": f"{res['rsi']:.2f}",
            "Stato Segnale": status,
            "Previsione / Condizioni Mancanti": res["forecast"]
        })
    except Exception as ex:
        eu_table_rows.append({
            "Asset": cfg["Name"], "Ticker": cfg["Ticker"], "Data Candela W": "-", 
            "Prezzo 3x": "-", "SMA20 W": "-", "RSI(14) W": "-", "Stato Segnale": "⚠️ Errore", "Previsione / Condizioni Mancanti": str(ex)
        })

st.dataframe(pd.DataFrame(eu_table_rows), use_container_width=True)
