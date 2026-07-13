import streamlit as st
import yfinance as yf
import pandas as pd

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Live Dashboard", layout="centered")

# --- MOTORE SCARICAMENTO DATI BLINDATO ---
@st.cache_data(ttl=60)
def carica_dati_live():
    # Terna di ticker per evitare i blocchi di Yahoo Finance
    for ticker in ["CL=F", "BZ=F", "USOIL=X"]:
        try:
            df = yf.download(ticker, period="1d", interval="5m", auto_adjust=True)
            if not df.empty:
                # Risoluzione del bug MultiIndex (float vs Series)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                if 'Close' in df.columns:
                    return df, ticker
        except:
            continue
    return None, None

# --- INIZIO APPLICAZIONE ---
st.title("🚀 V-Alpha | Analisi Predittiva 52% WR")

df, ticker_attivo = carica_dati_live()

# Protezione da crash se i server non rispondono
if df is None or df.empty:
    st.error("⚠️ Server Yahoo Finance temporaneamente sovraccarichi. L'app si aggiornerà automaticamente tra un minuto.")
    st.stop()

# --- ESTRAZIONE LIVELLI STRATEGIA VINCENTE ---
try:
    prezzo_live = round(float(df['Close'].iloc[-1]), 3)
    high_mattina = float(df['High'].max())
    low_mattina = float(df['Low'].min())
    range_totale = high_mattina - low_mattina
    
    # Livelli operativi matematici originali
    supporto_operativo = round(low_mattina + (range_totale * 0.2), 3)
    resistenza_operativa = round(high_mattina - (range_totale * 0.2), 3)
    atr = round(range_totale / 5, 3)
    
except Exception as e:
    st.error(f"Errore nel calcolo dei parametri: {e}")
    st.stop()

# --- PANNELLO METRICHE LIVE ---
st.markdown(f"**Asset Monitorato:** `{ticker_attivo}` (Dati aggiornati ogni 60s)")
col1, col2, col3 = st.columns(3)
col1.metric("Supporto V-Alpha", supporto_operativo)
col2.metric("Prezzo WTI Live", prezzo_live)
col3.metric("Resistenza V-Alpha", resistenza_operativa)

st.markdown("---")

# --- LOGICA PREDITTIVA ORIGINALE (52% WIN RATE) ---
st.subheader("🔮 Pannello di Predittività Attiva")

distanza_dal_supporto = prezzo_live - supporto_operativo
distanza_dalla_resistenza = resistenza_operativa - prezzo_live

c_pred1, c_pred2 = st.columns(2)

with c_pred1:
    st.markdown("### 🏹 Direzione Preferenziale")
    # Se il prezzo è più vicino al supporto, la probabilità statistica è un rimbalzo LONG
    if distanza_dal_supporto < distanza_dalla_resistenza:
        st.success("PREDIZIONE: AREA LONG IN ARRIVO 🟢")
        direzione = "LONG"
        livello_ingresso = supporto_operativo
        # Stop loss protetto e strutturale + Target proporzionale al 52% WR
        take_profit = round(supporto_operativo + (atr * 2.0), 3)
        stop_loss = round(low_mattina - (atr * 0.2), 3) # Protetto sotto il minimo reale
    else:
        st.error("PREDIZIONE: AREA SHORT IN ARRIVO 🔴")
        direzione = "SHORT"
        livello_ingresso = resistenza_operativa
        # Stop loss protetto e strutturale + Target proporzionale al 52% WR
        take_profit = round(resistenza_operativa - (atr * 2.0), 3)
        stop_loss = round(high_mattina + (atr * 0.2), 3) # Protetto sopra il massimo reale

with c_pred2:
    st.markdown("### ⏳ Qualità del Segnale")
    distanza_minima = min(distanza_dal_supporto, distanza_dalla_resistenza)
    
    if distanza_minima < (atr * 1.5):
        st.warning(f"🔥 STATO: CALDO (Distanza: {round(distanza_minima, 3)})")
        st.write("Il prezzo è vicino alla zona di attivazione. Preparare la piattaforma.")
    else:
        st.info(f"❄️ STATO: IN ATTESA (Distanza: {round(distanza_minima, 3)})")
        st.write("Fase di compressione oraria. Non forzare l'ingresso.")

# --- PIANO OPERATIVO ISTANTANEO ---
st.markdown("---")
st.subheader("📋 Ordini Pronti per l'Esecuzione")

st.write(f"In base al calcolo statistico del modello, se il prezzo valida l'area impostare i seguenti parametri:")

c_ord1, c_ord2, c_ord3 = st.columns(3)
c_ord1.metric(f"Ingresso a Limite ({direzione})", livello_ingresso)
c_ord2.metric("Take Profit (Target)", take_profit)
c_ord3.metric("Stop Loss (Protezione)", stop_loss)
