# -*- coding: utf-8 -*-
import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import pytz

# ==========================================
# 1. CONFIGURAZIONE PAGINA
# ==========================================
st.set_page_config(page_title="WTI AI Knockout - 10:00 AM Setup", layout="wide", page_icon="🛢️")

st.markdown("<h1 style='text-align: center; color: #D4AF37;'>🛢️ WTI KNOCKOUT AI ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Ottimizzato per Setup ore 10:00 | MA 40 | RSI 20 | Time-to-Target</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. LOGICA DI CALCOLO E ACQUISIZIONE DATI
# ==========================================
@st.cache_data(ttl=300)
def scarica_dati():
    df_5m = yf.download("CL=F", period="5d", interval="5m", auto_adjust=True)
    df_1h = yf.download("CL=F", period="1mo", interval="1h", auto_adjust=True)
    
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
    
    return df.dropna()

df_5m, df_1h = scarica_dati()

if df_5m.empty or df_1h.empty:
    st.error("Errore nel download dei dati dal mercato.")
    st.stop()

df_5m = calcola_indicatori(df_5m)
df_1h = calcola_indicatori(df_1h)

# ==========================================
# 3. FILTRO ORARIO: LA SESSIONE ASIATICA
# ==========================================
df_5m.index = df_5m.index.tz_convert('Europe/Rome')
oggi = datetime.now(pytz.timezone('Europe/Rome')).date()

dati_oggi = df_5m[df_5m.index.date == oggi]
asian_session = dati_oggi[(dati_oggi.index.hour < 10)]

if not asian_session.empty:
    asian_high = asian_session['High'].max()
    asian_low = asian_session['Low'].min()
else:
    asian_high = df_5m['High'].iloc[-1] + 0.3
    asian_low = df_5m['Low'].iloc[-1] - 0.3

# ==========================================
# 4. MOTORE LOGICO E TIMING PREDICTION
# ==========================================
ultimo_prezzo = float(df_5m['Close'].iloc[-1])
ma40_5m = float(df_5m['MA_40'].iloc[-1])
rsi20_5m = float(df_5m['RSI_20'].iloc[-1])
atr_5m = float(df_5m['ATR_14'].iloc[-1])

trend_orario_bullish = float(df_1h['Close'].iloc[-1]) > float(df_1h['MA_40'].iloc[-1])

st.sidebar.markdown("### Impostazioni IA e Rischio")
rr_ratio = st.sidebar.slider("Rapporto Rischio/Rendimento (R:R):", 1.0, 3.0, 1.6, 0.1)

direzione = "ATTESA"
ingresso, sl, tp, barriera_ko = 0.0, 0.0, 0.0, 0.0

if trend_orario_bullish and rsi20_5m < 45 and ultimo_prezzo >= (ma40_5m - 0.05):
    direzione = "LONG (Pullback Dinamico MA40)"
    ingresso = round(ma40_5m, 2)
    sl = round(ingresso - (atr_5m * 1.5), 2)
    tp = round(ingresso + ((ingresso - sl) * rr_ratio), 2)
    barriera_ko = round(sl - (atr_5m * 1.0), 2)

elif not trend_orario_bullish and rsi20_5m > 55 and ultimo_prezzo <= (ma40_5m + 0.05):
    direzione = "SHORT (Pullback Dinamico MA40)"
    ingresso = round(ma40_5m, 2)
    sl = round(ingresso + (atr_5m * 1.5), 2)
    tp = round(resistenza - ((sl - ingresso) * rr_ratio), 2) if 'resistenza' in locals() else round(ingresso - ((sl - ingresso) * rr_ratio), 2)
    barriera_ko = round(sl + (atr_5m * 1.0), 2)
    
else:
    if ultimo_prezzo > asian_high:
        direzione = "LONG (Breakout Supporto Statico Asiatico)"
        ingresso = round(asian_high, 2)
        sl = round(ingresso - (atr_5m * 1.8), 2)
        tp = round(ingresso + ((ingresso - sl) * rr_ratio), 2)
        barriera_ko = round(sl - (atr_5m * 1.2), 2)
    elif ultimo_prezzo < asian_low:
        direzione = "SHORT (Breakout Supporto Statico Asiatico)"
        ingresso = round(asian_low, 2)
        sl = round(ingresso + (atr_5m * 1.8), 2)
        tp = round(ingresso - ((sl - ingresso) * rr_ratio), 2)
        barriera_ko = round(sl + (atr_5m * 1.2), 2)

velocita_tick_5m = atr_5m  
distanza_tp = abs(ingresso - tp)
distanza_trigger = abs(ultimo_prezzo - ingresso)

if velocita_tick_5m > 0:
    candele_al_trigger = int(distanza_trigger / velocita_tick_5m)
    candele_al_tp = int(distanza_tp / velocita_tick_5m)
    tempo_trigger = candele_al_trigger * 5
    tempo_tp = candele_al_tp * 5
else:
    tempo_trigger, tempo_tp = 0, 0

# ==========================================
# 5. DASHBOARD UI
# ==========================================
st.header("Scansione Algoritmica (Filtro 10:00)")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Prezzo WTI Attuale", f"{ultimo_prezzo:.2f}")
c2.metric("MA 40 (Trend 5m)", f"{ma40_5m:.2f}")
c3.metric("RSI 20", f"{rsi20_5m:.2f}")
c4.metric("Volatilità (ATR 5m)", f"{atr_5m:.2f}")

st.markdown("---")

if direzione != "ATTESA":
    st.success(f"CONFIGURAZIONE RILEVATA: {direzione}")
    
    st.markdown("### Parametri Ordine (Knockout Fineco)")
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Ingresso (Trigger)", f"{ingresso:.2f}")
    o2.metric("Take Profit", f"{tp:.2f}")
    o3.metric("Stop Loss (Mentale/Macchina)", f"{sl:.2f}")
    o4.metric("Barriera Knockout", f"{barriera_ko:.2f}", help="Da usare nel certificato. Posizionata oltre lo SL per evitare false cacciate.")
    
    st.info(f"Previsione Tempistiche dell'IA (Basata su Volatilità Attuale):\n"
            f"- Tempo Stimato al Trigger: Il prezzo dovrebbe toccare l'ingresso in circa {tempo_trigger} minuti.\n"
            f"- Tempo Stimato al Target: Dall'ingresso, la proiezione per raggiungere il TP è di {tempo_tp} minuti.")
else:
    st.warning("Il mercato è in fase neutrale. Nessun setup rilevato in base alla tua strategia.")
