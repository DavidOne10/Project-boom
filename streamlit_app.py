import streamlit as st
import pandas as pd
import numpy as np
import pytz
from datetime import datetime, timedelta
from alpaca.trading.client import TradingClient
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

# Configurazione pagina
st.set_page_config(page_title="SP500 Bot Execution", page_icon="📈", layout="centered")

st.title("📈 SP500 Intraday Strategy")
st.caption("Dashboard di controllo e invio ordini su Alpaca")

# Credenziali API
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
    st.sidebar.success(f"Connesso! Saldo: ${float(account.equity):,.2f}")
except Exception as e:
    st.error(f"Errore connessione Alpaca: {e}")
    st.stop()

# Analisi Strategia
symbol = "SPY"
now_est = pd.Timestamp.now(tz=pytz.timezone('US/Eastern'))

current_time_str = now_est.strftime('%H:%M EST')

request_params = StockBarsRequest(
    symbol_or_symbols=symbol,
    timeframe=TimeFrame.Minute,
    start=now_est - timedelta(days=2)
)

bars = data_client.get_stock_bars(request_params)
df = bars.df.reset_index()
df['timestamp'] = pd.to_datetime(df['timestamp']).dt.tz_convert('US/Eastern')
df['Date'] = df['timestamp'].dt.date

df_5m = df.groupby('Date').resample('5min', on='timestamp').agg({
    'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
}).dropna().reset_index()

today = now_est.date()
df_today = df_5m[df_5m['Date'] == today].copy()

if df_today.empty or len(df_today) < 4:
    st.warning("⚠️ Dati di oggi non ancora sufficienti per l'analisi.")
    st.stop()

# Calcolo Indicatori
df_today['TP'] = (df_today['high'] + df_today['low'] + df_today['close']) / 3
df_today['PV'] = df_today['TP'] * df_today['volume']
df_today['VWAP'] = df_today['PV'].cumsum() / df_today['volume'].cumsum()

hl = df_today['high'] - df_today['low']
hc = np.abs(df_today['high'] - df_today['close'].shift())
lc = np.abs(df_today['low'] - df_today['close'].shift())
df_today['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

df_today.set_index('timestamp', inplace=True)
orb = df_today.between_time('09:30', '09:45')

if orb.empty:
    st.info("⏳ ORB 15m non ancora completato (attendi le 15:45 italiane).")
    st.stop()

orb_high = orb['high'].max()
orb_low = orb['low'].min()
last_bar = df_today.iloc[-1]
last_price = last_bar['close']
last_vwap = last_bar['VWAP']
last_atr = last_bar['ATR']

# Visualizzazione Dati Mercato
col1, col2, col3 = st.columns(3)
col1.metric("Prezzo Attuale", f"${last_price:.2f}")
col2.metric("VWAP", f"${last_vwap:.2f}")
col3.metric("ATR 14", f"${last_atr:.2f}")

st.divider()

# Logica Segnale
is_long = last_price > orb_high and last_price > last_vwap
is_short = last_price < orb_low and last_price < last_vwap

positions = trading_client.get_all_positions()
has_open_position = len(positions) > 0

if is_long or is_short:
    direction = "LONG" if is_long else "SHORT"
    sl_price = round(orb_low if is_long else orb_high, 2)
    tp_price = round(last_price + (2.0 * last_atr) if is_long else last_price - (2.0 * last_atr), 2)
    side = OrderSide.BUY if is_long else OrderSide.SELL

    risk = abs(last_price - sl_price)
    reward = abs(tp_price - last_price)

    st.subheader(f"🟢 SEGNALE ATTIVO: {direction}")
    
    # Valutazione Money Management
    if reward < risk:
        st.warning(f"⚠️ **MM Warning**: Trade svantaggioso! Rischio: `${risk:.2f}` | Rendimento: `${reward:.2f}`")
    else:
        st.success(f"✅ **MM OK**: Risk/Reward ottimale. Rischio: `${risk:.2f}` | Rendimento: `${reward:.2f}`")

    #     # 🇮🇹 SEZIONE FINECO AUTOMATIZZATA
    sst.divider()
st.subheader("🧮 Calcolatore Livelli Fineco (Knock-Out)")

# 1. Selezione Asset e Direzione
col_a, col_d = st.columns(2)
with col_a:
    asset_selected = st.selectbox(
        "Seleziona Asset:",
        ["S&P 500 (Indice)", "Petrolio WTI", "Oro (Gold)"]
    )

with col_d:
    direction = st.radio(
        "Direzione Operativa:",
        ["⬆️ LONG", "⬇️ SHORT"],
        horizontal=True
    )

# 2. Input Prezzo e Variazioni Percentuali
col_p, col_tp, col_sl = st.columns(3)

with col_p:
    fineco_price = st.number_input(
        "Prezzo Attuale su Fineco:",
        value=5800.0 if "S&P" in asset_selected else (70.50 if "Petrolio" in asset_selected else 2500.0),
        step=0.1,
        format="%.2f"
    )

with col_tp:
    tp_pct_input = st.number_input(
        "Variazione Target TP (%):",
        value=1.20,
        step=0.1,
        format="%.2f",
        help="Inserisci la percentuale (+) indicata nel messaggio Telegram"
    )

with col_sl:
    sl_pct_input = st.number_input(
        "Variazione Stop/KO (%):",
        value=1.00,
        step=0.1,
        format="%.2f",
        help="Inserisci la percentuale (-) indicata nel messaggio Telegram"
    )

# 3. Calcolo Automatico
is_long = "LONG" in direction

if is_long:
    tp_fineco = fineco_price * (1 + (tp_pct_input / 100))
    sl_fineco = fineco_price * (1 - (sl_pct_input / 100))
else:
    tp_fineco = fineco_price * (1 - (tp_pct_input / 100))
    sl_fineco = fineco_price * (1 + (sl_pct_input / 100))

dist_tp = abs(tp_fineco - fineco_price)
dist_sl = abs(fineco_price - sl_fineco)

# 4. Dashboard Risultati
st.markdown("---")
col_res1, col_res2, col_res3 = st.columns(3)

col_res1.metric("Prezzo Inserito", f"{fineco_price:.2f}")
col_res2.metric("🎯 TARGET PROFIT", f"{tp_fineco:.2f}", delta=f"{'+' if is_long else '-'}{dist_tp:.2f} pts")
col_res3.metric("🔴 BARRIERA KO (SL)", f"{sl_fineco:.2f}", delta=f"{'-' if is_long else '+'}{dist_sl:.2f} pts", delta_color="inverse")

st.code(
    f"📊 RIEPILOGO OPERATIVO FINECO ({asset_selected} - {direction})\n"
    f"--------------------------------------------------\n"
    f"🎯 Take Profit: {tp_fineco:.2f}  [Distanza: {dist_tp:.2f}]\n"
    f"🔴 Barriera KO:  {sl_fineco:.2f}  [Distanza: {dist_sl:.2f}]\n"
    f"⚖️ Risk/Reward:  1:{tp_pct_input/sl_pct_input:.2f}"
)



    #     # Gestione Posizione e Pulsanti
    if has_open_position:
        st.warning("⚠️ **Hai una posizione aperta su Alpaca.**")
        
        # Tasto per chiudere la posizione prima delle 22:00
        if st.button("🔴 CHIUDI POSIZIONE ADESSO (21:55)", type="primary", use_container_width=True):
            try:
                trading_client.close_all_positions(cancel_orders=True)
                st.success("✅ Posizione chiusa e ordini cancellati con successo!")
                st.rerun()
            except Exception as ex:
                st.error(f"Errore durante la chiusura: {ex}")
    else:
        if st.button("🚀 ESEGUI ORDINE BRACKET SU ALPACA", type="primary", use_container_width=True):
            try:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    qty=10,
                    side=side,
                    time_in_force=TimeInForce.DAY,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=tp_price),
                    stop_loss=StopLossRequest(stop_price=sl_price)
                )
                order = trading_client.submit_order(order_data)
                st.balloons()
                st.success(f"✅ Ordine inviato con successo! ID: {order.id}")
                st.rerun()
            except Exception as ex:
                st.error(f"Errore nell'invio dell'ordine: {ex}")

else:
    st.info(f"⏳ **Nessun segnale al momento** ({current_time_str}). Prezzo all'interno del range neutro.")

if st.button("🔄 Aggiorna Dati"):
    st.rerun()
