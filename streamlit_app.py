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
st.markdown("<h4 style='text-align: center; color: #888;'>Analisi Predittiva Simultanea Long / Short & Sincronizzazione Live</h4>", unsafe_allow_html=True)
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
    
    return df.dropna()

def calcola_probabilita_ia(df):
    features = ['RSI_20', 'ATR_14', 'Dist_MA']
    X = df[features].iloc[:-1]
    y = df['Target_UP'].iloc[:-1]
    X_live = df[features].iloc[[-1]]
    
    modello = RandomForestClassifier(n_estimators=100, max_depth=5, random_state=42)
    modello.fit(X, y)
    
    prob_long = modello.predict_proba(X_live)[0][1] * 100
    prob_short = 100 - prob_long
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

# Offset e Allineamento
offset_prezzo = prezzo_reale - prezzo_yahoo
ultimo_prezzo = prezzo_reale
ma40_5m = float(df_5m['MA_40'].iloc[-1]) + offset_prezzo
rsi20_5m = float(df_5m['RSI_20'].iloc[-1])
atr_5m = float(df_5m['ATR_14'].iloc[-1])

# Range Asiatico Sincronizzato
df_5m.index = df_5m.index.tz_convert('Europe/Rome')
oggi = datetime.now(pytz.timezone('Europe/Rome')).date()
asian_session = df_5m[(df_5m.index.date == oggi) & (df_5m.index.hour < 10)]

if not asian_session.empty:
    asian_high = asian_session['High'].max() + offset_prezzo
    asian_low = asian_session['Low'].min() + offset_prezzo
else:
    asian_high = ultimo_prezzo + 0.3
    asian_low = ultimo_prezzo - 0.3

# ==========================================
# 4. CALCOLO DOPPIO SCENARIO (LONG & SHORT)
# ==========================================
# Scenario LONG (basato su Breakout Resistenza o supporto MA40)
ing_long = round(max(asian_high, ma40_5m), 2)
sl_long = round(ing_long - (atr_5m * 1.5), 2)
tp_long = round(ing_long + ((ing_long - sl_long) * rr_ratio), 2)
ko_long = round(sl_long - (atr_5m * 1.0), 2)
t_trig_long = int(abs(ultimo_prezzo - ing_long) / max(atr_5m, 0.01)) * 5
t_tp_long = int(abs(ing_long - tp_long) / max(atr_5m, 0.01)) * 5

# Scenario SHORT (basato su Breakout Supporto o resistenza MA40)
ing_short = round(min(asian_low, ma40_5m), 2)
sl_short = round(ing_short + (atr_5m * 1.5), 2)
tp_short = round(ing_short - ((sl_short - ing_short) * rr_ratio), 2)
ko_short = round(sl_short + (atr_5m * 1.0), 2)
t_trig_short = int(abs(ultimo_prezzo - ing_short) / max(atr_5m, 0.01)) * 5
t_tp_short = int(abs(ing_short - tp_short) / max(atr_5m, 0.01)) * 5

# ==========================================
# 5. DASHBOARD UI (DOPPIA COLONNA)
# ==========================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prezzo WTI Sincronizzato", f"{ultimo_prezzo:.2f}")
c2.metric("MA 40", f"{ma40_5m:.2f}")
c3.metric("RSI 20", f"{rsi20_5m:.2f}")
c4.metric("Volatilità (ATR)", f"{atr_5m:.2f}")

st.markdown("---")
st.markdown("### 🎯 Scenari Operativi Predittivi in Tempo Reale")
st.info("⏰ **Validità Analisi:** Questa proiezione è ottimizzata per la fase di mercato attuale. Si consiglia di ripetere l'analisi o cliccare 'Aggiorna' ogni **15-30 minuti** per ricalcolare i livelli sulla base della nuova volatilità.")

col_long, col_short = st.columns(2)

# --- COLONNA LONG ---
with col_long:
    st.markdown("#### 📈 SCENARIO LONG (Rialzista)")
    st.metric("Win Rate IA (Probabilità)", f"{prob_long_ia:.1f}%")
    st.progress(int(prob_long_ia))
    
    st.markdown(f"""
    * **Trigger Ingresso:** `{ing_long:.2f}`
    * **Tempo al Trigger:** ~`{t_trig_long} min`
    * **Take Profit (TP):** `{tp_long:.2f}`
    * **Tempo al TP:** ~`{t_tp_long} min`
    * **Stop Loss (SL):** `{sl_long:.2f}`
    * **Barriera Knockout:** `{ko_long:.2f}`
    """)

# --- COLONNA SHORT ---
with col_short:
    st.markdown("#### 📉 SCENARIO SHORT (Ribassista)")
    st.metric("Win Rate IA (Probabilità)", f"{prob_short_ia:.1f}%")
    st.progress(int(prob_short_ia))
    
    st.markdown(f"""
    * **Trigger Ingresso:** `{ing_short:.2f}`
    * **Tempo al Trigger:** ~`{t_trig_short} min`
    * **Take Profit (TP):** `{tp_short:.2f}`
    * **Tempo al TP:** ~`{t_tp_short} min`
    * **Stop Loss (SL):** `{sl_short:.2f}`
    * **Barriera Knockout:** `{ko_short:.2f}`
    """)
