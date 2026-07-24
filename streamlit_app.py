# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from sklearn.ensemble import RandomForestClassifier

# ==========================================
# 1. CONFIGURAZIONE PAGINA
# ==========================================
st.set_page_config(page_title="WTI AI Dual Engine", layout="wide", page_icon="🛢️")

st.markdown("<h1 style='text-align: center; color: #D4AF37;'>🛢️ WTI DUAL SCENARIO AI ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Motore Blindato - Livelli geometricamente coerenti</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. ACQUISIZIONE DATI & MACHINE LEARNING
# ==========================================
def scarica_dati():
    df_5m = yf.download("CL=F", period="5d", interval="5m", auto_adjust=True, progress=False)
    df_1h = yf.download("CL=F", period="1mo", interval="1h", auto_adjust=True, progress=False)
    
    if isinstance(df_5m.columns, pd.MultiIndex):
        df_5m.columns = df_5m.columns.get_level_values(0)
        df_1h.columns = df_1h.columns.get_level_values(0)
        
    return df_5m, df_1h

def calcola_indicatori(df):
    df['MA_40'] = df['Close'].rolling(window=40).mean()
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=20).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=20).mean()
    rs = gain / loss
    df['RSI_20'] = 100 - (100 / (1 + rs))
    
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['ATR_14'] = np.max(ranges, axis=1).rolling(14).mean()
    
    df['Dist_MA'] = (df['Close'] - df['MA_40']) / df['MA_40']
    df['Target_UP'] = np.where(df['Close'].shift(-3) > df['Close'], 1, 0)
    df['Target_DOWN'] = np.where(df['Close'].shift(-3) < df['Close'], 1, 0)
    
    return df.dropna()

def calcola_probabilita_ia(df):
    features = ['RSI_20', 'ATR_14', 'Dist_MA']
    X = df[features].iloc[:-1]
    
    # Modello Long
    y_up = df['Target_UP'].iloc[:-1]
    modello_up = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    modello_up.fit(X, y_up)
    prob_long = modello_up.predict_proba(df[features].iloc[[-1]])[0][1] * 100

    # Modello Short
    y_down = df['Target_DOWN'].iloc[:-1]
    modello_down = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    modello_down.fit(X, y_down)
    prob_short = modello_down.predict_proba(df[features].iloc[[-1]])[0][1] * 100

    return prob_long, prob_short

df_5m, df_1h = scarica_dati()

if df_5m.empty or df_1h.empty:
    st.error("Errore di connessione dati.")
    st.stop()

df_5m = calcola_indicatori(df_5m)
df_1h = calcola_indicatori(df_1h)
prob_long_ia, prob_short_ia = calcola_probabilita_ia(df_5m)

# ==========================================
# 3. PANNELLO LATERALE: SINCRONIZZAZIONE
# ==========================================
st.sidebar.markdown("### 🔄 Sincronizzazione Prezzo")
prezzo_yahoo = float(df_5m['Close'].iloc[-1])
prezzo_reale = st.sidebar.number_input("Prezzo Live Fineco (CFD):", value=prezzo_yahoo, step=0.01)

if st.sidebar.button("🔄 Aggiorna / Ricarica"):
    st.rerun()

rr_ratio = st.sidebar.slider("Rischio/Rendimento (R:R):", 1.0, 3.0, 1.6, 0.1)

# Allineamento Prezzo Reale
ultimo_prezzo = prezzo_reale
atr_5m = float(df_5m['ATR_14'].iloc[-1])
if atr_5m == 0:
    atr_5m = 0.20 # Sicurezza contro divisioni a zero

# ==========================================
# 4. CALCOLO GEOMETRICO BLINDATO (LONG & SHORT)
# ==========================================
# SCENARIO LONG: Tutto deve essere SOTTO il prezzo attuale
ing_long = round(ultimo_prezzo - (atr_5m * 0.5), 2)  # Pullback leggero sotto il prezzo
sl_long = round(ing_long - (atr_5m * 1.5), 2)         # Sotto l'ingresso
tp_long = round(ing_long + ((ing_long - sl_long) * rr_ratio), 2) # Sopra l'ingresso
ko_long = round(sl_long - (atr_5m * 1.0), 2)         # Sotto lo Stop Loss

t_trig_long = int(abs(ultimo_prezzo - ing_long) / atr_5m) * 5
t_tp_long = int(abs(ing_long - tp_long) / atr_5m) * 5

# SCENARIO SHORT: Tutto deve essere SOPRA il prezzo attuale
ing_short = round(ultimo_prezzo + (atr_5m * 0.5), 2) # Pullback leggero sopra il prezzo
sl_short = round(ing_short + (atr_5m * 1.5), 2)        # Sopra l'ingresso
tp_short = round(ing_short - ((sl_short - ing_short) * rr_ratio), 2) # Sotto l'ingresso
ko_short = round(sl_short + (atr_5m * 1.0), 2)        # Sopra lo Stop Loss

t_trig_short = int(abs(ultimo_prezzo - ing_short) / atr_5m) * 5
t_tp_short = int(abs(ing_short - tp_short) / atr_5m) * 5

# ==========================================
# 5. DASHBOARD UI (DOPPIA COLONNA)
# ==========================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prezzo WTI Sincronizzato", f"{ultimo_prezzo:.2f}")
c2.metric("MA 40", f"{float(df_5m['MA_40'].iloc[-1]):.2f}")
c3.metric("RSI 20", f"{float(df_5m['RSI_20'].iloc[-1]):.2f}")
c4.metric("Volatilità (ATR)", f"{atr_5m:.2f}")

st.markdown("---")
st.markdown("### 🎯 Scenari Operativi Predittivi in Tempo Reale")
st.info("⏰ **Validità Analisi:** Analisi geometrica e probabilistica aggiornata al millisecondo. Ripetere il refresh ogni 15-30 minuti in base alla variazione della volatilità.")

col_long, col_short = st.columns(2)

# --- COLONNA LONG ---
with col_long:
    st.markdown("#### 📈 SCENARIO LONG (Rialzista)")
    st.metric("Win Rate IA (Probabilità)", f"{prob_long_ia:.1f}%")
    st.progress(int(min(max(prob_long_ia, 0), 100)))
    
    st.markdown(f"""
    * **Trigger Ingresso:** `{ing_long:.2f}` (Sotto il prezzo)
    * **Tempo al Trigger:** ~`{t_trig_long} min`
    * **Take Profit (TP):** `{tp_long:.2f}` (Sopra)
    * **Tempo al TP:** ~`{t_tp_long} min`
    * **Stop Loss (SL):** `{sl_long:.2f}` (Sotto)
    * **Barriera Knockout:** `{ko_long:.2f}` (Protezione extra)
    """)

# --- COLONNA SHORT ---
with col_short:
    st.markdown("#### 📉 SCENARIO SHORT (Ribassista)")
    st.metric("Win Rate IA (Probabilità)", f"{prob_short_ia:.1f}%")
    st.progress(int(min(max(prob_short_ia, 0), 100)))
    
    st.markdown(f"""
    * **Trigger Ingresso:** `{ing_short:.2f}` (Sopra il prezzo)
    * **Tempo al Trigger:** ~`{t_trig_short} min`
    * **Take Profit (TP):** `{tp_short:.2f}` (Sotto)
    * **Tempo al TP:** ~`{t_tp_short} min`
    * **Stop Loss (SL):** `{sl_short:.2f}` (Sopra)
    * **Barriera Knockout:** `{ko_short:.2f}` (Protezione extra)
    """)
