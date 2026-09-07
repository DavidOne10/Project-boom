import os
import time
import threading
from datetime import datetime, timedelta
from flask import Flask

app = Flask(__name__)

# Route per far rispondere il server a Render e UptimeRobot
@app.route('/')
def home():
    return "🟢 Bot ORB Attivo 24/7 (EU & USA)", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def execute_scans():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Avvio scansioni automatiche...", flush=True)
    # 1. Scansione Europa (CAC 40 via Euronext)
    os.system("python cac40_checker.py")
    # 2. Scansione USA (SPY, GLD, USO via Alpaca)
    os.system("python checker.py")

def precision_loop():
    # Prima esecuzione immediata all'avvio
    execute_scans()
    
    # Loop sincronizzato sui quarti d'ora
    while True:
        now = datetime.now()
        base_minute = (now.minute // 15) * 15
        target_time = now.replace(minute=base_minute, second=10, microsecond=0)

        if target_time <= now:
            target_time += timedelta(minutes=15)

        time.sleep((target_time - now).total_seconds())
        execute_scans()

if __name__ == "__main__":
    # Avvio del server web Flask su un thread separato
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Avvio del ciclo infinito di scansione
    precision_loop()
