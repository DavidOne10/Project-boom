import os
import requests
import streamlit as st
import pandas as pd
import numpy as np
import pytz
import yfinance as yf
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

st.set_page_config(page_title="Dashboard Trading — USA ORB & UE Swing 3X", page_icon="📈", layout="wide")

st.title("📈 Trading Dashboard — USA Real-Time & UE Swing 3X")

# =============================================================================
# CREDENZIALI & SETUP
# =============================================================================
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY") or st.secrets.get("API_KEY", "")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY") or st.secrets.get("SECRET_KEY", "")
ALPACA_BASE_URL = "https://data.alpaca.markets/v2"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN") or st.secrets.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("CHAT_ID") or st.secrets.get("TELEGRAM_CHAT_ID", "")

# Connessione Alpaca Trading (se credenziali presenti)
trading_client = None
if ALPACA_API_KEY and ALPACA_SECRET_KEY:
    try:
        trading_client = TradingClient(ALPACA_API_KEY, ALPACA_SECRET_KEY, paper=True)
        acc = trading_client.get_account()
        st.sidebar.success(f"Connesso ad Alpaca Paper!\nSaldo: ${float(acc.equity):,.2f}")
    except Exception as e:
        st.sidebar.error(f"Errore Alpaca: {e}")

# =============================================================================
# 🇺🇸 SEZIONE 1: MERCATI USA (CHECKER ORB 15M CON FILTRO R1/S1)
# =============================================================================
st.header("🇺🇸 Mercati USA — Breakout ORB 15m Real-Time")

def get_alpaca_bars_df(symbol, timeframe="15Min", limit=500):
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return pd.DataFrame()

    headers = {"APCA-API-KEY-ID": ALPACA_API_KEY, "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY}
    url = f"{ALPACA_BASE_URL}/stocks/bars?symbols={symbol}&timeframe={timeframe}&limit={limit}&feed=iex"
    
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

usa_results_dict = {}
usa_table_rows = []

for asset_name, symbol in usa_assets.items():
    df = get_alpaca_bars_df(symbol, timeframe="15Min", limit=500)
    
    if df.empty:
        usa_table_rows.append({"Asset": asset_name, "Ticker": symbol, "Prezzo": "-", "Stato Segnale": "⚠️ No Dati", "Dettagli": "Impossibile scaricare candele da Alpaca"})
        continue

    df.index = df.index.tz_convert("America/New_York")
    df['date'] = df.index.date

    # --- CALCOLO PIVOT POINTS (S/R giorno precedente) ---
    daily = df.groupby('date').agg({'High': 'max', 'Low': 'min', 'Close': 'last'})
    daily['pivot'] = (daily['High'] + daily['Low'] + daily['Close']) / 3
    daily['R1'] = (2 * daily['pivot']) - daily['Low']
    daily['S1'] = (2 * daily['pivot']) - daily['High']
    df = df.merge(daily[['R1', 'S1']].shift(1), left_on='date', right_index=True, how='left')

    # --- INDICATORI ---
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    df['SMA_50'] = df['Close'].rolling(window=50).mean()
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['RSI'] = 100 - (100 / (1 + (gain / loss)))

    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14, min_periods=1).mean()

    today_date = df.index.date.max()
    today_bars = df[df.index.date == today_date]

    if today_bars.empty:
        usa_table_rows.append({"Asset": asset_name, "Ticker": symbol, "Prezzo": "-", "Stato Segnale": "🕒 In Attesa Sessione", "Dettagli": "Nessuna candela per la data odierna"})
        continue

    orb_candle = today_bars[(today_bars.index.hour == 9) & (today_bars.index.minute == 30)]
    if orb_candle.empty:
        last_c = float(today_bars.iloc[-1]['Close'])
        usa_table_rows.append({"Asset": asset_name, "Ticker": symbol, "Prezzo": f"${last_c:.2f}", "Stato Segnale": "🕒 In Attesa ORB", "Dettagli": "Candela delle 09:30 EST non ancora chiusa"})
        continue

    orb_high, orb_low = float(orb_candle['High'].values[0]), float(orb_candle['Low'].values[0])
    orb_range, atr = orb_high - orb_low, float(orb_candle['ATR'].values[0])
    last_c = float(today_bars.iloc[-1]['Close'])

    if pd.isna(atr) or orb_range < (0.25 * atr):
        usa_table_rows.append({"Asset": asset_name, "Ticker": symbol, "Prezzo": f"${last_c:.2f}", "Stato Segnale": "⚠️ ATR Scarto", "Dettagli": f"ORB Range (${orb_range:.2f}) < 25% ATR (${0.25*atr:.2f})"})
        continue

    session_bars = today_bars[(today_bars.index.hour > 9) | ((today_bars.index.hour == 9) & (today_bars.index.minute >= 45))]
    if session_bars.empty:
        usa_table_rows.append({"Asset": asset_name, "Ticker": symbol, "Prezzo": f"${last_c:.2f}", "Stato Segnale": "🕒 In Attesa 09:45", "Dettagli": "Sessione operativa non ancora avviata"})
        continue

    first_signal_bar_idx, signal_type = None, None
    block_reason = None

    for i in range(len(session_bars)):
        bar = session_bars.iloc[i]
        c = float(bar['Close'])
        prev_c = float(session_bars.iloc[i-1]['Close']) if i > 0 else float(orb_candle['Close'].values[0])
        ema, sma = float(bar['EMA_200']), float(bar['SMA_50']) if not pd.isna(bar['SMA_50']) else c
        rsi = float(bar['RSI']) if not pd.isna(bar['RSI']) else 50

        is_long = (c > orb_high) and (prev_c <= orb_high) and (c > ema) and (c > sma) and (45 <= rsi <= 75)
        is_short = (c < orb_low) and (prev_c >= orb_low) and (c < ema) and (c < sma) and (25 <= rsi <= 55)

        if is_long or is_short:
            r1, s1 = float(bar['R1']), float(bar['S1'])
            sl = orb_low if is_long else orb_high
            risk = (c - sl) if is_long else (sl - c)
            
            if risk <= 0: continue
            tp = c + (1.3 * risk) if is_long else c - (1.3 * risk)

            blocked = False
            if is_long and not pd.isna(r1) and (c < r1 < tp): blocked = True
            if is_short and not pd.isna(s1) and (tp < s1 < c): blocked = True

            if not blocked:
                first_signal_bar_idx = i
                signal_type = "LONG" if is_long else "SHORT"
                break
            else:
                block_reason = "R1 (Resistenza)" if is_long else "S1 (Supporto)"

    # Costruzione stato
    last_bar = session_bars.iloc[-1]
    curr_price = float(last_bar['Close'])
    last_time_str = session_bars.index[-1].strftime('%H:%M')

    if first_signal_bar_idx is not None:
        sig_bar = session_bars.iloc[first_signal_bar_idx]
        sig_time_str = session_bars.index[first_signal_bar_idx].strftime('%H:%M')
        entry_p = float(sig_bar['Close'])
        sl_p = orb_low if signal_type == "LONG" else orb_high
        risk_v = abs(entry_p - sl_p)
        tp_p = entry_p + (1.3 * risk_v) if signal_type == "LONG" else entry_p - (1.3 * risk_v)
        
        risk_pct = (risk_v / entry_p) * 100
        tp_pct = risk_pct * 1.3

        is_current = (first_signal_bar_idx == len(session_bars) - 1)
        status_label = f"🟢 {signal_type} ATTIVO!" if is_current else f"🔵 {signal_type} PASSATO ({sig_time_str})"
        detail_label = f"Ingresso: ${entry_p:.2f} | TP (1.3x): ${tp_p:.2f} (+{tp_pct:.2f}%) | SL: ${sl_p:.2f} (-{risk_pct:.2f}%)"

        usa_results_dict[symbol] = {
            "name": asset_name,
            "signal": signal_type,
            "is_current": is_current,
            "entry": entry_p,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pct": risk_pct,
            "tp_pct": tp_pct,
            "status_str": status_label
        }
    elif block_reason:
        status_label = "❌ BLOCCATO"
        detail_label = f"Breakout presente ma ostacolato da {block_reason}"
        usa_results_dict[symbol] = {"name": asset_name, "signal": "BLOCKED", "status_str": status_label, "risk_pct": 0, "tp_pct": 0}
    else:
        status_label = "⚖️ In Range"
        detail_label = f"Nessun breakout | RSI: {last_bar['RSI']:.1f} | ORB Range: ${orb_range:.2f}"
        usa_results_dict[symbol] = {"name": asset_name, "signal": "NONE", "status_str": status_label, "risk_pct": 0, "tp_pct": 0}

    usa_table_rows.append({
        "Asset": asset_name,
        "Ticker": symbol,
        "Prezzo ($)": f"${curr_price:.2f}",
        "Stato Segnale": status_label,
        "Dettagli Operativi": detail_label
    })

st.dataframe(pd.DataFrame(usa_table_rows), use_container_width=True)

# --- CONVERTITORE FINECO & GESTIONE ALPACA ---
st.divider()
st.subheader("🎯 Gestione Ordini Alpaca & Convertitore Fineco (USA)")

selected_symbol = st.radio(
    "Seleziona l'asset USA da gestire:",
    options=list(usa_assets.values()),
    format_func=lambda x: f"{[k for k,v in usa_assets.items() if v==x][0]} ({x})",
    horizontal=True
)

if selected_symbol in usa_results_dict:
    info = usa_results_dict[selected_symbol]
    c_col1, c_col2 = st.columns(2)
    
    with c_col1:
        st.info(f"**Asset:** {info['name']}\n\n**Stato:** {info['status_str']}")

    with c_col2:
        if trading_client and info['signal'] in ["LONG", "SHORT"]:
            positions = [p for p in trading_client.get_all_positions() if p.symbol == selected_symbol]
            if positions:
                st.warning(f"⚠️ Posizione su {selected_symbol} già aperta su Alpaca.")
                if st.button(f"🔴 Chiudi Posizione {selected_symbol}", type="primary"):
                    trading_client.close_position(selected_symbol)
                    st.rerun()
            else:
                if st.button(f"🚀 Ordine Paper Alpaca ({selected_symbol})", type="primary"):
                    side_val = OrderSide.BUY if info['signal'] == "LONG" else OrderSide.SELL
                    order_req = MarketOrderRequest(
                        symbol=selected_symbol,
                        qty=10,
                        side=side_val,
                        time_in_force=TimeInForce.DAY,
                        order_class=OrderClass.BRACKET,
                        take_profit=TakeProfitRequest(limit_price=round(info['tp'], 2)),
                        stop_loss=StopLossRequest(stop_price=round(info['sl'], 2))
                    )
                    trading_client.submit_order(order_req)
                    st.balloons()
                    st.success("✅ Ordine inviato con successo!")
                    st.rerun()
        else:
            st.caption("Nessun ordine automatico disponibile al momento.")

    st.markdown(f"#### 🧮 Convertitore Fineco per **{selected_symbol}**")
    default_prices = {"SPY": 5800.0, "USO": 70.50, "GLD": 2500.0}
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fineco_in = st.number_input(
            f"Prezzo effettivo dello strumento su Fineco ({selected_symbol}):",
            value=default_prices.get(selected_symbol, 100.0),
            step=0.1,
            format="%.2f"
        )
    with col_f2:
        if info['signal'] == "LONG":
            st.success("Direzione: **⬆️ LONG**")
            curr_dir = "LONG"
        elif info['signal'] == "SHORT":
            st.error("Direzione: **⬇️ SHORT**")
            curr_dir = "SHORT"
        else:
            st.warning("⚠️ Nessun segnale attivo. Selezione manuale:")
            curr_dir = st.radio("Direzione per simulazione:", ["LONG", "SHORT"], horizontal=True)

    calc_risk = info['risk_pct'] if info['risk_pct'] > 0 else 0.50
    calc_tp = info['tp_pct'] if info['tp_pct'] > 0 else calc_risk * 1.3

    if curr_dir == "LONG":
        f_tp = fineco_in * (1 + (calc_tp / 100))
        f_sl = fineco_in * (1 - (calc_risk / 100))
    else:
        f_tp = fineco_in * (1 - (calc_tp / 100))
        f_sl = fineco_in * (1 + (calc_risk / 100))

    m1, m2, m3 = st.columns(3)
    m1.metric("Prezzo Ingresso Fineco", f"{fineco_in:.2f}")
    m2.metric("🎯 TARGET PROFIT FINECO (1.3x)", f"{f_tp:.2f}", delta=f"{calc_tp:.2f}%")
    m3.metric("🔴 STOP LOSS FINECO", f"{f_sl:.2f}", delta=f"-{calc_risk:.2f}%", delta_color="inverse")

# =============================================================================
# 🇪🇺 SEZIONE 2: MERCATI EUROPEI (CHECKER SWING SETTIMANALE 3X)
# =============================================================================
st.divider()
st.header("🇪🇺 Mercati Europei — Strategy Swing Settimanale ETF 3X")

def check_eu_swing_strategy(ticker, fee_rate, isin_code=None):
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
    stop_loss = close * 0.95
    take_profit = close * 1.09
    
    return {
        "date_str": date_str,
        "close_3x": close,
        "sma20": sma20,
        "rsi": rsi,
        "is_down": is_down,
        "is_signal": is_signal,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "isin": isin_code
    }

eu_configs = [
    {"Name": "CAC 40 3X", "Ticker": "^FCHI", "Fee": 0.0075, "ISIN": "IE00B7V0GB87"},
    {"Name": "DAX 40 3X", "Ticker": "^GDAXI", "Fee": 0.015, "ISIN": "N/D"}
]

eu_table_rows = []

for cfg in eu_configs:
    try:
        res = check_eu_swing_strategy(cfg["Ticker"], cfg["Fee"], cfg["ISIN"])
        
        status_txt = "🟢 SEGNALE LONG 3X" if res["is_signal"] else "⚖️ In Range (Nessun Segnale)"
        det_txt = (
            f"SL -5%: `{res['stop_loss']:.2f}` | TP +9%: `{res['take_profit']:.2f}` | ISIN: `{res['isin']}`"
            if res["is_signal"] else
            f"SMA20: {res['sma20']:.2f} | RSI: {res['rsi']:.2f} | Chiusura Negativa: {'Sì' if res['is_down'] else 'No'}"
        )
        
        eu_table_rows.append({
            "Asset": cfg["Name"],
            "Ticker": cfg["Ticker"],
            "Data Chiusura Settimana": res["date_str"],
            "Prezzo Simula 3x": f"{res['close_3x']:.2f}",
            "SMA20 Settimanale": f"{res['sma20']:.2f}",
            "RSI(14) Settimanale": f"{res['rsi']:.2f}",
            "Chiusura Neg.": "Sì" if res["is_down"] else "No",
            "Stato Segnale": status_txt,
            "Parametri Operativi": det_txt
        })
    except Exception as ex:
        eu_table_rows.append({
            "Asset": cfg["Name"],
            "Ticker": cfg["Ticker"],
            "Data Chiusura Settimana": "-",
            "Prezzo Simula 3x": "-",
            "SMA20 Settimanale": "-",
            "RSI(14) Settimanale": "-",
            "Chiusura Neg.": "-",
            "Stato Segnale": "⚠️ Errore Calcolo",
            "Parametri Operativi": str(ex)
        })

st.dataframe(pd.DataFrame(eu_table_rows), use_container_width=True)
