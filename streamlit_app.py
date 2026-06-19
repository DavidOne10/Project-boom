import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import os
from datetime import datetime

# Configurazione della pagina dell'applicazione
st.set_page_config(page_title="VST Trading IA", page_icon="🔮", layout="centered")

st.title("🔮 VTI Trading System - Beta App")
st.write("Generazione segnali intraday con DATI IN TEMPO REALE allineati ai CFD di Fineco.")

# --- INPUT UTENTE E PORTAFOGLIO ---
st.sidebar.header("⚙️ Impostazioni Portafoglio")
capitale_partenza = st.sidebar.number_input("💵 Capitale Iniziale (€):", min_value=100.0, value=2000.0, step=100.0)
budget_inserito = st.number_input("💰 Budget per Calcolo Rischio (€):", min_value=100.0, value=capitale_partenza, step=100.0)

if st.button("🚀 GENERA / AGGIORNA SEGNALE OPERATIVO"):
    with st.spinner("📡 Recuperando le quotazioni istantanee e ricalcolando i livelli..."):
        
        # 1. SCARICAMENTO DATI STORICI PER IA
        ticker_wti = yf.Ticker("CL=F")
        dati = ticker_wti.history(period="60d", interval="1h")
        
        if dati.empty:
            st.error("❌ Errore nel recupero dati dal server. Riprova tra qualche istante.")
            st.stop()
            
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)

        # 2. INDICATORI TECNICI
        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()
        dati['Target'] = np.where(dati['Close'].shift(-5) > dati['Close'], 1, 0)

        # RSI
        delta = dati['Close'].diff()
        guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = guadagno / perdita
        dati['RSI'] = 100 - (100 / (1 + rs))

        # Bollinger & Volatilità
        Componente_Volatilitata = dati['Close'].rolling(window=20).std()
        dati['Banda_Alta'] = dati['Media_20'] + (Componente_Volatilitata * 2)
        dati['Banda_Bassa'] = dati['Media_20'] - (Componente_Volatilitata * 2)
        dati['Dist_Media20'] = (dati['Close'] - dati['Media_20']) / dati['Media_20']
        dati['Dist_Media50'] = (dati['Close'] - dati['Media_50']) / dati['Media_50']
        dati['Larghezza_Bande'] = (dati['Banda_Alta'] - dati['Banda_Bassa']) / dati['Media_20']

        # MACD
        k = dati['Close'].ewm(span=12, adjust=False).mean()
        d = dati['Close'].ewm(span=26, adjust=False).mean()
        dati['MACD'] = k - d
        dati['MACD_Signal'] = dati['MACD'].ewm(span=9, adjust=False).mean()
        dati['MACD_Hist'] = dati['MACD'] - dati['MACD_Signal']

        # Pulizia totale anti-crash
        dati = dati.replace([np.inf, -np.inf], np.nan)
        dati_ia = dati.dropna().copy()

        # 3. ADDESTRAMENTO MODELLO RAPIDO
        variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                     'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

        X_train = dati_ia[variabili]
        y_train = dati_ia['Target']

        modello_ia = RandomForestClassifier(n_estimators=150, min_samples_leaf=5, random_state=42)
        modello_ia.fit(X_train, y_train)

        # 4. PREDIZIONE
        ultimo_dato = dati_ia[variabili].iloc[-1:]
        probabilita = modello_ia.predict_proba(ultimo_dato)[0]
        direzione_predetta = modello_ia.predict(ultimo_dato)[0]
        qualita_segnale = probabilita[direzione_predetta] * 100

        # --- ESTRAZIONE PREZZO LIVE ULTRA-RAPIDO (TICKER LIVE) ---
        try:
            prezzo_attuale = ticker_wti.fast_info['lastPrice']
            if prezzo_attuale is None or np.isnan(prezzo_attuale):
                prezzo_attuale = dati_ia['Close'].iloc[-1]
        except:
            prezzo_attuale = dati_ia['Close'].iloc[-1]

        rsi_attuale = dati_ia['RSI'].iloc[-1]
        macd_attuale = dati_ia['MACD'].iloc[-1]
        macd_sig_attuale = dati_ia['MACD_Signal'].iloc[-1]

        # Money Management
        if qualita_segnale < 55:
            percentuale_rischio_base = 0.01
        elif qualita_segnale < 65:
            percentuale_rischio_base = 0.02
        else:
            percentuale_rischio_base = 0.03

        somma_da_rischiare_eur = budget_inserito * percentuale_rischio_base

        # Geometria dei Supporti e Resistenze
        df_grafico = dati_ia.copy()
        finestra_nodi = 24
        df_grafico['Minimo_Locale'] = df_grafico['Close'].rolling(window=finestra_nodi, center=True).min()
        df_grafico['Massimo_Locale'] = df_grafico['Close'].rolling(window=finestra_nodi, center=True).max()

        supporti = df_grafico[df_grafico['Close'] == df_grafico['Minimo_Locale']]['Close'].unique()
        resistenze = df_grafico[df_grafico['Close'] == df_grafico['Massimo_Locale']]['Close'].unique()

        supporti_vicini = sorted([s for s in supporti if s < prezzo_attuale])[-2:]
        resistenze_vicine = sorted([r for r in resistenze if r > prezzo_attuale])[:2]

        # REGOLE RIGIDE SULLA DISTANZA PER INTRADAY
        STOP_MAX_TOLLERATO = 0.60  
        RAPPORTO_RR = 1.2      

        # --- LOGICA CALCOLO LIVELLI IN LIVE STREAMING ---
        ingresso_vst = prezzo_attuale

        if direzione_predetta == 1:  # CASO LONG
            stop_teorico = supporti_vicini[-1] if len(supporti_vicini) > 0 else ingresso_vst - STOP_MAX_TOLLERATO
            if (ingresso_vst - stop_teorico) > STOP_MAX_TOLLERATO or (ingresso_vst - stop_teorico) <= 0:
                stop_loss_vst = ingresso_vst - STOP_MAX_TOLLERATO
            else:
                stop_loss_vst = stop_teorico
                
            distanza_stop = ingresso_vst - stop_loss_vst
            take_profit_vst = ingresso_vst + (distanza_stop * RAPPORTO_RR)
                
        else:  # CASO SHORT
            stop_teorico = resistenze_vicine[0] if len(resistenze_vicine) > 0 else ingresso_vst + STOP_MAX_TOLLERATO
            if (stop_teorico - ingresso_vst) > STOP_MAX_TOLLERATO or (stop_teorico - ingresso_vst) <= 0:
                stop_loss_vst = ingresso_vst + STOP_MAX_TOLLERATO
            else:
                stop_loss_vst = stop_teorico
                
            distanza_stop = stop_loss_vst - ingresso_vst
            take_profit_vst = ingresso_vst - (distanza_stop * RAPPORTO_RR)

        # --- INTERFACCIA DI OUTPUT AGGIORNATA ---
        st.success("✅ Statistiche e livelli ricalcolati sul prezzo corrente!")
        st.markdown(f"### 🧠 Direzione: **{'LONG (Acquisto)' if direzione_predetta == 1 else 'SHORT (Vendita)'}**")
        
        col_rilievo1, col_rilievo2 = st.columns(2)
        col_rilievo1.metric(label="🔍 Prezzo Spot Rilevato", value=f"{prezzo_attuale:.2f} USD")
        col_rilievo2.metric(label="🎯 Affidabilità Segnale IA", value=f"{qualita_segnale:.2f}%")
        
        # Blocco Orario Italiano
        ora_utc = datetime.utcnow()
        ora_italiana_ora = (ora_utc.hour + 2) % 24
        ora_italiana_stringa = f"{ora_italiana_ora:02d}:{ora_utc.minute:02d}:{ora_utc.second:02d}"
        
        st.caption(f"Ultimo ricalcolo effettuato alle ore italiane: {ora_italiana_stringa}")
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        col1.metric(label="📊 Rischio Posizione", value=f"{percentuale_rischio_base * 100:.1f}%")
        col2.metric(label="🔥 Entità Puntata (Rischio Max)", value=f"{somma_da_rischiare_eur:.2f} €")
        
        st.markdown("---")
        st.markdown("### 🚨 LIVELLI AGGIORNATI DA APPLICARE SU FINECO:")
        st.info(f"🟩 PREZZO DI INGRESSO REALE: {ingresso_vst:.2f} USD")
        st.error(f"🛑 LIVELLO STOP LOSS CALCOLATO: {stop_loss_vst:.2f} USD")
        st.success(f"💰 LIVELLO TAKE PROFIT CALCOLATO: {take_profit_vst:.2f} USD")

# --- SEZIONE AGENDA / DIARIO DI TRADING ---
st.markdown("---")
st.header("📅 Agenda e Diario di Trading Real-Time")
st.write("Registra qui l'esito dei tuoi trade eseguiti su Fineco per tracciare le performance.")

FILE_DIARIO = "diario_trading.csv"

if os.path.exists(FILE_DIARIO):
    try:
        df_diario = pd.read_csv(FILE_DIARIO)
    except:
        df_diario = pd.DataFrame(columns=["Data", "Strumento", "Tipo", "Ingresso", "Esito", "Profitto_Perdita_EUR"])
else:
    df_diario = pd.DataFrame(columns=["Data", "Strumento", "Tipo", "Ingresso", "Esito", "Profitto_Perdita_EUR"])

with st.form("nuovo_trade_form"):
    st.subheader("📝 Registra Nuova Operazione Chiusa")
    col_d1, col_d2, col_d3 = st.columns(3)
    
    data_trade = col_d1.date_input("Data Operazione", datetime.now())
    tipo_trade = col_d2.selectbox("Tipo", ["LONG", "SHORT"])
    ingresso_reale = col_d3.number_input("Prezzo Ingresso (USD)", min_value=0.0, value=74.0, step=0.01)
    
    col_d4, col_d5 = st.columns(2)
    esito_trade = col_d4.selectbox("Esito", ["Take Profit (Gain)", "Stop Loss (Loss)", "Chiusura Manuale"])
    pnl_valore = col_d5.number_input("Profitto / Perdita Reale (€)", value=0.0, step=10.0)
    
    submit_trade = st.form_submit_button("💾 Salva in Agenda")

if submit_trade:
    nuovo_rigo = pd.DataFrame([{
        "Data": data_trade.strftime("%Y-%m-%d"),
        "Strumento": "Petrolio (WTI)",
        "Tipo": tipo_trade,
        "Ingresso": ingresso_reale,
        "Esito": esito_trade,
        "Profitto_Perdita_EUR": pnl_valore
    }])
    df_diario = pd.concat([df_diario, nuovo_rigo], ignore_index=True)
    df_diario.to_csv(FILE_DIARIO, index=False)
    st.success("📌 Trade registrato con successo!")
    st.rerun()

# --- RENDICONTO E BILANCIO DINAMICO ---
if not df_diario.empty:
    st.subheader("📊 Statistiche Performance Realizzate")
    
    tot_trade = len(df_diario)
    trade_vinti = len(df_diario[df_diario['Profitto_Perdita_EUR'] > 0])
    win_rate = (trade_vinti / tot_trade) * 100 if tot_trade > 0 else 0
    pnl_totale = df_diario['Profitto_Perdita_EUR'].sum()
    
    capitale_attuale = capitale_partenza + pnl_totale
    performance_percentuale = (pnl_totale / capitale_partenza) * 100 if capitale_partenza > 0 else 0
    
    c_cap1, c_cap2, c_cap3 = st.columns(3)
    c_cap1.metric("💵 Capitale Iniziale", f"{capitale_partenza:,.2f} €")
    c_cap2.metric("📈 Capitale Attuale", f"{capitale_attuale:,.2f} €", delta=f"{pnl_totale:+.2f} €")
    c_cap3.metric("📊 Rendimento Storico", f"{performance_percentuale:+.2f}%")
    
    st.markdown(" ")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Operazioni Totali", f"{tot_trade}")
    col_s2.metric("Win Rate %", f"{win_rate:.1f}%")
    
    st.subheader("🗂️ Storico Log Operazioni")
    st.dataframe(df_diario, use_container_width=True)
    
    st.markdown("---")
    st.subheader("🛠️ Correzione Errori")
    col_del1, col_del2 = st.columns([2, 1])
    
    riga_da_eliminare = col_del1.selectbox("Seleziona il numero di riga da eliminare:", options=df_diario.index.tolist())
    
    if col_del2.button("🗑️ Elimina Riga"):
        df_diario = df_diario.drop(index=riga_da_eliminare).reset_index(drop=True)
        df_diario.to_csv(FILE_DIARIO, index=False)
        st.warning(f"Riga {riga_da_eliminare} eliminata.")
        st.rerun()
        
    if st.button("🚨 Svuota Interamente l'Agenda"):
        if os.path.exists(FILE_DIARIO):
            os.remove(FILE_DIARIO)
        st.error("Tutta l'agenda è stata svuotata.")
        st.rerun()
else:
    st.info("L'agenda è vuota. Registra il tuo primo trade usando il modulo sopra!")
