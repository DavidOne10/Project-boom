# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Knockout Trading AI", layout="wide")

st.title("🤖 V-Alpha PRO | Random Forest AI (Anti-IA & Knockout Edition)")
st.markdown("---")

# --- 1. MOTORE ADDESTRAMENTO RANDOM FOREST (DAILY) ---
@st.cache_data(ttl=3600)
def addestra_modello_ia(ticker):
    try:
        dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)
            
        if dati.empty or len(dati) < 100:
            return None, None, None

        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()
        dati['Target'] = np.where(dati['Close'].shift(-1) > dati['Close'], 1, 0)

        delta = dati['Close'].diff()
        guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = guadagno / perdita
        dati['RSI'] = 100 - (100 / (1 + rs))

        std20 = dati['Close'].rolling(window=20).std()
        dati['Banda_Alta'] = dati['Media_20'] + (std20 * 2)
        dati['Banda_Bassa'] = dati['Media_20'] - (std20 * 2)
        dati['Dist_Media20'] = (dati['Close'] - dati['Media_20']) / dati['Media_20']
        dati['Dist_Media50'] = (dati['Close'] - dati['Media_50']) / dati['Media_50']
        dati['Larghezza_Bande'] = (dati['Banda_Alta'] - dati['Banda_Bassa']) / dati['Media_20']

        k = dati['Close'].ewm(span=12, adjust=False).mean()
        d = dati['Close'].ewm(span=26, adjust=False).mean()
        dati['MACD'] = k - d
        dati['MACD_Signal'] = dati['MACD'].ewm(span=9, adjust=False).mean()
        dati['MACD_Hist'] = dati['MACD'] - dati['MACD_Signal']

        variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                     'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

        dati_training = dati.dropna(subset=variabili + ['Target'])
        
        X = dati_training[variabili]
        y = dati_training['Target']

        modello = RandomForestClassifier(n_estimators=150, min_samples_leaf=5, random_state=42)
        modello.fit(X, y)

        ultimo_dato_fresco = dati[variabili].iloc[-1:]

        return modello, ultimo_dato_fresco, dati

    except Exception as e:
        st.error(f"Errore nell'addestramento IA: {e}")
        return None, None, None

# --- 2. SCARICAMENTO DATI LIVE INTRADAY ---
@st.cache_data(ttl=60)
def carica_dati_intraday():
    for ticker in ["CL=F", "BZ=F", "USOIL=X"]:
        try:
            df = yf.download(ticker, period="2d", interval="5m", auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty and 'Close' in df.columns:
                return df, ticker
        except Exception:
            continue
    return None, None

df_5m, ticker_attivo = carica_dati_intraday()

if df_5m is None:
    st.error("⚠️ Connessione ai dati di mercato non disponibile.")
    st.stop()

modello_rf, ultimo_dato_ia, df_storico_completo = addestra_modello_ia(ticker_attivo)

if modello_rf is None:
    st.error("⚠️ Errore nell'inizializzazione del modello IA.")
    st.stop()

# PREDIZIONE IA PURA LIVE
probabilita = modello_rf.predict_proba(ultimo_dato_ia)[0]
predizione_ia = modello_rf.predict(ultimo_dato_ia)[0] # 1 = LONG, 0 = SHORT
confidenza_ia = probabilita[predizione_ia] * 100

prezzo_live = round(float(df_5m['Close'].iloc[-1]), 3)
oggi = df_5m.index[-1].date()
df_today = df_5m[df_5m.index.date == oggi]
if df_today.empty:
    df_today = df_5m.tail(50)

high_mattina = float(df_today['High'].max())
low_mattina = float(df_today['Low'].min())
range_totale = high_mattina - low_mattina
supporto_operativo = round(low_mattina + (range_totale * 0.2), 3)
resistenza_operativa = round(high_mattina - (range_totale * 0.2), 3)
atr = round(range_totale / 5, 3)

# --- PANNELLO LATERALE ---
st.sidebar.header("💰 Gestione Capitale & Costi")
capitale_utente = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
costo_attrito = st.sidebar.number_input("Costi Fissi (Comm. + Spread €):", value=12.0, step=1.0)
soglia_filtro = st.sidebar.slider("Soglia Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)

st.sidebar.markdown("---")
st.sidebar.header("🔄 Modalità Operativa")
modalita_inversa = st.sidebar.checkbox("Attiva 'Anti-IA Mode' (Inverti Segnali)", value=True)

if confidenza_ia < 55:
    pct_rischio = 0.01
elif confidenza_ia < 65:
    pct_rischio = 0.02
else:
    pct_rischio = 0.03

euro_da_rischiare = capitale_utente * pct_rischio

# --- LOGICA LIVE: SEGNALE IA vs OPERAZIONE EFFETTIVA ---
segnalo_ia_str = "LONG" if predizione_ia == 1 else "SHORT"

# Se la modalità inversa è attiva, eseguiamo l'opposto di quello che dice l'IA
if modalita_inversa:
    operazione_eseguita = 0 if predizione_ia == 1 else 1
else:
    operazione_eseguita = predizione_ia

direzione_effettiva_str = "LONG" if operazione_eseguita == 1 else "SHORT"
stato_inversa_str = "ATTIVA 🔄" if modalita_inversa else "DISATTIVA"

st.markdown(f"**Asset Monitorato:** `{ticker_attivo}` | Modalità Inversa: **{stato_inversa_str}**")
col1, col2, col3 = st.columns(3)
col1.metric("Supporto V-Alpha", supporto_operativo)
col2.metric("Prezzo WTI Live", prezzo_live)
col3.metric("Resistenza V-Alpha", resistenza_operativa)

st.markdown("---")
st.subheader(f"🔮 Segnale Live (IA Pura: {segnalo_ia_str} ➡️ Eseguiamo: {direzione_effettiva_str})")

c_pred1, c_pred2 = st.columns(2)
with c_pred1:
    if direzione_effettiva_str == "LONG":
        st.success(f"OPERAZIONE A MERCATO: LONG 🟢 (L'IA diceva {segnalo_ia_str})")
    else:
        st.error(f"OPERAZIONE A MERCATO: SHORT 🔴 (L'IA diceva {segnalo_ia_str})")

with c_pred2:
    st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")
    st.metric("Rischio Profilo", f"{pct_rischio*100:.0f}% ({euro_da_rischiare:.2f} €)")

# ==========================================
# 3. BACKTEST STORICO CON SEPARAZIONE IA / OPERAZIONE
# ==========================================
st.markdown("---")
st.subheader("📊 Backtest Storico (Ultimi 6 Mesi con Costi Fissi)")

def esegui_backtest_rf(dati_completi, modello, capitale_iniziale, attrito, conf_minima, inverti):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    test_df = dati_completi.tail(126).copy()
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    for i in range(1, len(test_df)):
        riga_corr = test_df.iloc[i-1:i][variabili]
        if riga_corr.isna().any().any():
            continue
            
        prob = modello.predict_proba(riga_corr)[0]
        pred_ia_nativo = modello.predict(riga_corr)[0]
        conf = prob[pred_ia_nativo] * 100
        
        if conf < conf_minima:
            continue
            
        # Determiniamo l'operazione effettiva in base al flag di inversione
        if inverti:
            op_eseguita = 0 if pred_ia_nativo == 1 else 1
        else:
            op_eseguita = pred_ia_nativo
            
        data_trade = test_df.index[i].date()
        open_oggi = test_df['Open'].iloc[i]
        high_oggi = test_df['High'].iloc[i]
        low_oggi = test_df['Low'].iloc[i]
        
        atr_giornaliero = high_oggi - low_oggi
        if atr_giornaliero <= 0:
            continue
            
        if op_eseguita == 1: # LONG Effettivo
            rischio = atr_giornaliero * 0.5
            reward = atr_giornaliero * 1.0
            if high_oggi >= open_oggi + reward:
                pnl = reward - attrito
                esito = "WIN"
            else:
                pnl = -rischio - attrito
                esito = "LOSS"
        else: # SHORT Effettivo
            rischio = atr_giornaliero * 0.5
            reward = atr_giornaliero * 1.0
            if low_oggi <= open_oggi - reward:
                pnl = reward - attrito
                esito = "WIN"
            else:
                pnl = -rischio - attrito
                esito = "LOSS"
                
        capitale_corrente += pnl
        equity.append(capitale_corrente)
        trade_log.append({
            "Data": str(data_trade), 
            "Segnale IA": "LONG" if pred_ia_nativo==1 else "SHORT",
            "Eseguito": "LONG" if op_eseguita==1 else "SHORT", 
            "Esito": esito, 
            "PnL": round(pnl, 2), 
            "Equity": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

if df_storico_completo is not None:
    df_res_bt, eq_bt = esegui_backtest_rf(df_storico_completo, modello_rf, capitale_utente, costo_attrito, soglia_filtro, modalita_inversa)
    
    if not df_res_bt.empty:
        tot_t = len(df_res_bt)
        vinti_t = len(df_res_bt[df_res_bt['Esito'] == "WIN"])
        wr_t = (vinti_t / tot_t) * 100
        net_profit = eq_bt[-1] - capitale_utente
        
        bt_c1, bt_c2, bt_c3, bt_c4 = st.columns(4)
        bt_c1.metric("Trade Effettuati", tot_t)
        bt_c2.metric("Win Rate Storico", f"{wr_t:.1f}%")
        bt_c3.metric("Profitto Netto", f"{net_profit:.2f} €")
        bt_c4.metric("Capitale Finale", f"{eq_bt[-1]:.2f} €")
        
        st.line_chart(eq_bt)
        
        with st.expander("🔍 Vedi Storico Operazioni Backtest"):
            st.dataframe(df_res_bt)
    else:
        st.warning("⚠️ Nessun trade generato con la soglia di confidenza attuale.")
