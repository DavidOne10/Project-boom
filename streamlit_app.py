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
st.set_page_config(page_title="WTI AI Knockout", layout="wide", page_icon="🛢️")

st.markdown("<h1 style='text-align: center; color: #D4AF37;'>🛢️ WTI KNOCKOUT AI ENGINE</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Filtro IA Predittiva Attivo | Sincronizzazione Live Fineco</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. ACQUISIZIONE DATI (Senza Cache per Real-Time)
# ==========================================
def scarica_dati():
    # Usiamo un try-except per scaricare i dati senza bloccare l'app
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
# 3. PANNELLO LATERALE: SINCRONIZZAZIONE E FILTRI
# ==========================================
st.sidebar.markdown("### 🔄 1. Sincronizza Dati")
prezzo_yahoo = float(df_5m['Close'].iloc[-1])
prezzo_reale = st.sidebar.number_input("Prezzo Live Fineco (CFD):", value=prezzo_yahoo, step=0.01, 
                                       help="Se Yahoo è in ritardo o su un altro contratto, scrivi qui il prezzo esatto di Fineco.")
if st.sidebar.button("Forza Ricalcolo Immediato"):
    st.rerun()

st.sidebar.markdown("### ⚙️ 2. Regole Motore IA")
soglia_minima_ia = st.sidebar.slider("Soglia Minima Win Rate (%):", 50, 80, 55, 1, 
                                     help="L'IA scarterà tutti i trade con probabilità inferiore a questa soglia.")
rr_ratio = st.sidebar.slider("Rischio/Rendimento (R:R):", 1.0, 3.0, 1.6, 0.1)

# Calcolo differenza di prezzo tra Fineco e Yahoo (Offset)
offset_prezzo = prezzo_reale - prezzo_yahoo

# Applichiamo l'offset agli indicatori chiave per allinearli al TUO grafico Fineco
ultimo_prezzo = prezzo_reale
ma40_5m = float(df_5m['MA_40'].iloc[-1]) + offset_prezzo
rsi20_5m = float(df_5m['RSI_20'].iloc[-1])
atr_5m = float(df_5m['ATR_14'].iloc[-1])

trend_orario_bullish = (float(df_1h['Close'].iloc[-1]) + offset_prezzo) > (float(df_1h['MA_40'].iloc[-1]) + offset_prezzo)

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
# 4. MOTORE LOGICO
# ==========================================
direzione = "ATTESA"
ingresso, sl, tp, barriera_ko, win_rate = 0.0, 0.0, 0.0, 0.0, 0.0
motivo_scarto = ""

# Valutazione Tecnica
if trend_orario_bullish and rsi20_5m < 45 and ultimo_prezzo >= (ma40_5m - 0.05):
    direzione_temp = "LONG (Pullback Dinamico MA40)"
    ingresso = round(ma40_5m, 2)
    sl = round(ingresso - (atr_5m * 1.5), 2)
    tp = round(ingresso + ((ingresso - sl) * rr_ratio), 2)
    barriera_ko = round(sl - (atr_5m * 1.0), 2)
    win_rate = prob_long_ia

elif not trend_orario_bullish and rsi20_5m > 55 and ultimo_prezzo <= (ma40_5m + 0.05):
    direzione_temp = "SHORT (Pullback Dinamico MA40)"
    ingresso = round(ma40_5m, 2)
    sl = round(ingresso + (atr_5m * 1.5), 2)
    tp = round(ingresso - ((sl - ingresso) * rr_ratio), 2)
    barriera_ko = round(sl + (atr_5m * 1.0), 2)
    win_rate = prob_short_ia
    
else:
    if ultimo_prezzo > asian_high:
        direzione_temp = "LONG (Breakout Range)"
        ingresso = round(asian_high, 2)
        sl = round(ingresso - (atr_5m * 1.8), 2)
        tp = round(ingresso + ((ingresso - sl) * rr_ratio), 2)
        barriera_ko = round(sl - (atr_5m * 1.2), 2)
        win_rate = prob_long_ia
    elif ultimo_prezzo < asian_low:
        direzione_temp = "SHORT (Breakout Range)"
        ingresso = round(asian_low, 2)
        sl = round(ingresso + (atr_5m * 1.8), 2)
        tp = round(ingresso - ((sl - ingresso) * rr_ratio), 2)
        barriera_ko = round(sl + (atr_5m * 1.2), 2)
        win_rate = prob_short_ia
    else:
        direzione_temp = "NESSUNA (Setup non confermato)"

# FILTRO SMART IA
if direzione_temp != "NESSUNA (Setup non confermato)":
    if win_rate >= soglia_minima_ia:
        direzione = direzione_temp
    else:
        direzione = "SCARTATO DALL'IA"
        motivo_scarto = f"L'IA ha calcolato una probabilità del {win_rate:.1f}%, inferiore al tuo minimo richiesto del {soglia_minima_ia}%."

# Time to Target
if atr_5m > 0 and ingresso > 0:
    tempo_trigger = int(abs(ultimo_prezzo - ingresso) / atr_5m) * 5
    tempo_tp = int(abs(ingresso - tp) / atr_5m) * 5
else:
    tempo_trigger, tempo_tp = 0, 0

# ==========================================
# 5. DASHBOARD UI
# ==========================================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prezzo WTI Sincronizzato", f"{ultimo_prezzo:.2f}", 
          delta=f"Offset Yahoo: {offset_prezzo:+.2f}" if offset_prezzo != 0 else "Perfettamente Allineato", delta_color="off")
c2.metric("MA 40 Sincronizzata", f"{ma40_5m:.2f}")
c3.metric("RSI 20", f"{rsi20_5m:.2f}")
c4.metric("Volatilità (ATR 5m)", f"{atr_5m:.2f}")

st.markdown("---")

if direzione.startswith("LONG") or direzione.startswith("SHORT"):
    st.success(f"✅ **MIGLIOR SOLUZIONE PREDITTIVA:** {direzione}")
    
    st.markdown(f"### 📊 Probabilità di Successo (IA Random Forest): **{win_rate:.1f}%**")
    st.progress(int(win_rate))
    
    st.markdown("### 📋 Parametri Operativi Ottimizzati")
    o1, o2, o3, o4 = st.columns(4)
    o1.metric("Ingresso (Trigger)", f"{ingresso:.2f}")
    o2.metric("Take Profit", f"{tp:.2f}")
    o3.metric("Stop Loss", f"{sl:.2f}")
    o4.metric("Barriera Knockout Fineco", f"{barriera_ko:.2f}")
    
    st.info(f"⏱️ **Previsione Tempistiche:** Arrivo al trigger stimato in **{tempo_trigger} min**. Arrivo a TP stimato in **{tempo_tp} min**.")

elif direzione == "SCARTATO DALL'IA":
    st.error(f"🛑 **TRADE BLOCCATO PER BASSA PROBABILITÀ**")
    st.markdown(f"Setup tecnico rilevato ({direzione_temp}), ma **{motivo_scarto}** Operazione cancellata per proteggere il capitale.")
    st.progress(int(win_rate))

else:
    st.warning("⏳ Nessun ingresso tecnico rilevato al momento. Mercato in attesa sui supporti/resistenze.")
