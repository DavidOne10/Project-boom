# -*- coding: utf-8 -*-
import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier

# ==========================================
# 1. CONFIGURAZIONE TELEGRAM & SOGLIE
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SOGLIA_MINIMA_WINRATE = 56.0  # Invia il segnale solo se la IA supera questa percentuale

def invia_messaggio_telegram(testo):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Errore: Token o Chat ID di Telegram non configurati nelle Secrets.")
        return
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": testo,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        res_json = response.json()
        if not res_json.get("ok"):
            print(f"Errore nell'invio: {res_json}")
        else:
            print("Messaggio Telegram inviato con successo!")
    except Exception as e:
        print(f"Eccezione durante l'invio a Telegram: {e}")

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

# ==========================================
# 3. ESECUZIONE PRINCIPALE DEL CHECKER
# ==========================================
def main():
    print("Avvio analisi WTI in corso...")
    df_5m, df_1h = scarica_dati()
    
    if df_5m.empty or df_1h.empty:
        print("Errore: Impossibile scaricare i dati da Yahoo Finance.")
        return

    df_5m = calcola_indicatori(df_5m)
    prob_long_ia, prob_short_ia = calcola_probabilita_ia(df_5m)
    
    ultimo_prezzo = float(df_5m['Close'].iloc[-1])
    atr_5m = float(df_5m['ATR_14'].iloc[-1])
    if atr_5m == 0:
        atr_5m = 0.20
        
    rr_ratio = 1.6 # Valore standard coerente con la tua UI

    # Verifichiamo quale dei due scenari è più forte o supera la soglia
    if prob_long_ia >= SOGLIA_MINIMA_WINRATE and prob_long_ia >= prob_short_ia:
        # SCENARIO LONG
        ing_long = round(ultimo_prezzo - (atr_5m * 0.5), 2)
        sl_long = round(ing_long - (atr_5m * 1.5), 2)
        tp_long = round(ing_long + ((ing_long - sl_long) * rr_ratio), 2)
        
        testo_messaggio = (
            f"🚨 **NUOVO SEGNALE QUANTITATIVO WTI** 🚨\n\n"
            f"📈 **Scenario:** Long (Rialzista)\n"
            f"📊 **Win Rate IA:** {prob_long_ia:.1f}%\n"
            f"🎯 **Prezzo WTI:** {ultimo_prezzo:.2f}\n"
            f"📍 **Trigger Ingresso:** {ing_long:.2f}\n"
            f"💰 **Take Profit:** {tp_long:.2f}\n"
            f"🛑 **Stop Loss:** {sl_long:.2f}"
        )
        invia_messaggio_telegram(testo_messaggio)

    elif prob_short_ia >= SOGLIA_MINIMA_WINRATE and prob_short_ia > prob_long_ia:
        # SCENARIO SHORT
        ing_short = round(ultimo_prezzo + (atr_5m * 0.5), 2)
        sl_short = round(ing_short + (atr_5m * 1.5), 2)
        tp_short = round(ing_short - ((sl_short - ing_short) * rr_ratio), 2)
        
        testo_messaggio = (
            f"🚨 **NUOVO SEGNALE QUANTITATIVO WTI** 🚨\n\n"
            f"📉 **Scenario:** Short (Ribassista)\n"
            f"📊 **Win Rate IA:** {prob_short_ia:.1f}%\n"
            f"🎯 **Prezzo WTI:** {ultimo_prezzo:.2f}\n"
            f"📍 **Trigger Ingresso:** {ing_short:.2f}\n"
            f"💰 **Take Profit:** {tp_short:.2f}\n"
            f"🛑 **Stop Loss:** {sl_short:.2f}"
        )
        invia_messaggio_telegram(testo_messaggio)
    else:
        print(f"Nessun segnale forte (Long: {prob_long_ia:.1f}%, Short: {prob_short_ia:.1f}% sotto soglia). Nessun messaggio inviato.")

if __name__ == "__main__":
    main()
