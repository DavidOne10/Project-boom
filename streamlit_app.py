import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="V-Alpha PRO | Safe Mode", layout="wide")

# --- MEMORIA DI SISTEMA ---
if 'supporto' not in st.session_state: st.session_state.supporto = 74.20
if 'resistenza' not in st.session_state: st.session_state.resistenza = 75.10
if 'atr' not in st.session_state: st.session_state.atr = 0.20

# --- FUNZIONE SCARICAMENTO DATI ---
@st.cache_data(ttl=60)
def get_live_data():
    try:
        # Scarichiamo dati dell'ultima giornata
        df = yf.download("CL=F", period="1d", interval="5m")
        return df
    except:
        return None

st.title("🚀 V-Alpha | Sistema a Scaricamento Automatico")

# Scarica dati
df = get_live_data()

# --- CORREZIONE DEFINITIVA ---
if df is not None and not df.empty:
    try:
        # Estrazione sicura del valore Close
        prezzo_raw = df['Close'].iloc[-1]
        prezzo_reale = float(prezzo_raw.item() if hasattr(prezzo_raw, 'item') else prezzo_raw)
        
        # Estrazione sicura High e Low
        high_raw = df['High'].max()
        low_raw = df['Low'].min()
        
        high = float(high_raw.item() if hasattr(high_raw, 'item') else high_raw)
        low = float(low_raw.item() if hasattr(low_raw, 'item') else low_raw)
        
        # Aggiornamento memoria
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

# --- LOGICA PREDITTIVA (Preset Ore 10:00) ---
st.subheader("📊 Analisi V-Alpha (Preset 10:00)")
col1, col2, col3 = st.columns(3)
col1.metric("Supporto", st.session_state.supporto)
col2.metric("Prezzo", prezzo_reale)
col3.metric("Resistenza", st.session_state.resistenza)

direzione = "NEUTRO"
target, sl = 0.0, 0.0

if prezzo_reale > st.session_state.resistenza:
    direzione = "SHORT"
    target = round(prezzo_reale - (st.session_state.atr * 2.0), 3)
    sl = round(prezzo_reale + (st.session_state.atr * 0.6), 3)
elif prezzo_reale < st.session_state.supporto:
    direzione = "LONG"
    target = round(prezzo_reale + (st.session_state.atr * 2.0), 3)
    sl = round(prezzo_reale - (st.session_state.atr * 0.6), 3)

if direzione != "NEUTRO":
    st.success(f"### Segnale: {direzione}")
    col_a, col_b = st.columns(2)
    col_a.metric("Take Profit (Target x2.0)", target)
    col_b.metric("Stop Loss (SL x0.6)", sl)
else:
    st.info("Prezzo in zona di attesa (Consolidamento).")
