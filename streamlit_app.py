# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Daily KO Clean", layout="wide", page_icon="📈")

st.title("🤖 V-Alpha PRO | Daily Knock-Out (S&P 500) - Version Clean")
st.markdown("---")

# --- 1. CARICAMENTO DATI REALI S&P 500 ---
@st.cache_data(ttl=3600)
def scarica_dati_puliti():
    # Ticker ufficiale S&P 500 senza alterazioni di prezzo sui futures
    dati = yf.download("^GSPC", period="3y", interval="1d", auto_adjust=False, progress=False)
    if isinstance(dati.columns, pd.MultiIndex):
        dati.columns = dati.columns.get_level_values(0)
        
    if dati.empty or len(dati) < 200:
        return None

    # Indicatori tecnici calcolati strictly sulla candela corrente t
    dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
    dati['Media_20'] = dati['Close'].rolling(window=20).mean()
    dati['Media_50'] = dati['Close'].rolling(window=50).mean()

    delta = dati['Close'].diff()
    guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = guadagno / perdita
    dati['RSI'] = 100 - (100 / (1 + rs))

    std20 = dati['Close'].rolling(window=20).std()
    dati['Banda_Alta'] = dati['Media_20'] + (std20 * 2)
    dati['Banda_Bassa'] = dati['Media_20'] - (std20 * 2)
    dati['Dist_Media20'] = (dati['Close'] - dati['Media_20']) / dati['Media_20']
    dati['Dist_Media50'] = (dati['Close'] - dati['Media_50']) / dati['Media_50']
    dati['Larghezza_Bande'] = (dati['Banda_Alta'] - dati['Banda_Bassa']) / dati['Media_20']

    k = dati['Close'].ewm(span=12, adjust=False).mean()
    d = dati['Close'].ewm(span=26, adjust=False).mean()
    dati['MACD'] = k - d
    dati['MACD_Signal'] = dati['MACD'].ewm(span=9, adjust=False).mean()
    dati['MACD_Hist'] = dati['MACD'] - dati['MACD_Signal']

    # TARGET CORRETTO: 1 se la chiusura di DOMANI (t+1) > chiusura di OGGI (t)
    dati['Target'] = np.where(dati['Close'].shift(-1) > dati['Close'], 1, 0)

    return dati.dropna()

df_storico = scarica_dati_puliti()

if df_storico is None:
    st.error("⚠️ Errore nel caricamento dei dati di mercato S&P 500 (^GSPC).")
    st.stop()
else:
    st.sidebar.success("🌐 Fonte dati attiva: ^GSPC (S&P 500 Index)")

# --- PANNELLO LATERALE ---
st.sidebar.header("⚙️ Impostazioni Daily KO")

with st.sidebar.expander("💰 Capitale & Costi", expanded=True):
    capitale_utente = st.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
    spread_cost = st.number_input("Costo Spread/Commissioni ($):", value=0.50, step=0.10, format="%.2f")
    dimensione_lotto = st.number_input("Moltiplicatore Contratto:", value=1.0, step=0.1)

with st.sidebar.expander("🛡️ Stop Loss & Take Profit", expanded=True):
    attiva_sltp = st.checkbox("Attiva SL / TP Intraday", value=True)
    pct_sl = st.slider("Stop Loss (%)", 0.2, 1.5, 0.8, 0.1) / 100.0
    pct_tp = st.slider("Take Profit (%)", 0.5, 3.0, 1.6, 0.1) / 100.0

with st.sidebar.expander("🚀 Filtri Strategia", expanded=True):
    soglia_filtro = st.slider("Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
    attiva_upgrade = st.checkbox("Attiva Filtri Upgrade (Filtro RSI 45-55)", value=True)

# --- MOTORE WALK-FORWARD CORRETTO ---
def esegui_walk_forward_pulito(dati, capitale_iniziale, spread, conf_minima, lotto, usa_sltp, sl_val, tp_val, usa_upgrade):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    finestra_test = 126
    # Ci fermiamo a len(dati)-1 perché l'ultima riga non ha ancora il Target di domani definito
    punto_inizio = len(dati) - finestra_test - 1
    
    for i in range(punto_inizio, len(dati) - 1):
        # 1. Train solo sui dati passati fino a i-1
        dati_train = dati.iloc[:i]
        X_train = dati_train[variabili]
        y_train = dati_train['Target']
        
        modello = RandomForestClassifier(
            n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
        )
        modello.fit(X_train, y_train)
        
        # 2. Predizione sul giorno i (usando i dati di chiusura del giorno i)
        riga_test = dati.iloc[i:i+1][variabili]
        prob = modello.predict_proba(riga_test)[0]
        pred_ia = modello.predict(riga_test)[0]
        conf = prob[pred_ia] * 100
        
        if conf < conf_minima:
            continue
            
        rsi_attuale = dati['RSI'].iloc[i]
        close_attuale = dati['Close'].iloc[i]
        sma50_attuale = dati['Media_50'].iloc[i]
        
        # 3. Filtri operativi Upgrade
        if usa_upgrade:
            if 45 <= rsi_attuale <= 55:
                continue
            if pred_ia == 1 and close_attuale < sma50_attuale:
                continue
            if pred_ia == 0 and close_attuale > sma50_attuale:
                continue

        # 4. Esecuzione trade il giorno i+1 (domani)
        idx_domani = i + 1
        data_trade = dati.index[idx_domani].date()
        prezzo_entrata = dati['Open'].iloc[idx_domani]
        high_giorno = dati['High'].iloc[idx_domani]
        low_giorno = dati['Low'].iloc[idx_domani]
        prezzo_chiusura = dati['Close'].iloc[idx_domani]
        
        prezzo_uscita = prezzo_chiusura
        esito_uscita = "SCADENZA GIORNALIERA"
        
        if usa_sltp:
            if pred_ia == 1: # LONG
                prezzo_sl = prezzo_entrata * (1 - sl_val)
                prezzo_tp = prezzo_entrata * (1 + tp_val)
                if low_giorno <= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "KNOCK-OUT / STOP"
                elif high_giorno >= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"
            else: # SHORT
                prezzo_sl = prezzo_entrata * (1 + sl_val)
                prezzo_tp = prezzo_entrata * (1 - tp_val)
                if high_giorno >= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "KNOCK-OUT / STOP"
                elif low_giorno <= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"

        variazione = prezzo_uscita - prezzo_entrata
        pnl_lordo = variazione * lotto if pred_ia == 1 else -variazione * lotto
        pnl_netto = pnl_lordo - (spread * lotto)
        
        capitale_corrente += pnl_netto
        equity.append(capitale_corrente)
        
        trade_log.append({
            "Data": str(data_trade),
            "Eseguito": "LONG (CALL)" if pred_ia == 1 else "SHORT (PUT)",
            "Uscita": esito_uscita,
            "Esito": "WIN" if pnl_netto > 0 else "LOSS",
            "Confidenza (%)": round(conf, 1),
            "RSI": round(rsi_attuale, 1),
            "PnL (€)": round(pnl_netto, 2),
            "Capitale (€)": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

# --- SEGNALE LIVE CORRETTO ---
variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
             'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

# Fit sull'intero storico disponibile tranne l'ultima riga aperta
X_live = df_storico[variabili].iloc[:-1]
y_live = df_storico['Target'].iloc[:-1]

modello_live = RandomForestClassifier(
    n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
)
modello_live.fit(X_live, y_live)

# Predizione sull'ultima candela CHIUSA
ultimo_dato_chiuso = df_storico[variabili].iloc[[-1]]
prob_live = modello_live.predict_proba(ultimo_dato_chiuso)[0]
pred_live = modello_live.predict(ultimo_dato_chiuso)[0]

confidenza_ia = prob_live[pred_live] * 100
prezzo_riferimento = round(float(df_storico['Close'].iloc[-1]), 2)
rsi_live = round(float(df_storico['RSI'].iloc[-1]), 1)
direzione_str = "LONG (CALL)" if pred_live == 1 else "SHORT (PUT)"

if pred_live == 1:
    sl_live_val = prezzo_riferimento * (1 - pct_sl)
    tp_live_val = prezzo_riferimento * (1 + pct_tp)
else:
    sl_live_val = prezzo_riferimento * (1 + pct_sl)
    tp_live_val = prezzo_riferimento * (1 - pct_tp)

df_res, eq_res = esegui_walk_forward_pulito(
    df_storico, capitale_utente, spread_cost, soglia_filtro, 
    dimensione_lotto, attiva_sltp, pct_sl, pct_tp, attiva_upgrade
)

# --- LAYOUT INTERFACCIA ---
tab_live, tab_diagnostica, tab_storico = st.tabs(["🎯 Segnale Daily KO Live", "🔬 Diagnostica & Filtri", "📋 Storico Dettagliato"])

with tab_live:
    st.subheader("Verdetto Operativo Daily Knock-Out (Segnale Ufficiale)")
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if pred_live == 1:
            st.success(f"### STRUMENTO: {direzione_str} 🟢")
        else:
            st.error(f"### STRUMENTO: {direzione_str} 🔴")

    with col_l2:
        st.metric("Ultima Chiusura S&P 500 (^GSPC)", f"{prezzo_riferimento} pt")
        st.metric("Confidenza IA / RSI Chiusura", f"{confidenza_ia:.1f}% / RSI: {rsi_live}")
        
    st.markdown("---")
    st.subheader("🛠️ Livelli per Daily Options Knock-Out su Fineco")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("Prezzo Riferimento", f"{prezzo_riferimento}")
    col_p2.metric("Barriera / Stop Loss", f"{sl_live_val:.2f}", delta=f"-{pct_sl*100:.1f}%", delta_color="inverse")
    col_p3.metric("Take Profit", f"{tp_live_val:.2f}", delta=f"+{pct_tp*100:.1f}%", delta_color="normal")

with tab_diagnostica:
    st.subheader("Anatomia dei Trade (Walk-Forward Pulito)")
    if not df_res.empty:
        vinti_df = df_res[df_res['Esito'] == "WIN"]
        persi_df = df_res[df_res['Esito'] == "LOSS"]
        
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Trade Vincenti", len(vinti_df))
        d2.metric("Trade Perdenti", len(persi_df))
        d3.metric("Win Rate Reale", f"{(len(vinti_df)/len(df_res))*100:.1f}%")
        d4.metric("PnL Totale Reale", f"{df_res['PnL (€)'].sum():.2f} €")
        
        st.markdown("---")
        st.line_chart(eq_res)
    else:
        st.warning("⚠️ Nessun trade generato con i filtri selezionati.")

with tab_storico:
    st.subheader("Registro Completo delle Operazioni (Senza Ricalcoli)")
    if not df_res.empty:
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("⚠️ Nessun dato presente.")
