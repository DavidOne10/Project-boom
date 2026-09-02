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
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def precision_loop():
    while True:
        now = datetime.now()
        # Calcola i minuti mancanti al prossimo blocco da 15 minuti
        minutes_to_add = 15 - (now.minute % 15)
        # Calcola la prossima scansione (:00, :15, :30, :45) + 10 sec di tolleranza dati
        next_time = (now + timedelta(minutes=minutes_to_add)).replace(second=10, microsecond=0)

        sleep_seconds = max((next_time - now).total_seconds(), 5)
        time.sleep(sleep_seconds)

        print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] Avvio scansione...")
        
        # Esecuzione script Europa e USA (verifica solo che i nomi dei file .py su GitHub siano questi)
        os.system("python cac40_checker.py")
        os.system("python checker.py")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    precision_loop()
