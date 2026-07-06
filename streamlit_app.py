import streamlit as st
import pandas as pd
import os
from datetime import datetime
import pytz

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Quant Drop Manual Mode", layout="wide", page_icon="💧")

FILE_DIARIO = "diario_trading.csv"
COLONNE_DIARIO = ["Data/Ora", "Direzione", "Qualità", "Trigger", "SL Initial", "TP", "Contratti", "Prezzo Uscita Fineco", "Esito", "Profitto (€)", "Prezzo KO IN (€)", "Prezzo KO OUT (€)"]

def load_diario():
    if os.path.exists(FILE_DIARIO):
        return pd.read_csv(FILE_DIARIO)
    return pd.DataFrame(columns=COLONNE_DIARIO)

# --- UI BARRA LATERALE ---
st.sidebar.markdown("### 🛠️ Configurazione Input")
prezzo_manuale = st.sidebar.number_input("Inserisci Prezzo WTI (Real-Time):", value=68.46, step=0.01, format="%.2f")
tipo_strumento = st.sidebar.selectbox("Strumento Utilizzato:", ["Fineco Knockout (Certificati)", "Micro WTI (MCL CFD)", "Standard WTI (CL CFD)"])
volatilita_set = st.sidebar.slider("Fattore Volatilità (SL/TP):", min_value=0.10, max_value=1.00, value=0.45, step=0.05)

# --- LOGICA DI CALCOLO PREDITTIVO ---
st.title("💧 Quant Drop | Analisi Predittiva")
st.info(f"Analisi basata su prezzo WTI: **{prezzo_manuale} USD**")

# Logica di Direzione (Esempio basato su soglia dinamica)
direzione = "SHORT" if prezzo_manuale > 68.40 else "LONG"

# Calcolo dei livelli predittivi
if direzione == "SHORT":
    trigger = round(prezzo_manuale - 0.05, 3)
    sl = round(trigger + (volatilita_set * 0.8), 3)
    tp = round(trigger - (volatilita_set * 1.2), 3)
else:
    trigger = round(prezzo_manuale + 0.05, 3)
    sl = round(trigger - (volatilita_set * 0.8), 3)
    tp = round(trigger + (volatilita_set * 1.2), 3)

st.subheader(f"🎯 Strategia: {direzione}")
col1, col2, col3 = st.columns(3)
col1.metric("Trigger Previsionale", trigger)
col2.metric("Stop Loss (SL)", sl)
col3.metric("Take Profit (TP)", tp)

st.warning(f"Segnale: **{direzione}**. Verifica sempre il trend grafico prima di eseguire.")

# --- REGISTRAZIONE TRADE ---
if st.button("REGISTRA QUESTO SEGNALE"):
    ora_it = datetime.now(pytz.timezone('Europe/Rome')).strftime("%d/%m/%Y %H:%M")
    nuovo_trade = {
        "Data/Ora": ora_it, 
        "Direzione": direzione, 
        "Qualità": "Manuale",
        "Trigger": trigger, 
        "SL Initial": sl, 
        "TP": tp,
        "Contratti": 1,
        "Esito": "IN CORSO ⏳", 
        "Prezzo KO IN (€)": 1.00 if "Knockout" in tipo_strumento else "--"
    }
    df = pd.concat([load_diario(), pd.DataFrame([nuovo_trade])], ignore_index=True)
    df.to_csv(FILE_DIARIO, index=False)
    st.success("Trade registrato con successo!")
    st.rerun()

# --- POSIZIONI ATTIVE ---
st.markdown("---")
st.header("📝 Posizioni Attive")
diario_df = load_diario()
aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]

if not aperte.empty:
    for idx, row in aperte.iterrows():
        with st.expander(f"⚙️ {row['Direzione']} | Aperto il {row['Data/Ora']}"):
            val_out = st.number_input("Prezzo Uscita:", value=float(row.get("Trigger", 0)), key=f"out_{idx}")
            if st.button("CHIUDI TRADE", key=f"btn_{idx}"):
                diario_df.at[idx, ["Esito", "Prezzo Uscita Fineco"]] = ["CHIUSO ✅", val_out]
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.rerun()
else:
    st.info("Portafoglio Flat.")

# --- STORICO ---
if not diario_df.empty:
    st.markdown("---")
    st.subheader("🗄️ Storico Operazioni")
    st.dataframe(diario_df, use_container_width=True)
