import streamlit as st
import yfinance as yf
import pandas as pd

# Configurazione Pagina
st.set_page_config(page_title="V-Alpha Core System", layout="wide")

def get_data():
    # Recupero dati storici per il calcolo dei livelli
    df = yf.download("CL=F", period="5d", interval="5m")
    return df

def calcola_livelli(df):
    high = df['High'].max()
    low = df['Low'].min()
    # Logica di calcolo livelli V-Alpha
    sup = round(low + (high - low) * 0.2, 3)
    res = round(high - (high - low) * 0.2, 3)
    return sup, res

st.title("🚀 V-Alpha | Sistema Operativo")

# Caricamento dati
df = get_data()
if not df.empty:
    supporto, resistenza = calcola_livelli(df)
    prezzo_yahoo = round(df['Close'].iloc[-1], 2)
    
    # Sidebar per override manuale
    st.sidebar.header("Override Prezzo")
    prezzo_reale = st.sidebar.number_input("Prezzo WTI Reale (Fineco/TV):", value=prezzo_yahoo, step=0.01, format="%.2f")
    
    # Visualizzazione Livelli
    col1, col2, col3 = st.columns(3)
    col1.metric("Supporto V-Alpha", supporto)
    col2.metric("Prezzo Operativo", prezzo_reale)
    col3.metric("Resistenza V-Alpha", resistenza)
    
    # Analisi Predittiva
    st.subheader("Analisi Direzionale")
    if prezzo_reale > resistenza:
        st.error("DIREZIONE: SHORT - Zona Resistenza")
    elif prezzo_reale < supporto:
        st.success("DIREZIONE: LONG - Zona Supporto")
    else:
        st.info("DIREZIONE: NEUTRA - Range di Consolidamento")
        
    st.write("---")
    st.write("Il sistema utilizza i massimi/minimi a 5 giorni per definire i livelli operativi.")
else:
    st.error("Errore: Impossibile caricare i dati storici.")
