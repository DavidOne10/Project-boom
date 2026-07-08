import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="V-Alpha PRO | Predittività Totale", layout="wide")

# --- MEMORIA DI SISTEMA ---
if 'supporto' not in st.session_state: st.session_state.supporto = 74.20
if 'resistenza' not in st.session_state: st.session_state.resistenza = 75.10
if 'atr' not in st.session_state: st.session_state.atr = 0.20

# --- FUNZIONE SCARICAMENTO DATI ---
@st.cache_data(ttl=60)
def get_live_data():
    try:
        df = yf.download("CL=F", period="1d", interval="5m")
        return df
    except:
        return None

st.title("🚀 V-Alpha | Predittività Continua 10:00")

# Scarica dati
df = get_live_data()

# --- ESTRAZIONE SICURA ---
if df is not None and not df.empty:
    try:
        prezzo_raw = df['Close'].iloc[-1]
        prezzo_reale = float(prezzo_raw.item() if hasattr(prezzo_raw, 'item') else prezzo_raw)
        
        high_raw = df['High'].max()
        low_raw = df['Low'].min()
        
        high = float(high_raw.item() if hasattr(high_raw, 'item') else high_raw)
        low = float(low_raw.item() if hasattr(low_raw, 'item') else low_raw)
        
        # Calcolo dinamico dei livelli V-Alpha
        st.session_state.supporto = round(low + (high - low) * 0.2, 3)
        st.session_state.resistenza = round(high - (high - low) * 0.2, 3)
        st.session_state.atr = round((high - low) / 5, 3)
        
        st.success("✅ Dati aggiornati in tempo reale.")
    except Exception as e:
        st.warning("⚠️ Errore nel processamento dati, uso memoria.")
        prezzo_reale = 74.64
else:
    st.warning("⚠️ Connessione a Yahoo Finance instabile. Uso ultimi valori in memoria.")
    prezzo_reale = 74.64

# FIX: Arrotondamento del prezzo reale per eliminare i decimali infiniti
prezzo_reale = round(prezzo_reale, 3)

# --- VISUALIZZAZIONE LIVE ---
st.subheader("📊 Analisi Livelli Correnti")
col1, col2, col3 = st.columns(3)
col1.metric("Supporto V-Alpha", st.session_state.supporto)
col2.metric("Prezzo WTI Live", prezzo_reale)
col3.metric("Resistenza V-Alpha", st.session_state.resistenza)

st.markdown("---")
st.subheader("🔮 Pannello di Predittività Attiva")

# Pre-calcolo predittivo degli scenari futuri sui livelli fissi
target_long_teorico = round(st.session_state.supporto + (st.session_state.atr * 2.0), 3)
sl_long_teorico = round(st.session_state.supporto - (st.session_state.atr * 0.6), 3)

target_short_teorico = round(st.session_state.resistenza - (st.session_state.atr * 2.0), 3)
sl_short_teorico = round(st.session_state.resistenza + (st.session_state.atr * 0.6), 3)

# Controllo trigger segnali
if prezzo_reale < st.session_state.supporto:
    st.success("### 🚨 SEGNALE IN CORSO: LONG (Prezzo sotto il Supporto)")
    target_attuale = round(prezzo_reale + (st.session_state.atr * 2.0), 3)
    sl_attuale = round(prezzo_reale - (st.session_state.atr * 0.6), 3)
    col_a, col_b = st.columns(2)
    col_a.metric("TAKE PROFIT ATTIVO", target_attuale)
    col_b.metric("STOP LOSS ATTIVO", sl_attuale)

elif prezzo_reale > st.session_state.resistenza:
    st.danger("### 🚨 SEGNALE IN CORSO: SHORT (Prezzo sopra la Resistenza)")
    target_attuale = round(prezzo_reale - (st.session_state.atr * 2.0), 3)
    sl_attuale = round(prezzo_reale + (st.session_state.atr * 0.6), 3)
    col_a, col_b = st.columns(2)
    col_a.metric("TAKE PROFIT ATTIVO", target_attuale)
    col_b.metric("STOP LOSS ATTIVO", sl_attuale)

else:
    # Se siamo in consolidamento, mostriamo la predittività di ENTRAMBI i piani pronti
    st.info("ℹ️ Il prezzo è in compressione nel canale. Ecco i tuoi ordini pronti al target:")
    
    col_l, col_s = st.columns(2)
    with col_l:
        st.markdown("#### 🟢 Se il prezzo scende al Supporto:")
        st.write(f"Ordine d'acquisto stimato a quota: **{st.session_state.supporto}**")
        st.metric("Take Profit Target (x2.0)", target_long_teorico)
        st.metric("Stop Loss Protezione (x0.6)", sl_long_teorico)
        
    with col_s:
        st.markdown("#### 🔴 Se il prezzo sale alla Resistenza:")
        st.write(f"Ordine di vendita stimato a quota: **{st.session_state.resistenza}**")
        st.metric("Take Profit Target (x2.0)", target_short_teorico)
        st.metric("Stop Loss Protezione (x0.6)", sl_short_teorico)
