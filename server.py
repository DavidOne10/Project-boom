import os
import time
import threading
from datetime import datetime
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
        # Calcola i secondi alla prossima candela a 15 min (+ 10 sec di tolleranza)
        next_minute = (now.minute // 15 + 1) * 15
        if next_minute == 60:
            next_time = now.replace(hour=(now.hour + 1) % 24, minute=0, second=10, microsecond=0)
        else:
            next_time = now.replace(minute=next_minute, second=10, microsecond=0)

        sleep_seconds = max((next_time - now).total_seconds(), 5)
        time.sleep(sleep_seconds)

        print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] Avvio scansione...")
        # Esegue i tuoi script identici a prima
        os.system("python cac40_checker.py")
        os.system("python checker.py")

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    precision_loop()
