import os
import streamlit as st
import pandas as pd
import numpy as np
import pytz
import yfinance as yf
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

st.set_page_config(page_title="Trading Dashboard ORB 15m", page_icon="📈", layout="wide")

st.title("📈 Dashboard ORB 15m — USA & UE")

# --- CREDENZIALI ALPACA ---
API_KEY = st.secrets.get("API_KEY", "PKSRPGHTEKXA6KIP4HV6AOEZ5Z")
SECRET_KEY = st.secrets.get("SECRET_KEY", "7ZdgT6TyiEW5wkxSJqqpPHJL5qnxmJTMpoTk8PQ6cihw")

@st.cache_resource
def get_clients():
    trading = TradingClient(API_KEY, SECRET_KEY, paper=True)
    data = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    return trading, data

try:
    trading_client, data_client = get_clients()
    account = trading_client.get_account()
    st.sidebar.success(f"Connesso ad Alpaca Paper!\nSaldo: ${float(account.equity):,.2f}")
except Exception as e:
    st.sidebar.error(f"Errore Alpaca: {e}")

# =============================================================================
# ENGINE INDICATORI
# =============================================================================
def process_indicators(df_raw, tz_str):
    df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp']).dt.tz_convert(tz_str)
    df_raw['Date'] = df_raw['timestamp'].dt.date
    
    df_15m = df_raw.groupby('Date').resample('15min', on='timestamp').agg({
        'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
    }).dropna().reset_index()
    
    daily = df_15m.groupby('Date').agg({'high': 'max', 'low': 'min', 'close': 'last'})
    daily['pivot'] = (daily['high'] + daily['low'] + daily['close']) / 3
    daily['R1'] = (2 * daily['pivot']) - daily['low']
    daily['S1'] = (2 * daily['pivot']) - daily['high']
    
    df_15m = df_15m.merge(daily[['R1', 'S1']].shift(1), left_on='Date', right_index=True, how='left')
    
    df_15m['EMA_200'] = df_15m['close'].ewm(span=200, adjust=False).mean()
    df_15m['SMA_50'] = df_15m['close'].rolling(window=50).mean()
    
    delta = df_15m['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df_15m['RSI'] = 100 - (100 / (1 + (gain / loss)))
    
    hl = df_15m['high'] - df_15m['low']
    hc = np.abs(df_15m['high'] - df_15m['close'].shift())
    lc = np.abs(df_15m['low'] - df_15m['close'].shift())
    df_15m['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14, min_periods=1).mean()
    
    df_15m.set_index('timestamp', inplace=True)
    return df_15m

# =============================================================================
# 🇺🇸 SEZIONE USA - TABELLA PANORAMICA
# =============================================================================
st.header("🇺🇸 Mercati USA — Panoramica Segnali")

usa_tickers = {
    "SPY": "S&P 500 (SPY)",
    "USO": "Petrolio WTI (USO)",
    "GLD": "Oro (GLD)"
}

now_est = pd.Timestamp.now(tz=pytz.timezone('US/Eastern'))

usa_data_dict = {}
usa_table_rows = []

for ticker, name in usa_tickers.items():
    try:
        req = StockBarsRequest(
            symbol_or_symbols=ticker,
            timeframe=TimeFrame.Minute,
            start=now_est - timedelta(days=5)
        )
        res = data_client.get_stock_bars(req)
        df_usa = process_indicators(res.df.reset_index(), 'US/Eastern')
        today_usa = df_usa[df_usa['Date'] == now_est.date()].copy()
        
        if today_usa.empty:
            usa_table_rows.append({"Asset": name, "Ticker": ticker, "Prezzo ($)": "-", "Stato Segnale": "⚠️ No Dati Oggi", "Dettagli": "Nessuna candela disponibile"})
            continue
            
        orb_c = today_usa[(today_usa.index.hour == 9) & (today_usa.index.minute == 30)]
        if orb_c.empty:
            usa_table_rows.append({"Asset": name, "Ticker": ticker, "Prezzo ($)": "-", "Stato Segnale": "🕒 In Attesa ORB", "Dettagli": "Candela 09:30 EST non chiusa"})
            continue

        orb_h, orb_l = float(orb_c['high'].iloc[0]), float(orb_c['low'].iloc[0])
        orb_r, atr_v = orb_h - orb_l, float(orb_c['ATR'].iloc[0])
        
        last_b = today_usa.iloc[-1]
        c_price = float(last_b['close'])
        ema_200 = float(last_b['EMA_200'])
        sma_50 = float(last_b['SMA_50']) if not pd.isna(last_b['SMA_50']) else c_price
        rsi_val = float(last_b['RSI']) if not pd.isna(last_b['RSI']) else 50.0
        r1_v, s1_v = float(last_b['R1']), float(last_b['S1'])
        
        prev_c = float(today_usa.iloc[-2]['close']) if len(today_usa) > 1 else orb_h
        is_long = (c_price > orb_h) and (prev_c <= orb_h) and (c_price > ema_200) and (c_price > sma_50) and (45 <= rsi_val <= 75)
        is_short = (c_price < orb_l) and (prev_c >= orb_l) and (c_price < ema_200) and (c_price < sma_50) and (25 <= rsi_val <= 55)

        sig_type = "NONE"
        status_str = "⚖️ In Range"
        detail_str = f"RSI: {rsi_val:.1f} | EMA200: ${ema_200:.2f}"
        sl_p, tp_p = 0.0, 0.0
        risk_pct, tp_pct = 0.0, 0.0

        if orb_r < (0.25 * atr_v):
            status_str = "⚠️ ATR Scarto"
            detail_str = f"Range orario stretto (${orb_r:.2f} < ${0.25*atr_v:.2f})"
        elif is_long or is_short:
            sig_type = "LONG" if is_long else "SHORT"
            sl_p = round(orb_l if is_long else orb_h, 2)
            risk_val = abs(c_price - sl_p)
            tp_p = round(c_price + (1.3 * risk_val) if is_long else c_price - (1.3 * risk_val), 2)
            
            risk_pct = (risk_val / c_price) * 100
            tp_pct = risk_pct * 1.3

            blocked = False
            if is_long and not pd.isna(r1_v) and (c_price < r1_v < tp_p): blocked = True
            if is_short and not pd.isna(s1_v) and (tp_p < s1_v < c_price): blocked = True

            if blocked:
                status_str = "❌ BLOCCATO"
                detail_str = "Ostacolo statico R1/S1 tra prezzo e TP"
                sig_type = "BLOCKED"
            else:
                status_str = "🟢 LONG" if is_long else "🔴 SHORT"
                detail_str = f"Entry: ${c_price:.2f} | TP (1.3x): ${tp_p:.2f} | SL: ${sl_p:.2f}"

        usa_table_rows.append({
            "Asset": name,
            "Ticker": ticker,
            "Prezzo ($)": f"{c_price:.2f}",
            "Stato Segnale": status_str,
            "Dettagli": detail_str
        })

        usa_data_dict[ticker] = {
            "name": name,
            "price": c_price,
            "signal": sig_type,
            "status_str": status_str,
            "sl": sl_p,
            "tp": tp_p,
            "risk_pct": risk_pct,
            "tp_pct": tp_pct,
        }

    except Exception as ex:
        usa_table_rows.append({"Asset": name, "Ticker": ticker, "Prezzo ($)": "-", "Stato Segnale": "⚠️ Errore", "Dettagli": str(ex)})

st.dataframe(pd.DataFrame(usa_table_rows), use_container_width=True)

# =============================================================================
# SELEZIONE PALLINI (RADIO) & CONVERTITORE FINECO / ALPACA
# =============================================================================
st.divider()
st.subheader("🎯 Seleziona Asset per Convertitore Fineco & Esecuzione Ordine")

selected_ticker = st.radio(
    "Scegli l'asset da gestire con la spunta:",
    options=list(usa_tickers.keys()),
    format_func=lambda x: f"{usa_tickers[x]} ({x})",
    horizontal=True
)

if selected_ticker in usa_data_dict:
    asset_info = usa_data_dict[selected_ticker]
    
    col_alp1, col_alp2 = st.columns(2)
    with col_alp1:
        st.info(f"**Asset Selezionato:** {asset_info['name']}\n\n**Stato Segnale Alpaca:** {asset_info['status_str']}")
    
    with col_alp2:
        if asset_info['signal'] in ["LONG", "SHORT"]:
            pos = [p for p in trading_client.get_all_positions() if p.symbol == selected_ticker]
            if len(pos) > 0:
                st.warning(f"⚠️ Posizione su {selected_ticker} già aperta su Alpaca.")
                if st.button(f"🔴 Chiudi Posizione {selected_ticker} su Alpaca", type="primary"):
                    trading_client.close_position(selected_ticker)
                    st.rerun()
            else:
                if st.button(f"🚀 Invia Ordine Simulato su Alpaca per {selected_ticker}", type="primary"):
                    side = OrderSide.BUY if asset_info['signal'] == "LONG" else OrderSide.SELL
                    order_data = MarketOrderRequest(
                        symbol=selected_ticker,
                        qty=10,
                        side=side,
                        time_in_force=TimeInForce.DAY,
                        order_class=OrderClass.BRACKET,
                        take_profit=TakeProfitRequest(limit_price=asset_info['tp']),
                        stop_loss=StopLossRequest(stop_price=asset_info['sl'])
                    )
                    trading_client.submit_order(order_data)
                    st.balloons()
                    st.success("✅ Ordine inviato ad Alpaca Paper!")
                    st.rerun()
        else:
            st.caption("Nessun ordine simulato Alpaca disponibile al momento.")

    st.markdown(f"#### 🧮 Convertitore Fineco per {selected_ticker}")
    
    default_fineco_prices = {"SPY": 5800.0, "USO": 70.50, "GLD": 2500.0}
    
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        fineco_price_input = st.number_input(
            f"Inserisci il Prezzo Reale di **{selected_ticker}** su Fineco:",
            value=default_fineco_prices.get(selected_ticker, 100.0),
            step=0.1,
            format="%.2f"
        )
    
    with col_f2:
        if asset_info['signal'] == "LONG":
            st.success("Direzione rilevata in automatico: **⬆️ LONG**")
            current_dir = "LONG"
        elif asset_info['signal'] == "SHORT":
            st.error("Direzione rilevata in automatico: **⬇️ SHORT**")
            current_dir = "SHORT"
        else:
            st.warning("⚠️ Nessun segnale attivo su Alpaca. Selezione manuale per calcolo:")
            current_dir = st.radio("Direzione da simulare su Fineco:", ["LONG", "SHORT"], horizontal=True)

    calc_risk_pct = asset_info['risk_pct'] if asset_info['risk_pct'] > 0 else 0.50
    calc_tp_pct = calc_risk_pct * 1.3

    if current_dir == "LONG":
        fineco_tp = fineco_price_input * (1 + (calc_tp_pct / 100))
        fineco_sl = fineco_price_input * (1 - (calc_risk_pct / 100))
    else:
        fineco_tp = fineco_price_input * (1 - (calc_tp_pct / 100))
        fineco_sl = fineco_price_input * (1 + (calc_risk_pct / 100))

    dist_tp_pts = abs(fineco_tp - fineco_price_input)
    dist_sl_pts = abs(fineco_price_input - fineco_sl)

    res_c1, res_c2, res_c3 = st.columns(3)
    res_c1.metric("Prezzo Ingresso Fineco", f"{fineco_price_input:.2f}")
    res_c2.metric("🎯 TARGET PROFIT FINECO (1.3x)", f"{fineco_tp:.2f}", delta=f"{'+' if current_dir=='LONG' else '-'}{dist_tp_pts:.2f} pts ({calc_tp_pct:.2f}%)")
    res_c3.metric("🔴 BARRIERA KO / STOP FINECO", f"{fineco_sl:.2f}", delta=f"{'-' if current_dir=='LONG' else '+'}{dist_sl_pts:.2f} pts ({calc_risk_pct:.2f}%)", delta_color="inverse")

# =============================================================================
# 🇪🇺 SEZIONE 2: MERCATI UE (RISOLTO PROBLEMA MULTIINDEX YFINANCE)
# =============================================================================
st.divider()
st.header("🇪🇺 Mercati Europei — Monitoraggio & Diagnostica")

eu_assets = [
    {"Asset": "CAC 40", "Ticker": "^FCHI", "Hour": 9, "Min": 0, "TZ": "Europe/Paris"},
    {"Asset": "DAX 40", "Ticker": "^GDAXI", "Hour": 9, "Min": 0, "TZ": "Europe/Berlin"},
    {"Asset": "FTSE MIB", "Ticker": "FTSEMIB.MI", "Hour": 9, "Min": 0, "TZ": "Europe/Rome"},
]

results_eu = []
for item in eu_assets:
    try:
        ticker_obj = yf.Ticker(item["Ticker"])
        df_raw = ticker_obj.history(period="5d", interval="15m")
        
        if df_raw.empty:
            results_eu.append({"Asset": item["Asset"], "Ticker": item["Ticker"], "Stato Segnale": "⚠️ No Dati", "Dettagli": "Nessun dato scaricato"})
            continue
            
        df_raw = df_raw.reset_index()
        time_col = 'Datetime' if 'Datetime' in df_raw.columns else 'Date'
        df_raw.rename(columns={time_col: 'timestamp', 'Open':'open', 'High':'high', 'Low':'low', 'Close':'close', 'Volume':'volume'}, inplace=True)
        
        df_15m = process_indicators(df_raw, item["TZ"])
        today_date = df_15m.index.date.max()
        today_b = df_15m[df_15m.index.date == today_date]
        
        orb_b = today_b[(today_b.index.hour == item["Hour"]) & (today_b.index.minute == item["Min"])]
        if orb_b.empty:
            results_eu.append({"Asset": item["Asset"], "Ticker": item["Ticker"], "Stato Segnale": "🕒 In Attesa ORB", "Dettagli": "Candela 09:00 in formazione"})
            continue
            
        orb_h, orb_l = float(orb_b['high'].iloc[0]), float(orb_b['low'].iloc[0])
        orb_r, atr_v = orb_h - orb_l, float(orb_b['ATR'].iloc[0])
        
        last_b = today_b.iloc[-1]
        c_price, c_ema = float(last_b['close']), float(last_b['EMA_200'])
        c_sma = float(last_b['SMA_50']) if not pd.isna(last_b['SMA_50']) else c_price
        c_rsi = float(last_b['RSI']) if not pd.isna(last_b['RSI']) else 50.0
        
        is_long = (c_price > orb_h) and (c_price > c_ema) and (c_price > c_sma) and (45 <= c_rsi <= 75)
        is_short = (c_price < orb_l) and (c_price < c_ema) and (c_price < c_sma) and (25 <= c_rsi <= 55)
        
        if orb_r < (0.25 * atr_v):
            st_text, reason = "⚠️ ATR Scarto", f"Range stretto ({orb_r:.1f})"
        elif is_long:
            tp = c_price + (1.3 * (c_price - orb_l))
            st_text, reason = "🟢 LONG", f"Breakout sopra {orb_h:.1f} | TP 1.3x: {tp:.1f}"
        elif is_short:
            tp = c_price - (1.3 * (orb_h - c_price))
            st_text, reason = "🔴 SHORT", f"Breakdown sotto {orb_l:.1f} | TP 1.3x: {tp:.1f}"
        else:
            st_text, reason = "⚖️ In Range", f"Prezzo: {c_price:.1f} | RSI: {c_rsi:.1f}"

        results_eu.append({"Asset": item["Asset"], "Ticker": item["Ticker"], "Stato Segnale": st_text, "Dettagli": reason})
    except Exception as ex:
        results_eu.append({"Asset": item["Asset"], "Ticker": item["Ticker"], "Stato Segnale": "⚠️ Errore", "Dettagli": str(ex)})

st.dataframe(pd.DataFrame(results_eu), use_container_width=True)
