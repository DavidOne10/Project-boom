import streamlit as st
import yfinance as tf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import pytz

# CONFIGURAZIONE PAGINA
st.set_page_config(page_title="Crude Oil Trading Assistant v4.3.1", layout="wide", page_icon="🛢️")

st.title("🛢️ Crude Oil Trading Assistant v4.3.1")
st.subheader("Algoritmo Quantitativo: Filtro Compressione e Stelle (Bug Fix Tabella)")
st.markdown("---")

# FILE DATABASE PERMANENTE
FILE_DIARIO = "diario_trading.csv"

# Definiamo le colonne standard per evitare disallineamenti nel CSV
COLONNE_DIARIO = [
    "Data/Ora", "Direzione", "Qualità", "Trigger", "SL Initial", "TP", "Contratti", "Prezzo Uscita Fineco", "Esito", "Profitto (€)"
]

if os.path.exists(FILE_DIARIO):
    try:
        diario_df = pd.read_csv(FILE_DIARIO)
        # Forza il riallineamento delle colonne se carichi un vecchio file
        for col in COLONNE_DIARIO:
            if col not in diario_df.columns:
                diario_df[col] = "--"
        diario_df = diario_df[COLONNE_DIARIO]
    except:
        diario_df = pd.DataFrame(columns=COLONNE_DIARIO)
else:
    diario_df = pd.DataFrame(columns=COLONNE_DIARIO)

# GESTIONE ORARIA
ZONA_IT = pytz.timezone('Europe/Rome')
ora_attiva_it = datetime.now(ZONA_IT)
st.sidebar.metric(label="🕒 Ora Italiana Corrente", value=ora_attiva_it.strftime("%H:%M:%S"))

st.sidebar.markdown("### 🛠️ Configurazione Rischio Dinamico")
base_risk = st.sidebar.number_input("Rischio Base (2 Stelle) in €:", min_value=10, max_value=200, value=50)
cuscinetto_tp = st.sidebar.slider("Cuscinetto TP (USD):", min_value=0.02, max_value=0.10, value=0.05, step=0.01)

# 1. GENERAZIONE SEGNALE LIVE V4.3.1
st.header("⚡ Scansione Mercato e Valutazione Qualità (Stelle)")

if st.button("🚀 AVVIA SCANSIONE QUANTITATIVA"):
    with st.spinner("Analizzando Bande di Bollinger, ATR e strutture Daily..."):
        try:
            ticker = tf.Ticker("CL=F")
            dati_daily = ticker.history(period="60d", interval="1d")
            dati_5min = ticker.history(period="2d", interval="5m")
            
            if not dati_daily.empty and not dati_5min.empty:
                prezzo_attuale = round(dati_5min['Close'].iloc[-1], 3)
                
                # CALCOLO BANDE DI BOLLINGER SUL 5 MIN (Per rilevare compressione)
                ma20_5m = dati_5min['Close'].rolling(window=20).mean()
                std20_5m = dati_5min['Close'].rolling(window=20).std()
                banda_superiore = ma20_5m + (2 * std20_5m)
                banda_inferiore = ma20_5m - (2 * std20_5m)
                larghezza_bande = (banda_superiore.iloc[-1] - banda_inferiore.iloc[-1])
                
                is_compressione = larghezza_bande < 0.15
                
                # CALCOLO ATR DAILY
                high_low = dati_daily['High'] - dati_daily['Low']
                high_close = np.abs(dati_daily['High'] - dati_daily['Close'].shift())
                low_close = np.abs(dati_daily['Low'] - dati_daily['Close'].shift())
                ranges = pd.concat([high_low, high_close, low_close], axis=1)
                atr_daily = ranges.max(axis=1).rolling(14).mean().iloc[-1]
                stop_elastico_base = round(atr_daily * 0.20, 3)
                
                # SUPPORTI E TREND DAILY
                storico_daily = dati_daily.iloc[:-1]
                supporto_daily = storico_daily['Low'].min()
                resistenza_daily = storico_daily['High'].max()
                
                dati_daily['MA20_Daily'] = dati_daily['Close'].rolling(window=20).mean()
                trend_daily_bull = prezzo_attuale >= dati_daily['MA20_Daily'].iloc[-1]
                
                dati_5min['EMA_21'] = dati_5min['Close'].ewm(span=21, adjust=False).mean()
                ema_5min_attuale = dati_5min['EMA_21'].iloc[-1]
                
                # DETERMINAZIONE DIREZIONE
                if prezzo_attuale < ema_5min_attuale:
                    direzione = "SHORT"
                    minimo_intraday = dati_5min['Low'].tail(24).min()
                    livello_chiave = supporto_daily if abs(prezzo_attuale - supporto_daily) < abs(prezzo_attuale - minimo_intraday) else minimo_intraday
                    trigger = round(livello_chiave - 0.02, 3)
                    sl_tecnico = max(dati_5min['High'].tail(24).max(), ema_5min_attuale)
                    sl = round(sl_tecnico + stop_elastico_base, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger - (distanza_sl * 1.5) + cuscinetto_tp, 3)
                    allineato = not trend_daily_bull
                else:
                    direzione = "LONG"
                    massimo_intraday = dati_5min['High'].tail(24).max()
                    livello_chiave = resistenza_daily if abs(prezzo_attuale - resistenza_daily) < abs(prezzo_attuale - massimo_intraday) else massimo_intraday
                    trigger = round(livello_chiave + 0.03, 3)
                    sl_tecnico = min(dati_5min['Low'].tail(24).min(), ema_5min_attuale)
                    sl = round(sl_tecnico - stop_elastico_base, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger + (distanza_sl * 1.5) - cuscinetto_tp, 3)
                    allineato = trend_daily_bull

                # STELLE
                if is_compressione:
                    stelle = "⭐ (1 Stella - COMPRESSIONE)"
                    budget_rischio = round(base_risk * 0.4)
                elif allineato:
                    stelle = "⭐⭐⭐ (3 Stelle - CECCHINO ALINEATO)"
                    budget_rischio = round(base_risk * 1.5)
                else:
                    stelle = "⭐⭐ (2 Stelle - Standard)"
                    budget_rischio = base_risk
                
                contratti_consigliati = max(1, int(budget_rischio / (distanza_sl * 100)))
                
                st.info(f"📊 Prezzo Attuale: **{prezzo_attuale} USD** | Larghezza Bollinger: **{round(larghezza_bande, 3)}**")
                
                col_st1, col_st2, col_st3 = st.columns(3)
                col_st1.metric("QUALITÀ SEGNALE", stelle)
                col_st2.metric("BUDGET RISCHIO ASSEGNATO", f"{budget_rischio} €")
                col_st3.metric("CONTRATTI CONSIGLIATI", contratti_consigliati)
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("DIREZIONE", direzione)
                col2.metric("TRIGGER INGRESSO", f"{trigger} USD")
                col3.metric("STOP LOSS ELASTICO", f"{sl} USD")
                col4.metric("TAKE PROFIT ANTICIPATO", f"{tp} USD")
                
                st.session_state.nuovo_trade_temp = {
                    "Data/Ora": ora_attiva_it.strftime("%d/%m/%Y %H:%M"),
                    "Direzione": direzione,
                    "Qualità": stelle,
                    "Trigger": trigger,
                    "SL Initial": sl,
                    "TP": tp,
                    "Contratti": contratti_consigliati,
                    "Prezzo Uscita Fineco": "--",
                    "Esito": "IN CORSO ⏳",
                    "Profitto (€)": 0.0
                }
            else:
                st.error("Errore nel caricamento dati.")
        except Exception as e:
            st.error(f"Errore tecnico: {e}")

# 2. CONFERMA
if 'nuovo_trade_temp' in st.session_state:
    st.markdown("---")
    st.write("### 🗹 Confirm Esecuzione Fineco")
    prezzo_reale = st.number_input("Prezzo Reale Eseguito:", value=st.session_state.nuovo_trade_temp["Trigger"], step=0.001, format="%.3f")
    giuro = st.checkbox("Accetto la size consigliata in base alle Stelle del segnale.")
    
    if st.button("SALVA OPERAZIONE IN CORSO"):
        if giuro:
            st.session_state.nuovo_trade_temp["Trigger"] = prezzo_reale
            nuovo_df = pd.DataFrame([st.session_state.nuovo_trade_temp])
            diario_df = pd.concat([diario_df, nuovo_df], ignore_index=True)
            diario_df.to_csv(FILE_DIARIO, index=False)
            st.success("Operazione registrata!")
            del st.session_state.nuovo_trade_temp
            st.rerun()

# 3. PANNELLO LIVE E STORICO
st.markdown("---")
st.header("📝 Pannello Controllo Operazioni Live & Storico")
posizioni_aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]

if not posizioni_aperte.empty:
    for idx, row in posizioni_aperte.iterrows():
        with st.expander(f"Modifica Trade | {row['Qualità']} | {row['Direzione']} da {row['Trigger']}"):
            prezzo_uscita = st.number_input(f"Prezzo uscita Fineco:", value=row["Trigger"], step=0.001, format="%.3f", key=f"out_{idx}")
            esito_scelto = st.selectbox("Esito:", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
            
            if st.button("SALVA CHIUSURA", key=f"btn_{idx}"):
                punti = (prezzo_uscita - row["Trigger"]) if row["Direzione"] == "LONG" else (row["Trigger"] - prezzo_uscita)
                profitto = punti * 100 * row["Contratti"]
                diario_df.at[idx, "Prezzo Uscita Fineco"] = prezzo_uscita
                diario_df.at[idx, "Esito"] = esito_scelto
                diario_df.at[idx, "Profitto (€)"] = round(profitto, 2)
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.rerun()

# 4. BUG FIX APPLICATO QUI (.map() al posto di .applymap())
if not diario_df.empty:
    st.write("### Diario Completo")
    def colora_esito(val):
        if val == "GAIN ✅": return 'background-color: rgba(40, 167, 69, 0.2)'
        elif val == "LOSS ❌": return 'background-color: rgba(220, 53, 69, 0.2)'
        elif val == "IN CORSO ⏳": return 'background-color: rgba(255, 193, 7, 0.2)'
        return ''
    
    # Visualizzazione pulita e robusta
    st.dataframe(diario_df.style.map(colora_esito, subset=['Esito']))
else:
    st.info("Nessun trade registrato nel database.")
