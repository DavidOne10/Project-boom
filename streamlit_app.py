# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Multi-Asset Risk Scanner", layout="wide")

st.title("🤖 V-Alpha PRO | Multi-Asset Scanner & Risk Management OOS")
st.markdown("---")

# --- 1. CONFIGURAZIONE PANIER BISNESS ---
ASSET_BASKET = {
    "Petrolio WTI (CL=F)": "CL=F",
    "Oro (GC=F)": "GC=F",
    "S&P 500 (^GSPC)": "^GSPC",
    "EUR/USD (EURUSD=X)": "EURUSD=X"
}

# --- 2. FUNZIONE DI PREPARAZIONE DATI ---
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

# --- PANNELLO LATERALE ---
st.sidebar.header("💰 Gestione Capitale & Rischio")
capitale_utente = st.sidebar.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
spread_cost = st.sidebar.number_input("Costo Spread/Attrito ($):", value=0.04, step=0.01, format="%.2f")
soglia_filtro = st.sidebar.slider("Soglia Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
dimensione_lotto = st.sidebar.number_input("Moltiplicatore Contratto:", value=10.0, step=1.0)

st.sidebar.markdown("---")
st.sidebar.header("🛡️ Parametri Stop Loss / Take Profit")
attiva_sl_tp = st.sidebar.checkbox("Attiva SL / TP Dinamici", value=True)
pct_sl = st.sidebar.slider("Stop Loss (%)", 0.5, 3.0, 1.5, 0.1) / 100.0
pct_tp = st.sidebar.slider("Take Profit (%)", 0.5, 5.0, 2.5, 0.1) / 100.0

st.sidebar.markdown("---")
st.sidebar.header("🔄 Modalità Operativa")
modalita_inversa = st.sidebar.checkbox("Attiva 'Anti-IA Mode' (Inverti Segnali)", value=True)

asset_selezionato_nome = st.sidebar.selectbox("Scegli Asset Principale per Segnale Live:", list(ASSET_BASKET.keys()))
ticker_attivo = ASSET_BASKET[asset_selezionato_nome]

# ==========================================
# 3. MOTORE BACKTEST WALK-FORWARD CON SL/TP
# ==========================================
def esegui_walk_forward_avanzato(dati, capitale_iniziale, spread, conf_minima, inverti, lotto, usa_sltp, sl_val, tp_val):
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
        
        # Gestione SL / TP o Close-to-Close standard
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
# 4. SCANSIONE MULTI-ASSET (LEADERBOARD)
# ==========================================
st.subheader("🏆 Leaderboard Profittabilità Multi-Asset (Walk-Forward OOS)")
leaderboard_data = []

with st.spinner("Scansione e test di tutti i mercati in corso..."):
    for nome, tkr in ASSET_BASKET.items():
        df_temp = scarica_e_prepara_dati(tkr)
        if df_temp is not None:
            df_res, eq_res = esegui_walk_forward_avanzato(
                df_temp, capitale_utente, spread_cost, soglia_filtro, modalita_inversa, dimensione_lotto, attiva_sl_tp, pct_sl, pct_tp
            )
            if not df_res.empty:
                tot = len(df_res)
                vinti = len(df_res[df_res['Esito'] == "WIN"])
                wr = (vinti / tot) * 100
                profitto = eq_res[-1] - capitale_utente
                leaderboard_data.append({
                    "Asset": nome,
                    "Profitto Netto (€)": round(profitto, 2),
                    "Capitale Finale (€)": round(eq_res[-1], 2),
                    "Win Rate (%)": round(wr, 1),
                    "Trade Effettuati": tot
                })

if leaderboard_data:
    df_leaderboard = pd.DataFrame(leaderboard_data).sort_values(by="Profitto Netto (€)", ascending=False)
    st.dataframe(df_leaderboard, use_container_width=True)
else:
    st.warning("⚠️ Impossibile generare la classifica con i parametri attuali.")

# ==========================================
# 5. ANALISI DETTAGLIATA ASSET SELEZIONATO
# ==========================================
st.markdown("---")
st.subheader(f"📊 Analisi Dettagliata & Segnale Live: {asset_selezionato_nome}")

df_storico_attivo = scarica_e_prepara_dati(ticker_attivo)

if df_storico_attivo is not None:
    # Modello live per l'asset scelto
    variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD',
                 'MACD_Signal', 'MACD_Hist', 'Dist_Media20', 'Dist_Media50', 'Larghezza_Bande']
    
    modello_attivo = RandomForestClassifier(
        n_estimators=50, max_depth=3, min_samples_split=40, min_samples_leaf=25, random_state=42
    )
    modello_attivo.fit(df_storico_attivo[variabili].iloc[:-1], df_storico_attivo['Target'].iloc[:-1])
    
    ultimo_dato = df_storico_attivo[variabili].iloc[[-1]]
    prob_live = modello_attivo.predict_proba(ultimo_dato)[0]
    pred_live_nativa = modello_attivo.predict(ultimo_dato)[0]
    confidenza_ia = prob_live[pred_live_nativa] * 100
    prezzo_live = round(float(df_storico_attivo['Close'].iloc[-1]), 3)

    segnalo_ia_str = "LONG" if pred_live_nativa == 1 else "SHORT"
    op_live = 0 if (pred_live_nativa == 1 and modalita_inversa) or (pred_live_nativa == 0 and not modalita_inversa) else 1
    direzione_effettiva_str = "LONG" if op_live == 1 else "SHORT"
    stato_inversa_str = "ATTIVA 🔄" if modalita_inversa else "DISATTIVA"

    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if direzione_effettiva_str == "LONG":
            st.success(f"SEGNALE LIVE: LONG 🟢 (IA diceva: {segnalo_ia_str})")
        else:
            st.error(f"SEGNALE LIVE: SHORT 🔴 (IA diceva: {segnalo_ia_str})")

    with col_l2:
        st.metric(f"Prezzo Odierno ({asset_selezionato_nome})", prezzo_live)
        st.metric("Confidenza IA", f"{confidenza_ia:.1f}%")

    # Esegui backtest dettagliato per l'asset attivo
    df_res_attivo, eq_attivo = esegui_walk_forward_avanzato(
        df_storico_attivo, capitale_utente, spread_cost, soglia_filtro, modalita_inversa, dimensione_lotto, attiva_sl_tp, pct_sl, pct_tp
    )
    
    if not df_res_attivo.empty:
        st.line_chart(eq_attivo)
        with st.expander(f"🔍 Storico Operazioni Dettagliato ({asset_selezionato_nome})"):
            st.dataframe(df_res_attivo)
