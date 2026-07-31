# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests

# ==========================================
# 1. CONFIGURAZIONE TELEGRAM & PAGINA
# ==========================================
TELEGRAM_TOKEN = "INSERISCI_QUI_IL_TUO_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_QUI_IL_TUO_CHAT_ID"

def invia_notifica_telegram(messaggio):
    if TELEGRAM_TOKEN == "INSERISCI_QUI_IL_TUO_TOKEN":
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

st.set_page_config(page_title="Nasdaq ORB Engine - Knockout Fineco", layout="wide", page_icon="📈")
st.markdown("<h1 style='text-align: center; color: #2E8B57;'>📈 NASDAQ 100 - OPENING RANGE BREAKOUT (FHB)</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Strategia Meccanica a Bassa Frequenza per Certificati Knock Out</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. DOWNLOAD DATI NASDAQ (QQQ o NQ=F)
# ==========================================
@st.cache_data(ttl=3600)
def carica_dati_nasdaq():
    try:
        # Usiamo QQQ (ETF Nasdaq 100) o NQ=F per dati orari puliti
        df = yf.download("QQQ", period="6mo", interval="1h", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or 'Close' not in df.columns: 
            return pd.DataFrame()
        return df.dropna()
    except Exception:
        return pd.DataFrame()

df_base = carica_dati_nasdaq()

if df_base.empty:
    st.error("⚠️ Impossibile scaricare i dati da Yahoo Finance. Riprova tra poco.")
    st.stop()

# ==========================================
# 3. PANNELLO LATERALE: MONEY MANAGEMENT
# ==========================================
st.sidebar.markdown("### ⚖️ Parametri di Rischio Knockout")
capitale_iniziale = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
costo_attrito = st.sidebar.number_input("Costi Fissi (Comm. + Spread €):", value=12.0, step=1.0)
 moltiplicatore_tp = st.sidebar.slider("Rapporto Take Profit / Rischio (RR):", 1.0, 3.0, 1.5, 0.5)

# ==========================================
# 4. MOTORE DI BACKTEST MECCANICO (FHB)
# ==========================================
def esegui_backtest_fhb(df, capitale, attrito, rr_target):
    equity = [capitale]
    trade_log = []
    
    # Assicuriamoci che l'indice sia datetime
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
        
    # Raggruppiamo per giorno solare per identificare la prima candela della sessione
    df['Date'] = df.index.date
    giorni = df['Date'].unique()
    
    capitale_corrente = capitale
    
    for giorno in giorni:
        df_giorno = df[df['Date'] == giorno]
        if len(df_giorno) < 3: 
            continue # Serve una seduta con abbastanza candele orarie
            
        # La prima candela della giornata fa da "Range di Apertura"
        candela_apertura = df_giorno.iloc[0]
        high_or = candela_apertura['High']
        low_or = candela_apertura['Low']
        ampiezza_or = high_or - low_or
        
        if ampiezza_or <= 0:
            continue
            
        # Analizziamo le candele successive nella stessa giornata per il breakout
        resto_giornata = df_giorno.iloc[1:]
        
        pos_aperta = False
        for idx, row in resto_giornata.iterrows():
            if pos_aperta:
                break # Un solo trade al giorno per evitare overtrading
                
            h = row['High']
            l = row['Low']
            c = row['Close']
            
            # Condizione LONG: Prezzo rompe il massimo della prima ora
            if h >= high_or:
                pos_aperta = True
                entry_price = high_or
                stop_loss = low_or # Rischio = ampiezza della prima candela
                rischio_pt = entry_price - stop_loss
                tp_price = entry_price + (rischio_pt * rr_target)
                tp_pt = tp_price - entry_price
                
                # Valutiamo l'esito nelle ore rimanenti della giornata
                esito = "LOSS"
                pnl_netto = -rischio_pt - attrito
                
                # Semplificazione simulazione intraday successiva
                future_subset = resto_giornata.loc[idx:]
                for _, sub_row in future_subset.iterrows():
                    if sub_row['Low'] <= stop_loss:
                        esito = "LOSS"
                        pnl_netto = -rischio_pt - attrito
                        break
                    elif sub_row['High'] >= tp_price:
                        esito = "WIN"
                        pnl_netto = tp_pt - attrito
                        break
                
                capitale_corrente += pnl_netto
                equity.append(capitale_corrente)
                trade_log.append({"Data": str(giorno), "Direzione": "LONG", "Esito": esito, "PnL": pnl_netto, "Equity": capitale_corrente})
                
            # Condizione SHORT: Prezzo rompe il minimo della prima ora
            elif l <= low_or:
                pos_aperta = True
                entry_price = low_or
                stop_loss = high_or
                rischio_pt = stop_loss - entry_price
                tp_price = entry_price - (rischio_pt * rr_target)
                tp_pt = entry_price - tp_price
                
                esito = "LOSS"
                pnl_netto = -rischio_pt - attrito
                
                future_subset = resto_giornata.loc[idx:]
                for _, sub_row in future_subset.iterrows():
                    if sub_row['High'] >= stop_loss:
                        esito = "LOSS"
                        pnl_netto = -rischio_pt - attrito
                        break
                    elif sub_row['Low'] <= tp_price:
                        esito = "WIN"
                        pnl_netto = tp_pt - attrito
                        break
                
                capitale_corrente += pnl_netto
                equity.append(capitale_corrente)
                trade_log.append({"Data": str(giorno), "Direzione": "SHORT", "Esito": esito, "PnL": pnl_netto, "Equity": capitale_corrente})
                
    return pd.DataFrame(trade_log), equity

df_trades, curva_equity = esegui_backtest_fhb(df_base, capitale_iniziale, costo_attrito, moltiplicatore_tp)

# ==========================================
# 5. DASHBOARD RISULTATI
# ==========================================
if not df_trades.empty:
    tot_trade = len(df_trades)
    vinti = len(df_trades[df_trades['Esito'] == "WIN"])
    win_rate = (vinti / tot_trade) * 100 if tot_trade > 0 else 0
    
    lordo_profitti = df_trades[df_trades['PnL'] > 0]['PnL'].sum()
    lordo_perdite = abs(df_trades[df_trades['PnL'] < 0]['PnL'].sum())
    profit_factor = lordo_profitti / lordo_perdite if lordo_perdite > 0 else 0.0
    
    arr_eq = np.array(curva_equity)
    peak = np.maximum.accumulate(arr_eq)
    max_dd = np.max(peak - arr_eq) if len(arr_eq) > 0 else 0
    
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Trade Totali (6 Mesi)", tot_trade)
    c2.metric("Win Rate Meccanico", f"{win_rate:.1f}%")
    c3.metric("Profit Factor", f"{profit_factor:.2f}")
    c4.metric("Max Drawdown", f"-{max_dd:.2f} €")
    c5.metric("Profitto Netto", f"{curva_equity[-1] - capitale_iniziale:.2f} €")
    
    st.markdown("### 📈 Curva di Equity - Strategia Meccanica ORB")
    st.line_chart(curva_equity)
    
    with st.expander("🔍 Dettaglio Storico Operazioni"):
        st.dataframe(df_trades)
else:
    st.warning("⚠️ Nessun trade generato con i parametri attuali.")
