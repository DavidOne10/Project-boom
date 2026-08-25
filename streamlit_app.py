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
    st.write("---")
    st.subheader("🇮🇹 Livelli Knock-Out Fineco (S&P 500 Indice)")

    # Prezzo stimato (SPY x 10)
    estimated_fineco = round(last_price * 10.0, 1)

    # Input diretto del prezzo Fineco
    fineco_price_input = st.number_input(
        "Inserisci la quotazione ATTUALE dell'S&P 500 su Fineco:",
        value=estimated_fineco,
        step=0.5,
        format="%.1f",
        help="Digita qui il prezzo che vedi su Fineco. L'app ricalcolerà istantaneamente il KO e le distanze esatte."
    )

    # Calcolo automatico del Delta (Scarto)
    delta_offset = fineco_price_input - (last_price * 10.0)

    # Ricalcolo automatico dei livelli KO e TP con il Delta
    sl_fineco = (sl_price * 10.0) + delta_offset
    tp_fineco = (tp_price * 10.0) + delta_offset

    # Distanze dinamiche in punti
    dist_sl_pts = abs(fineco_price_input - sl_fineco)
    dist_tp_pts = abs(tp_fineco - fineco_price_input)

    # Visualizzazione dinamica e chiara
    col_f1, col_f2, col_f3 = st.columns(3)
    col_f1.metric("Prezzo Fineco", f"{fineco_price_input:.1f} pts")
    col_f2.metric("Distanza KO (Rischio)", f"{dist_sl_pts:.1f} pts")
    col_f3.metric("Distanza TP (Target)", f"{dist_tp_pts:.1f} pts")

    st.code(
        f"🔴 BARRIERA KO (Stop Loss):     {sl_fineco:.1f} pts  [Distanza: -{dist_sl_pts:.1f} pts]\n"
        f"🟢 TARGET PROFIT (Take Profit): {tp_fineco:.1f} pts  [Distanza: +{dist_tp_pts:.1f} pts]\n"
        f"ℹ️ Delta rilevato (Fineco vs SPY): {delta_offset:+.1f} pts"
    )


    # Pulsante Invio Ordine
    if has_open_position:
        st.info("⚠️ Posizione già aperta su Alpaca. Impossibile inviare nuovi ordini.")
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
            except Exception as ex:
                st.error(f"Errore nell'invio dell'ordine: {ex}")
else:
    st.info(f"⏳ **Nessun segnale al momento** ({current_time_str}). Prezzo all'interno del range neutro.")

if st.button("🔄 Aggiorna Dati"):
    st.rerun()
