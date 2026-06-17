import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

# Configurazione della pagina dell'applicazione
st.set_page_config(page_title="VST Trading IA", page_icon="🔮", layout="centered")

st.title("🔮 VTI Trading System - Beta App")
st.write("Generazione segnali intraday mirati per le sessioni delle 9:30 e 16:30.")

# --- INPUT UTENTE ---
budget_inserito = st.number_input("💰 Inserisci il budget sul tuo conto (€):", min_value=100.0, value=40000.0, step=100.0)

if st.button("🚀 GENERA SEGNALE OPERATIVO"):
    with st.spinner("📡 Interrogando Yahoo Finance e calcolando gli indicatori..."):
        
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

        dati_ia = dati.dropna()

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

        # Money Management
        if qualita_segnale < 55:
            percentuale_rischio_base = 0.01
        elif qualita_segnale < 65:
            percentuale_rischio_base = 0.02
        else:
            percentuale_rischio_base = 0.03

        somma_da_rischiare = budget_inserito * percentuale_rischio_base

        # Supporti e Resistenze
        df_grafico = dati_ia.copy()
        finestra_nodi = 24
        df_grafico['Minimo_Locale'] = df_grafico['Close'].rolling(window=finestra_nodi, center=True).min()
        df_grafico['Massimo_Locale'] = df_grafico['Close'].rolling(window=finestra_nodi, center=True).max()

        supporti = df_grafico[df_grafico['Close'] == df_grafico['Minimo_Locale']]['Close'].unique()
        resistenze = df_grafico[df_grafico['Close'] == df_grafico['Massimo_Locale']]['Close'].unique()

        prezzo_attuale = df_grafico['Close'].iloc[-1]
        supporti_vicini = sorted([s for s in supporti if s < prezzo_attuale])[-2:]
        resistenze_vicine = sorted([r for r in resistenze if r > prezzo_attuale])[:2]

        STOP_MINIMO_SICUREZZA = 1.20 

        if direzione_predetta == 1:
            ingresso_vst = prezzo_attuale
            stop_calcolato = supporti_vicini[-1] if len(supporti_vicini) > 0 else ingresso_vst - 1.50
            stop_loss_vst = ingresso_vst - STOP_MINIMO_SICUREZZA if (ingresso_vst - stop_calcolato) < STOP_MINIMO_SICUREZZA else stop_calcolato
            take_profit_vst = resistenze_vicine[0] if len(resistenze_vicine) > 0 else ingresso_vst + 2.00
        else:
            ingresso_vst = prezzo_attuale
            stop_calcolato = resistenze_vicine[0] if len(resistenze_vicine) > 0 else ingresso_vst + 1.50
            stop_loss_vst = ingresso_vst + STOP_MINIMO_SICUREZZA if (stop_calcolato - ingresso_vst) < STOP_MINIMO_SICUREZZA else stop_calcolato
            take_profit_vst = supporti_vicini[-1] if len(supporti_vicini) > 0 else ingresso_vst - 2.00

        # --- INTERFACCIA DI OUTPUT RECONDIZIONATA ---
        st.success("✅ Segnale Calcolato!")
        
        st.markdown(f"### 🧠 Direzione: **{'LONG (Acquisto)' if direzione_predetta == 1 else 'SHORT (Vendita)'}**")
        st.metric(label="🎯 Affidabilità Segnale IA", value=f"{qualita_segnale:.2f}%")
        
        col1, col2 = st.columns(2)
        col1.metric(label="📊 Rischio Posizione", value=f"{percentuale_rischio_base * 100:.1f}%")
        col2.metric(label="🔥 Entità Puntata", value=f"{somma_da_rischiare:.2f} €")
        
        st.markdown("---")
        st.markdown("### 🛠️ LIVELLI DA INSERIRE SUL BROKER:")
        st.info(f"🟩 **PREZZO DI INGRESSO (TRIGGER):** {ingresso_vst:.2f} USD")
        st.error(f"🛑 **LIVELLO STOP LOSS (USCITA):** {stop_loss_vst:.2f} USD (Protetto Anti-Hunt)")
        st.success(f"💰 **LIVELLO TAKE PROFIT (TARGET):** {take_profit_vst:.2f} USD")
