# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Regularized RF Walk-Forward", layout="wide")

st.title("🤖 V-Alpha PRO | Random Forest Regolarizzato (Anti-Overfitting)")
st.markdown("---")

# --- 1. FUNZIONE DI ADDESTRAMENTO CON REGOLARIZZAZIONE FORTE ---
@st.cache_data(ttl=3600)
def scarica_dati_base(ticker):
    try:
        dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)
            
        if dati.empty or len(dati) < 200:
            return None

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

        return dati.dropna()

    except Exception as e:
        st.error(f"Errore nel download dati: {e}")
        return None

ticker_attivo = "CL=F" # WTI Crude Oil
df_storico = scarica_dati_base(ticker_attivo)

if df_storico is None:
    st.error("⚠️ Errore nel caricamento dei dati di mercato.")
    st.stop()

prezzo_live = round(float(df_storico['Close'].iloc[-1]), 3)

# --- PANNELLO LATERALE ---
st.sidebar.header("💰 Gestione Capitale & Costi")
capitale_utente = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
costo_attrito = st.sidebar.number_input("Costi Fissi (Comm. + Spread €):", value=12.0, step=1.0)
soglia_filtro = st.sidebar.slider("Soglia Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
dimensione_lotto = st.sidebar.number_input("Moltiplicatore Contratto (Barili):", value=10.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.header("🔄 Modalità Operativa")
modalita_inversa = st.sidebar.checkbox("Attiva 'Anti-IA Mode' (Inverti Segnali)", value=True)

# Variabili e Modello Regolarizzato per il Live
variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
             'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

# Parametri anti-overfitting severi: max_depth basso e min_samples alti
modello_live = RandomForestClassifier(
    n_estimators=50, 
    max_depth=3, 
    min_samples_split=40, 
    min_samples_leaf=25, 
    random_state=42
)
modello_live.fit(df_storico[variabili].iloc[:-1], df_storico['Target'].iloc[:-1])

ultimo_dato = df_storico[variabili].iloc[[-1]]
prob_live = modello_live.predict_proba(ultimo_dato)[0]
pred_live_nativa = modello_live.predict(ultimo_dato)[0]
confidenza_ia = prob_live[pred_live_nativa] * 100

segnalo_ia_str = "LONG" if pred_live_nativa == 1 else "SHORT"
op_live = 0 if (pred_live_nativa == 1 and modalita_inversa) or (pred_live_nativa == 0 and not modalita_inversa) else 1
direzione_effettiva_str = "LONG" if op_live == 1 else "SHORT"
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
    st.metric("Confidenza IA (Regolarizzata)", f"{confidenza_ia:.1f}%")

# ==========================================
# 2. BACKTEST WALK-FORWARD CON MODELLO POTATO
# ==========================================
st.markdown("---")
st.subheader("📊 Backtest Walk-Forward (Modello Regolarizzato OOS)")

def esegui_walk_forward_rigido(dati, capitale_iniziale, attrito, conf_minima, inverti, lotto):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    finestra_test = 126
    punto_inizio = len(dati) - finestra_test
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    for i in range(punto_inizio, len(dati) - 1):
        dati_train = dati.iloc[:i]
        
        X_train = dati_train[variabili]
        y_train = dati_train['Target']
        
        # Modello con vincoli severi per impedire la memorizzazione del passato
        modello_wf = RandomForestClassifier(
            n_estimators=50, 
            max_depth=3, 
            min_samples_split=40, 
            min_samples_leaf=25, 
            random_state=42
        )
        modello_wf.fit(X_train, y_train)
        
        riga_test = dati.iloc[i:i+1][variabili]
        prob = modello_wf.predict_proba(riga_test)[0]
        pred_ia = modello_wf.predict(riga_test)[0]
        conf = prob[pred_ia] * 100
        
        if conf < conf_minima:
            continue
            
        if inverti:
            op_eseguita = 0 if pred_ia == 1 else 1
        else:
            op_eseguita = pred_ia
            
        data_trade = dati.index[i].date()
        prezzo_entrata = dati['Close'].iloc[i]
        prezzo_uscita = dati['Close'].iloc[i+1]
        
        variazione = prezzo_uscita - prezzo_entrata
        pnl_lordo = variazione * lotto if op_eseguita == 1 else -variazione * lotto
        pnl_netto = pnl_lordo - attrito
        
        capitale_corrente += pnl_netto
        equity.append(capitale_corrente)
        
        esito = "WIN" if pnl_netto > 0 else "LOSS"
        
        trade_log.append({
            "Data": str(data_trade),
            "IA": "LONG" if pred_ia == 1 else "SHORT",
            "Eseguito": "LONG" if op_eseguita == 1 else "SHORT",
            "Confidenza": round(conf, 1),
            "Esito": esito,
            "PnL (€)": round(pnl_netto, 2),
            "Capitale (€)": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

if df_storico is not None:
    df_res_wf, eq_wf = esegui_walk_forward_rigido(df_storico, capitale_utente, costo_attrito, soglia_filtro, modalita_inversa, dimensione_lotto)
    
    if not df_res_wf.empty:
        tot_t = len(df_res_wf)
        vinti_t = len(df_res_wf[df_res_wf['Esito'] == "WIN"])
        wr_t = (vinti_t / tot_t) * 100
        net_profit = eq_wf[-1] - capitale_utente
        
        wf_c1, wf_c2, wf_c3, wf_c4 = st.columns(4)
        wf_c1.metric("Trade OOS Effettuati", tot_t)
        wf_c2.metric("Win Rate Regolarizzato", f"{wr_t:.1f}%")
        wf_c3.metric("Profitto Netto OOS", f"{net_profit:.2f} €")
        wf_c4.metric("Capitale Finale OOS", f"{eq_wf[-1]:.2f} €")
        
        st.line_chart(eq_wf)
        
        with st.expander("🔍 Vedi Storico Dettagliato Walk-Forward Regolarizzato"):
            st.dataframe(df_res_wf)
    else:
        st.warning("⚠️ Nessun trade generato con la soglia di confidenza attuale.")
