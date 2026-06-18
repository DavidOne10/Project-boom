
import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

# Configurazione della pagina dell'applicazione
st.set_page_config(page_title="VST Trading IA", page_icon="🔮", layout="centered")

st.title("🔮 VTI Trading System - Beta App")
st.write("Generazione segnali intraday con filtri dinamici di Breakout su Supporti/Resistenze.")

# --- INPUT UTENTE ---
budget_inserito = st.number_input("💰 Inserisci il budget sul tuo conto (€):", min_value=100.0, value=40000.0, step=100.0)

if st.button("🚀 GENERA SEGNALE OPERATIVO"):
    with st.spinner("📡 Analizzando la forza del trend (MACD/RSI)..."):
        
        # 1. SCARICAMENTO DATI
        dati = yf.download("CL=F", period="730d", interval="1h")
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

        # 4. PREDIZIONE ULTIMO DATO
        ultimo_dato = dati_ia[variabili].iloc[-1:]
        probabilita = modello_ia.predict_proba(ultimo_dato)[0]
        direzione_predetta = modello_ia.predict(ultimo_dato)[0]
        qualita_segnale = probabilita[direzione_predetta] * 100

        # Estrazione valori attuali per la logica di Breakout
        prezzo_attuale = df_grafico = dati_ia['Close'].iloc[-1]
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

        STOP_MINIMO_SICUREZZA = 1.20 
        RAPPORTO_RR_MINIMO = 1.5 

        # --- LOGICA DI CALCOLO LIVELLI CON FILTRI MACD/RSI ---
        if direzione_predetta == 1:  # CASO LONG
            ingresso_vst = prezzo_attuale
            
            # Calcolo Stop Loss protetto
            stop_calcolato = supporti_vicini[-1] if len(supporti_vicini) > 0 else ingresso_vst - 1.50
            stop_loss_vst = ingresso_vst - STOP_MINIMO_SICUREZZA if (ingresso_vst - stop_calcolato) < STOP_MINIMO_SICUREZZA else stop_calcolato
            distanza_stop = ingresso_vst - stop_loss_vst
            
            # VALUTAZIONE ROTTURA RESISTENZA (Filtro MACD e RSI)
            # Se MACD incrociato al rialzo e RSI non è ancora in ipercomprato (>65) -> IPOTESI BREAKOUT
            if macd_attuale > macd_sig_attuale and rsi_attuale < 65:
                # Forza un target ampio ignorando resistenze troppo vicine
                take_profit_vst = ingresso_vst + (distanza_stop * RAPPORTO_RR_MINIMO)
            else:
                tp_teorico = resistenze_vicine[0] if len(resistenze_vicine) > 0 else ingresso_vst + (distanza_stop * RAPPORTO_RR_MINIMO)
                # Protezione finale R:R minimo
                take_profit_vst = tp_teorico if (tp_teorico - ingresso_vst) >= (distanza_stop * RAPPORTO_RR_MINIMO) else ingresso_vst + (distanza_stop * RAPPORTO_RR_MINIMO)
                
        else:  # CASO SHORT
            ingresso_vst = prezzo_attuale
            
            # Calcolo Stop Loss protetto
            stop_calcolato = resistenze_vicine[0] if len(resistenze_vicine) > 0 else ingresso_vst + 1.50
            stop_loss_vst = ingresso_vst + STOP_MINIMO_SICUREZZA if (stop_calcolato - ingresso_vst) < STOP_MINIMO_SICUREZZA else stop_calcolato
            distanza_stop = stop_loss_vst - ingresso_vst
            
            # VALUTAZIONE ROTTURA SUPPORTO (Filtro MACD e RSI)
            # Se MACD incrociato al ribasso e RSI ha spazio per scendere (>35) -> IPOTESI BREAKOUT
            if macd_attuale < macd_sig_attuale and rsi_attuale > 35:
                # Forza un target ampio ignorando supporti troppo vicini
                take_profit_vst = ingresso_vst - (distanza_stop * RAPPORTO_RR_MINIMO)
            else:
                tp_teorico = supporti_vicini[-1] if len(supporti_vicini) > 0 else ingresso_vst - (distanza_stop * RAPPORTO_RR_MINIMO)
                # Protezione finale R:R minimo
                take_profit_vst = tp_teorico if (ingresso_vst - tp_teorico) >= (distanza_stop * RAPPORTO_RR_MINIMO) else ingresso_vst - (distanza_stop * RAPPORTO_RR_MINIMO)

        # --- INTERFACCIA DI OUTPUT ---
        st.success("✅ Livelli calcolati con validazione di Momentum (MACD/RSI)!")
        st.markdown(f"### 🧠 Direzione: **{'LONG (Acquisto)' if direzione_predetta == 1 else 'SHORT (Vendita)'}**")
        st.metric(label="🎯 Affidabilità Segnale IA", value=f"{qualita_segnale:.2f}%")
        
        st.markdown("---")
        st.markdown("### 🚨 LIVELLI DA USARE PER IL KNOCKOUT FINECO:")
        st.info(f"🟩 PREZZO DI INGRESSO (TRIGGER): {ingresso_vst:.2f} USD")
        st.error(f"🛑 LIVELLO STOP LOSS (Barriera Knockout vicina a): {stop_loss_vst:.2f} USD")
        st.success(f"💰 LIVELLO TAKE PROFIT: {take_profit_vst:.2f} USD")
