import streamlit as st
import yfinance as yf
import pandas as pd
import os
from datetime import datetime
import pytz

# --- CONFIGURAZIONE E SETUP ---
st.set_page_config(page_title="V-Alpha Professional", layout="wide", page_icon="🚀")
FILE_DIARIO = "diario_trading_pro.csv"

def get_orario_status():
    # Orario locale in Italia
    now = datetime.now(pytz.timezone('Europe/Rome'))
    
    # Logica orari operativi
    if now.hour >= 14 and now.hour < 17:
        return "🔥 ALTA VOLATILITÀ (Sessione USA)", "success"
    elif now.hour == 16 and 30 <= now.minute <= 45:
        return "⚠️ ATTENZIONE: News/Scorte (Volatilità Estrema)", "warning"
    else:
        return "💤 MERCATO LENTO (Volume Ridotto)", "info"

def load_data():
    # Caricamento storico per analisi V-Alpha
    try:
        df = yf.download("CL=F", period="5d", interval="5m")
        return df
    except:
        return pd.DataFrame()

def calcola_indicatori(df):
    high = df['High'].max()
    low = df['Low'].min()
    # Calcolo V-Alpha
    supporto = round(low + (high - low) * 0.2, 3)
    resistenza = round(high - (high - low) * 0.2, 3)
    atr = round((high - low) / 5, 3)
    return supporto, resistenza, atr

# --- INTERFACCIA ---
st.title("🚀 V-Alpha | Sistema Operativo Completo")

# Integrazione Stato Orario
stato_orario, stato_colore = get_orario_status()
if stato_colore == "success": st.success(f"STATO MERCATO: {stato_orario}")
elif stato_colore == "warning": st.warning(f"STATO MERCATO: {stato_orario}")
else: st.info(f"STATO MERCATO: {stato_orario}")

df = load_data()
if not df.empty:
    supporto, resistenza, atr = calcola_indicatori(df)
    prezzo_base = round(df['Close'].iloc[-1], 2)
    
    # Sidebar: Controllo di Precisione
    st.sidebar.header("🛠️ Input di Precisione")
    prezzo_reale = st.sidebar.number_input("Prezzo WTI Reale (Fineco/TV):", value=prezzo_base, step=0.01, format="%.2f")
    rischio_euro = st.sidebar.number_input("Rischio Operazione (€):", value=50, step=10)
    
    # Analisi V-Alpha
    st.subheader("📊 Analisi Tecnica V-Alpha")
    col1, col2, col3 = st.columns(3)
    col1.metric("Supporto", supporto)
    col2.metric("Prezzo Mercato", prezzo_reale)
    col3.metric("Resistenza", resistenza)
    
    # Logica Predittiva
    if prezzo_reale > resistenza:
        direzione = "SHORT"
        target = round(prezzo_reale - (atr * 1.5), 3)
        sl = round(prezzo_reale + (atr * 0.8), 3)
    elif prezzo_reale < supporto:
        direzione = "LONG"
        target = round(prezzo_reale + (atr * 1.5), 3)
        sl = round(prezzo_reale - (atr * 0.8), 3)
    else:
        direzione = "NEUTRO"
        target, sl = 0, 0
        st.warning("Prezzo in zona di consolidamento. Attendi rottura livelli.")

    if direzione != "NEUTRO":
        st.success(f"### Segnale: {direzione}")
        col_a, col_b = st.columns(2)
        col_a.metric("Take Profit", target)
        col_b.metric("Stop Loss", sl)
        
        # --- REGISTRAZIONE ---
        if st.button("REGISTRA OPERAZIONE"):
            nuovo_trade = pd.DataFrame({
                "Data": [datetime.now(pytz.timezone('Europe/Rome')).strftime("%d/%m %H:%M")],
                "Direzione": [direzione],
                "Prezzo": [prezzo_reale],
                "SL": [sl],
                "TP": [target]
            })
            if os.path.exists(FILE_DIARIO):
                nuovo_trade.to_csv(FILE_DIARIO, mode='a', header=False, index=False)
            else:
                nuovo_trade.to_csv(FILE_DIARIO, index=False)
            st.success("Operazione salvata correttamente.")

    # Storico
    if os.path.exists(FILE_DIARIO):
        st.markdown("---")
        st.subheader("📋 Storico Operazioni")
        st.dataframe(pd.read_csv(FILE_DIARIO))

else:
    st.error("Errore di caricamento dati. Verifica la connessione.")
