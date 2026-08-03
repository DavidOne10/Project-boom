# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# --- CONFIGURAZIONE INTERFACCIA ---
st.set_page_config(page_title="V-Alpha PRO | Fineco Daily Knock-Out", layout="wide", page_icon="📈")

st.title("🤖 V-Alpha PRO | Fineco Daily Knock-Out (S&P 500)")
st.markdown("---")

# --- 1. FUNZIONE DI PREPARAZIONE DATI CON FALLBACK AUTOMATICO ---
@st.cache_data(ttl=3600)
def scarica_e_prepara_dati():
    tickers_da_provare = ["ES=F", "^GSPC", "SPY"]
    for ticker in tickers_da_provare:
        try:
            dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True, progress=False)
            if isinstance(dati.columns, pd.MultiIndex):
                dati.columns = dati.columns.get_level_values(0)
                
            if not dati.empty and len(dati) >= 200:
                dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
                dati['Media_20'] = dati['Close'].rolling(window=20).mean()
                dati['Media_50'] = dati['Close'].rolling(window=50).mean()
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

                puliti = dati.dropna()
                if not puliti.empty:
                    return puliti, ticker
        except Exception:
            continue
    return None, None

df_storico, ticker_usato = scarica_e_prepara_dati()

if df_storico is None:
    st.error("⚠️ Errore nel caricamento dei dati di mercato. Riprova tra qualche minuto.")
    st.stop()
else:
    st.sidebar.success(f"🌐 Fonte dati attiva: {ticker_usato}")

# --- PANNELLO LATERALE PULITO ---
st.sidebar.header("⚙️ Impostazioni Daily KO")

with st.sidebar.expander("💰 Capitale & Costi", expanded=True):
    capitale_utente = st.number_input("Capitale Iniziale (€):", value=1500.0, step=100.0)
    spread_cost = st.number_input("Costo Spread ($):", value=0.50, step=0.10, format="%.2f")
    dimensione_lotto = st.number_input("Moltiplicatore Contratto:", value=1.0, step=0.1)

with st.sidebar.expander("🛡️ Stop Loss & Take Profit", expanded=True):
    attiva_sl_tp = st.checkbox("Attiva SL / TP Intraday", value=True)
    pct_sl = st.slider("Stop Loss (%)", 0.2, 1.5, 0.8, 0.1) / 100.0
    pct_tp = st.slider("Take Profit (%)", 0.5, 3.0, 1.6, 0.1) / 100.0

with st.sidebar.expander("🔄 Filtri IA", expanded=True):
    soglia_filtro = st.slider("Confidenza Minima IA (%):", 50.0, 75.0, 55.0, 1.0)
    modalita_inversa = st.checkbox("Attiva 'Anti-IA Mode'", value=True)

# --- MOTORE BACKTEST DAILY KO ---
def esegui_walk_forward_daily_ko(dati, capitale_iniziale, spread, conf_minima, inverti, lotto, usa_sltp, sl_val, tp_val):
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
        prezzo_entrata = dati['Open'].iloc[i]
        high_giorno = dati['High'].iloc[i]
        low_giorno = dati['Low'].iloc[i]
        prezzo_chiusura = dati['Close'].iloc[i]
        rsi_attuale = dati['RSI'].iloc[i-1]
        
        prezzo_uscita = prezzo_chiusura
        esito_uscita = "SCADENZA GIORNALIERA"
        
        if usa_sltp:
            if op_eseguita == 1: # LONG (CALL)
                prezzo_sl = prezzo_entrata * (1 - sl_val)
                prezzo_tp = prezzo_entrata * (1 + tp_val)
                if low_giorno <= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "KNOCK-OUT / STOP"
                elif high_giorno >= prezzo_tp:
                    prezzo_uscita = prezzo_tp
                    esito_uscita = "TAKE PROFIT"
            else: # SHORT (PUT)
                prezzo_sl = prezzo_entrata * (1 + sl_val)
                prezzo_tp = prezzo_entrata * (1 - tp_val)
                if high_giorno >= prezzo_sl:
                    prezzo_uscita = prezzo_sl
                    esito_uscita = "KNOCK-OUT / STOP"
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
            "Eseguito": "LONG (CALL)" if op_eseguita == 1 else "SHORT (PUT)",
            "Uscita": esito_uscita,
            "Esito": esito,
            "Confidenza (%)": round(conf, 1),
            "RSI": round(rsi_attuale, 1),
            "PnL (€)": round(pnl_netto, 2),
            "Capitale (€)": round(capitale_corrente, 2)
        })
        
    return pd.DataFrame(trade_log), equity

# Calcolo modello live
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
rsi_live = round(float(df_storico['RSI'].iloc[-1]), 1)

segnalo_ia_str = "LONG (CALL)" if pred_live_nativa == 1 else "SHORT (PUT)"
op_live = 0 if (pred_live_nativa == 1 and modalita_inversa) or (pred_live_nativa == 0 and not modalita_inversa) else 1
direzione_effettiva_str = "LONG (CALL)" if op_live == 1 else "SHORT (PUT)"

if op_live == 1:
    sl_live_val = prezzo_riferimento * (1 - pct_sl)
    tp_live_val = prezzo_riferimento * (1 + pct_tp)
else:
    sl_live_val = prezzo_riferimento * (1 + pct_sl)
    tp_live_val = prezzo_riferimento * (1 - pct_tp)

df_res, eq_res = esegui_walk_forward_daily_ko(
    df_storico, capitale_utente, spread_cost, soglia_filtro, modalita_inversa, dimensione_lotto, attiva_sl_tp, pct_sl, pct_tp
)

# --- STRUTTURA A SCHEDE ---
tab_live, tab_diagnostica, tab_storico = st.tabs(["🎯 Segnale Daily KO Live", "🔬 Diagnostica & Filtri", "📋 Storico Dettagliato"])

with tab_live:
    st.subheader("Verdetto Operativo Daily Knock-Out")
    
    col_l1, col_l2 = st.columns(2)
    with col_l1:
        if "LONG" in direzione_effettiva_str:
            st.success(f"### STRUMENTO: {direzione_effettiva_str} 🟢\n*(Il modello originale suggeriva: {segnalo_ia_str})*")
        else:
            st.error(f"### STRUMENTO: {direzione_effettiva_str} 🔴\n*(Il modello originale suggeriva: {segnalo_ia_str})*")

    with col_l2:
        st.metric("Ultimo Prezzo S&P 500", prezzo_riferimento)
        st.metric("Confidenza IA / RSI Live", f"{confidenza_ia:.1f}% / RSI: {rsi_live}")
        
    st.markdown("---")
    st.subheader("🛠️ Livelli per Daily Options Knock-Out su Fineco")
    
    col_p1, col_p2, col_p3 = st.columns(3)
    col_p1.metric("Prezzo Riferimento", f"{prezzo_riferimento}")
    col_p2.metric("Barriera / Stop Loss", f"{sl_live_val:.2f}", delta=f"-{pct_sl*100}%", delta_color="inverse")
    col_p3.metric("Take Profit", f"{tp_live_val:.2f}", delta=f"+{pct_tp*100}%", delta_color="normal")
    
    st.info("💡 **Regola Daily KO:** Trattandosi di opzioni giornaliere che scadono a fine seduta, apri la posizione all'apertura e lasciala a scadenza o proteggila con i livelli indicati. Nessun rischio overnight.")

with tab_diagnostica:
    st.subheader("🔍 Anatomia dei Trade")
    if not df_res.empty:
        vinti_df = df_res[df_res['Esito'] == "WIN"]
        persi_df = df_res[df_res['Esito'] == "LOSS"]
        
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("Trade Vincenti", len(vinti_df))
        d2.metric("Trade Perdenti", len(persi_df))
        d3.metric("Confidenza Media (WIN)", f"{vinti_df['Confidenza (%)'].mean():.1f}%" if len(vinti_df)>0 else "N/D")
        d4.metric("Confidenza Media (LOSS)", f"{persi_df['Confidenza (%)'].mean():.1f}%" if len(persi_df)>0 else "N/D")
        
        st.markdown("---")
        st.markdown("#### Curva Equity Daily KO")
        st.line_chart(eq_res)
    else:
        st.warning("⚠️ Nessun dato diagnostico disponibile.")

with tab_storico:
    st.subheader("Registro Completo delle Operazioni Daily KO")
    if not df_res.empty:
        st.dataframe(df_res, use_container_width=True)
    else:
        st.warning("⚠️ Nessun dato da mostrare nello storico.")
