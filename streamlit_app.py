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
    elif v_m['status'] == "SHORT":
        st.sidebar.error(f"🔴 V-ALPHA: TRIGGER SHORT ATTIVO a {v_m['trigger']:.3f}")
    else:
        st.sidebar.warning("Monitoraggio attivo. Prezzo in range neutro.")

# ==========================================
# 1. MOTORE DI SCANSIONE QUANTITATIVA
# ==========================================
st.header("⚡ Scansione Mercato WTI Sottostante")
if st.button("🚀 AVVIA SCANSIONE QUANTITATIVA"):
    with st.spinner("Analizzando dati..."):
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
                larghezza_bande = (ma20_5m.iloc[-1] + (2 * std20_5m.iloc[-1])) - (ma20_5m.iloc[-1] - (2 * std20_5m.iloc[-1]))
                is_compressione = larghezza_bande < 0.15
                
                atr_daily = (dati_daily['High'] - dati_daily['Low']).rolling(14).mean().iloc[-1]
                stop_elastico = round(atr_daily * 0.20, 3)
                trend_daily_bull = prezzo_attuale >= dati_daily['Close'].rolling(window=20).mean().iloc[-1]
                ema_5min_attuale = dati_5min['Close'].ewm(span=21, adjust=False).mean().iloc[-1]
                
                if prezzo_attuale < ema_5min_attuale:
                    direzione = "SHORT"
                    trigger = round(dati_5min['Low'].tail(24).min() - 0.02, 3)
                    sl = round(max(dati_5min['High'].tail(24).max(), ema_5min_attuale) + stop_elastico, 3)
                    tp = round(trigger - (abs(trigger - sl) * 1.5) + cuscinetto_tp, 3)
                    allineato = not trend_daily_bull
                else:
                    direzione = "LONG"
                    trigger = round(dati_5min['High'].tail(24).max() + 0.03, 3)
                    sl = round(min(dati_5min['Low'].tail(24).min(), ema_5min_attuale) - stop_elastico, 3)
                    tp = round(trigger + (abs(trigger - sl) * 1.5) - cuscinetto_tp, 3)
                    allineato = trend_daily_bull

                stelle, budget_rischio = ("⭐ (1 Stella)", round(base_risk * 0.4)) if is_compressione else ("⭐⭐⭐ (3 Stelle)", round(base_risk * 1.5)) if allineato else ("⭐⭐ (2 Stelle)", base_risk)
                
                st.session_state.ultimo_segnale = {"prezzo_attuale": prezzo_attuale, "larghezza_bande": larghezza_bande, "stelle": stelle, "budget_rischio": budget_rischio, "direzione": direzione, "trigger": trigger, "sl": sl, "tp": tp}
                st.session_state.nuovo_trade_temp = {"Data/Ora": ora_attiva_it.strftime("%d/%m/%Y %H:%M"), "Direzione": direzione, "Qualità": stelle, "Trigger": trigger, "SL Initial": sl, "TP": tp, "Contratti": "--", "Prezzo Uscita Fineco": "--", "Esito": "IN CORSO ⏳", "Profitto (€)": 0.0, "Prezzo KO IN (€)": "--", "Prezzo KO OUT (€)": "--"}
                st.rerun()
        except Exception as e:
            st.error(f"Errore: {e}")

# --- RENDERING PERSISTENTE ---
if st.session_state.ultimo_segnale:
    s = st.session_state.ultimo_segnale
    st.info(f"📊 Prezzo WTI: **{s['prezzo_attuale']} USD**")
    st.markdown(f"### 🎯 DIREZIONE: {s['direzione']}")
    if s['direzione'] == "LONG": st.success("Analisi: Tendenza LONG confermata")
    else: st.error("Analisi: Tendenza SHORT confermata")
    col1, col2 = st.columns(2)
    col1.metric("QUALITÀ", s['stelle'])
    col2.metric("RISCHIO", f"{s['budget_rischio']} €")
    st.write(f"📍 Ingresso: **{s['trigger']}** | SL: **{s['sl']}** | TP: **{s['tp']}**")

# ==========================================
# 2. CONFERMA E REGISTRAZIONE
# ==========================================
if st.session_state.nuovo_trade_temp:
    st.markdown("---")
    st.write(f"### 🗹 Registra Esecuzione: {tipo_strumento}")
    if "Knockout" in tipo_strumento:
        ko_in = st.number_input("Prezzo Acquisto Certificato (€):", value=1.00, step=0.01)
        ko_qta = 1
        st.info("Quantità impostata automaticamente a 1.")
    else:
        ko_in, ko_qta = "--", st.number_input("Contratti:", value=1, step=1)
        prezzo_reale_wti = st.number_input("Prezzo Eseguito:", value=float(st.session_state.nuovo_trade_temp["Trigger"]))
    
    if st.checkbox("Confermo inserimento ordine"):
        if st.button("CONFERMA E REGISTRA"):
            data = st.session_state.nuovo_trade_temp
            if "Knockout" in tipo_strumento: data.update({"Prezzo KO IN (€)": ko_in, "Contratti": ko_qta})
            else: data.update({"Trigger": prezzo_reale_wti, "Contratti": ko_qta})
            df = pd.concat([load_diario(), pd.DataFrame([data])], ignore_index=True)
            df.to_csv(FILE_DIARIO, index=False)
            st.session_state.update({"nuovo_trade_temp": None, "ultimo_segnale": None})
            st.rerun()
    if st.button("ANNULLA"):
        st.session_state.update({"nuovo_trade_temp": None, "ultimo_segnale": None})
        st.rerun()

# ==========================================
# 3. POSIZIONI ATTIVE E ARCHIVIO
# ==========================================
st.markdown("---")
st.header("📝 Posizioni Attive")
diario_df = load_diario()
aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]
if not aperte.empty:
    for idx, row in aperte.iterrows():
        is_ko = str(row.get("Prezzo KO IN (€)", "--")) != "--"
        with st.expander(f"⚙️ {row['Direzione']} | Q.tà: {row['Contratti']}"):
            val_out = st.number_input("Prezzo Uscita:", value=float(row["Prezzo KO IN (€)"] if is_ko else row["Trigger"]), key=f"out_{idx}")
            esito = st.selectbox("Esito:", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
            if st.button("SALVA CHIUSURA", key=f"btn_{idx}"):
                qta = float(row["Contratti"])
                prof = 0.0 if "BREAK-EVEN" in esito else (val_out - float(row["Prezzo KO IN (€)"])) * qta if is_ko else (val_out - float(row["Trigger"])) * (1000 if "Standard" in tipo_strumento else 100) * qta if row["Direzione"] == "LONG" else (float(row["Trigger"]) - val_out) * (1000 if "Standard" in tipo_strumento else 100) * qta
                diario_df.at[idx, ["Prezzo KO OUT (€)" if is_ko else "Prezzo Uscita Fineco", "Esito", "Profitto (€)"]] = [val_out, esito, round(prof, 2)]
                diario_df.to_csv(FILE_DIARIO, index=False)
                st.rerun()
else:
    st.info("Portafoglio Flat.")

st.markdown("---")
if not diario_df.empty:
    st.write("### 🗄️ Storico")
    st.dataframe(diario_df, use_container_width=True)
    with st.expander("🗑️ Elimina operazione"):
        scelta = st.selectbox("Seleziona:", [f"{idx}: {r['Data/Ora']} | {r['Direzione']}" for idx, r in diario_df.iterrows()])
        if st.button("ELIMINA"):
            diario_df.drop(int(scelta.split(":")[0])).to_csv(FILE_DIARIO, index=False)
            st.rerun()
