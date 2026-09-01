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

# Configurazione pagina
st.set_page_config(page_title="Trading Bot & Dashboard Diagnostica", page_icon="📈", layout="wide")

st.title("📈 Dashboard Trading & Monitor Diagnostico")

# --- CREDENZIALI API ALPACA ---
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
    st.sidebar.success(f"Connesso ad Alpaca! Saldo: ${float(account.equity):,.2f}")
except Exception as e:
    st.sidebar.error(f"Errore connessione Alpaca: {e}")

# =============================================================================
# 1. MONITOR & ESECUZIONE ORDINI ALPACA (SPY)
# =============================================================================
st.header("⚡ Strategia S&P 500 Intraday (Alpaca Direct)")

symbol = "SPY"
now_est = pd.Timestamp.now(tz=pytz.timezone('US/Eastern'))
current_time_str = now_est.strftime('%H:%M EST')

try:
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
        st.warning("⚠️ Dati SPY di oggi non ancora sufficienti per l'analisi.")
    else:
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
        else:
            orb_high = orb['high'].max()
            orb_low = orb['low'].min()
            last_bar = df_today.iloc[-1]
            last_price = last_bar['close']
            last_vwap = last_bar['VWAP']
            last_atr = last_bar['ATR']

            # Visualizzazione Dati Mercato
            col1, col2, col3 = st.columns(3)
            col1.metric("Prezzo Attuale SPY", f"${last_price:.2f}")
            col2.metric("VWAP", f"${last_vwap:.2f}")
            col3.metric("ATR 14", f"${last_atr:.2f}")

            # Logica Segnale
            is_long = last_price > orb_high and last_price > last_vwap
            is_short = last_price < orb_low and last_price < last_vwap

            positions = trading_client.get_all_positions()
            has_open_position = len(positions) > 0

            if is_long or is_short:
                direction_str = "LONG" if is_long else "SHORT"
                sl_price = round(orb_low if is_long else orb_high, 2)
                tp_price = round(last_price + (2.0 * last_atr) if is_long else last_price - (2.0 * last_atr), 2)
                side = OrderSide.BUY if is_long else OrderSide.SELL

                risk = abs(last_price - sl_price)
                reward = abs(tp_price - last_price)

                st.subheader(f"🟢 SEGNALE ATTIVO SPY: {direction_str}")
                
                if reward < risk:
                    st.warning(f"⚠️ **MM Warning**: Trade svantaggioso! Rischio: `${risk:.2f}` | Rendimento: `${reward:.2f}`")
                else:
                    st.success(f"✅ **MM OK**: Risk/Reward ottimale. Rischio: `${risk:.2f}` | Rendimento: `${reward:.2f}`")

                # Gestione Posizione e Pulsanti
                if has_open_position:
                    st.warning("⚠️ **Hai una posizione aperta su Alpaca.**")
                    if st.button("🔴 CHIUDI POSIZIONE ADESSO", type="primary", use_container_width=True):
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
                st.info(f"⏳ **Nessun segnale attivo su SPY** ({current_time_str}). Prezzo nel range neutro.")

except Exception as e_market:
    st.error(f"Errore durante l'analisi Alpaca: {e_market}")

# =============================================================================
# 2. TABELLA DIAGNOSTICA MULTI-ASSET (PERCHÉ NON CI SONO SEGNALI?)
# =============================================================================
st.divider()
st.header("🔍 Diagnostica Strategia ORB (Tutti gli Asset)")

def analyze_asset_status(sym, source, orb_start_hour, orb_start_min, tz_str):
    tz = pytz.timezone(tz_str)
    now = datetime.now(tz)
    
    try:
        if source == "ALPACA":
            req = StockBarsRequest(
                symbol_or_symbols=sym,
                timeframe=TimeFrame.Minute,
                start=now - timedelta(days=2)
            )
            res = data_client.get_stock_bars(req)
            df_raw = res.df.reset_index()
            df_raw['timestamp'] = pd.to_datetime(df_raw['timestamp']).dt.tz_convert(tz_str)
            df_raw['Date'] = df_raw['timestamp'].dt.date
            
            df_15m = df_raw.groupby('Date').resample('15min', on='timestamp').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'
            }).dropna().reset_index()
            df_15m.set_index('timestamp', inplace=True)
        else: # YFINANCE (CAC 40)
            df_15m = yf.download(sym, period="5d", interval="15m", progress=False)
            if df_15m.empty:
                return "⚠️ Errore Dati", "Impossibile scaricare le candele"
            if isinstance(df_15m.columns, pd.MultiIndex):
                df_15m.columns = df_15m.columns.get_level_values(0)
            df_15m.index = df_15m.index.tz_convert(tz_str)
            df_15m.rename(columns={'Open':'open', 'High':'high', 'Low':'low', 'Close':'close'}, inplace=True)

        # Indicatore EMA 200 e ATR
        df_15m['EMA_200'] = df_15m['close'].ewm(span=200, adjust=False).mean()
        hl = df_15m['high'] - df_15m['low']
        hc = np.abs(df_15m['high'] - df_15m['close'].shift())
        lc = np.abs(df_15m['low'] - df_15m['close'].shift())
        df_15m['ATR'] = pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(14).mean()

        today_date = df_15m.index.date.max()
        today_bars = df_15m[df_15m.index.date == today_date]
        
        orb_bar = today_bars[(today_bars.index.hour == orb_start_hour) & (today_bars.index.minute == orb_start_min)]
        
        if orb_bar.empty:
            return "🕒 In Attesa ORB", f"Candela {orb_start_hour:02d}:{orb_start_min:02d} non ancora disponibile"

        orb_h = float(orb_bar['high'].iloc[0])
        orb_l = float(orb_bar['low'].iloc[0])
        orb_r = orb_h - orb_l
        atr_val = float(orb_bar['ATR'].iloc[0])

        last_b = today_bars.iloc[-1]
        c_price = float(last_b['close'])
        c_ema = float(last_b['EMA_200'])

        if pd.isna(atr_val) or orb_r < (0.25 * atr_val):
            return "⚠️ Scartato da ATR", f"Range ORB stretto ({orb_r:.2f} < 25% ATR {atr_val:.2f})"
        elif c_price > orb_h and c_price <= c_ema:
            return "❌ Blocco EMA 200", f"Sopra Max ({orb_h:.2f}) ma SOTTO EMA200 ({c_ema:.2f})"
        elif c_price < orb_l and c_price >= c_ema:
            return "❌ Blocco EMA 200", f"Sotto Min ({orb_l:.2f}) ma SOPRA EMA200 ({c_ema:.2f})"
        elif c_price > orb_h and c_price > c_ema:
            return "🟢 SEGNALE LONG", f"Breakout confermato sopra {orb_h:.2f}"
        elif c_price < orb_l and c_price < c_ema:
            return "🔴 SEGNALE SHORT", f"Breakdown confermato sotto {orb_l:.2f}"
        else:
            return "⚖️ No Breakout", f"Prezzo ({c_price:.2f}) inside range [{orb_l:.2f} - {orb_h:.2f}]"

    except Exception as ex:
        return "⚠️ Errore Analisi", str(ex)

diag_assets = [
    {"Asset": "CAC 40", "Ticker": "^FCHI", "Source": "YFINANCE", "Hour": 9, "Min": 0, "TZ": "Europe/Paris"},
    {"Asset": "S&P 500 (SPY)", "Ticker": "SPY", "Source": "ALPACA", "Hour": 9, "Min": 30, "TZ": "America/New_York"},
    {"Asset": "Petrolio (USO)", "Ticker": "USO", "Source": "ALPACA", "Hour": 9, "Min": 30, "TZ": "America/New_York"},
    {"Asset": "Oro (GLD)", "Ticker": "GLD", "Source": "ALPACA", "Hour": 9, "Min": 30, "TZ": "America/New_York"},
]

results = []
for item in diag_assets:
    st_res, reason = analyze_asset_status(item["Ticker"], item["Source"], item["Hour"], item["Min"], item["TZ"])
    results.append({
        "Asset": item["Asset"],
        "Fonte": item["Source"],
        "Stato Strategy": st_res,
        "Diagnosi / Motivo": reason
    })

st.dataframe(pd.DataFrame(results), use_container_width=True)

if st.button("🔄 Aggiorna Diagnostica e Dati"):
    st.rerun()

# =============================================================================
# 3. CALCOLATORE LIVELLI FINECO (KNOCK-OUT)
# =============================================================================
st.divider()
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
    default_price = 5800.0 if "S&P" in asset_selected else (70.50 if "Petrolio" in asset_selected else 2500.0)
    fineco_price = st.number_input(
        "Prezzo Attuale su Fineco:",
        value=default_price,
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
is_long_fineco = "LONG" in direction

if is_long_fineco:
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

rr_ratio = (tp_pct_input / sl_pct_input) if sl_pct_input > 0 else 0.0

col_res1.metric("Prezzo Inserito", f"{fineco_price:.2f}")
col_res2.metric("🎯 TARGET PROFIT", f"{tp_fineco:.2f}", delta=f"{'+' if is_long_fineco else '-'}{dist_tp:.2f} pts")
col_res3.metric("🔴 BARRIERA KO (SL)", f"{sl_fineco:.2f}", delta=f"{'-' if is_long_fineco else '+'}{dist_sl:.2f} pts", delta_color="inverse")

st.code(
    f"📊 RIEPILOGO OPERATIVO FINECO ({asset_selected} - {direction})\n"
    f"--------------------------------------------------\n"
    f"🎯 Take Profit: {tp_fineco:.2f}  [Distanza: {dist_tp:.2f}]\n"
    f"🔴 Barriera KO:  {sl_fineco:.2f}  [Distanza: {dist_sl:.2f}]\n"
    f"⚖️ Risk/Reward:  1:{rr_ratio:.2f}"
)
