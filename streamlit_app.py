# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | S&P 500 Intraday", layout="wide", page_icon="📈")

st.title("🤖 V-Alpha PRO | S&P 500 Intraday Control Center")
st.markdown("---")

TICKER = "^GSPC"  # S&P 500

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
        # Il target prevede la direzione della seduta stessa (Close vs Open o Close rispetto a ieri)
        dati['Target'] = np.where(dati['Close'] > dati['Open'], 1, 0)

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

# --- PANNELLO LATERALE PULITO ---
st.sidebar.header("⚙️ Impostazioni Intraday")

with st.sidebar.expander("💰 Capitale & Costi", expanded=True):
    capitale_utente = st.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
    spread_cost = st.number_input("Costo Spread ($):", value=0.50, step=0.10, format="%.2f")
    dimensione_lotto = st.number_input("Moltiplicatore Contratto:", value=1.0, step=0.1)

with st.sidebar.expander("🛡️ Stop Loss & Take Profit (Stretta Intraday)", expanded=True):
    attiva_sl_tp = st.checkbox("Attiva SL / TP Intraday", value=True)
    pct_sl = st.slider("Stop Loss (%)", 0.2, 1.5, 0.8, 0.1) / 100.0  # Rischio ridotto per intraday
    pct_tp = st.slider("Take Profit (%)", 0.5, 3.0, 1.5, 0.1) / 100.0

with st.sidebar.expander("🔄 Filtri IA", expanded=True):
    soglia_filtro = st.slider("Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
    modalita_inversa = st.checkbox("Attiva 'Anti-IA Mode'", value=True)

# --- MOTORE BACKTEST 100% INTRADAY ---
def esegui_walk_forward_intraday(dati, capitale_iniziale, spread, conf_minima, inverti, lotto, usa_sltp, sl_val, tp_val):
    equity = [capitale_iniziale]
    trade_log = []
    capitale_corrente = capitale_iniziale
    
    finestra_test = 126
    punto_inizio = len(dati) - finestra_test
    
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    for i in range(punto_inizio, len(dati)):
        dati_train = dati.iloc[:i-1]
        X_train = dati_train[variabili]
        y_train = dati_train['Target']
        
        modello_wf = RandomForestClassifier(
            n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
        )
        modello_wf.fit(X_train, y_train)
        
        # Test basato sulla chiusura di ieri per operare oggi
        riga_test = dati.iloc[i-1:i][variabili]
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
        prezzo_entrata = dati['Open'].iloc[i]  # Entrata all'apertura della seduta
        high_giorno = dati['High'].iloc[i]
        low_giorno = dati['Low'].iloc[i]
        prezzo_chiusura = dati['Close'].iloc[i]
        
        prezzo_uscita = prezzo_chiusura
        esito_uscita = "CLOSE"
        
        if usa_sltp:
            if op_eseguita == 1: # LONG
                prezzo_sl = prezzo_entrata * (1 - sl_val)
                prezzo_tp = prezzo_entrata * (1 + tp_val)
                if low_giorno <= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "STOP LOSS"
                elif high_giorno >= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"
            else: # SHORT
                prezzo_sl = prezzo_entrata * (1 + sl_val)
                prezzo_tp = prezzo_entrata * (1 - tp_val)
                if high_giorno >= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "STOP LOSS"
                elif low_giorno <= prezzo_tp:
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

# Calcolo modello live intraday per oggi
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
prezzo_riferimento = round(float(df_storico['Close'].iloc[-1]), 2)

segnalo_ia_str = "LONG" if pred_live_nativa == 1 else "SHORT"
op_live = 0 if (pred_live_nativa == 1 and modalita_inversa) or (pred_live_nativa == 0 and not modalita_inversa) else 1
direzione_effettiva_str = "LONG" if op_live == 1 else "SHORT"

if direzione_effettiva_str == "LONG":
    sl_live_val = prezzo_riferimento * (1 - pct_sl)
    tp_live_val = prezzo_riferimento * (1 + pct_tp)
else:
    sl_live_val = prezzo_riferimento * (1 + pct_sl)
    tp_live_val = prezzo_riferimento * (1 - pct_tp)

df_res, eq_res = esegui_walk_forward_intraday(
    df_storico, capitale_utente, spread_cost, soglia_filtro, modalita_inversa, dimensione_lotto, attiva_sl_tp, pct_sl, pct_tp
)

# --- STRUTTURA A SCHEDE ---
tab_live, tab_backtest, tab_storico = st.tabs(["🎯 Segnale Intraday Live", "📊 Analisi & Performance", "📋 Storico Dettagliato"])

with tab_live:
    st.subheader("Verdetto Operativo Intraday")
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if direzione_effettiva_str == "LONG":
            st.success(f"### DIREZIONE: LONG 🟢\n*(Il modello originale suggeriva: {segnalo_ia_str})*")
        else:
            st.error(f"### DIREZIONE: SHORT 🔴\n*(Il modello originale suggeriva: {segnalo_ia_str})*")

    with col_l2:
        st.metric("Ultimo Prezzo Chiusura", prezzo_riferimento)
        st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")
        
    st.markdown("---")
    st.subheader("🛠️ Parametri Knock-Out Intraday (Stretti)")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("Riferimento Ingresso", f"{prezzo_riferimento}")
    col_p2.metric("Stop Loss Intraday", f"{sl_live_val:.2f}", delta=f"-{pct_sl*100}%", delta_color="inverse")
    col_p3.metric("Take Profit Intraday", f"{tp_live_val:.2f}", delta=f"+{pct_tp*100}%", delta_color="normal")
    
    st.info("💡 **Regola Intraday:** Apri la posizione all'apertura e chiudila tassativamente in giornata. Nessun mantenimento overnight.")

with tab_backtest:
    st.subheader("Performance Storica Intraday (OOS)")
    if not df_res.empty:
        tot_t = len(df_res)
        vinti_t = len(df_res[df_res['Esito'] == "WIN"])
        wr_t = (vinti_t / tot_t) * 100
        net_profit = eq_res[-1] - capitale_utente
        
        wf_c1, wf_c2, wf_c3, wf_c4 = st.columns(4)
        wf_c1.metric("Trade Effettuati", tot_t)
        wf_c2.metric("Win Rate Reale", f"{wr_t:.1f}%")
        wf_c3.metric("Profitto Netto OOS", f"{net_profit:.2f} €")
        wf_c4.metric("Capitale Finale", f"{eq_res[-1]:.2f} €")
        
        st.markdown("#### Curva Equity Intraday")
        st.line_chart(eq_res)
    else:
        st.warning("⚠️ Nessun trade generato con i parametri attuali.")

with tab_storico:
    st.subheader("Registro Completo delle Operazioni Intraday")
    if not df_res.empty:
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("⚠️ Nessun dato da mostrare nello storico.")
