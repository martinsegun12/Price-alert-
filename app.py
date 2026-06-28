from flask import Flask, request, jsonify, send_from_directory
import requests
import threading
import time
import os
from datetime import datetime

app = Flask(__name__, static_folder='static')

# ─── Config from environment variables ───────────────────────────────────────
TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')
NTFY_TOPIC = os.environ.get('NTFY_TOPIC', '')

# ─── Alert state ─────────────────────────────────────────────────────────────
alert_state = {
    'active': False,
    'pair': '',
    'target': 0.0,
    'direction': 'above',
    'interval': 30,
    'current_price': None,
    'last_updated': None,
    'triggered': False,
    'log': []
}

monitor_thread = None
stop_event = threading.Event()


# ─── Fetch price from Twelve Data ────────────────────────────────────────────
def fetch_price(pair):
    symbol = pair.replace('/', '%2F')
    url = f'https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_API_KEY}'
    res = requests.get(url, timeout=10)
    data = res.json()
    if data.get('status') == 'error':
        raise Exception(data.get('message', 'Unknown error'))
    if 'price' not in data:
        raise Exception('No price returned')
    return float(data['price'])


# ─── Send ntfy notification ───────────────────────────────────────────────────
def send_ntfy(pair, price, target, direction):
    topic = NTFY_TOPIC
    title = f'🚨 FOREX ALERT — {pair}'
    body = f'Price {direction} your POI!\nCurrent: {price}\nTarget: {target}'

    # Send notification every 30s for 5 minutes (10 times)
    for i in range(10):
        try:
            requests.post(
                f'https://ntfy.sh/{topic}',
                data=body.encode('utf-8'),
                headers={
                    'Title': title,
                    'Priority': 'max',
                    'Tags': 'rotating_light,chart_with_upwards_trend',
                    'Sound': 'default',
                },
                timeout=10
            )
        except Exception as e:
            print(f'Ntfy error: {e}')
        
        if i < 9:  # Don't sleep after last one
            time.sleep(30)


# ─── Monitor loop ─────────────────────────────────────────────────────────────
def monitor_loop():
    global alert_state
    pair = alert_state['pair']
    target = alert_state['target']
    direction = alert_state['direction']
    interval = alert_state['interval']

    add_log(f'Started watching {pair} — alert if price goes {direction} {target}')

    while not stop_event.is_set():
        try:
            price = fetch_price(pair)
            alert_state['current_price'] = price
            alert_state['last_updated'] = datetime.now().strftime('%H:%M:%S')

            triggered = price >= target if direction == 'above' else price <= target

            if triggered and not alert_state['triggered']:
                alert_state['triggered'] = True
                alert_state['active'] = False
                add_log(f'🚨 TRIGGERED! {pair} hit {price} (target {direction} {target})')

                # Send notifications in background thread
                notif_thread = threading.Thread(
                    target=send_ntfy,
                    args=(pair, price, target, direction),
                    daemon=True
                )
                notif_thread.start()
                break

        except Exception as e:
            add_log(f'Error: {str(e)}')

        stop_event.wait(interval)

    add_log('Monitor stopped.')


def add_log(msg):
    alert_state['log'].insert(0, {
        'time': datetime.now().strftime('%H:%M:%S'),
        'msg': msg
    })
    # Keep max 50 log entries
    alert_state['log'] = alert_state['log'][:50]


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/start', methods=['POST'])
def start_alert():
    global monitor_thread, stop_event

    data = request.json
    pair = data.get('pair', '').strip().upper()
    target = float(data.get('target', 0))
    direction = data.get('direction', 'above')
    interval = int(data.get('interval', 30))

    if not pair:
        return jsonify({'error': 'Pair is required'}), 400
    if not target:
        return jsonify({'error': 'Target price is required'}), 400
    if not TWELVE_DATA_API_KEY:
        return jsonify({'error': 'API key not configured on server'}), 500
    if not NTFY_TOPIC:
        return jsonify({'error': 'NTFY topic not configured on server'}), 500

    # Stop existing monitor
    stop_event.set()
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=5)

    # Reset state
    stop_event = threading.Event()
    alert_state.update({
        'active': True,
        'pair': pair,
        'target': target,
        'direction': direction,
        'interval': interval,
        'current_price': None,
        'last_updated': None,
        'triggered': False,
        'log': []
    })

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    return jsonify({'status': 'started', 'pair': pair, 'target': target, 'direction': direction})


@app.route('/api/stop', methods=['POST'])
def stop_alert():
    global stop_event
    stop_event.set()
    alert_state['active'] = False
    add_log('Alert stopped by user.')
    return jsonify({'status': 'stopped'})


@app.route('/api/status', methods=['GET'])
def get_status():
    return jsonify(alert_state)


@app.route('/api/config', methods=['GET'])
def get_config():
    return jsonify({
        'ntfy_topic': NTFY_TOPIC,
        'has_api_key': bool(TWELVE_DATA_API_KEY)
    })


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
