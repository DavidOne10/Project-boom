import streamlit as st
from datetime import datetime
import pytz

st.set_page_config(page_title="V-Alpha Pro", layout="wide")

# --- MEMORIA DI SISTEMA (Session State) ---
# Questi valori rimangono fissi finché non li cambi tu
if 'supporto' not in st.session_state: st.session_state.supporto = 74.20
if 'resistenza' not in st.session_state: st.session_state.resistenza = 75.10
if 'atr' not in st.session_state: st.session_state.atr = 0.20

st.title("🚀 V-Alpha | Sistema Predittivo")

# --- SIDEBAR: CONTROLLO TOTALE ---
st.sidebar.header("🛠️ Configurazione Predittiva")
prezzo_reale = st.sidebar.number_input("Prezzo WTI Reale:", value=74.64, step=0.01, format="%.2f")

# Aggiornamento memoria (se cambi i valori, restano memorizzati)
st.session_state.supporto = st.sidebar.number_input("Supporto V-Alpha (Memoria):", value=st.session_state.supporto, step=0.01)
st.session_state.resistenza = st.sidebar.number_input("Resistenza V-Alpha (Memoria):", value=st.session_state.resistenza, step=0.01)
st.session_state.atr = st.sidebar.number_input("ATR (Memoria):", value=st.session_state.atr, step=0.01)

# --- ANALISI PREDITTIVA ---
st.subheader("📊 Analisi V-Alpha Attiva")
col1, col2, col3 = st.columns(3)
col1.metric("Supporto", st.session_state.supporto)
col2.metric("Prezzo", prezzo_reale)
col3.metric("Resistenza", st.session_state.resistenza)

# Logica di calcolo costante (usa sempre la memoria)
direzione = "NEUTRO"
target, sl = 0.0, 0.0

if prezzo_reale > st.session_state.resistenza:
    direzione = "SHORT"
    target = round(prezzo_reale - (st.session_state.atr * 1.5), 3)
    sl = round(prezzo_reale + (st.session_state.atr * 0.8), 3)
elif prezzo_reale < st.session_state.supporto:
    direzione = "LONG"
    target = round(prezzo_reale + (st.session_state.atr * 1.5), 3)
    sl = round(prezzo_reale - (st.session_state.atr * 0.8), 3)

if direzione != "NEUTRO":
    st.success(f"### Segnale: {direzione}")
    col_a, col_b = st.columns(2)
    col_a.metric("Take Profit", target)
    col_b.metric("Stop Loss", sl)
    st.info(f"Il sistema sta calcolando la predittività basandosi su: S={st.session_state.supporto} | R={st.session_state.resistenza} | ATR={st.session_state.atr}")

if st.button("RESET MEMORIA"):
    st.session_state.supporto = 74.20
    st.session_state.resistenza = 75.10
    st.session_state.atr = 0.20
    st.rerun()
