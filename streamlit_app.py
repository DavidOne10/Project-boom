import streamlit as st
import yfinance as yf
import pandas as pd

# Configurazione Pagina
st.set_page_config(page_title="V-Alpha PRO | Predittività", layout="centered")

# --- MOTORE DATI ROBUSTO ---
@st.cache_data(ttl=60)
def get_data():
    # Tenta prima con il WTI, poi fallback su Brent
    for ticker in ["CL=F", "BZ=F"]:
        try:
            df = yf.download(ticker, period="1d", interval="5m", auto_adjust=True)
            if not df.empty:
                return df
        except:
            continue
    return None

st.title("🚀 V-Alpha | Controllo Operativo")
df = get_data()

if df is not None and not df.empty:
    # Calcoli V-Alpha
    prezzo_reale = round(float(df['Close'].iloc[-1]), 3)
    high = float(df['High'].max())
    low = float(df['Low'].min())
    
    supporto = round(low + (high - low) * 0.2, 3)
    resistenza = round(high - (high - low) * 0.2, 3)
    atr = round((high - low) / 5, 3)

    # --- DASHBOARD LIVE ---
    c1, c2, c3 = st.columns(3)
    c1.metric("Supporto", supporto)
    c2.metric("Prezzo Live", prezzo_reale)
    c3.metric("Resistenza", resistenza)

    st.markdown("---")

    # --- PANELLO DI PREDITTIVITÀ ---
    st.subheader("🔮 Pannello di Predittività Attiva")
    
    dist_supp = prezzo_reale - supporto
    dist_res = resistenza - prezzo_reale

    col_p1, col_p2 = st.columns(2)

    with col_p1:
        st.markdown("### 🏹 Direzione")
        if dist_supp < dist_res:
            st.success("PREDIZIONE: LONG in arrivo")
            target = round(prezzo_reale + (atr * 2.0), 3)
        else:
            st.error("PREDIZIONE: SHORT in arrivo")
            target = round(prezzo_reale - (atr * 2.0), 3)

    with col_p2:
        st.markdown("### ⏳ Qualità Segnale")
        min_dist = min(dist_supp, dist_res)
        qualita = "🔥 CALDO (Entrata vicina)" if min_dist < (atr * 2) else "❄️ FREDDO (In attesa)"
        st.write(f"Stato: **{qualita}**")
        st.write(f"Distanza: **{round(min_dist, 3)}**")

    # --- PIANO OPERATIVO ---
    st.markdown("---")
    st.subheader("📋 Piano di Esecuzione")
    if dist_supp < dist_res:
        st.info(f"Monitora Supporto **{supporto}**. Target suggerito: **{target}**")
    else:
        st.info(f"Monitora Resistenza **{resistenza}**. Target suggerito: **{target}**")

else:
    st.error("Errore: Impossibile scaricare dati. Riprova tra un minuto.")
