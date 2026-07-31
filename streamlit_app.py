# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | S&P 500 Special Edition", layout="wide")

st.title("🤖 V-Alpha PRO | S&P 500 Target Dedicato (Anti-Overfitting & SL/TP)")
st.markdown("---")

TICKER = "^GSPC"  # S&P 500 fisso sul cavallo vincente

# --- 1. FUNZIONE DI PREPARAZIONE DATI ---
@st.cache_data(ttl=3600)
def scarica_e_prepara_dati(ticker):
    try:
        dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False)
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)
            
        if dati.empty or len(dati) < 200:
            return None

        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()
        dati['Target'] = np.where(dati['Close'].shift(-1) > dati['Close'], 1, 0)

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

        return dati.dropna()
    except Exception:
        return None

df_storico = scarica_e_prepara_dati(TICKER)

if df_storico is None:
    st.error("⚠️ Errore nel caricamento dei dati dello S&P 500.")
    st.stop()

# --- PANNELLO LATERALE ---
st.sidebar.header("💰 Gestione Capitale & Rischio")
capitale_utente = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
spread_cost = st.sidebar.number_input("Costo Spread/Attrito ($):", value=0.50, step=0.10, format="%.2f")
soglia_filtro = st.sidebar.slider("Soglia Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
dimensione_lotto = st.sidebar.number_input("Moltiplicatore Contratto:", value=1.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.header("🛡️ Parametri Stop Loss / Take Profit")
attiva_sl_tp = st.sidebar.checkbox("Attiva SL / TP Dinamici", value=True)
pct_sl = st.sidebar.slider("Stop Loss (%)", 0.5, 3.0, 1.5, 0.1) / 100.0
pct_tp = st.sidebar.slider("Take Profit (%)", 0.5, 5.0, 2.5, 0.1) / 100.0

st.sidebar.markdown("---")
st.sidebar.header("🔄 Modalità Operativa")
modalita_inversa = st.sidebar.checkbox("Attiva 'Anti-IA Mode' (Inverti Segnali)", value=True)

# ==========================================
# 2. MOTORE BACKTEST WALK-FORWARD CON SL/TP
# ==========================================
def esegui_walk_forward_ssp500(dati, capitale_iniziale, spread, conf_minima, inverti, lotto, usa_sltp, sl_val, tp_val):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    finestra_test = 126
    punto_inizio = len(dati) - finestra_test
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    for i in range(punto_inizio, len(dati) - 1):
        dati_train = dati.iloc[:i]
        X_train = dati_train[variabili]
        y_train = dati_train['Target']
        
        modello_wf = RandomForestClassifier(
            n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
        )
        modello_wf.fit(X_train, y_train)
        
        riga_test = dati.iloc[i:i+1][variabili]
        prob = modello_wf.predict_proba(riga_test)[0]
        pred_ia = modello_wf.predict(riga_test)[0]
        conf = prob[pred_ia] * 100
        
        if conf < conf_minima:
            continue
            
        if inverti:
            op_eseguita = 0 if pred_ia == 1 else 1
        else:
            op_eseguita = pred_ia
            
        data_trade = dati.index[i].date()
        prezzo_entrata = dati['Close'].iloc[i]
        high_seguente = dati['High'].iloc[i+1]
        low_seguente = dati['Low'].iloc[i+1]
        prezzo_chiusura = dati['Close'].iloc[i+1]
        
        prezzo_uscita = prezzo_chiusura
        esito_uscita = "CLOSE"
        
        if usa_sltp:
            if op_eseguita == 1: # LONG
                prezzo_sl = prezzo_entrata * (1 - sl_val)
                prezzo_tp = prezzo_entrata * (1 + tp_val)
                if low_seguente <= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "STOP LOSS"
                elif high_seguente >= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"
            else: # SHORT
                prezzo_sl = prezzo_entrata * (1 + sl_val)
                prezzo_tp = prezzo_entrata * (1 - tp_val)
                if high_seguente >= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "STOP LOSS"
                elif low_seguente <= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"

        variazione = prezzo_uscita - prezzo_entrata
        pnl_lordo = variazione * lotto if op_eseguita == 1 else -variazione * lotto
        costo_totale = spread * lotto
        pnl_netto = pnl_lordo - costo_totale
        
        capitale_corrente += pnl_netto
        equity.append(capitale_corrente)
        
        esito = "WIN" if pnl_netto > 0 else "LOSS"
        
        trade_log.append({
            "Data": str(data_trade),
            "Eseguito": "LONG" if op_eseguita == 1 else "SHORT",
            "Uscita per": esito_uscita,
            "Esito": esito,
            "PnL (€)": round(pnl_netto, 2),
            "Capitale (€)": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

# ==========================================
# 3. ESECUZIONE E SEGNALE LIVE S&P 500
# ==========================================
variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
             'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']

modello_live = RandomForestClassifier(
    n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
)
modello_live.fit(df_storico[variabili].iloc[:-1], df_storico['Target'].iloc[:-1])

ultimo_dato = df_storico[variabili].iloc[[-1]]
prob_live = modello_live.predict_proba(ultimo_dato)[0]
pred_live_nativa = modello_live.predict(ultimo_dato)[0]
confidenza_ia = prob_live[pred_live_nativa] * 100
prezzo_live = round(float(df_storico['Close'].iloc[-1]), 2)

segnalo_ia_str = "LONG" if pred_live_nativa == 1 else "SHORT"
op_live = 0 if (pred_live_nativa == 1 and modalita_inversa) or (pred_live_nativa == 0 and not modalita_inversa) else 1
direzione_effettiva_str = "LONG" if op_live == 1 else "SHORT"
stato_inversa_str = "ATTIVA 🔄" if modalita_inversa else "DISATTIVA"

st.subheader("🎯 Segnale Operativo Live S&P 500")
col_l1, col_l2 = st.columns(2)
with col_l1:
    if direzione_effettiva_str == "LONG":
        st.success(f"SEGNALE LIVE: LONG 🟢 (IA originaria: {segnalo_ia_str})")
    else:
        st.error(f"SEGNALE LIVE: SHORT 🔴 (IA originaria: {segnalo_ia_str})")

with col_l2:
    st.metric("Prezzo S&P 500 Odierno", prezzo_live)
    st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")

st.markdown("---")
st.subheader("📊 Risultati Walk-Forward & Curva Equity (S&P 500)")

df_res, eq_res = esegui_walk_forward_ssp500(
    df_storico, capitale_utente, spread_cost, soglia_filtro, modalita_inversa, dimensione_lotto, attiva_sl_tp, pct_sl, pct_tp
)

if not df_res.empty:
    tot_t = len(df_res)
    vinti_t = len(df_res[df_res['Esito'] == "WIN"])
    wr_t = (vinti_t / tot_t) * 100
    net_profit = eq_res[-1] - capitale_utente
    
    wf_c1, wf_c2, wf_c3, wf_c4 = st.columns(4)
    wf_c1.metric("Trade OOS Effettuati", tot_t)
    wf_c2.metric("Win Rate Reale", f"{wr_t:.1f}%")
    wf_c3.metric("Profitto Netto OOS", f"{net_profit:.2f} €")
    wf_c4.metric("Capitale Finale", f"{eq_res[-1]:.2f} €")
    
    st.line_chart(eq_res)
    
    with st.expander("🔍 Storico Operazioni Dettagliato"):
        st.dataframe(df_res, use_container_width=True)
else:
    st.warning("⚠️ Nessun trade generato con i parametri attuali. Prova ad abbassare la soglia di confidenza.")
