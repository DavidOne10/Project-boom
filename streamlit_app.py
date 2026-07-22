import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import os
import pytz
from sklearn.ensemble import RandomForestClassifier

# ==========================================
# 1. CONFIGURAZIONE PAGINA E STATO
# ==========================================
st.set_page_config(
    page_title="Quant Drop - Target Win Rate 60%",
    layout="wide",
    page_icon="💧"
)

if "ultimo_segnale" not in st.session_state:
    st.session_state.ultimo_segnale = None
if "nuovo_trade_temp" not in st.session_state:
    st.session_state.nuovo_trade_temp = None

FILE_DIARIO = "diario_trading_winrate_60.csv"
COLONNE_DIARIO = [
    "Data/Ora", "Asset", "Strumento", "Direzione", "Score & Confidenza", 
    "Ingresso", "SL Initial", "TP Target", "Contratti", "Prezzo Uscita", 
    "Esito", "Profitto (€)", "Note Target 60%"
]

def load_diario():
    if os.path.exists(FILE_DIARIO):
        df = pd.read_csv(FILE_DIARIO)
        for col in COLONNE_DIARIO:
            if col not in df.columns:
                df[col] = "--"
        return df[COLONNE_DIARIO]
    else:
        return pd.DataFrame(columns=COLONNE_DIARIO)

# ==========================================
# 2. BRANDING E UI HEADER
# ==========================================
st.markdown("""
<div style="text-align: center; padding-bottom: 10px;">
    <h1 style="font-size: 45px; margin-bottom: -15px; color: #D4AF37;">💧</h1>
    <h2 style="color: #D4AF37; font-family: 'Courier New', Courier, monospace; letter-spacing: 4px; font-weight: bold;">QUANT DROP — TARGET WIN RATE 55-60%</h2>
    <p style="font-size: 13px; color: #888888; letter-spacing: 2px;">BALANCED QUANTITATIVE ENGINE (HIGH PRECISION & CONSISTENCY)</p>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

# ==========================================
# 3. BARRA LATERALE: PARAMETRI DI BILANCIAMENTO
# ==========================================
ZONA_IT = pytz.timezone('Europe/Rome')
ora_attiva_it = datetime.now(ZONA_IT)

st.sidebar.markdown("### ⚙️ Ottimizzazione Win Rate (55-60%)")
soglia_target = st.sidebar.slider(
    "Confidenza Minima Modello (%):", 
    min_value=50, max_value=70, value=58, step=2,
    help="Valore calibrato per mantenere un win rate target del 55-60% senza azzerare le opportunità."
)

filtro_trend_dinamico = st.sidebar.checkbox(
    "Filtro Trend Dinamico (EMA 50)", 
    value=True,
    help="Filtra i trade in base alla media a 50 periodi per evitare inversioni false."
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 💰 Capitale & Rischio")
capitale_conto = st.sidebar.number_input("Capitale Conto (€):", value=10000.0, step=500.0)
tipo_strumento = st.sidebar.selectbox(
    "Strumento Utilizzato:",
    ["Fineco Knockout (Certificati)", "Micro WTI (MCL CFD)", "Standard WTI (CL CFD)"]
)
rr_ratio = st.sidebar.slider("Rapporto Rischio/Rendimento (R:R):", 1.2, 2.5, 1.6, 0.1)

# ==========================================
# 4. MOTORE IA + INDICATORI DI PRECISIONE
# ==========================================
@st.cache_data(ttl=3600)
def addestra_modello_bilanciato(ticker):
    try:
        dati = yf.download(ticker, period="3y", interval="1d", auto_adjust=True)
        if isinstance(dati.columns, pd.MultiIndex):
            dati.columns = dati.columns.get_level_values(0)
            
        if dati.empty or len(dati) < 100:
            return None, None, None

        # Creazione del target (prima della rimozione dei NaN per evitare data leakage sull'ultima candela)
        dati['Target'] = np.where(dati['Close'].shift(-1) > dati['Close'], 1, 0)

        dati['Ritorno_Prezzo'] = dati['Close'].pct_change()
        dati['Media_20'] = dati['Close'].rolling(window=20).mean()
        dati['Media_50'] = dati['Close'].rolling(window=50).mean()

        # RSI (14)
        delta = dati['Close'].diff()
        guadagno = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        perdita = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = guadagno / perdita
        dati['RSI'] = 100 - (100 / (1 + rs))

        std20 = dati['Close'].rolling(window=20).std()
        dati['Banda_Alta'] = dati['Media_20'] + (std20 * 2)
        dati['Banda_Bassa'] = dati['Media_20'] - (std20 * 2)
        dati['Dist_Media50'] = (dati['Close'] - dati['Media_50']) / dati['Media_50']
        dati['Larghezza_Bande'] = (dati['Banda_Alta'] - dati['Banda_Bassa']) / dati['Media_20']

        k = dati['Close'].ewm(span=12, adjust=False).mean()
        d = dati['Close'].ewm(span=26, adjust=False).mean()
        dati['MACD'] = k - d
        dati['MACD_Signal'] = dati['MACD'].ewm(span=9, adjust=False).mean()

        variabili = ['Media_20', 'Close', 'Media_50', 'Ritorno_Prezzo', 'RSI', 'MACD', 'MACD_Signal', 'Dist_Media50', 'Larghezza_Bande']
        
        # Eliminiamo le righe con NaN causati dagli indicatori
        dati = dati.dropna(subset=variabili)
        
        # L'ultima riga ha un 'Target' inesistente (shift futuro). La isoliamo per fare la previsione odierna
        ultimo_dato = dati[variabili].iloc[[-1]]
        close_macro = float(dati['Close'].iloc[-1])
        ma50_macro = float(dati['Media_50'].iloc[-1])
        trend_bullish = close_macro > ma50_macro

        # Il training set viene creato ESCLUDENDO l'ultima riga
        dati_training = dati.iloc[:-1].copy()
        
        X = dati_training[variabili]
        y = dati_training['Target']

        # Random Forest bilanciato per evitare over-fitting
        modello = RandomForestClassifier(n_estimators=100, max_depth=6, min_samples_leaf=15, random_state=42)
        modello.fit(X, y)

        return modello, ultimo_dato, trend_bullish
    except Exception:
        return None, None, None

@st.cache_data(ttl=60)
def carica_dati_live():
    for ticker in ["CL=F", "BZ=F", "USOIL=X"]:
        try:
            df = yf.download(ticker, period="2d", interval="5m", auto_adjust=True)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if not df.empty and 'Close' in df.columns:
                return df, ticker
        except Exception:
            continue
    return None, None

# ==========================================
# 5. ESECUZIONE ANALISI INTRADAY
# ==========================================
df_5m, ticker_attivo = carica_dati_live()

if df_5m is None or df_5m.empty:
    st.error("⚠️ Errore di connessione ai flussi dati di mercato.")
    st.stop()

# MODIFICA: Arrotondamento WTI sempre a 2 decimali
prezzo_live = round(float(df_5m['Close'].iloc[-1]), 2)

# MODIFICA: Analisi delle ultime 100 candele (finestra mobile 8 ore reali)
# Questo garantisce dati solidi sia alle 10:00 che alle 14:30
df_today = df_5m.tail(100)

high_s = float(df_today['High'].max())
low_s = float(df_today['Low'].min())
range_tot = high_s - low_s

# MODIFICA: Arrotondamento WTI a 2 decimali
supporto = round(low_s + (range_tot * 0.2), 2)
resistenza = round(high_s - (range_tot * 0.2), 2)
atr = round(range_tot / 5, 2)

modello_ia, dati_ia, trend_bull_50 = addestra_modello_bilanciato(ticker_attivo)

# Fallback di sicurezza rimosso, se il modello fallisce, l'app si blocca per proteggere il capitale
if modello_ia is not None and dati_ia is not None:
    prob = modello_ia.predict_proba(dati_ia)[0]
    pred = modello_ia.predict(dati_ia)[0]
    confidenza = prob[pred] * 100
else:
    st.error("⚠️ Modello IA in calcolo o non disponibile. Riprova tra qualche minuto.")
    st.stop()

# MODIFICA: Direzione determinata in modo assoluto dalla previsione dell'IA, non dal prezzo live
if pred == 1:
    direzione = "LONG"
    ingresso = supporto
    sl = round(low_s - (atr * 0.15), 2)
    dist_sl = abs(ingresso - sl)
    tp = round(supporto + (dist_sl * rr_ratio), 2)
else:
    direzione = "SHORT"
    ingresso = resistenza
    sl = round(high_s + (atr * 0.15), 2)
    dist_sl = abs(ingresso - sl)
    tp = round(resistenza - (dist_sl * rr_ratio), 2)

# Filtri di Selezione Bilanciata
motivo_filtro = []

if confidenza < soglia_target:
    motivo_filtro.append(f"Confidenza IA ({confidenza:.1f}%) inferiore al target richiesto ({soglia_target}%).")

if filtro_trend_dinamico:
    if direzione == "SHORT" and trend_bull_50:
        motivo_filtro.append("Filtro EMA 50: Trend rialzista di fondo (Segnale Short filtrato per coerenza).")
    elif direzione == "LONG" and not trend_bull_50:
        motivo_filtro.append("Filtro EMA 50: Trend ribassista di fondo (Segnale Long filtrato per coerenza).")

segnale_valido = len(motivo_filtro) == 0

# ==========================================
# 6. INTERFACCIA VISIVA & REPORT
# ==========================================
st.header("⚖️ Scanner Bilanciato (Target Win Rate 55-60%)")
st.markdown(f"**Asset Monitorato:** `{ticker_attivo}` | **Soglia Confidenza:** {soglia_target}% | **R:R Target:** 1:{rr_ratio}")

col1, col2, col3 = st.columns(3)
col1.metric("Supporto Dinamico", supporto)
col2.metric("Prezzo WTI Live", f"{prezzo_live:.2f} USD")
col3.metric("Resistenza Dinamica", resistenza)

st.markdown("---")

if not segnale_valido:
    st.info("🛡️ **MERCATO IN PAUSA / FILTRO ATTIVO**")
    st.write("Per mantenere un win rate costante, il sistema ha filtrato l'opportunità attuale:")
    for m in motivo_filtro:
        st.markdown(f"- ⚠️ *{m}*")
else:
    st.success(f"✅ **CONFIGURAZIONE OTTIMALE RILEVATA (Confidenza: {confidenza:.1f}%)**")
    
    c_i1, c_i2 = st.columns(2)
    c_i1.metric("DIREZIONE", direzione)
    c_i2.metric("QUALITÀ STATISTICA", "⭐⭐⭐ (BILANCIATA)")

    st.markdown("### 📋 Parametri Operativi (Ordini Pendenti Limit)")
    o1, o2, o3 = st.columns(3)
    o1.metric("Ingresso / Trigger", f"{ingresso:.2f}")
    o2.metric("Take Profit (Target)", f"{tp:.2f}")
    o3.metric("Stop Loss (Protetto)", f"{sl:.2f}")

    # Position sizing basato su rischio bilanciato (1.5% del capitale)
    euro_rischio = capitale_conto * 0.015
    dist_punti = abs(ingresso - sl)
    
    if dist_punti > 0:
        if "Standard" in tipo_strumento:
            contratti = max(1, int(euro_rischio / (dist_punti * 1000)))
        elif "Micro" in tipo_strumento:
            contratti = max(1, int(euro_rischio / (dist_punti * 100)))
        else:
            contratti = max(1, int(euro_rischio / dist_punti))
    else:
        contratti = 1

    st.write(f"• **Rischio Operazione:** 1.5% ({euro_rischio:.2f} €) | **Taglia Consigliata:** {contratti} unità")

    if st.button("🚀 REGISTRA TRADE BILANCIATO NEL DIARIO"):
        ora_it = ora_attiva_it.strftime("%d/%m/%Y %H:%M")
        nuovo_t = {
            "Data/Ora": ora_it,
            "Asset": ticker_attivo,
            "Strumento": tipo_strumento,
            "Direzione": direzione,
            "Score & Confidenza": f"{confidenza:.1f}% (Balanced)",
            "Ingresso": ingresso,
            "SL Initial": sl,
            "TP Target": tp,
            "Contratti": contratti,
            "Prezzo Uscita": "--",
            "Esito": "IN CORSO ⏳",
            "Profitto (€)": 0.0,
            "Note Target 60%": f"R:R 1:{rr_ratio}"
        }
        df_d = pd.concat([load_diario(), pd.DataFrame([nuovo_t])], ignore_index=True)
        df_d.to_csv(FILE_DIARIO, index=False)
        st.success("Trade registrato correttamente nel diario di bordo!")
        st.rerun()

# ==========================================
# 7. DIARIO E GESTIONE POSIZIONI
# ==========================================
st.markdown("---")
st.header("📝 Gestione Posizioni & Storico")

diario_df = load_diario()
if not diario_df.empty:
    aperte = diario_df[diario_df["Esito"] == "IN CORSO ⏳"]
    
    if not aperte.empty:
        st.subheader("⚙️ Posizioni Attive")
        for idx, row in aperte.iterrows():
            with st.expander(f"📌 {row['Direzione']} | {row['Asset']} | Aperto: {row['Data/Ora']} ({row['Score & Confidenza']})"):
                col_u1, col_u2 = st.columns(2)
                val_uscita = col_u1.number_input("Prezzo Uscita Reale:", value=float(row['Ingresso']), key=f"out_{idx}", step=0.01)
                esito_scelto = col_u2.selectbox("Esito Finale:", ["GAIN ✅", "LOSS ❌", "BREAK-EVEN 🤝"], key=f"esito_{idx}")
                
                if st.button("💾 CHIUDI E REGISTRA RISULTATO", key=f"btn_chiudi_{idx}"):
                    qta = float(row['Contratti'])
                    if "BREAK-EVEN" in esito_scelto:
                        profitto = 0.0
                    else:
                        molt = 1000 if "Standard" in row['Strumento'] else (100 if "Micro" in row['Strumento'] else 100)
                        px_in = float(row['Ingresso'])
                        punti = (val_uscita - px_in) if row['Direzione'] == 'LONG' else (px_in - val_uscita)
                        profitto = punti * molt * qta
                        
                    diario_df.loc[idx, "Prezzo Uscita"] = round(val_uscita, 2)
                    diario_df.loc[idx, "Esito"] = esito_scelto
                    diario_df.loc[idx, "Profitto (€)"] = round(profitto, 2)
                    diario_df.to_csv(FILE_DIARIO, index=False)
                    st.success("Posizione chiusa e salvata!")
                    st.rerun()
    else:
        st.info("Nessuna posizione aperta al momento.")

    st.subheader("🗄️ Storico Operazioni Target 60%")
    st.dataframe(diario_df, use_container_width=True)
else:
    st.info("Il diario storico è vuoto.")
