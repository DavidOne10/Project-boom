# -*- coding: utf-8 -*-
import os
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

# Configurazione della pagina Streamlit
st.set_page_config(page_title="WTI Predictive Bot", layout="wide", page_icon="🛢️")

# Recupero credenziali Telegram (compatibile con Streamlit Secrets o variabili d'ambiente)
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", st.secrets.get("TELEGRAM_TOKEN", ""))
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", st.secrets.get("TELEGRAM_CHAT_ID", ""))

# Parametri operativi personalizzabili (CORRETTO)
SOGLIA_WINRATE = st.sidebar.slider("Soglia Win Rate Predittivo (%)", 40.0, 75.0, 52.0, 0.5)
SCARTO_BARRIERA = st.sidebar.number_input("Scarto Barriera Stop (USD)", value=0.60, step=0.05)
RR_MINIMO = st.sidebar.slider("Rapporto R:R Minimo", 1.0, 3.0, 1.5, 0.1)

def invia_notifica_telegram(messaggio):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        st.warning("⚠️ Token o Chat ID di Telegram non configurati. Impossibile inviare la notifica.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            return True
        else:
            st.error(f"❌ Errore Telegram API ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        st.error(f"❌ Eccezione durante l'invio Telegram: {e}")
        return False

st.title("🛢️ WTI Predictive & Smart Trading Bot")
st.markdown("Sistema di analisi predittiva basato su **Machine Learning (KNN)** e gestione avanzata del rischio sul petrolio greggio.")

if st.button("🚀 Esegui Analisi e Controlla Segnali", type="primary"):
    with st.spinner("Scaricamento dati storici e calcolo del motore predittivo in corso..."):
        try:
            # 1. Download dei dati storici orari del WTI
            df = yf.download("CL=F", period="6mo", interval="1h", auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
                
            if df.empty or 'Close' not in df.columns:
                st.error("❌ Errore: Impossibile recuperare i dati da yfinance.")
                st.stop()

            # 2. Analisi Tecnica e Feature Engineering Completo
            df['MA_Macro_5H'] = df['Close'].rolling(window=200).mean()
            df['Supporto_Macro'] = df['Low'].rolling(window=150).min()
            df['Resistenza_Macro'] = df['High'].rolling(window=150).max()

            # Calcolo RSI a 20 periodi
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            df['RSI_20'] = 100 - (100 / (1 + (gain / loss)))

            # Calcolo ATR (Average True Range) e ATR percentuale
            high_low = df['High'] - df['Low']
            high_close = np.abs(df['High'] - df['Close'].shift())
            low_close = np.abs(df['Low'] - df['Close'].shift())
            df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()
            df['ATR_pct'] = (df['ATR'] / df['Close']) * 100

            # Distanze percentuali dalle strutture macro
            df['Dist_MA_Macro_pct'] = ((df['Close'] - df['MA_Macro_5H']) / df['MA_Macro_5H']) * 100
            df['Dist_Supporto_pct'] = ((df['Close'] - df['Supporto_Macro']) / df['Supporto_Macro']) * 100
            
            # 3. Etichettatura Predittiva per il Modello (Target futuri)
            df['Future_Min'] = df['Low'].shift(-5).rolling(5).min()
            df['Future_Max'] = df['High'].shift(-5).rolling(5).max()
            df['Hit_Short'] = np.where(df['Future_Min'] <= (df['Close'] - 1.0), 1, 0)
            df['Hit_Long'] = np.where(df['Future_Max'] >= (df['Close'] + 1.0), 1, 0)
            
            df = df.dropna()
            if df.empty:
                st.error("❌ Dataset vuoto dopo la pulizia dei dati NaN.")
                st.stop()

            # 4. Modulo di Machine Learning (KNN Classifier)
            features = ['RSI_20', 'Dist_MA_Macro_pct', 'Dist_Supporto_pct', 'ATR_pct']
            X = df[features].iloc[:-5]
            y_short = df['Hit_Short'].iloc[:-5]
            y_long = df['Hit_Long'].iloc[:-5]
            
            situazione_attuale = df[features].iloc[[-1]]
            
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            attuale_scaled = scaler.transform(situazione_attuale)
            
            # Addestramento KNN per SHORT
            knn_short = KNeighborsClassifier(n_neighbors=50, weights='distance')
            knn_short.fit(X_scaled, y_short)
            prob_short = knn_short.predict_proba(attuale_scaled)[0][1] * 100
            
            # Addestramento KNN per LONG
            knn_long = KNeighborsClassifier(n_neighbors=50, weights='distance')
            knn_long.fit(X_scaled, y_long)
            prob_long = knn_long.predict_proba(attuale_scaled)[0][1] * 100

            # Estrazione valori di mercato attuali
            prezzo_reale = float(df['Close'].iloc[-1])
            atr_attuale = float(df['ATR'].iloc[-1])
            supporto_macro = float(df['Supporto_Macro'].iloc[-1])
            resistenza_macro = float(df['Resistenza_Macro'].iloc[-1])
            
            # --- PRESENTAZIONE RISULTATI A SCHERMO ---
            st.success("Analisi completata con successo!")
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Prezzo WTI Attuale", f"${prezzo_reale:.2f}")
            col2.metric("Win Rate Predittivo SHORT", f"{prob_short:.1f}%")
            col3.metric("Win Rate Predittivo LONG", f"{prob_long:.1f}%")

            st.divider()

            # --- VERIFICA E GESTIONE SCENARIO SHORT ---
            ing_short_limit = round(prezzo_reale + (atr_attuale * 0.4), 2)  
            barriera_short = round(ing_short_limit + SCARTO_BARRIERA, 2)
            tp_short = round(supporto_macro, 2)
            rr_calcolato_short = round((ing_short_limit - tp_short) / SCARTO_BARRIERA, 2)

            st.subheader("📉 Valutazione Scenario SHORT")
            st.write(f"- **Sell Limit:** `{ing_short_limit}` | **Take Profit:** `{tp_short}` | **Barriera Stop:** `{barriera_short}`")
            st.write(f"- **Rapporto R:R:** `1:{rr_calcolato_short}` (Minimo richiesto: `{RR_MINIMO}`)")

            if prob_short >= SOGLIA_WINRATE and rr_calcolato_short >= RR_MINIMO:
                st.markdown("✅ **SEGNALE SHORT VALIDATO DAL MODELLO!**")
                msg_short = (
                    f"📉 *SEGNALE WTI SHORT AUTOMATICO*\n"
                    f"📊 Win Rate: *{prob_short:.1f}%*\n"
                    f"📥 Sell Limit: `{ing_short_limit}`\n"
                    f"🎯 Take Profit: `{tp_short}`\n"
                    f"🛡️ Barriera Stop: `{barriera_short}`\n"
                    f"⚖️ R:R: `1:{rr_calcolato_short}`"
                )
                if invia_notifica_telegram(msg_short):
                    st.toast("Alert SHORT inviato su Telegram!", icon="🚀")
            else:
                st.info("ℹ️ Condizioni non soddisfatte per lo SHORT (Win Rate o R:R inferiori ai paletti impostati).")

            st.divider()

            # --- VERIFICA E GESTIONE SCENARIO LONG ---
            ing_long_limit = round(prezzo_reale - (atr_attuale * 0.4), 2)  
            barriera_long = round(ing_long_limit - SCARTO_BARRIERA, 2)
            tp_long = round(resistenza_macro, 2)
            rr_calcolato_long = round((tp_long - ing_long_limit) / SCARTO_BARRIERA, 2)

            st.subheader("🚀 Valutazione Scenario LONG")
            st.write(f"- **Buy Limit:** `{ing_long_limit}` | **Take Profit:** `{tp_long}` | **Barriera Stop:** `{barriera_long}`")
            st.write(f"- **Rapporto R:R:** `1:{rr_calcolato_long}` (Minimo richiesto: `{RR_MINIMO}`)")

            if prob_long >= SOGLIA_WINRATE and rr_calcolato_long >= RR_MINIMO:
                st.markdown("✅ **SEGNALE LONG VALIDATO DAL MODELLO!**")
                msg_long = (
                    f"🚀 *SEGNALE WTI LONG AUTOMATICO*\n"
                    f"📊 Win Rate: *{prob_long:.1f}%*\n"
                    f"📥 Buy Limit: `{ing_long_limit}`\n"
                    f"🎯 Take Profit: `{tp_long}`\n"
                    f"🛡️ Barriera Stop: `{barriera_long}`\n"
                    f"⚖️ R:R: `1:{rr_calcolato_long}`"
                )
                if invia_notifica_telegram(msg_long):
                    st.toast("Alert LONG inviato su Telegram!", icon="🚀")
            else:
                st.info("ℹ️ Condizioni non soddisfatte per il LONG (Win Rate o R:R inferiori ai paletti impostati).")

        except Exception as e:
            st.error(f"❌ Errore critico durante l'esecuzione dell'analisi predittiva: {e}")
