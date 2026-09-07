import os
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# Password di sicurezza per autorizzare le chiamate da TradingView
WEBHOOK_SECRET = "BOOM_ORB_2026"

@app.route('/')
def home():
    return "🟢 Bot ORB Attivo 24/7", 200

@app.route('/webhook-cac40', methods=['POST'])
def cac40_webhook():
    try:
        data = request.get_json(force=True)
        
        # Controllo sicurezza
        if not data or data.get('secret') != WEBHOOK_SECRET:
            print("⚠️ [WEBHOOK CAC40] Tentativo di accesso non autorizzato.")
            return jsonify({'status': 'unauthorized'}), 401
        
        action = data.get('action')  # "BUY" o "SELL"
        price = data.get('price')    # Prezzo d'ingresso
        sl = data.get('sl')          # Stop Loss
        tp = data.get('tp')          # Take Profit
        
        print(f"\n⚡ [{datetime.now().strftime('%H:%M:%S')}] SEGNALE WEBHOOK CAC 40 RICEVUTO: {action} a {price} (SL: {sl}, TP: {tp})", flush=True)
        
        # Esegue cac40_checker.py passando i parametri ricevuti dal Webhook
        cmd = f'python cac40_checker.py --action {action} --price {price} --sl {sl} --tp {tp}'
        threading.Thread(target=lambda: os.system(cmd), daemon=True).start()
        
        return jsonify({'status': 'success', 'message': 'Signal dispatched'}), 200

    except Exception as e:
        print(f"❌ [WEBHOOK ERROR]: {e}", flush=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def execute_scans():
    print(f"\n⏰ [{datetime.now().strftime('%H:%M:%S')}] Avvio scansione USA (Alpaca API)...", flush=True)
    os.system("python checker.py")

def precision_loop():
    # 1. Scansione immediata all'avvio (USA)
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

        # 2. Scansione ad ogni spacco di 15 minuti (USA)
        execute_scans()

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    precision_loop()
