# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

# ==========================================
# 1. CONFIGURAZIONE TELEGRAM & PAGINA
# ==========================================
TELEGRAM_TOKEN = "INSERISCI_QUI_IL_TUO_TOKEN"
TELEGRAM_CHAT_ID = "INSERISCI_QUI_IL_TUO_CHAT_ID"

def invia_notifica_telegram(messaggio):
    if TELEGRAM_TOKEN == "INSERISCI_QUI_IL_TUO_TOKEN":
        return  # Non invia se non configurato
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

st.set_page_config(page_title="WTI AI - Knockout & Telegram Engine", layout="wide", page_icon="🛢️")
st.markdown("<h1 style='text-align: center; color: #D4AF37;'>🛢️ WTI KNOCKOUT & TELEGRAM BOT ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Analisi Storica KNN, Pullback e Notifiche Automatiche</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. MOTORE DI CALCOLO STORICO & PREZZO LIVE
# ==========================================
@st.cache_data(ttl=60)
def ottieni_prezzo_live():
    try:
        t = yf.Ticker("CL=F")
        price = t.fast_info.get('last_price', None)
        if price is None:
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist['Close'].iloc[-1])
        return float(price) if price else 75.0
    except Exception:
        return 75.0

@st.cache_data(ttl=3600)
def carica_e_processa_dati():
    try:
        df = yf.download("CL=F", period="6mo", interval="1h", auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or 'Close' not in df.columns: 
            return pd.DataFrame()

        df['MA_Macro_5H'] = df['Close'].rolling(window=200).mean()
        df['Supporto_Macro'] = df['Low'].rolling(window=150).min()
        df['Resistenza_Macro'] = df['High'].rolling(window=150).max()

        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['RSI_20'] = 100 - (100 / (1 + (gain / loss)))

        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()
        df['ATR_pct'] = (df['ATR'] / df['Close']) * 100

        df['Dist_MA_Macro_pct'] = ((df['Close'] - df['MA_Macro_5H']) / df['MA_Macro_5H']) * 100
        df['Dist_Supporto_pct'] = ((df['Close'] - df['Supporto_Macro']) / df['Supporto_Macro']) * 100
        
        df['Future_Min'] = df['Low'].shift(-5).rolling(5).min()
        df['Future_Max'] = df['High'].shift(-5).rolling(5).max()
        df['Hit_Short'] = np.where(df['Future_Min'] <= (df['Close'] - 1.0), 1, 0)
        df['Hit_Long'] = np.where(df['Future_Max'] >= (df['Close'] + 1.0), 1, 0)
        
        return df.dropna()
    except Exception as e:
        return pd.DataFrame()

df = carica_e_processa_dati()

if df.empty:
    st.error("⚠️ **Yahoo Finance ha bloccato temporaneamente la richiesta.** Inserisci il prezzo manualmente nel pannello a sinistra.")
    st.stop()

def calcola_winrate_storico(df):
    features = ['RSI_20', 'Dist_MA_Macro_pct', 'Dist_Supporto_pct', 'ATR_pct']
    X = df[features].iloc[:-5]
    y_short = df['Hit_Short'].iloc[:-5]
    y_long = df['Hit_Long'].iloc[:-5]
    
    situazione_attuale = df[features].iloc[[-1]]
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    attuale_scaled = scaler.transform(situazione_attuale)
    
    knn_short = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_short.fit(X_scaled, y_short)
    prob_short = knn_short.predict_proba(attuale_scaled)[0][1] * 100
    
    knn_long = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_long.fit(X_scaled, y_long)
    prob_long = knn_long.predict_proba(attuale_scaled)[0][1] * 100
    
    return prob_long, prob_short

win_long, win_short = calcola_winrate_storico(df)

# ==========================================
# 3. PANNELLO LATERALE: SINCRONIZZAZIONE & RISCHIO
# ==========================================
st.sidebar.markdown("### 🔄 Inserimento Dati (10:00 / 14:30)")
prezzo_default_yahoo = ottieni_prezzo_live()
prezzo_reale = st.sidebar.number_input("Prezzo Live Fineco (CFD):", value=float(prezzo_default_yahoo), step=0.01, format="%.2f")

st.sidebar.markdown("### ⚖️ Money Management Knockout")
scarto_barriera = st.sidebar.slider("Distanza Barriera Knockout (Punti):", 0.40, 1.00, 0.60, 0.05)
rr_minimo = st.sidebar.number_input("R:R Minimo Accettabile:", value=1.5, step=0.1)

atr_attuale = float(df['ATR'].iloc[-1])
supporto_macro = float(df['Supporto_Macro'].iloc[-1])
resistenza_macro = float(df['Resistenza_Macro'].iloc[-1])

# ==========================================
# 4. CALCOLO LIVELLI LIMIT E KNOCKOUT
# ==========================================
ing_short_limit = round(prezzo_reale + (atr_attuale * 0.4), 2)  
barriera_short = round(ing_short_limit + scarto_barriera, 2)
tp_short = round(supporto_macro, 2)
rr_calcolato_short = round((ing_short_limit - tp_short) / scarto_barriera, 2)

ing_long_limit = round(prezzo_reale - (atr_attuale * 0.4), 2)  
barriera_long = round(ing_long_limit - scarto_barriera, 2)
tp_long = round(resistenza_macro, 2)
rr_calcolato_long = round((tp_long - ing_long_limit) / scarto_barriera, 2)

# ==========================================
# 5. DASHBOARD UI & INVIO TELEGRAM AUTOMATICO
# =================5=========================
c1, c2, c3 = st.columns(3)
c1.metric("Prezzo Live", f"{prezzo_reale:.2f}")
c2.metric("Rischio Massimo (Barriera)", f"{scarto_barriera:.2f} pt")
c3.metric("ATR Volatilità", f"{atr_attuale:.2f}")

st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📈 SCENARIO LONG (Ordine Buy Limit)")
    st.metric("Win Rate Statistico", f"{win_long:.1f}%")
    st.progress(int(win_long))
    
    if rr_calcolato_long >= rr_minimo:
        st.success(f"✅ Money Management Approvato (R:R 1:{rr_calcolato_long})")
        st.markdown(f"""
        * 📥 **Ingresso Limit (Buy):** `{ing_long_limit:.2f}`
        * 🎯 **Take Profit (Resistenza 5H):** `{tp_long:.2f}`
        * 🛡️ **Cerca Knockout con Barriera a:** `{barriera_long:.2f}` o inferiore
        """)
        
        if st.button("🚀 Invia Segnale LONG su Telegram"):
            msg = f"📈 *SEGNALE WTI LONG (Approvato)*\nWin Rate: {win_long:.1f}%\nBuy Limit: {ing_long_limit}\nTP: {tp_long}\nBarriera: {barriera_long}"
            invia_notifica_telegram(msg)
            st.success("Notifiche Telegram inviate!")
    else:
        st.error(f"⛔ TRADE SCARTATO - R:R Sfavorevole (1:{rr_calcolato_long})")

with col2:
    st.markdown("#### 📉 SCENARIO SHORT (Ordine Sell Limit)")
    st.metric("Win Rate Statistico", f"{win_short:.1f}%")
    st.progress(int(win_short))
    
    if rr_calcolato_short >= rr_minimo:
        st.success(f"✅ Money Management Approvato (R:R 1:{rr_calcolato_short})")
        st.markdown(f"""
        * 📥 **Ingresso Limit (Sell):** `{ing_short_limit:.2f}`
        * 🎯 **Take Profit (Supporto 5H):** `{tp_short:.2f}`
        * 🛡️ **Cerca Knockout con Barriera a:** `{barriera_short:.2f}` o superiore
        """)
        
        if st.button("🚀 Invia Segnale SHORT su Telegram"):
            msg = f"📉 *SEGNALE WTI SHORT (Approvato)*\nWin Rate: {win_short:.1f}%\nSell Limit: {ing_short_limit}\nTP: {tp_short}\nBarriera: {barriera_short}"
            invia_notifica_telegram(msg)
            st.success("Notifiche Telegram inviate!")
    else:
        st.error(f"⛔ TRADE SCARTATO - R:R Sfavorevole (1:{rr_calcolato_short})")
