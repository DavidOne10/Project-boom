import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import pytz

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Quant Drop - WTI V-Alpha", layout="wide", page_icon="💧")

# --- INIZIALIZZAZIONE SESSION STATE ---
if "ultimo_segnale" not in st.session_state:
    st.session_state.ultimo_segnale = None
if "nuovo_trade_temp" not in st.session_state:
    st.session_state.nuovo_trade_temp = None
if "valpha_metrics" not in st.session_state:
    st.session_state.valpha_metrics = None

# --- UI LOGO ---
if os.path.exists("logo.jpg"):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo.jpg", use_column_width=True)
else:
    st.markdown("""
    <div style="text-align: center; padding-bottom: 20px;">
        <h1 style="font-size: 50px; margin-bottom: -15px; color: #D4AF37;">💧</h1>
        <h2 style="color: #D4AF37; font-family: 'Courier New', Courier, monospace; letter-spacing: 4px; font-weight: bold;">QUANT DROP</h2>
        <p style="font-size: 13px; color: #888888; letter-spacing: 2px;">WTI ALGORITHMIC TRADING ASSISTANT V4.3.2 + V-ALPHA</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# --- GESTIONE DATABASE CSV ---
FILE_DIARIO = "diario_trading.csv"
COLONNE_DIARIO = ["Data/Ora", "Direzione", "Qualità", "Trigger", "SL Initial", "TP", "Contratti", "Prezzo Uscita Fineco", "Esito", "Profitto (€)", "Prezzo KO IN (€)", "Prezzo KO OUT (€)"]

def load_diario():
    if os.path.exists(FILE_DIARIO):
        df = pd.read_csv(FILE_DIARIO)
        for col in COLONNE_DIARIO:
            if col not in df.columns:
                df[col] = "--"
        return df[COLONNE_DIARIO]
    else:
        return pd.DataFrame(columns=COLONNE_DIARIO)

# --- CONFIGURAZIONE BARRA LATERALE ---
ZONA_IT = pytz.timezone('Europe/Rome')
ora_attiva_it = datetime.now(ZONA_IT)

st.sidebar.markdown("### 🕒 Stato Sistema")
st.sidebar.metric(label="Ora Italiana Corrente", value=ora_attiva_it.strftime("%H:%M:%S"))

st.sidebar.markdown("### 🛠️ Configurazione Broker & Rischio")
tipo_strumento = st.sidebar.selectbox("Strumento Utilizzato:", ["Fineco Knockout (Certificati)", "Micro WTI (MCL CFD)", "Standard WTI (CL CFD)"])

base_risk = st.sidebar.number_input("Rischio Base (2 Stelle) in €:", min_value=10, max_value=1000, value=50, step=10)
cuscinetto_tp = st.sidebar.slider("Cuscinetto TP (USD sul WTI):", min_value=0.02, max_value=0.10, value=0.05, step=0.01)

if st.session_state.valpha_metrics:
    v_m = st.session_state.valpha_metrics
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🚀 V-Alpha Parallela (5 Giorni)")
    st.sidebar.write(f"**Livello Supporto:** {v_m['supporto']:.3f}")
    st.sidebar.write(f"**Livello Resistenza:** {v_m['resistenza']:.3f}")
    
    if v_m['status'] == "LONG":
        st.sidebar.success(f"🟢 V-ALPHA: TRIGGER LONG ATTIVO a {v_m['trigger']:.3f}")
        st.sidebar.info(f"SL Fisso: {v_m['sl']:.3f} | TP: {v_m['tp']:.3f}")
    elif v_m['status'] == "SHORT":
        st.sidebar.error(f"🔴 V-ALPHA: TRIGGER SHORT ATTIVO a {v_m['trigger']:.3f}")
        st.sidebar.info(f"SL Fisso: {v_m['sl']:.3f} | TP: {v_m['tp']:.3f}")
    else:
        st.sidebar.warning("Monitoraggio attivo. Prezzo in range neutro.")

# ==========================================
# 1. MOTORE DI SCANSIONE QUANTITATIVA
# ==========================================
st.header("⚡ Scansione Mercato WTI Sottostante")

if st.button("🚀 AVVIA SCANSIONE QUANTITATIVA"):
    with st.spinner("Analizzando strutture volumetriche e compressioni volatilità..."):
        try:
            ticker = yf.Ticker("CL=F")
            dati_daily = ticker.history(period="60d", interval="1d")
            dati_5min = ticker.history(period="3d", interval="5m")
            
            if not dati_daily.empty and not dati_5min.empty:
                prezzo_attuale = round(dati_5min['Close'].iloc[-1], 3)
                
                last_5d = dati_daily.iloc[-6:-1] 
                supporto_va = last_5d['Low'].min()
                resistenza_va = last_5d['High'].max()
                
                v_status = "NEUTRO"
                v_trig, v_sl, v_tp = 0.0, 0.0, 0.0
                if abs(prezzo_attuale - supporto_va) < 0.05:
                    v_status, v_trig, v_sl, v_tp = "LONG", supporto_va + 0.05, supporto_va - 0.20, resistenza_va
                elif abs(prezzo_attuale - resistenza_va) < 0.05:
                    v_status, v_trig, v_sl, v_tp = "SHORT", resistenza_va - 0.05, resistenza_va + 0.20, supporto_va

                st.session_state.valpha_metrics = {"supporto": supporto_va, "resistenza": resistenza_va, "status": v_status, "trigger": v_trig, "sl": v_sl, "tp": v_tp}
                
                ma20_5m = dati_5min['Close'].rolling(window=20).mean()
                std20_5m = dati_5min['Close'].rolling(window=20).std()
                banda_sup = ma20_5m + (2 * std20_5m)
                banda_inf = ma20_5m - (2 * std20_5m)
                larghezza_bande = (banda_sup.iloc[-1] - banda_inf.iloc[-1])
                is_compressione = larghezza_bande < 0.15
                
                dati_daily['H-L'] = dati_daily['High'] - dati_daily['Low']
                atr_daily = dati_daily['H-L'].rolling(14).mean().iloc[-1]
                stop_elastico = round(atr_daily * 0.20, 3)
                
                dati_daily['MA20_Daily'] = dati_daily['Close'].rolling(window=20).mean()
                trend_daily_bull = prezzo_attuale >= dati_daily['MA20_Daily'].iloc[-1]
                
                dati_5min['EMA_21'] = dati_5min['Close'].ewm(span=21, adjust=False).mean()
                ema_5min_attuale = dati_5min['EMA_21'].iloc[-1]
                
                supporto_daily = dati_daily['Low'].iloc[-2:-1].min()
                resistenza_daily = dati_daily['High'].iloc[-2:-1].max()
                
                if prezzo_attuale < ema_5min_attuale:
                    direzione = "SHORT"
                    minimo_intraday = dati_5min['Low'].tail(24).min()
                    livello_chiave = supporto_daily if abs(prezzo_attuale - supporto_daily) < abs(prezzo_attuale - minimo_intraday) else minimo_intraday
                    trigger = round(livello_chiave - 0.02, 3)
                    sl_tecnico = max(dati_5min['High'].tail(24).max(), ema_5min_attuale)
                    sl = round(sl_tecnico + stop_elastico, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger - (distanza_sl * 1.5) + cuscinetto_tp, 3)
                    allineato = not trend_daily_bull
                else:
                    direzione = "LONG"
                    massimo_intraday = dati_5min['High'].tail(24).max()
                    livello_chiave = resistenza_daily if abs(prezzo_attuale - resistenza_daily) < abs(prezzo_attuale - massimo_intraday) else massimo_intraday
                    trigger = round(livello_chiave + 0.03, 3)
                    sl_tecnico = min(dati_5min['Low'].tail(24).min(), ema_5min_attuale)
                    sl = round(sl_tecnico - stop_elastico, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger + (distanza_sl * 1.5) - cuscinetto_tp, 3)
                    allineato = trend_daily_bull

                if is_compressione:
                    stelle, budget_rischio = "⭐ (1 Stella - COMPRESSIONE)", round(base_risk * 0.4)
                elif allineato:
                    stelle, budget_rischio = "⭐⭐⭐ (3 Stelle - CECCHINO)", round(base_risk * 1.5)
                else:
                    stelle, budget_rischio = "⭐⭐ (2 Stelle - Standard)", base_risk
                
                st.session_state.ultimo_segnale = {
                    "prezzo_attuale": prezzo_attuale, "larghezza_bande": larghezza_bande,
                    "stelle": stelle, "budget_rischio": budget_rischio,
                    "direzione": direzione, "trigger": trigger, "sl": sl, "tp": tp
                }
                
                st.session_state.nuovo_trade_temp = {
                    "Data/Ora": ora_attiva_it.strftime("%d/%m/%Y %H:%M"),
                    "Direzione": direzione, "Qualità": stelle, "Trigger": trigger,
                    "SL Initial": sl, "TP": tp, "Contratti": "--",
                    "Prezzo Uscita Fineco": "--", "Esito": "IN CORSO ⏳", "Profitto (€)": 0.0,
                    "Prezzo KO IN (€)": "--", "Prezzo KO OUT (€)": "--"
                }
                st.rerun()
            else:
                st.error("Nessun dato ricevuto da Yahoo Finance.")
        except Exception as e:
            st.error(f"Errore durante l'elaborazione dei dati: {e}")

# --- RENDERING PERSISTENTE DEL SEGNALE ---
if st.session_state.ultimo_segnale:
    s = st.session_state.ultimo_segnale
    st.info(f"📊 Prezzo Attuale WTI: **{s['prezzo_attuale']} USD** | Larghezza Bollinger: **{round(s['larghezza_bande'], 3)}**")
    
    # --- RIGHE AGGIUNTE PER VEDERE DIREZIONE ---
    st.markdown(f"### 🎯 DIREZIONE: {s['direzione']}")
    if s['direzione'] == "LONG":
        st.success("Analisi: Tendenza LONG confermata")
    else:
        st.error("Analisi: Tendenza SHORT confermata")
    # -------------------------------------------
    
    col_st1, col_st2 = st.columns(2)
    col_st1.metric("QUALITÀ SEGNALE", s['stelle'])
    col_st2.metric("RISCHIO DA INVESTIRE", f"{s['budget_rischio']} €")
    
    st.write(f"📍 **LIVELLI SOTTOSTANTE WTI:** Ingresso a **{s['trigger']}** | Stop Loss a **{s['sl']}** | Take Profit a **{s['tp']}**")

# ==========================================
# 2. CONFERMA E REQUISITI DI INGRESSO
# ==========================================
if st.session_state.nuovo_trade_temp:
    st.markdown("---")
    st.write(f"### 🗹 Registra Esecuzione su {tipo_strumento}")
    
    if "Knockout" in tipo_strumento:
        st.write("Inserisci i dati esatti del Certificato Knockout acquistato su Fineco:")
        col_in1, col_in2 = st.columns(2)
        with col_in1:
            ko_in = st.number_input("Prezzo Acquisto Certificato (€):", min_value=0.01, value=1.00, step=0.01, format="%.2f")
        with col_in2:
            ko_qta = st.number_input("Quantità Certificati acquistati:", min_value=1, value=100, step=10)
    else:
        ko_in = "--"
        ko_qta = st.number_input("Numero di Contratti CFD:", min_value=1, value=1, step=1)
        prezzo_reale_wti = st.number_input("Prezzo WTI Eseguito sul Broker:", value=float(st.session_state.nuovo_trade_temp["Trigger"]), step=0.01)

    conferma_piano = st.checkbox("Dichiaro di aver inserito l'ordine sul broker.")
    
    if st.button("CONFERMA E REGISTRA TRADE"):
        if conferma_piano:
            trade_data = st.session_state.nuovo_trade_temp
            
            if "Knockout" in tipo_strumento:
                trade_data["Prezzo KO IN (€)"] = ko_in
                trade_data["Contratti"] = ko_qta
            else:
                trade_data["Trigger"] = prezzo_reale_wti
                trade_data["Contratti"] = ko_qta
            
            df_storico = load_diario()
            df_storico = pd.concat([df_storico, pd.DataFrame([trade_data])], ignore_index=True)
            df_storico.to_csv(FILE_DIARIO, index=False)
            
            st.success("Operazione registrata all'interno del database storico!")
            st.session_state.nuovo_trade_temp = None
            st.session_state.ultimo_segnale = None 
            st.rerun()
        else:
            st.warning("È necessario spuntare la casella di controllo prima di salvare.")
            
    if st.button("ANNULLA SEGNALE", type="secondary"):
        st.session_state.nuovo_trade_temp = None
        st.session_state.ultimo_segnale = None
        st.rerun()

# ==========================================
# 3. PANNELLO GESTIONE POSIZIONI APERTE
# ==========================================
st.markdown("---")
st.header("📝 Posizioni Attive a Mercato")

diario_df = load_diario()
posizioni_aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]

if not posizioni_aperte.empty:
    for idx, row in posizioni_aperte.iterrows():
        is_knockout = str(row.get("Prezzo KO IN (€)", "--")) != "--"

        with st.expander(f"⚙️ {row['Direzione']} | Data: {row['Data/Ora']} | Q.tà: {row['Contratti']}"):
            col_a, col_b = st.columns(2)
            
            with col_a:
                if is_knockout:
                    prezzo_uscita = st.number_input("Prezzo di Vendita del Certificato (€):", value=float(row["Prezzo KO IN (€)"]), step=0.01, format="%.2f", key=f"out_{idx}")
                else:
                    prezzo_uscita = st.number_input("Prezzo WTI di Chiusura:", value=float(row["Trigger"]), step=0.001, format="%.3f", key=f"out_{idx}")
            
            with col_b:
                esito_scelto = st.selectbox("Esito Operazione:", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
            
            if st.button("SALVA CHIUSURA POSIZIONE", key=f"btn_{idx}"):
                try:
                    qta = float(row["Contratti"])
                except:
                    qta = 1.0

                if "BREAK-EVEN" in esito_scelto:
                    profitto = 0.0
                else:
                    if is_knockout:
                        profitto = (prezzo_uscita - float(row["Prezzo KO IN (€)"])) * qta
                    else:
                        moltiplicatore = 1000 if "Standard" in tipo_strumento else 100
                        punti = (prezzo_uscita - float(row["Trigger"])) if row["Direzione"] == "LONG" else (float(row["Trigger"]) - prezzo_uscita)
                        profitto = punti * moltiplicatore * qta
                
                if is_knockout:
                    diario_df.at[idx, "Prezzo KO OUT (€)"] = prezzo_uscita
                else:
                    diario_df.at[idx, "Prezzo Uscita Fineco"] = prezzo_uscita
                
                diario_df.at[idx, "Esito"] = esito_scelto
                diario_df.at[idx, "Profitto (€)"] = round(profitto, 2)
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.rerun()
else:
    st.info("Nessun ordine aperto nel diario. Il portafoglio è Flat.")

# ==========================================
# 4. ARCHIVIO DIARIO STORICO E GESTIONE
# ==========================================
st.markdown("---")
if not diario_df.empty:
    st.write("### 🗄️ Registro Storico Operazioni Complete")
    
    def style_dataframe(val):
        if isinstance(val, str):
            if "GAIN" in val: return 'background-color: rgba(40, 167, 69, 0.25); color: #28a745; font-weight: bold;'
            if "LOSS" in val: return 'background-color: rgba(220, 53, 69, 0.25); color: #dc3545; font-weight: bold;'
            if "IN CORSO" in val: return 'background-color: rgba(255, 193, 7, 0.2); color: #ffc107;'
        return ''
    
    st.dataframe(diario_df.style.map(style_dataframe, subset=['Esito']), use_container_width=True)
    
    st.markdown("<br>", unsafe_html=True)
    
    with st.expander("🗑️ Elimina un'operazione dal diario"):
        st.warning("Attenzione: l'eliminazione è irreversibile.")
        opzioni_delete = {f"ID: {idx} | {row['Data/Ora']} | {row['Direzione']} | Esito: {row['Esito']}": idx for idx, row in diario_df.iterrows()}
        trade_da_eliminare = st.selectbox("Seleziona l'operazione da cancellare:", list(opzioni_delete.keys()))
        
        if st.button("🗑️ ELIMINA DEFINITIVAMENTE"):
            idx_to_drop = opzioni_delete[trade_da_eliminare]
            df_aggiornato = load_diario()
            df_aggiornato = df_aggiornato.drop(idx_to_drop).reset_index(drop=True)
            df_aggiornato.to_csv(FILE_DIARIO, index=False)
            st.success("Operazione eliminata con successo!")
            st.rerun()
else:
    st.info("Il diario storico è attualmente vuoto.")
import streamlit as st
import yfinance as tf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import pytz

# CONFIGURAZIONE PAGINA
st.set_page_config(page_title="Quant Drop - WTI Trading v4.3.2", layout="wide", page_icon="💧")

# --- INIZIO SEZIONE LOGO E UI PREMIUM ---
# Il sistema cerca un file "logo.jpg" nella cartella. Se c'è, lo mostra centrato.
# Se non c'è, carica l'intestazione HTML stile Tech/Minimalista.
if os.path.exists("logo.jpg"):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.image("logo.jpg", use_column_width=True)
else:
    st.markdown("""
    <div style="text-align: center; padding-bottom: 20px;">
        <h1 style="font-size: 60px; margin-bottom: -15px; color: #D4AF37;">💧</h1>
        <h2 style="color: #D4AF37; font-family: 'Courier New', Courier, monospace; letter-spacing: 4px; font-weight: bold;">QUANT DROP</h2>
        <p style="font-size: 14px; color: #888888; letter-spacing: 2px;">WTI ALGORITHMIC TRADING ASSISTANT V4.3.2</p>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")
# --- FINE SEZIONE LOGO ---

# FILE DATABASE PERMANENTE
FILE_DIARIO = "diario_trading.csv"

# Definiamo le colonne standard per evitare disallineamenti nel CSV
COLONNE_DIARIO = [
    "Data/Ora", "Direzione", "Qualità", "Trigger", "SL Initial", "TP", "Contratti", "Prezzo Uscita Fineco", "Esito", "Profitto (€)"
]

if os.path.exists(FILE_DIARIO):
    try:
        diario_df = pd.read_csv(FILE_DIARIO)
        # Forza il riallineamento delle colonne se carichi un vecchio file
        for col in COLONNE_DIARIO:
            if col not in diario_df.columns:
                diario_df[col] = "--"
        diario_df = diario_df[COLONNE_DIARIO]
        
        # FIX PER LA STABILITA': Resetta gli indici in modo pulito
        diario_df.reset_index(drop=True, inplace=True)
    except:
        diario_df = pd.DataFrame(columns=COLONNE_DIARIO)
else:
    diario_df = pd.DataFrame(columns=COLONNE_DIARIO)

# GESTIONE ORARIA
ZONA_IT = pytz.timezone('Europe/Rome')
ora_attiva_it = datetime.now(ZONA_IT)
st.sidebar.markdown("### 🕒 Stato Sistema")
st.sidebar.metric(label="Ora Italiana Corrente", value=ora_attiva_it.strftime("%H:%M:%S"))

st.sidebar.markdown("### 🛠️ Configurazione Rischio")
base_risk = st.sidebar.number_input("Rischio Base (2 Stelle) in €:", min_value=10, max_value=200, value=50)
cuscinetto_tp = st.sidebar.slider("Cuscinetto TP (USD):", min_value=0.02, max_value=0.10, value=0.05, step=0.01)

# 1. GENERAZIONE SEGNALE LIVE
st.header("⚡ Scansione Mercato e Valutazione Setup")

if st.button("🚀 AVVIA SCANSIONE QUANTITATIVA"):
    with st.spinner("Analizzando Bande di Bollinger, ATR e strutture Daily..."):
        try:
            ticker = tf.Ticker("CL=F")
            dati_daily = ticker.history(period="60d", interval="1d")
            dati_5min = ticker.history(period="2d", interval="5m")
            
            if not dati_daily.empty and not dati_5min.empty:
                prezzo_attuale = round(dati_5min['Close'].iloc[-1], 3)
                
                # CALCOLO BANDE DI BOLLINGER SUL 5 MIN (Per rilevare compressione)
                ma20_5m = dati_5min['Close'].rolling(window=20).mean()
                std20_5m = dati_5min['Close'].rolling(window=20).std()
                banda_superiore = ma20_5m + (2 * std20_5m)
                banda_inferiore = ma20_5m - (2 * std20_5m)
                larghezza_bande = (banda_superiore.iloc[-1] - banda_inferiore.iloc[-1])
                
                is_compressione = larghezza_bande < 0.15
                
                # CALCOLO ATR DAILY
                high_low = dati_daily['High'] - dati_daily['Low']
                high_close = np.abs(dati_daily['High'] - dati_daily['Close'].shift())
                low_close = np.abs(dati_daily['Low'] - dati_daily['Close'].shift())
                ranges = pd.concat([high_low, high_close, low_close], axis=1)
                atr_daily = ranges.max(axis=1).rolling(14).mean().iloc[-1]
                stop_elastico_base = round(atr_daily * 0.20, 3)
                
                # SUPPORTI E TREND DAILY
                storico_daily = dati_daily.iloc[:-1]
                supporto_daily = storico_daily['Low'].min()
                resistenza_daily = storico_daily['High'].max()
                
                dati_daily['MA20_Daily'] = dati_daily['Close'].rolling(window=20).mean()
                trend_daily_bull = prezzo_attuale >= dati_daily['MA20_Daily'].iloc[-1]
                
                dati_5min['EMA_21'] = dati_5min['Close'].ewm(span=21, adjust=False).mean()
                ema_5min_attuale = dati_5min['EMA_21'].iloc[-1]
                
                # DETERMINAZIONE DIREZIONE
                if prezzo_attuale < ema_5min_attuale:
                    direzione = "SHORT"
                    minimo_intraday = dati_5min['Low'].tail(24).min()
                    livello_chiave = supporto_daily if abs(prezzo_attuale - supporto_daily) < abs(prezzo_attuale - minimo_intraday) else minimo_intraday
                    trigger = round(livello_chiave - 0.02, 3)
                    sl_tecnico = max(dati_5min['High'].tail(24).max(), ema_5min_attuale)
                    sl = round(sl_tecnico + stop_elastico_base, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger - (distanza_sl * 1.5) + cuscinetto_tp, 3)
                    allineato = not trend_daily_bull
                else:
                    direzione = "LONG"
                    massimo_intraday = dati_5min['High'].tail(24).max()
                    livello_chiave = resistenza_daily if abs(prezzo_attuale - resistenza_daily) < abs(prezzo_attuale - massimo_intraday) else massimo_intraday
                    trigger = round(livello_chiave + 0.03, 3)
                    sl_tecnico = min(dati_5min['Low'].tail(24).min(), ema_5min_attuale)
                    sl = round(sl_tecnico - stop_elastico_base, 3)
                    distanza_sl = abs(trigger - sl)
                    tp = round(trigger + (distanza_sl * 1.5) - cuscinetto_tp, 3)
                    allineato = trend_daily_bull

                # STELLE E QUALITA'
                if is_compressione:
                    stelle = "⭐ (1 Stella - COMPRESSIONE)"
                    budget_rischio = round(base_risk * 0.4)
                elif allineato:
                    stelle = "⭐⭐⭐ (3 Stelle - CECCHINO ALLINEATO)"
                    budget_rischio = round(base_risk * 1.5)
                else:
                    stelle = "⭐⭐ (2 Stelle - Standard)"
                    budget_rischio = base_risk
                
                contratti_consigliati = max(1, int(budget_rischio / (distanza_sl * 100)))
                
                st.info(f"📊 Prezzo Attuale WTI: **{prezzo_attuale} USD** | Larghezza Bollinger: **{round(larghezza_bande, 3)}**")
                
                col_st1, col_st2, col_st3 = st.columns(3)
                col_st1.metric("QUALITÀ SEGNALE", stelle)
                col_st2.metric("BUDGET RISCHIO ASSEGNATO", f"{budget_rischio} €")
                col_st3.metric("CONTRATTI CONSIGLIATI", contratti_consigliati)
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("DIREZIONE", direzione)
                col2.metric("TRIGGER INGRESSO", f"{trigger} USD")
                col3.metric("STOP LOSS ELASTICO", f"{sl} USD")
                col4.metric("TAKE PROFIT ANTICIPATO", f"{tp} USD")
                
                st.session_state.nuovo_trade_temp = {
                    "Data/Ora": ora_attiva_it.strftime("%d/%m/%Y %H:%M"),
                    "Direzione": direzione,
                    "Qualità": stelle,
                    "Trigger": trigger,
                    "SL Initial": sl,
                    "TP": tp,
                    "Contratti": contratti_consigliati,
                    "Prezzo Uscita Fineco": "--",
                    "Esito": "IN CORSO ⏳",
                    "Profitto (€)": 0.0
                }
            else:
                st.error("Errore nel caricamento dati di mercato.")
        except Exception as e:
            st.error(f"Errore tecnico API: {e}")

# 2. CONFERMA ESECUZIONE
if 'nuovo_trade_temp' in st.session_state:
    st.markdown("---")
    st.write("### 🗹 Conferma Esecuzione Piattaforma")
    prezzo_reale = st.number_input("Prezzo Reale Eseguito su Fineco:", value=st.session_state.nuovo_trade_temp["Trigger"], step=0.001, format="%.3f")
    giuro = st.checkbox("Ho rispettato la size consigliata in base al rischio.")
    
    if st.button("SALVA OPERAZIONE IN CORSO"):
        if giuro:
            st.session_state.nuovo_trade_temp["Trigger"] = prezzo_reale
            nuovo_df = pd.DataFrame([st.session_state.nuovo_trade_temp])
            diario_df = pd.concat([diario_df, nuovo_df], ignore_index=True)
            diario_df.to_csv(FILE_DIARIO, index=False)
            st.success("Operazione registrata con successo nel database!")
            del st.session_state.nuovo_trade_temp
            st.rerun()
        else:
            st.warning("Devi spuntare la casella di controllo del rischio per procedere.")

# 3. PANNELLO CONTROLLO E CHIUSURA
st.markdown("---")
st.header("📝 Pannello Gestione Operazioni")
posizioni_aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]

if not posizioni_aperte.empty:
    for idx, row in posizioni_aperte.iterrows():
        # Lettura sicura dei float per evitare crash pandas
        try:
            trigger_val = float(row["Trigger"])
        except ValueError:
            trigger_val = 0.0
        
        try:
            contratti_val = float(row["Contratti"])
        except ValueError:
            contratti_val = 1.0

        with st.expander(f"⚙️ Gestisci Trade | {row['Qualità']} | {row['Direzione']} da {trigger_val}"):
            prezzo_uscita = st.number_input(f"Prezzo effettivo di uscita:", value=trigger_val, step=0.001, format="%.3f", key=f"out_{idx}")
            esito_scelto = st.selectbox("Esito Operazione:", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
            
            if st.button("SALVA CHIUSURA E CALCOLA P&L", key=f"btn_{idx}"):
                punti = (prezzo_uscita - trigger_val) if row["Direzione"] == "LONG" else (trigger_val - prezzo_uscita)
                profitto = punti * 100 * contratti_val
                
                # Modifica solida con .loc
                diario_df.loc[idx, "Prezzo Uscita Fineco"] = prezzo_uscita
                diario_df.loc[idx, "Esito"] = esito_scelto
                diario_df.loc[idx, "Profitto (€)"] = round(profitto, 2)
                
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.rerun()
else:
    st.info("Nessuna posizione attualmente in corso. Mercato flat.")

# 4. DATABASE STORICO
st.markdown("---")
if not diario_df.empty:
    st.write("### 🗄️ Diario Storico Quantitativo")
    def colora_esito(val):
        if val == "GAIN ✅": return 'background-color: rgba(40, 167, 69, 0.2); font-weight: bold;'
        elif val == "LOSS ❌": return 'background-color: rgba(220, 53, 69, 0.2); font-weight: bold;'
        elif val == "IN CORSO ⏳": return 'background-color: rgba(255, 193, 7, 0.2);'
        return ''
    
    st.dataframe(diario_df.style.map(colora_esito, subset=['Esito']), use_container_width=True)
else:
    st.warning("Il database è vuoto. Inizia a registrare i trade.")
