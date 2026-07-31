# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Daily Coherent Backtest", layout="wide")

st.title("🤖 V-Alpha PRO | Daily Coherent Backtest (Anti-IA & Costi Fissi)")
st.markdown("---")

# --- 1. MOTORE ADDESTRAMENTO RANDOM FOREST (DAILY COERENTE) ---
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
        
        # TARGET COERENTE: Domani Close > Oggi Close
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

# --- 2. SCARICAMENTO DATI ---
ticker_attivo = "CL=F" # WTI Crude Oil
df_storico_completo = addestra_modello_ia(ticker_attivo)[2]
modello_rf, ultimo_dato_ia, _ = addestra_modello_ia(ticker_attivo)

if modello_rf is None:
    st.error("⚠️ Errore nell'inizializzazione del modello IA.")
    st.stop()

# PREDIZIONE IA PURA LIVE
probabilita = modello_rf.predict_proba(ultimo_dato_ia)[0]
predizione_ia = modello_rf.predict(ultimo_dato_ia)[0]
confidenza_ia = probabilita[predizione_ia] * 100

prezzo_live = round(float(df_storico_completo['Close'].iloc[-1]), 3)

# --- PANNELLO LATERALE ---
st.sidebar.header("💰 Gestione Capitale & Costi")
capitale_utente = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
costo_attrito = st.sidebar.number_input("Costi Fissi (Comm. + Spread €):", value=12.0, step=1.0)
soglia_filtro = st.sidebar.slider("Soglia Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
dimensione_lotto = st.sidebar.number_input("Moltiplicatore Contratto (Barili/Unità):", value=10.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.header("🔄 Modalità Operativa")
modalita_inversa = st.sidebar.checkbox("Attiva 'Anti-IA Mode' (Inverti Segnali)", value=True)

segnalo_ia_str = "LONG" if predizione_ia == 1 else "SHORT"
operazione_eseguita = 0 if (predizione_ia == 1 and modalita_inversa) or (predizione_ia == 0 and not modalita_inversa) else 1
direzione_effettiva_str = "LONG" if operazione_eseguita == 1 else "SHORT"
stato_inversa_str = "ATTIVA 🔄" if modalita_inversa else "DISATTIVA"

st.markdown(f"**Asset Monitorato:** `{ticker_attivo}` | Modalità Inversa: **{stato_inversa_str}**")

col1, col2 = st.columns(2)
with col1:
    if direzione_effettiva_str == "LONG":
        st.success(f"SEGNALE LIVE: LONG 🟢 (IA diceva: {segnalo_ia_str})")
    else:
        st.error(f"SEGNALE LIVE: SHORT 🔴 (IA diceva: {segnalo_ia_str})")

with col2:
    st.metric("Prezzo WTI Odierno", prezzo_live)
    st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")

# ==========================================
# 3. BACKTEST STORICO COERENTE (CLOSE-TO-CLOSE)
# ==========================================
st.markdown("---")
st.subheader("📊 Backtest Storico Coerente (Ultimi 6 Mesi - Close to Close)")

def esegui_backtest_coerente(dati_completi, modello, capitale_iniziale, attrito, conf_minima, inverti, lotto):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    test_df = dati_completi.tail(126).copy()
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    for i in range(len(test_df) - 1):
        riga_corr = test_df.iloc[i:i+1][variabili]
        if riga_corr.isna().any().any():
            continue
            
        prob = modello.predict_proba(riga_corr)[0]
        pred_ia_nativo = modello.predict(riga_corr)[0]
        conf = prob[pred_ia_nativo] * 100
        
        if conf < conf_minima:
            continue
            
        # Logica Anti-IA
        if inverti:
            op_eseguita = 0 if pred_ia_nativo == 1 else 1
        else:
            op_eseguita = pred_ia_nativo
            
        data_trade = test_df.index[i].date()
        prezzo_entrata = test_df['Close'].iloc[i]
        prezzo_uscita = test_df['Close'].iloc[i+1]
        
        variazione_prezzo = prezzo_uscita - prezzo_entrata
        
        if op_eseguita == 1: # LONG
            pnl_lordo = variazione_prezzo * lotto
        else: # SHORT
            pnl_lordo = -variazione_prezzo * lotto
            
        pnl_netto = pnl_lordo - attrito
        capitale_corrente += pnl_netto
        equity.append(capitale_corrente)
        
        esito = "WIN" if pnl_netto > 0 else "LOSS"
        
        trade_log.append({
            "Data": str(data_trade),
            "IA": "LONG" if pred_ia_nativo == 1 else "SHORT",
            "Eseguito": "LONG" if op_eseguita == 1 else "SHORT",
            "Entrata": round(prezzo_entrata, 2),
            "Uscita": round(prezzo_uscita, 2),
            "Esito": esito,
            "PnL (€)": round(pnl_netto, 2),
            "Capitale (€)": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

if df_storico_completo is not None:
    df_res_bt, eq_bt = esegui_backtest_coerente(df_storico_completo, modello_rf, capitale_utente, costo_attrito, soglia_filtro, modalita_inversa, dimensione_lotto)
    
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
        
        with st.expander("🔍 Vedi Storico Operazioni Coerente"):
            st.dataframe(df_res_bt)
    else:
        st.warning("⚠️ Nessun trade generato con la soglia di confidenza attuale.")
