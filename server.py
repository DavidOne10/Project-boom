import os
import time
import threading
from datetime import datetime, timedelta
from flask import Flask

app = Flask(__name__)

@app.route('/')
def home():
    return "🟢 Bot ORB Attivo 24/7", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def execute_scans():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Avvio scansione...", flush=True)
    os.system("python cac40_checker.py")
    os.system("python checker.py")

def precision_loop():
    # 1. Scansione immediata all'avvio
    execute_scans()

    while True:
        now = datetime.now()
        
        # Trova l'inizio del quarto d'ora corrente (:00, :15, :30, :45)
        base_minute = (now.minute // 15) * 15
        target_time = now.replace(minute=base_minute, second=10, microsecond=0)

        # Se lo spacco dei :10 di questo quarto d'ora è passato, punta al prossimo
        if target_time <= now:
            target_time += timedelta(minutes=15)

        sleep_seconds = (target_time - now).total_seconds()
        time.sleep(sleep_seconds)

        # 2. Scansione ad ogni spacco di 15 minuti
        execute_scans()

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    precision_loop()
