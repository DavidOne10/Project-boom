# -*- coding: utf-8 -*-
import os
import yfinance as yf
import pandas as pd
import numpy as np
import requests
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Soglia di Win Rate personalizzabile
SOGLIA_WINRATE = 52.0

def invia_notifica_telegram(messaggio):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Credenziali Telegram mancanti.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": messaggio,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            print("🚀 Notifica Telegram inviata con successo!")
        else:
            print(f"❌ Errore Telegram API: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"❌ Eccezione invio Telegram: {e}")

def main():
    print("1. Scarico i dati storici del WTI (CL=F)...")
    df = yf.download("CL=F", period="6mo", interval="1h", auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.empty or 'Close' not in df.columns:
        print("❌ Errore: Dati non disponibili.")
        return

    print("2. Calcolo indicatori ed etichettatura predittiva...")
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
    
    df = df.dropna()
    if df.empty:
        print("❌ Errore: Dataset vuoto dopo il filtraggio.")
        return

    features = ['RSI_20', 'Dist_MA_Macro_pct', 'Dist_Supporto_pct', 'ATR_pct']
    X = df[features].iloc[:-5]
    y_short = df['Hit_Short'].iloc[:-5]
    y_long = df['Hit_Long'].iloc[:-5]
    
    situazione_attuale = df[features].iloc[[-1]]
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    attuale_scaled = scaler.transform(situazione_attuale)
    
    print("3. Esecuzione modello KNN...")
    knn_short = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_short.fit(X_scaled, y_short)
    prob_short = knn_short.predict_proba(attuale_scaled)[0][1] * 100
    
    knn_long = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_long.fit(X_scaled, y_long)
    prob_long = knn_long.predict_proba(attuale_scaled)[0][1] * 100

    prezzo_reale = float(df['Close'].iloc[-1])
    atr_attuale = float(df['ATR'].iloc[-1])
    supporto_macro = float(df['Supporto_Macro'].iloc[-1])
    resistenza_macro = float(df['Resistenza_Macro'].iloc[-1])
    
    scarto_barriera = 0.60
    rr_minimo = 1.5

    print(f"📊 WTI: {prezzo_reale:.2f} | Short: {prob_short:.1f}% | Long: {prob_long:.1f}%")

    # Check Short
    ing_short_limit = round(prezzo_reale + (atr_attuale * 0.4), 2)  
    barriera_short = round(ing_short_limit + scarto_barriera, 2)
    tp_short = round(supporto_macro, 2)
    rr_calcolato_short = round((ing_short_limit - tp_short) / scarto_barriera, 2)

    if prob_short >= SOGLIA_WINRATE and rr_calcolato_short >= rr_minimo:
        msg = f"📉 *SEGNALE WTI SHORT AUTOMATICO*\nWin Rate: {prob_short:.1f}%\nSell Limit: {ing_short_limit}\nTP: {tp_short}\nBarriera: {barriera_short}"
        invia_notifica_telegram(msg)

    # Check Long
    ing_long_limit = round(prezzo_reale - (atr_attuale * 0.4), 2)  
    barriera_long = round(ing_long_limit - scarto_barriera, 2)
    tp_long = round(resistenza_macro, 2)
    rr_calcolato_long = round((tp_long - ing_long_limit) / scarto_barriera, 2)

    if prob_long >= SOGLIA_WINRATE and rr_calcolato_long >= rr_minimo:
        msg = f"🚀 *SEGNALE WTI LONG AUTOMATICO*\nWin Rate: {prob_long:.1f}%\nBuy Limit: {ing_long_limit}\nTP: {tp_long}\nBarriera: {barriera_long}"
        invia_notifica_telegram(msg)

if __name__ == "__main__":
    main()
