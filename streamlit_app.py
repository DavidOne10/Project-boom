import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Pure AI Trading", layout="centered")

st.title("🤖 V-Alpha PRO | Random Forest AI (Pure Mode)")

# --- 1. MOTORE ADDESTRAMENTO RANDOM FOREST (DAILY) ---
@st.cache_data(ttl=3600)  # Aggiorna e riaddestra il modello ogni ora con i nuovi dati
def addestra_modello_ia(ticker):
    try:
        # Scarica lo storico Daily a 3 anni
        dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True)
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)
            
        if dati.empty or len(dati) < 100:
            return None, None

        # Indicatori Tecnici
        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()

        # TARGET D+1 (Previsione a 1 giorno)
        dati['Target'] = np.where(dati['Close'].shift(-1) > dati['Close'], 1, 0)

        # RSI (14 periodi)
        delta = dati['Close'].diff()
        guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = guadagno / perdita
        dati['RSI'] = 100 - (100 / (1 + rs))

        # Bande di Bollinger & Volatilità
        std20 = dati['Close'].rolling(window=20).std()
        dati['Banda_Alta'] = dati['Media_20'] + (std20 * 2)
        dati['Banda_Bassa'] = dati['Media_20'] - (std20 * 2)
        dati['Dist_Media20'] = (dati['Close'] - dati['Media_20']) / dati['Media_20']
        dati['Dist_Media50'] = (dati['Close'] - dati['Media_50']) / dati['Media_50']
        dati['Larghezza_Bande'] = (dati['Banda_Alta'] - dati['Banda_Bassa']) / dati['Media_20']

        # MACD
        k = dati['Close'].ewm(span=12, adjust=False).mean()
        d = dati['Close'].ewm(span=26, adjust=False).mean()
        dati['MACD'] = k - d
        dati['MACD_Signal'] = dati['MACD'].ewm(span=9, adjust=False).mean()
        dati['MACD_Hist'] = dati['MACD'] - dati['MACD_Signal']

        variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                     'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

        # Dataset per l'addestramento (esclude l'ultima riga che ha Target NaN)
        dati_training = dati.dropna(subset=variabili + ['Target'])
        
        X = dati_training[variabili]
        y = dati_training['Target']

        # Modello Random Forest Classifier
        modello = RandomForestClassifier(n_estimators=150, min_samples_leaf=5, random_state=42)
        modello.fit(X, y)

        # Estrazione dell'ultimo dato disponibile con le 11 variabili aggiornate ad OGGI
        ultimo_dato_fresco = dati[variabili].iloc[-1:]

        return modello, ultimo_dato_fresco

    except Exception as e:
        st.error(f"Errore nell'addestramento IA: {e}")
        return None, None

# --- 2. SCARICAMENTO DATI LIVE INTRADAY ---
@st.cache_data(ttl=60)
def carica_dati_intraday():
    for ticker in ["CL=F", "BZ=F", "USOIL=X"]:
        try:
            df = yf.download(ticker, period="2d", interval="5m", auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty and 'Close' in df.columns:
                return df, ticker
        except Exception:
            continue
    return None, None

# --- ESECUZIONE SISTEMA ---
df_5m, ticker_attivo = carica_dati_intraday()

if df_5m is None:
    st.error("⚠️ Connessione ai dati di mercato non disponibile. Riprova tra un minuto.")
    st.stop()

modello_rf, ultimo_dato_ia = addestra_modello_ia(ticker_attivo)

if modello_rf is None or ultimo_dato_ia is None:
    st.error("⚠️ Errore nell'inizializzazione del modello IA.")
    st.stop()

# PREDIZIONE IA PURA
probabilita = modello_rf.predict_proba(ultimo_dato_ia)[0]
predizione_ia = modello_rf.predict(ultimo_dato_ia)[0]  # 1 = LONG, 0 = SHORT
confidenza_ia = probabilita[predizione_ia] * 100

# Parametri Intraday Live
prezzo_live = round(float(df_5m['Close'].iloc[-1]), 3)
oggi = df_5m.index[-1].date()
df_today = df_5m[df_5m.index.date == oggi]

if df_today.empty:
    df_today = df_5m.tail(50)

high_mattina = float(df_today['High'].max())
low_mattina = float(df_today['Low'].min())
range_totale = high_mattina - low_mattina

supporto_operativo = round(low_mattina + (range_totale * 0.2), 3)
resistenza_operativa = round(high_mattina - (range_totale * 0.2), 3)
atr = round(range_totale / 5, 3)

# --- GESTIONE CAPITALE E RISCHIO ---
st.sidebar.header("💰 Gestione Capitale")
capitale_utente = st.sidebar.number_input("Inserisci Capitale (€):", value=10000.0, step=500.0)

if confidenza_ia < 55:
    pct_rischio = 0.01
elif confidenza_ia < 65:
    pct_rischio = 0.02
else:
    pct_rischio = 0.03

euro_da_rischiare = capitale_utente * pct_rischio

# --- PANNELLO METRICHE LIVE ---
st.markdown(f"**Asset Monitorato:** `{ticker_attivo}` | Aggiornato ogni 60s")

col1, col2, col3 = st.columns(3)
col1.metric("Supporto V-Alpha", supporto_operativo)
col2.metric("Prezzo WTI Live", prezzo_live)
col3.metric("Resistenza V-Alpha", resistenza_operativa)

st.markdown("---")

# --- VERDETTO IA PURA ---
st.subheader("🔮 Segnale Random Forest AI")

c_pred1, c_pred2 = st.columns(2)

with c_pred1:
    st.markdown("### 🏹 Direzione Suggerita")
    
    if predizione_ia == 1:
        st.success("PREDIZIONE IA: LONG 🟢")
        direzione = "LONG"
        livello_ingresso = supporto_operativo
        take_profit = round(supporto_operativo + (atr * 2.0), 3)
        stop_loss = round(low_mattina - (atr * 0.2), 3)
    else:
        st.error("PREDIZIONE IA: SHORT 🔴")
        direzione = "SHORT"
        livello_ingresso = resistenza_operativa
        take_profit = round(resistenza_operativa - (atr * 2.0), 3)
        stop_loss = round(high_mattina + (atr * 0.2), 3)

with c_pred2:
    st.markdown("### 📊 Affidabilità e Rischio")
    st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")
    st.metric("Rischio Posizione", f"{pct_rischio*100:.0f}% ({euro_da_rischiare:.2f} €)")

# --- PIANO OPERATIVO ISTANTANEO ---
st.markdown("---")
st.subheader("📋 Ordini Pronti per l'Esecuzione")

c_ord1, c_ord2, c_ord3 = st.columns(3)
c_ord1.metric(f"Ingresso a Limite ({direzione})", livello_ingresso)
c_ord2.metric("Take Profit (Target)", take_profit)
c_ord3.metric("Stop Loss (Protezione)", stop_loss)
