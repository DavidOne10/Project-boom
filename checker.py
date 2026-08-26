# -*- coding: utf-8 -*-
import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# Alpaca SDK
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Machine Learning
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import StandardScaler

# --- CONFIGURAZIONE ---
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY", "IL_TUO_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "IL_TUO_SECRET_KEY")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "USO"  # United States Oil Fund (Proxy WTI su Alpaca)
SOGLIA_WINRATE = 60.0  # Alzata al 60% per massima selettività
RR_MINIMO = 1.5

def invia_notifica_telegram(messaggio):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Credenziali Telegram mancanti.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": messaggio, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
        print("🚀 Notifica Telegram inviata!")
    except Exception as e:
        print(f"❌ Errore Telegram: {e}")

def scarica_dati_alpaca(symbol, giorni=180):
    """Download dati ultra-veloce via Alpaca Data API"""
    client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=giorni)
    
    request_params = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Hour,
        start=start_date,
        end=end_date
    )
    bars = client.get_stock_bars(request_params)
    df = bars.df.reset_index(level=0, drop=True)
    df = df.rename(columns={
        'open': 'Open', 'high': 'High', 'low': 'Low', 
        'close': 'Close', 'volume': 'Volume'
    })
    return df

def calcola_indicatori(df):
    # EMA Trend Macro
    df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
    
    # RSI 14
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['RSI_14'] = 100 - (100 / (1 + (gain / loss)))

    # ATR 14
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    df['ATR'] = np.max(pd.concat([high_low, high_close, low_close], axis=1), axis=1).rolling(14).mean()
    df['ATR_pct'] = (df['ATR'] / df['Close']) * 100

    # ADX (Filtro Forza Trend)
    plus_dm = df['High'].diff()
    minus_dm = df['Low'].diff().abs()
    plus_dm = np.where((plus_dm > minus_dm) & (plus_dm > 0), plus_dm, 0)
    minus_dm = np.where((minus_dm > plus_dm) & (minus_dm > 0), minus_dm, 0)
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr_adx = tr.rolling(14).mean()
    
    plus_di = 100 * (pd.Series(plus_dm).rolling(14).mean() / atr_adx)
    minus_di = 100 * (pd.Series(minus_dm).rolling(14).mean() / atr_adx)
    dx = 100 * (np.abs(plus_di - minus_di) / (plus_di + minus_di))
    df['ADX'] = dx.rolling(14).mean()

    # Distanze percentuali
    df['Dist_EMA200_pct'] = ((df['Close'] - df['EMA_200']) / df['EMA_200']) * 100
    df['Supporto_Macro'] = df['Low'].rolling(100).min()
    df['Resistenza_Macro'] = df['High'].rolling(100).max()
    
    return df

def main():
    print(f"1. Download dati da Alpaca per {SYMBOL}...")
    df = scarica_dati_alpaca(SYMBOL)
    
    if df.empty:
        print("❌ Nessun dato ricevuto da Alpaca.")
        return

    print("2. Calcolo indicatori ed etichettatura dinamica...")
    df = calcola_indicatori(df).dropna().copy()

    # Target dinamico legato all'ATR (1.5x ATR)
    df['Future_Min'] = df['Low'].shift(-5).rolling(5).min()
    df['Future_Max'] = df['High'].shift(-5).rolling(5).max()
    df['Hit_Short'] = np.where(df['Future_Min'] <= (df['Close'] - (1.5 * df['ATR'])), 1, 0)
    df['Hit_Long'] = np.where(df['Future_Max'] >= (df['Close'] + (1.5 * df['ATR'])), 1, 0)

    features = ['RSI_14', 'Dist_EMA200_pct', 'ATR_pct', 'ADX']

    # Dataset Training vs Predizione Attuale
    train_df = df.iloc[:-5].dropna()
    X_train = train_df[features]
    y_short = train_df['Hit_Short']
    y_long = train_df['Hit_Long']
    
    situazione_attuale = df[features].iloc[[-1]]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)
    attuale_scaled = scaler.transform(situazione_attuale)

    print("3. Esecuzione k-NN...")
    knn_short = KNeighborsClassifier(n_neighbors=30, weights='distance')
    knn_short.fit(X_scaled, y_short)
    prob_short = knn_short.predict_proba(attuale_scaled)[0][1] * 100

    knn_long = KNeighborsClassifier(n_neighbors=30, weights='distance')
    knn_long.fit(X_scaled, y_long)
    prob_long = knn_long.predict_proba(attuale_scaled)[0][1] * 100

    prezzo = float(df['Close'].iloc[-1])
    atr = float(df['ATR'].iloc[-1])
    adx_attuale = float(df['ADX'].iloc[-1])
    ema200 = float(df['EMA_200'].iloc[-1])
    
    print(f"📊 {SYMBOL}: ${prezzo:.2f} | ADX: {adx_attuale:.1f} | Short Prob: {prob_short:.1f}% | Long Prob: {prob_long:.1f}%")

    # FILTRO VOLATILITÀ: Se ADX < 20 il mercato è in range/rumore
    if adx_attuale < 20:
        print("⚠️ Mercato in fase laterale (ADX < 20). Nessun segnale generato.")
        return

    # LOGICA SEGNALE SHORT (Solo se sotto EMA200)
    if prob_short >= SOGLIA_WINRATE and prezzo < ema200:
        sl_short = round(prezzo + (atr * 1.2), 2)
        tp_short = round(prezzo - (atr * 2.0), 2)
        rr_short = round((prezzo - tp_short) / (sl_short - prezzo), 2)
        
        if rr_short >= RR_MINIMO:
            msg = f"📉 *SEGNALE {SYMBOL} SHORT*\nWin Rate Stima: {prob_short:.1f}%\nPrezzo: ${prezzo:.2f}\nStop Loss: ${sl_short:.2f}\nTake Profit: ${tp_short:.2f}\nR/R: {rr_short}"
            invia_notifica_telegram(msg)

    # LOGICA SEGNALE LONG (Solo se sopra EMA200)
    elif prob_long >= SOGLIA_WINRATE and prezzo > ema200:
        sl_long = round(prezzo - (atr * 1.2), 2)
        tp_long = round(prezzo + (atr * 2.0), 2)
        rr_long = round((tp_long - prezzo) / (prezzo - sl_long), 2)
        
        if rr_long >= RR_MINIMO:
            msg = f"🚀 *SEGNALE {SYMBOL} LONG*\nWin Rate Stima: {prob_long:.1f}%\nPrezzo: ${prezzo:.2f}\nStop Loss: ${sl_long:.2f}\nTake Profit: ${tp_long:.2f}\nR/R: {rr_long}"
            invia_notifica_telegram(msg)

if __name__ == "__main__":
    main()
