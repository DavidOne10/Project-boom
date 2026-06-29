import streamlit as st
import yfinance as tf
import pandas as pd
from datetime import datetime, time
import os
import pytz

# CONFIGURAZIONE PAGINA
st.set_page_config(page_title="Crude Oil Trading Assistant v3.0", layout="wide", page_icon="🛢️")

st.title("🛢️ Crude Oil Trading Assistant v3.0")
st.subheader("Il tuo centro di controllo permanente e anti-emotività")
st.markdown("---")

# FILE DATABASE PERMANENTE
FILE_DIARIO = "diario_trading.csv"

# Caricamento o creazione del database reale
if os.path.exists(FILE_DIARIO):
    diario_df = pd.read_csv(FILE_DIARIO)
else:
    diario_df = pd.DataFrame(columns=[
        "Data/Ora", "Fascia", "Direzione", "Trigger", 
        "SL Initial", "TP", "Contratti", "Prezzo Uscita Fineco", "Esito", "Profitto (€)"
    ])

# GESTIONE ORARIA
ZONA_IT = pytz.timezone('Europe/Rome')
ora_attiva_it = datetime.now(ZONA_IT)
ora_solo_tempo = ora_attiva_it.time()

st.sidebar.metric(label="🕒 Ora Italiana Corrente", value=ora_attiva_it.strftime("%H:%M:%S"))

sessione_sicura = True
if ora_solo_tempo >= time(15, 0):
    sessione_sicura = False
    st.sidebar.error("⚠️ REGIME SERALE ATTIVO: Rischio Volatilità USA.")
else:
    st.sidebar.success("🟢 REGIME MATTUTINO: Sessione ideale.")

# 1. GENERAZIONE SEGNALE LIVE
st.header("⚡ Generazione Segnale Real-Time")

if st.button("🚀 CALCOLA LIVELLI TECNICI"):
    with st.spinner("Analizzando i dati di Yahoo Finance..."):
        try:
            ticker = tf.Ticker("CL=F")
            dati = ticker.history(period="1d", interval="5m")
            
            if not dati.empty:
                prezzo_attuale = round(dati['Close'].iloc[-1], 3)
                ora_dati = dati.index[-1].astimezone(ZONA_IT)
                differenza_minuti = (ora_attiva_it - ora_dati).total_seconds() / 60
                
                continua_calcolo = True
                if differenza_minuti > 13:
                    st.error(f"🚨 DATI SCADUTI! Ritardo di {int(differenza_minuti)} min. Attendi il flusso corretto.")
                    continua_calcolo = False
                elif diferencia_minuti > 5:
                    st.warning(f"⚠️ RITARDO FLUSSO ({int(differenza_minuti)} min). Verifica i prezzi reali su Fineco!")
                else:
                    st.info(f"📊 Mercato aggiornato a: **{prezzo_attuale} USD**")
                
                if continua_calcolo:
                    if not sessione_sicura:
                        direzione = "LONG (Segui Trend)"
                        trigger = round(prezzo_attuale + 0.05, 3)
                        sl = round(trigger - 0.25, 3)
                        tp = round(trigger + 0.50, 3)
                    else:
                        direzione = "SHORT"
                        trigger = round(prezzo_attuale - 0.03, 3)
                        sl = round(trigger + 0.20, 3)  # Nota: Possiamo allargarlo a 0.30 per dare più respiro
                        tp = round(trigger - 0.40, 3)
                    
                    rischio_max = st.sidebar.number_input("Rischio Max (€):", min_value=10, max_value=500, value=50)
                    distanza_sl = abs(trigger - sl)
                    contratti_consigliati = max(1, int(rischio_max / (distanza_sl * 100))) 
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("DIREZIONE", direzione)
                    col2.metric("TRIGGER", f"{trigger} USD")
                    col3.metric("STOP LOSS", f"{sl} USD")
                    col4.metric("TAKE PROFIT", f"{tp} USD")
                    
                    # Salva temporaneamente nello session_state per la conferma
                    st.session_state.nuovo_trade_temp = {
                        "Data/Ora": ora_attiva_it.strftime("%d/%m/%Y %H:%M"),
                        "Fascia": "MATTINA" if sessione_sicura else "POMERIGGIO",
                        "Direzione": direzione,
                        "Trigger": trigger,
                        "SL Initial": sl,
                        "TP": tp,
                        "Contratti": contratti_consigliati,
                        "Prezzo Uscita Fineco": "--",
                        "Esito": "IN CORSO ⏳",
                        "Profitto (€)": 0.0
                    }
                    st.success("📌 Livelli pronti! Conferma l'apertura qui sotto per metterlo in tabella.")
            else:
                st.error("Impossibile caricare i dati.")
        except Exception as e:
            st.error(f"Errore: {e}")

# 2. SEZIONE CONFERMA E GESTIONE IN CORSO
if 'nuovo_trade_temp' in st.session_state:
    st.markdown("---")
    st.write("### 🗹 Conferma Apertura Posizione su Fineco")
    prezzo_reale_ingresso = st.number_input("Prezzo Reale Eseguito su Fineco:", value=st.session_state.nuovo_trade_temp["Trigger"], step=0.001, format="%.3f")
    giuramento = st.checkbox("Giuro solennemente che sto seguendo il piano senza vendetta.")
    
    if st.button("METTI IL TRADE IN CORSO"):
        if giuramento:
            st.session_state.nuovo_trade_temp["Trigger"] = prezzo_reale_ingresso
            # Accoda al DataFrame permanente
            nuovo_df = pd.DataFrame([st.session_state.nuovo_trade_temp])
            diario_df = pd.concat([diario_df, nuovo_df], ignore_index=True)
            diario_df.to_csv(FILE_DIARIO, index=False)
            st.success("Posizione inserita nel pannello live! Chiudi pure Fineco.")
            del st.session_state.nuovo_trade_temp
            st.rerun()
        else:
            st.error("Devi spuntare il controllo emotivo.")

# 3. PANNELLO LIVE: AGGIORNA I DATI DOPO LA CHIUSURA
st.markdown("---")
st.header("📝 Pannello Controllo Operazioni Live & Storico")

# Se ci sono operazioni in corso, permette di chiuderle
posizioni_aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]

if not posizioni_aperte.empty:
    st.write("### ⚙️ Aggiorna Esito Operazioni in Corso")
    for idx, row in posizioni_aperte.iterrows():
        with st.expander(f"Modifica Trade del {row['Data/Ora']} | {row['Direzione']} da {row['Trigger']}"):
            prezzo_uscita = st.number_input(f"Prezzo finale di uscita Fineco (ID: {idx}):", value=row["Trigger"], step=0.001, format="%.3f", key=f"out_{idx}")
            esito_scelto = st.selectbox("Com'è andata?", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
            
            if st.button("CHIUDI E SALVA OPERAZIONE", key=f"btn_{idx}"):
                # Calcolo Profitto indicativo in Euro (1 punto = 1000$ standard, ma calcolato sui mini/CFD a leva)
                moltiplicatore = 100 # Adattato alla formula dei 50 euro tarata sui tuoi contratti
                punti = (prezzo_uscita - row["Trigger"]) if row["Direzione"] == "LONG" else (row["Trigger"] - prezzo_uscita)
                profitto_calcolato = punti * moltiplicatore * row["Contratti"]
                
                diario_df.at[idx, "Prezzo Uscita Fineco"] = prezzo_uscita
                diario_df.at[idx, "Esito"] = esito_scelto
                diario_df.at[idx, "Profitto (€)"] = round(profitto_calcolato, 2)
                
                # Salva su file permanente
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.success("Trade archiviato con successo!")
                st.rerun()

# 4. LA TABELLA BELLA E COLORATA
if not diario_df.empty:
    st.write("### Diario Completo (I dati non si cancellano più)")
    
    # Funzione per colorare le righe in base all'esito
    def colora_esito(val):
        if val == "GAIN ✅":
            return 'background-color: rgba(40, 167, 69, 0.2)'
        elif val == "LOSS ❌":
            return 'background-color: rgba(220, 53, 69, 0.2)'
        elif val == "IN CORSO ⏳":
            return 'background-color: rgba(255, 193, 7, 0.2)'
        return ''

    st.dataframe(diario_df.style.applymap(colora_esito, subset=['Esito']))
else:
    st.info("Nessun trade registrato nel database permanente.")
