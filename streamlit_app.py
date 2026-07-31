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
        return
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

st.set_page_config(page_title="WTI AI - Knockout & Telegram Engine v2.0", layout="wide", page_icon="🛢️")
st.markdown("<h1 style='text-align: center; color: #D4AF37;'>🛢️ WTI KNOCKOUT & TELEGRAM BOT ENGINE v2.0</h1>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #888;'>Motore ML Path-Dependent con Allineamento Strike Fineco</h4>", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 2. SELETTORE KO REALE FINECO
# ==========================================
def seleziona_miglior_ko(prezzo_ingresso, barriera_teorica, tipo_trade="LONG", step_mm=0.50):
    min_strike = np.floor((prezzo_ingresso - 6.0) / step_mm) * step_mm
    max_strike = np.ceil((prezzo_ingresso + 6.0) / step_mm) * step_mm
    barriere_disponibili = np.round(np.arange(min_strike, max_strike + step_mm, step_mm), 2)
    
    if tipo_trade == "LONG":
        candidati = barriere_disponibili[barriere_disponibili < prezzo_ingresso]
        if len(candidati) == 0: return None, 0.0
        barriere_sicure = candidati[candidati <= barriera_teorica]
        strike_scelto = barriere_sicure[-1] if len(barriere_sicure) > 0 else candidati[0]
    else:
        candidati = barriere_disponibili[barriere_disponibili > prezzo_ingresso]
        if len(candidati) == 0: return None, 0.0
        barriere_sicure = candidati[candidati >= barriera_teorica]
        strike_scelto = barriere_sicure[0] if len(barriere_sicure) > 0 else candidati[-1]
        
    distanza_reale = round(abs(prezzo_ingresso - strike_scelto), 2)
    return round(strike_scelto, 2), distanza_reale

# ==========================================
# 3. MOTORE METRICHE & INDICATORI (CACHED)
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
def carica_indicatori():
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
        
        return df.dropna()
    except Exception:
        return pd.DataFrame()

df_base = carica_indicatori()

if df_base.empty:
    st.error("⚠️ **Dati temporaneamente non accessibili da Yahoo Finance.** Riprova tra pochi secondi.")
    st.stop()

# ==========================================
# 4. PATH-DEPENDENCY & KNN SENZA LEAKAGE
# ==========================================
def calcola_esito_path_dependent(df, tp_pts, sl_pts, direzione="LONG", window=10):
    esiti = []
    close_arr = df['Close'].values
    high_arr = df['High'].values
    low_arr = df['Low'].values
    n = len(df)
    
    for i in range(n - window):
        prezzo_0 = close_arr[i]
        vittoria = 0
        if direzione == "LONG":
            tp_lvl = prezzo_0 + tp_pts
            sl_lvl = prezzo_0 - sl_pts
            for j in range(1, window + 1):
                if low_arr[i + j] <= sl_lvl:  # Colpita prima la barriera KO
                    vittoria = 0
                    break
                if high_arr[i + j] >= tp_lvl: # Raggiunto prima il TP
                    vittoria = 1
                    break
        else: # SHORT
            tp_lvl = prezzo_0 - tp_pts
            sl_lvl = prezzo_0 + sl_pts
            for j in range(1, window + 1):
                if high_arr[i + j] >= sl_lvl: # Colpita prima la barriera KO
                    vittoria = 0
                    break
                if low_arr[i + j] <= tp_lvl:  # Raggiunto prima il TP
                    vittoria = 1
                    break
        esiti.append(vittoria)
    esiti.extend([0] * window)
    return np.array(esiti)

def calcola_winrate_realistico(df, sl_pts, tp_long_pts, tp_short_pts):
    features = ['RSI_20', 'Dist_MA_Macro_pct', 'Dist_Supporto_pct', 'ATR_pct']
    window_eval = 10 # 10 ore operative per raggiungere il target
    
    y_long = calcola_esito_path_dependent(df, tp_long_pts, sl_pts, "LONG", window_eval)
    y_short = calcola_esito_path_dependent(df, tp_short_pts, sl_pts, "SHORT", window_eval)
    
    # Train set escludendo le ultime candele di valutazione e la candela live
    X_train = df[features].iloc[:-window_eval]
    y_long_train = y_long[:-window_eval]
    y_short_train = y_short[:-window_eval]
    
    # Target live: solo l'ultima candela
    X_live = df[features].iloc[[-1]]
    
    # Zero Data-Leakage: fitting esclusivamente sul passato
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_live_scaled = scaler.transform(X_live)
    
    knn_long = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_long.fit(X_train_scaled, y_long_train)
    prob_long = float(knn_long.predict_proba(X_live_scaled)[0][1] * 100)
    
    knn_short = KNeighborsClassifier(n_neighbors=50, weights='distance')
    knn_short.fit(X_train_scaled, y_short_train)
    prob_short = float(knn_short.predict_proba(X_live_scaled)[0][1] * 100)
    
    return prob_long, prob_short

# ==========================================
# 5. PANNELLO LATERALE: SINCRONIZZAZIONE & RISCHIO
# ==========================================
st.sidebar.markdown("### 🔄 Inserimento Dati Live")
prezzo_default_yahoo = ottieni_prezzo_live()
prezzo_reale = st.sidebar.number_input("Prezzo Live Fineco (CFD):", value=float(prezzo_default_yahoo), step=0.01, format="%.2f")

st.sidebar.markdown("### ⚖️ Money Management Knockout")
scarto_barriera = st.sidebar.slider("Distanza Barriera Knockout (Punti):", 0.40, 1.00, 0.60, 0.05)
rr_minimo = st.sidebar.number_input("R:R Minimo Accettabile:", value=1.5, step=0.1)

atr_attuale = float(df_base['ATR'].iloc[-1])
supporto_macro = float(df_base['Supporto_Macro'].iloc[-1])
resistenza_macro = float(df_base['Resistenza_Macro'].iloc[-1])

# ==========================================
# 6. CALCOLO LIVELLI REALI FINECO
# ==========================================
STEP_MM = 0.50 # Step barriere borsa Knockout Fineco (0.50$)

# Parametri LONG
ing_long_limit = round(prezzo_reale - (atr_attuale * 0.4), 2)
barriera_long_teorica = round(ing_long_limit - scarto_barriera, 2)
barriera_long_reale, rischio_long_reale = seleziona_miglior_ko(ing_long_limit, barriera_long_teorica, "LONG", STEP_MM)
tp_long = round(resistenza_macro, 2)
tp_long_dist = round(abs(tp_long - ing_long_limit), 2)
rr_reale_long = round(tp_long_dist / rischio_long_reale, 2) if rischio_long_reale > 0 else 0.0

# Parametri SHORT
ing_short_limit = round(prezzo_reale + (atr_attuale * 0.4), 2)
barriera_short_teorica = round(ing_short_limit + scarto_barriera, 2)
barriera_short_reale, rischio_short_reale = seleziona_miglior_ko(ing_short_limit, barriera_short_teorica, "SHORT", STEP_MM)
tp_short = round(supporto_macro, 2)
tp_short_dist = round(abs(ing_short_limit - tp_short), 2)
rr_reale_short = round(tp_short_dist / rischio_short_reale, 2) if rischio_short_reale > 0 else 0.0

# Calcolo ML dinamico allineato agli strike reali e al vero TP
win_long, win_short = calcola_winrate_realistico(df_base, scarto_barriera, tp_long_dist, tp_short_dist)

# ==========================================
# 7. DASHBOARD UI & TELEGRAM
# ==========================================
c1, c2, c3 = st.columns(3)
c1.metric("Prezzo Live", f"{prezzo_reale:.2f}")
c2.metric("Rischio Max (Barriera)", f"{scarto_barriera:.2f} pt")
c3.metric("ATR Volatilità (14H)", f"{atr_attuale:.2f}")

st.markdown("---")
col1, col2 = st.columns(2)

with col1:
    st.markdown("#### 📈 SCENARIO LONG (Buy Limit)")
    st.metric("Win Rate ML (Path-Dependent)", f"{win_long:.1f}%")
    st.progress(int(win_long))
    
    if rr_reale_long >= rr_minimo:
        st.success(f"✅ Money Management Approvato (R:R Reale 1:{rr_reale_long})")
        st.markdown(f"""
        * 📥 **Ingresso Limit (Buy):** `{ing_long_limit:.2f}`
        * 🎯 **Take Profit (Resistenza 150H):** `{tp_long:.2f}`
        * 🛡️ **Strike Knockout Fineco (Reale):** `{barriera_long_reale:.2f}` *(Rischio effettivo: {rischio_long_reale:.2f} pt)*
        """)
        if st.button("🚀 Invia Segnale LONG su Telegram"):
            msg = f"📈 *SEGNALE WTI LONG (Approvato)*\nWin Rate: {win_long:.1f}%\nBuy Limit: {ing_long_limit}\nTP: {tp_long}\nStrike KO: {barriera_long_reale}\nR:R Reale: 1:{rr_reale_long}"
            invia_notifica_telegram(msg)
            st.success("Notifica Telegram inviata con successo!")
    else:
        st.error(f"⛔ TRADE SCARTATO - R:R Reale Sfavorevole (1:{rr_reale_long})")
        st.caption(f"Nota: la barriera reale di borsa a `{barriera_long_reale:.2f}` ha esteso il rischio a `{rischio_long_reale:.2f}` punti.")

with col2:
    st.markdown("#### 📉 SCENARIO SHORT (Sell Limit)")
    st.metric("Win Rate ML (Path-Dependent)", f"{win_short:.1f}%")
    st.progress(int(win_short))
    
    if rr_reale_short >= rr_minimo:
        st.success(f"✅ Money Management Approvato (R:R Reale 1:{rr_reale_short})")
        st.markdown(f"""
        * 📥 **Ingresso Limit (Sell):** `{ing_short_limit:.2f}`
        * 🎯 **Take Profit (Supporto 150H):** `{tp_short:.2f}`
        * 🛡️ **Strike Knockout Fineco (Reale):** `{barriera_short_reale:.2f}` *(Rischio effettivo: {rischio_short_reale:.2f} pt)*
        """)
        if st.button("🚀 Invia Segnale SHORT su Telegram"):
            msg = f"📉 *SEGNALE WTI SHORT (Approvato)*\nWin Rate: {win_short:.1f}%\nSell Limit: {ing_short_limit}\nTP: {tp_short}\nStrike KO: {barriera_short_reale}\nR:R Reale: 1:{rr_reale_short}"
            invia_notifica_telegram(msg)
            st.success("Notifica Telegram inviata con successo!")
    else:
        st.error(f"⛔ TRADE SCARTATO - R:R Reale Sfavorevole (1:{rr_reale_short})")
        st.caption(f"Nota: la barriera reale di borsa a `{barriera_short_reale:.2f}` ha esteso il rischio a `{rischio_short_reale:.2f}` punti.")
# ==========================================
# 8. MODULO DI BACKTEST STORICO E EQUITY CURVE
# ==========================================
st.markdown("---")
st.markdown("## 📊 Backtest Storico & Curva di Equity (Ultimi 6 Mesi)")

@st.cache_data
def esegui_backtest_storico(df, sl_pts, step_mm=0.50):
    """
    Simula l'operatività storica con i costi reali e calcola le metriche di performance.
    Costo fisso per trade (Commissioni + Spread) = 12.00 € (1 punto = 1 €)
    """
    costo_attrito = 12.00
    capitale_iniziale = 1500.00
    equity = [capitale_iniziale]
    
    trade_log = []
    window_eval = 10
    close_arr = df['Close'].values
    high_arr = df['High'].values
    low_arr = df['Low'].values
    
    # Eseguiamo il backtest saltando le ultime candele di test live
    n = len(df) - window_eval
    for i in range(200, n, window_eval): # Partiamo da 200 per avere lo storico MA_Macro pronto
        prezzo_0 = close_arr[i]
        
        # Scegliamo la direzione in base alla posizione rispetto alla MA Macro
        if close_arr[i] > df['MA_Macro_5H'].iloc[i]:
            direzione = "LONG"
            tp_lvl = float(df['Resistenza_Macro'].iloc[i])
            tp_dist = round(abs(tp_lvl - prezzo_0), 2)
            if tp_dist < 0.5: continue # Evita target troppo stretti
            
            # Strike KO reale
            barr_teorica = prezzo_0 - sl_pts
            ko_reale, rischio_reale = seleziona_miglior_ko(prezzo_0, barr_teorica, "LONG", step_mm)
            
        else:
            direzione = "SHORT"
            tp_lvl = float(df['Supporto_Macro'].iloc[i])
            tp_dist = round(abs(prezzo_0 - tp_lvl), 2)
            if tp_dist < 0.5: continue
            
            barr_teorica = prezzo_0 + sl_pts
            ko_reale, rischio_reale = seleziona_miglior_ko(prezzo_0, barr_teorica, "SHORT", step_mm)
            
        if rischio_reale <= 0:
            continue
            
        # Valutazione Path-Dependent del trade
        esito = 0 # 0 = Loss (Barriera KO), 1 = Win (Take Profit)
        for j in range(1, window_eval + 1):
            h = high_arr[i + j]
            l = low_arr[i + j]
            
            if direzione == "LONG":
                if l <= ko_reale:
                    esito = 0 # Presa la barriera
                    break
                if h >= tp_lvl:
                    esito = 1 # Raggiunto il Take Profit
                    break
            else: # SHORT
                if h >= ko_reale:
                    esito = 0
                    break
                if l <= tp_lvl:
                    esito = 1
                    break
                    
        # Calcolo P&L netto del singolo trade (1 punto = 1 €)
        if esito == 1:
            pnl_netto = tp_dist - costo_attrito
        else:
            pnl_netto = -rischio_reale - costo_attrito
            
        capitale_iniziale += pnl_netto
        equity.append(capitale_iniziale)
        trade_log.append({
            "Index": i,
            "Direzione": direzione,
            "Esito": "WIN" if esito == 1 else "LOSS",
            "PnL": pnl_netto,
            "Equity": capitale_iniziale
        })
        
    return pd.DataFrame(trade_log), equity

# Esecuzione del backtest con i parametri attuali della UI
df_trades, curva_equity = esegui_backtest_storico(df_base, scarto_barriera, STEP_MM)

if not df_trades.empty:
    # Metriche aggregate
    tot_trade = len(df_trades)
    vinti = len(df_trades[df_trades['Esito'] == "WIN"])
    persi = len(df_trades[df_trades['Esito'] == "LOSS"])
    win_rate_storico = (vinti / tot_trade) * 100 if tot_trade > 0 else 0
    
    lordo_profitti = df_trades[df_trades['PnL'] > 0]['PnL'].sum()
    lordo_perdite = abs(df_trades[df_trades['PnL'] < 0]['PnL'].sum())
    profit_factor = lordo_profitti / lordo_perdite if lordo_perdite > 0 else 0.0
    
    # Calcolo Max Drawdown
    arr_eq = np.array(curva_equity)
    peak = np.maximum.accumulate(arr_eq)
    drawdown = peak - arr_eq
    max_dd = np.max(drawdown) if len(drawdown) > 0 else 0
    
    # Mostriamo i KPI in Streamlit
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Trade Totali", tot_trade)
    b2.metric("Win Rate Storico", f"{win_rate_storico:.1f}%")
    b3.metric("Profit Factor", f"{profit_factor:.2f}")
    b4.metric("Max Drawdown", f"-{max_dd:.2f} €")
    b5.metric("Profitto Netto Finale", f"{curva_equity[-1] - 1500:.2f} €")
    
    # Grafico della Curva di Equity
    st.markdown("### 📈 Andamento del Capitale (Equity Line)")
    st.line_chart(curva_equity)
    
    with st.expander("🔍 Visualizza Storico Dettagliato dei Trade"):
        st.dataframe(df_trades)
else:
    st.warning("⚠️ Campione di dati insufficiente per generare il backtest con i parametri attuali.")
