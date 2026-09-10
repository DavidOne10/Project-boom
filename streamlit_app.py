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

st.set_page_config(page_title="Trading Bot USA & UE + Convertitore Fineco", page_icon="📈", layout="wide")

st.title("📈 Dashboard ORB 15m — USA, Convertitore Fineco & UE")

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
# FUNZIONE ENGINE INDICATORI
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
# 🇺🇸 SEZIONE 1: MERCATI USA (SPY, USO, GLD) — MONITOR & ALPACA ORDERS
# =============================================================================
st.header("🇺🇸 1. Mercati USA — Monitor & Esecuzione Simulazione Alpaca")

asset_usa_map = {"S&P 500 (SPY)": "SPY", "Petrolio WTI (USO)": "USO", "Oro (GLD)": "GLD"}
selected_usa_label = st.selectbox("Seleziona Asset USA da analizzare/operare:", list(asset_usa_map.keys()))
selected_usa_ticker = asset_usa_map[selected_usa_label]

now_est = pd.Timestamp.now(tz=pytz.timezone('US/Eastern'))

# Variabili condivise con il convertitore Fineco
active_signal = None  # "LONG", "SHORT", None
alpaca_risk_pct = 1.0 # Default %
alpaca_tp_pct = 1.3   # Default %

try:
    req = StockBarsRequest(
        symbol_or_symbols=selected_usa_ticker,
        timeframe=TimeFrame.Minute,
        start=now_est - timedelta(days=5)
    )
    res = data_client.get_stock_bars(req)
    df_usa = process_indicators(res.df.reset_index(), 'US/Eastern')
    
    today_usa = df_usa[df_usa['Date'] == now_est.date()].copy()
    
    if today_usa.empty:
        st.warning(f"⚠️ Dati per {selected_usa_ticker} di oggi non ancora disponibili.")
    else:
        orb_c = today_usa[(today_usa.index.hour == 9) & (today_usa.index.minute == 30)]
        if orb_c.empty:
            st.info("⏳ Candela ORB 15m (09:30 EST) non ancora chiusa.")
        else:
            orb_h, orb_l = float(orb_c['high'].iloc[0]), float(orb_c['low'].iloc[0])
            orb_r, atr_v = orb_h - orb_l, float(orb_c['ATR'].iloc[0])
            
            last_b = today_usa.iloc[-1]
            c_price = float(last_b['close'])
            ema_200 = float(last_b['EMA_200'])
            sma_50 = float(last_b['SMA_50']) if not pd.isna(last_b['SMA_50']) else c_price
            rsi_val = float(last_b['RSI']) if not pd.isna(last_b['RSI']) else 50.0
            r1_v, s1_v = float(last_b['R1']), float(last_b['S1'])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Prezzo Alpaca", f"${c_price:.2f}")
            c2.metric("EMA200 / SMA50", f"${ema_200:.2f} / ${sma_50:.2f}")
            c3.metric("RSI (14)", f"{rsi_val:.1f}")
            c4.metric("Range ORB vs ATR", f"${orb_r:.2f} (ATR: ${atr_v:.2f})")

            prev_c = float(today_usa.iloc[-2]['close']) if len(today_usa) > 1 else orb_h
            is_long = (c_price > orb_h) and (prev_c <= orb_h) and (c_price > ema_200) and (c_price > sma_50) and (45 <= rsi_val <= 75)
            is_short = (c_price < orb_l) and (prev_c >= orb_l) and (c_price < ema_200) and (c_price < sma_50) and (25 <= rsi_val <= 55)

            if orb_r < (0.25 * atr_v):
                st.warning("⚠️ Sessione scartata: Volatilità ORB troppo bassa.")
            elif is_long or is_short:
                active_signal = "LONG" if is_long else "SHORT"
                sl_p = round(orb_l if is_long else orb_h, 2)
                risk_val = abs(c_price - sl_p)
                tp_p = round(c_price + (1.3 * risk_val) if is_long else c_price - (1.3 * risk_val), 2)

                # Calcolo percentuali per Fineco
                alpaca_risk_pct = (risk_val / c_price) * 100
                alpaca_tp_pct = alpaca_risk_pct * 1.3

                blocked = False
                if is_long and not pd.isna(r1_v) and (c_price < r1_v < tp_p): blocked = True
                if is_short and not pd.isna(s1_v) and (tp_p < s1_v < c_price): blocked = True

                if blocked:
                    st.error("❌ SEGNALE BLOCCATO: Presenza di un ostacolo statico (R1/S1).")
                    active_signal = None
                else:
                    st.success(f"🟢 **SEGNALE VALIDATO {selected_usa_ticker}: {active_signal}** | Entry: `${c_price:.2f}` | TP (1.3x): `${tp_p:.2f}` | SL: `${sl_p:.2f}`")

                    # CONTROLLO E PULSANTE ALPACA
                    pos = [p for p in trading_client.get_all_positions() if p.symbol == selected_usa_ticker]
                    if len(pos) > 0:
                        st.warning(f"⚠️ Posizione su {selected_usa_ticker} già aperta su Alpaca Paper.")
                        if st.button(f"🔴 CHIUDI POSIZIONE {selected_usa_ticker} SU ALPACA", type="primary"):
                            trading_client.close_position(selected_usa_ticker)
                            st.rerun()
                    else:
                        if st.button(f"🚀 INVIA ORDINE SIMULATO SU ALPACA PER {selected_usa_ticker}", type="primary"):
                            side = OrderSide.BUY if is_long else OrderSide.SELL
                            order_data = MarketOrderRequest(
                                symbol=selected_usa_ticker,
                                qty=10,
                                side=side,
                                time_in_force=TimeInForce.DAY,
                                order_class=OrderClass.BRACKET,
                                take_profit=TakeProfitRequest(limit_price=tp_p),
                                stop_loss=StopLossRequest(stop_price=sl_p)
                            )
                            trading_client.submit_order(order_data)
                            st.balloons()
                            st.success("✅ Ordine inviato ad Alpaca!")
                            st.rerun()
            else:
                st.info(f"⏳ Nessun segnale attivo su {selected_usa_ticker}.")

except Exception as ex_usa:
    st.error(f"Errore Sezione USA: {ex_usa}")

# =============================================================================
# 🧮 SEZIONE CONVERTITORE FINECO (INSERIMENTO PREZZO REALE)
# =============================================================================
st.divider()
st.header(f"🧮 2. Convertitore Segnale per Operatività Reale Fineco ({selected_usa_label})")

st.write("Inserisci il prezzo dell'asset che stai vedendo su Fineco. Il sistema applicherà la % di Stop Loss e Target (1.3x) rilevata dal segnale Alpaca.")

col_f1, col_f2, col_f3 = st.columns(3)

with col_f1:
    # Prezzo di default indicativo per Fineco a seconda dell'asset
    default_fineco = 5800.0 if "SPY" in selected_usa_ticker else (70.50 if "USO" in selected_usa_ticker else 2500.0)
    fineco_price_input = st.number_input(
        f"Prezzo Attuale {selected_usa_label} su Fineco:",
        value=default_fineco,
        step=0.1,
        format="%.2f"
    )

with col_f2:
    signal_dir = st.radio(
        "Direzione Operativa:",
        ["⬆️ LONG", "⬇️ SHORT"],
        index=0 if (active_signal == "LONG" or active_signal is None) else 1,
        horizontal=True
    )

with col_f3:
    risk_pct_input = st.number_input(
        "Rischio Stop Loss (%):",
        value=float(round(alpaca_risk_pct, 2)),
        step=0.05,
        format="%.2f",
        help="Calcolato automaticamente dallo Stop Loss del segnale Alpaca"
    )

# Calcolo Livelli Fineco
is_long_fineco = "LONG" in signal_dir
tp_pct_calculated = risk_pct_input * 1.3

if is_long_fineco:
    fineco_tp = fineco_price_input * (1 + (tp_pct_calculated / 100))
    fineco_sl = fineco_price_input * (1 - (risk_pct_input / 100))
else:
    fineco_tp = fineco_price_input * (1 - (tp_pct_calculated / 100))
    fineco_sl = fineco_price_input * (1 + (risk_pct_input / 100))

dist_tp_pts = abs(fineco_tp - fineco_price_input)
dist_sl_pts = abs(fineco_price_input - fineco_sl)

res_c1, res_c2, res_c3 = st.columns(3)
res_c1.metric("Prezzo Ingresso Fineco", f"{fineco_price_input:.2f}")
res_c2.metric("🎯 TARGET PROFIT FINECO (1.3x)", f"{fineco_tp:.2f}", delta=f"{'+' if is_long_fineco else '-'}{dist_tp_pts:.2f} pts ({tp_pct_calculated:.2f}%)")
res_c3.metric("🔴 BARRIERA KO / STOP FINECO", f"{fineco_sl:.2f}", delta=f"{'-' if is_long_fineco else '+'}{dist_sl_pts:.2f} pts ({risk_pct_input:.2f}%)", delta_color="inverse")

st.code(
    f"📊 ORDINE REAL TIME FINECO — {selected_usa_label} ({'LONG' if is_long_fineco else 'SHORT'})\n"
    f"----------------------------------------------------------------------\n"
    f"▸ Prezzo di Ingresso Inserito: {fineco_price_input:.2f}\n"
    f"🎯 TAKE PROFIT (1.3x):         {fineco_tp:.2f}   (Distanza: {dist_tp_pts:.2f} punti / +{tp_pct_calculated:.2f}%)\n"
    f"🔴 BARRIERA KO / STOP LOSS:    {fineco_sl:.2f}   (Distanza: {dist_sl_pts:.2f} punti / -{risk_pct_input:.2f}%)\n"
    f"⚖️ Risk / Reward Ratio:         1 : 1.30"
)

# =============================================================================
# 🇪🇺 SEZIONE 3: MERCATI UE (CAC 40, DAX, FTSE MIB) — SOLO MONITORAGGIO
# =============================================================================
st.divider()
st.header("🇪🇺 3. Mercati Europei — Solo Monitoraggio & Diagnostica")

eu_assets = [
    {"Asset": "CAC 40", "Ticker": "^FCHI", "Hour": 9, "Min": 0, "TZ": "Europe/Paris"},
    {"Asset": "DAX 40", "Ticker": "^GDAXI", "Hour": 9, "Min": 0, "TZ": "Europe/Berlin"},
    {"Asset": "FTSE MIB", "Ticker": "FTSEMIB.MI", "Hour": 9, "Min": 0, "TZ": "Europe/Rome"},
]

results_eu = []
for item in eu_assets:
    try:
        df_raw = yf.download(item["Ticker"], period="5d", interval="15m", progress=False)
        if df_raw.empty:
            results_eu.append({"Asset": item["Asset"], "Stato": "⚠️ No Dati", "Dettaglio": "Nessun dato scaricato"})
            continue
            
        if isinstance(df_raw.columns, pd.MultiIndex):
            df_raw.columns = df_raw.columns.get_level_values(0)
        df_raw.index = df_raw.index.tz_convert(item["TZ"])
        df_raw.rename(columns={'Open':'open', 'High':'high', 'Low':'low', 'Close':'close', 'Volume':'volume'}, inplace=True)
        df_raw['timestamp'] = df_raw.index
        
        df_15m = process_indicators(df_raw, item["TZ"])
        today_date = df_15m.index.date.max()
        today_b = df_15m[df_15m.index.date == today_date]
        
        orb_b = today_b[(today_b.index.hour == item["Hour"]) & (today_b.index.minute == item["Min"])]
        if orb_b.empty:
            results_eu.append({"Asset": item["Asset"], "Stato": "🕒 In Attesa ORB", "Dettaglio": "Candela 09:00 in formazione"})
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

        results_eu.append({"Asset": item["Asset"], "Stato": st_text, "Dettaglio": reason})
    except Exception as ex:
        results_eu.append({"Asset": item["Asset"], "Stato": "⚠️ Errore", "Dettaglio": str(ex)})

st.dataframe(pd.DataFrame(results_eu), use_container_width=True)
