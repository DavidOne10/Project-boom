import streamlit as st
import yfinance as yf
import pandas as pd

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="V-Alpha PRO | Predittività", layout="centered")

# --- MOTORE DATI ROBUSTO ---
@st.cache_data(ttl=60)
def get_data():
    # Tenta prima con il WTI (CL=F), poi fallback su Brent (BZ=F) o USOIL (USOIL=X)
    tickers = ["CL=F", "BZ=F", "USOIL=X"]
    for ticker in tickers:
        try:
            # auto_adjust per evitare problemi di formattazione prezzi
            df = yf.download(ticker, period="1d", interval="5m", auto_adjust=True)
            # Verifica che il dataframe sia valido e contenga la colonna 'Close'
            if not df.empty and 'Close' in df.columns:
                return df
        except:
            continue
    return None

# --- INTESTAZIONE ---
st.title("🚀 V-Alpha | Controllo Operativo")

# Recupero Dati
df = get_data()

# --- CONTROLLO ERRORI CRUCIALE ---
# Se df è None o vuoto, fermiamo tutto qui per evitare crash
if df is None or df.empty:
    st.error("⚠️ I server di Yahoo Finance non rispondono o i dati non sono disponibili in questo momento. Riprova tra poco.")
    st.stop() 

# --- CALCOLI V-ALPHA ---
try:
    # Estrazione valori e conversione in float per sicurezza
    prezzo_reale = round(float(df['Close'].iloc[-1]), 3)
    high = float(df['High'].max())
    low = float(df['Low'].min())
    
    # Calcolo Livelli
    supporto = round(low + (high - low) * 0.2, 3)
    resistenza = round(high - (high - low) * 0.2, 3)
    
    # Calcolo ATR (usando un quinto del range giornaliero come proxy)
    atr = round((high - low) / 5, 3)
except Exception as e:
    st.error(f"Errore durante il calcolo dei livelli: {e}")
    st.stop()

# --- DASHBOARD LIVE ---
st.markdown("### 📊 Analisi Livelli Correnti")
c1, c2, c3 = st.columns(3)
c1.metric("Supporto V-Alpha", supporto)
c2.metric("Prezzo WTI Live", prezzo_reale)
c3.metric("Resistenza V-Alpha", resistenza)

st.markdown("---")

# --- PANNELLO DI PREDITTIVITÀ ---
st.subheader("🔮 Pannello di Predittività Attiva")

# Calcolo Distanze (Quanto manca al segnale?)
dist_supp = round(prezzo_reale - supporto, 3)
dist_res = round(resistenza - prezzo_reale, 3)
min_dist = min(dist_supp, dist_res)

col_p1, col_p2 = st.columns(2)

with col_p1:
    st.markdown("### 🏹 Direzione Preferenziale")
    if dist_supp < dist_res:
        st.write("Il prezzo è in compressione verso il **SUPPORTO**.")
        st.success("PREDIZIONE: Prepararsi per possibile **LONG** 🟢")
        
        # Calcolo dei target
        target = round(supporto + (atr * 2.0), 3)
        stop_loss = round(supporto - (atr * 0.6), 3)
        livello_chiave = supporto
        tipo_ordine = "LONG"
    else:
        st.write("Il prezzo è in compressione verso la **RESISTENZA**.")
        st.error("PREDIZIONE: Prepararsi per possibile **SHORT** 🔴")
        
        # Calcolo dei target
        target = round(resistenza - (atr * 2.0), 3)
        stop_loss = round(resistenza + (atr * 0.6), 3)
        livello_chiave = resistenza
        tipo_ordine = "SHORT"

with col_p2:
    st.markdown("### ⏳ Qualità & Tempistica")
    # Calcolo qualità segnale basato sulla vicinanza (più è vicino, più il segnale è 'caldo')
    if min_dist < (atr * 2):
        qualita = "🔥 ALTA (Livello a portata di mano)"
    else:
        qualita = "❄️ BASSA (Attesa prolungata)"
        
    st.write(f"Qualità Segnale: **{qualita}**")
    st.write(f"Distanza dal livello target: **{min_dist}**")

# --- PIANO OPERATIVO DIRETTO ---
st.markdown("---")
st.subheader("📋 Esecuzione Piano Operativo")

if tipo_ordine == "LONG":
    st.info(f"Monitora area **{livello_chiave}**. Se il prezzo scende al Supporto, ecco i tuoi ordini pronti al target:")
else:
    st.info(f"Monitora area **{livello_chiave}**. Se il prezzo sale alla Resistenza, ecco i tuoi ordini pronti al target:")

c_op1, c_op2, c_op3 = st.columns(3)
c_op1.metric(f"Ordine a quota ({tipo_ordine})", livello_chiave)
c_op2.metric("Take Profit Target (x2.0)", target)
c_op3.metric("Stop Loss Protezione (x0.6)", stop_loss)
