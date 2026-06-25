import streamlit as st
import yfinance as yf
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import os
from datetime import datetime

# Configurazione della pagina dell'applicazione
st.set_page_config(page_title="VST Trading IA Pro+", page_icon="🔮", layout="centered")

st.title("🔮 VTI Trading System - Volatilità & Fattibilità v3")
st.write("Ordini condizionati ottimizzati sulla volatilità reale (ATR) per evitare la perdita dei trend.")

# --- INPUT UTENTE E PORTAFOGLIO ---
st.sidebar.header("⚙️ Impostazioni Portafoglio")
capitale_partenza = st.sidebar.number_input("💵 Capitale Iniziale (€):", min_value=100.0, value=2000.0, step=100.0)
budget_inserito = st.number_input("💰 Budget per Calcolo Rischio (€):", min_value=100.0, value=capitale_partenza, step=100.0)

if st.button("🚀 CALCOLA LIVELLI STRATEGICI"):
    with st.spinner("📡 Analizzando volatilità dinamica e calcolando probabilità di aggancio..."):
        
        # 1. SCARICAMENTO DATI STORICI PER IA
        ticker_wti = yf.Ticker("CL=F")
        dati = ticker_wti.history(period="60d", interval="1h")
        
        if dati.empty:
            st.error("❌ Errore nel recupero dati dal server. Riprova tra qualche istante.")
            st.stop()
            
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)

        # 2. INDICATORI TECNICI & CALCOLO VOLATILITÀ REALE (ATR)
        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()
        dati['Target'] = np.where(dati['Close'].shift(-5) > dati['Close'], 1, 0)

        # Calcolo ATR (Calcolatore di volatilità nativo)
        high_low = dati['High'] - dati['Low']
        high_close = np.abs(dati['High'] - dati['Close'].shift())
        low_close = np.abs(dati['Low'] - dati['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        dati['ATR'] = true_range.rolling(14).mean()

        # RSI & Bollinger
        delta = dati['Close'].diff()
        guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = guadagno / perdita
        dati['RSI'] = 100 - (100 / (1 + rs))
        
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

        dati = dati.replace([np.inf, -np.inf], np.nan).dropna()

        # 3. ADDESTRAMENTO MODELLO
        variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                     'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
        X_train = dati[variabili]
        y_train = dati['Target']
        modello_ia = RandomForestClassifier(n_estimators=150, min_samples_leaf=5, random_state=42)
        modello_ia.fit(X_train, y_train)

        # 4. PREDIZIONE
        ultimo_dato = dati[variabili].iloc[-1:]
        probabilita = modello_ia.predict_proba(ultimo_dato)[0]
        direzione_predetta = modello_ia.predict(ultimo_dato)[0]
        qualita_segnale = probabilita[direzione_predetta] * 100

        # Controllo Orario e Volatilità Corrente
        ora_utc = datetime.utcnow()
        ora_italiana_ora = (ora_utc.hour + 2) % 24
        ora_italiana_stringa = f"{ora_italiana_ora:02d}:{ora_utc.minute:02d}:{ora_utc.second:02d}"
        sessione_pomeridiana = ora_italiana_ora >= 15
        
        atr_attuale = dati['ATR'].iloc[-1]
        # Impediamo all'ATR di assumere valori assurdi (cap minimo e massimo di sicurezza)
        atr_flessibile = max(min(atr_attuale, 0.80), 0.40) 

        # --- RECUPERO PREZZO LIVE ---
        try:
            prezzo_attuale = ticker_wti.fast_info['lastPrice']
            if prezzo_attuale is None or np.isnan(prezzo_attuale):
                prezzo_attuale = dati['Close'].iloc[-1]
        except:
            prezzo_attuale = dati['Close'].iloc[-1]

        # Geometria dei nodi per i livelli
        df_grafico = dati.copy()
        df_grafico['Minimo_Locale'] = df_grafico['Close'].rolling(window=12, center=True).min()
        df_grafico['Massimo_Locale'] = df_grafico['Close'].rolling(window=12, center=True).max()
        supporti = df_grafico[df_grafico['Close'] == df_grafico['Minimo_Locale']]['Close'].unique()
        resistenze = df_grafico[df_grafico['Close'] == df_grafico['Massimo_Locale']]['Close'].unique()
        supporti_vicini = sorted([s for s in supporti if s < prezzo_attuale])
        resistenze_vicine = sorted([r for r in resistenze if r > prezzo_attuale])

        # --- APPLICAZIONE FILTRO ANTICRACH POMERIDIANO ---
        if sessione_pomeridiana:
            macd_attuale = dati['MACD'].iloc[-1]
            if direzione_predetta == 0 and macd_attuale > 0:
                qualita_segnale -= 20

        # --- CALCOLO LIVELLI DINAMICI (ATR-BASED) ---
        tolleranza_ingresso = atr_flessibile * 0.30  # Distanza ottimale basata sul respiro del mercato

        if direzione_predetta == 1:  # LONG
            trigger_teorico = supporti_vicini[-1] if len(supporti_vicini) > 0 else prezzo_attuale - tolleranza_ingresso
            # Controllo Fuga: Se il livello grafico è troppo lontano, stringiamo l'ingresso per non perdere il viaggio
            if (prezzo_attuale - trigger_teorico) > (atr_flessibile * 0.8):
                trigger_teorico = prezzo_attuale - (atr_flessibile * 0.25)
                
            stop_loss_vst = trigger_teorico - atr_flessibile
            take_profit_vst = trigger_teorico + (atr_flessibile * 1.4) # Target più ambizioso nei trend sani
        else:  # SHORT
            trigger_teorico = resistenze_vicine[0] if len(resistenze_vicine) > 0 else prezzo_attuale + tolleranza_ingresso
            if (trigger_teorico - prezzo_attuale) > (atr_flessibile * 0.8):
                trigger_teorico = prezzo_attuale + (atr_flessibile * 0.25)
                
            stop_loss_vst = trigger_teorico + atr_flessibile
            take_profit_vst = trigger_teorico - (atr_flessibile * 1.4)

        # Valutazione della Fattibilità del Trigger (Distanza dallo spot rispetto all'ATR)
        distanza_assoluta = abs(prezzo_attuale - trigger_teorico)
        if distanza_assoluta <= (atr_flessibile * 0.20):
            fattibilita = "🟢 ALTA (Esecuzione Imminente)"
            colore_fatt = "green"
        elif distanza_assoluta <= (atr_flessibile * 0.50):
            fattibilita = "🟡 MEDIA (Attendi oscillazione)"
            colore_fatt = "orange"
        else:
            fattibilita = "🔴 BASSA (Il mercato corre veloce - Valuta ingresso manuale aggressivo)"
            colore_fatt = "red"

        # Money Management
        if qualita_segnale < 55:
            percentuale_rischio_base = 0.01
        elif qualita_segnale < 65:
            percentuale_rischio_base = 0.02
        else:
            percentuale_rischio_base = 0.03
        somma_da_rischiare_eur = budget_inserito * percentuale_rischio_base

        # --- OUTPUT INTERFACCIA ---
        st.success("🎯 Livelli ricalcolati con successo sulla volatilità corrente!")
        
        if sessione_pomeridiana:
            st.warning("⚠️ Sessione Americana Attiva: Filtri anti-rumore attivati.")

        st.markdown(f"### 🧠 Direzione Stimata: **{'LONG (Acquisto)' if direzione_predetta == 1 else 'SHORT (Vendita)'}**")
        
        col_rilievo1, col_rilievo2 = st.columns(2)
        col_rilievo1.metric(label="🔍 Prezzo Spot Corrente", value=f"{prezzo_attuale:.2f} USD")
        col_rilievo2.metric(label="🎯 Affidabilità Filtrata", value=f"{qualita_segnale:.2f}%")
        
        st.markdown(f"📊 **Possibilità di Raggiungimento del Trigger:** :{colore_fatt}[{fattibilita}]")
        st.caption(f"Volatilità Oraria Rilevata (ATR): {atr_attuale:.2f} USD | Ora italiana: {ora_italiana_stringa}")
        st.markdown("---")
        
        st.markdown("### 🚨 COORDINATE AGGIORNATE DA INSERIRE SU FINECO:")
        st.info(f"🟩 INGRESSO TARGET (Trigger): **{trigger_teorico:.2f} USD**")
        st.error(f"🛑 STOP LOSS DINAMICO (Protezione): **{stop_loss_vst:.2f} USD** (Scarto: {abs(trigger_teorico-stop_loss_vst):.2f})")
        st.success(f"💰 TAKE PROFIT DINAMICO (Target Viaggio): **{take_profit_vst:.2f} USD** (Scarto: {abs(trigger_teorico-take_profit_vst):.2f})")

# --- SEZIONE DIARIO E BACKUP DI SICUREZZA ---
st.markdown("---")
st.header("📅 Agenda e Diario di Trading Real-Time")
st.write("Usa il tasto 'Esporta' sotto prima di chiudere la sessione per salvare lo storico sul tuo dispositivo.")

FILE_DIARIO = "diario_trading.csv"

if os.path.exists(FILE_DIARIO):
    try:
        df_diario = pd.read_csv(FILE_DIARIO)
    except:
        df_diario = pd.DataFrame(columns=["Data", "Strumento", "Tipo", "Ingresso", "Esito", "Profitto_Perdita_EUR"])
else:
    df_diario = pd.DataFrame(columns=["Data", "Strumento", "Tipo", "Ingresso", "Esito", "Profitto_Perdita_EUR"])

with st.form("nuovo_trade_form"):
    st.subheader("📝 Registra Nuova Operazione")
    col_d1, col_d2, col_d3 = st.columns(3)
    data_trade = col_d1.date_input("Data", datetime.now())
    tipo_trade = col_d2.selectbox("Tipo", ["LONG", "SHORT"])
    ingresso_reale = col_d3.number_input("Prezzo Ingresso (USD)", min_value=0.0, value=75.0, step=0.01)
    col_d4, col_d5 = st.columns(2)
    esito_trade = col_d4.selectbox("Esito", ["Take Profit (Gain)", "Stop Loss (Loss)", "Chiusura Manuale"])
    pnl_valore = col_d5.number_input("Profitto / Perdita Reale (€)", value=0.0, step=10.0)
    submit_trade = st.form_submit_button("💾 Salva Temporaneamente")

if submit_trade:
    nuovo_rigo = pd.DataFrame([{"Data": data_trade.strftime("%Y-%m-%d"), "Strumento": "Petrolio (WTI)", "Tipo": tipo_trade, "Ingresso": ingresso_reale, "Esito": esito_trade, "Profitto_Perdita_EUR": pnl_valore}])
    df_diario = pd.concat([df_diario, nuovo_rigo], ignore_index=True)
    df_diario.to_csv(FILE_DIARIO, index=False)
    st.success("📌 Registrato in memoria!")
    st.rerun()

if not df_diario.empty:
    st.subheader("🗂️ Operazioni in Memoria Oggi")
    st.dataframe(df_diario, use_container_width=True)
    csv = df_diario.to_csv(index=False).encode('utf-8')
    st.download_button(label="📥 ESPORTA DIARIO IN CSV", data=csv, file_name=f"diario_trading_{datetime.now().strftime('%Y%m%d')}.csv", mime='text/csv')
