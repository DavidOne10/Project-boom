import os
import requests


def send_telegram_message(message):
  token = os.environ.get('TELEGRAM_BOT_TOKEN')
  chat_id = os.environ.get('TELEGRAM_CHAT_ID')

  if not token or not chat_id:
    print('Errore: Token o Chat ID non configurati nelle variabili d ambiente.')
    return

  url = f'https://api.telegram.org/bot{token}/sendMessage'
  payload = {'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}

  response = requests.post(url, json=payload)
  if response.status_code == 200:
    print('Notifica Telegram inviata con successo!')
  else:
    print(f"Errore nell'invio: {response.text}")


def main():
  # --- INSERISCI QUI LA LOGICA DEL TUO MODELLO QUANTITATIVO ---
  # Esempio basato sui dati del tuo modello:
  win_rate = 58.6

  # Condizione di attivazione del segnale
  if win_rate > 56.0:
    messaggio = (
        '🚨 *NUOVO SEGNALE QUANTITATIVO* 🚨\n\n'
        '📉 *Scenario:* Short (Ribassista)\n'
        f'📊 *Win Rate IA:* {win_rate}%\n'
        '🎯 *Trigger Ingresso:* 84.01\n'
        '💰 *Take Profit:* 83.56\n'
        '🛑 *Stop Loss:* 83.53'
    )
    send_telegram_message(messaggio)
  else:
    print(
        f'Analisi completata. Win Rate ({win_rate}%) sotto la soglia minima.'
    )


if __name__ == '__main__':
  main()
