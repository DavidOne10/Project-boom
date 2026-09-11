from datetime import datetime
import pandas as pd
import yfinance as yf

# 1. Download dati giornalieri
df = yf.download(
    "^GDAXI", period="3mo", interval="1d", progress=False, auto_adjust=True
)
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df = df.reset_index()

today_str = datetime.now().strftime("%Y-%m-%d")
last_date_str = df["Date"].dt.strftime("%Y-%m-%d").iloc[-1]

# 2. Verifica ritardo candela odierna
if last_date_str != today_str:
    print(
        f"[AVVISO] Candela del {today_str} non ancora presente in yfinance (Ultima: {last_date_str})."
    )
    print("Recupero l'ultimo prezzo utile dai dati intraday...")

    # Fetch dati a 5m per estrarre la chiusura di oggi
    df_intra = yf.download(
        "^GDAXI", period="1d", interval="5m", progress=False, auto_adjust=True
    )
    if isinstance(df_intra.columns, pd.MultiIndex):
        df_intra.columns = df_intra.columns.get_level_values(0)

    if not df_intra.empty:
        today_close = df_intra["Close"].iloc[-1]
        today_open = df_intra["Open"].iloc[0]
        today_high = df_intra["High"].max()
        today_low = df_intra["Low"].min()

        # Append manuale della candela odierna
        new_row = pd.DataFrame(
            [{
                "Date": pd.to_datetime(today_str),
                "Open": today_open,
                "High": today_high,
                "Low": today_low,
                "Close": today_close,
            }]
        )

        df = pd.concat([df, new_row], ignore_index=True)
        print(
            f"[OK] Candela odierna ricostruita con successo! Chiusura stimata: {today_close:.2f}"
        )
else:
    print(f"[OK] Dati aggiornati all'ultima chiusura ({last_date_str}).")

# 3. Calcolo Segnale per Domani
df["ema50"] = df["Close"].ewm(span=50, adjust=False).mean()
df["high_10"] = df["Close"].shift(1).rolling(10).max()

last_row = df.iloc[-1]
signal_today = (last_row["Close"] > last_row["ema50"]) and (
    last_row["Close"] > last_row["high_10"]
)

print(f"\nDAX Spot Close: {last_row['Close']:.2f}")
print(f"EMA50: {last_row['ema50']:.2f} | Max 10g: {last_row['high_10']:.2f}")
print(f"SEGNALE PER DOMANI IN APERTURA: {'INSERIRE ORDINE LONG' if signal_today else 'NESSUNA AZIONE'}")
