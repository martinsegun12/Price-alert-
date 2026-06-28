from flask import Flask, request, jsonify, send_from_directory
import requests
import threading
import time
import os
from datetime import datetime
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__, static_folder='static')

# ── Environment variables ──────────────────────────────────────────────────────
TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')
FIREBASE_CREDS = os.environ.get('FIREBASE_CREDS', '')  # JSON string of service account

# ── Init Firebase Admin ────────────────────────────────────────────────────────
firebase_ok = False
try:
    if FIREBASE_CREDS:
        import json
        cred_dict = json.loads(FIREBASE_CREDS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        firebase_ok = True
        print('Firebase Admin initialized')
except Exception as e:
    print(f'Firebase Admin init failed: {e}')

# ── Firebase client config (served to frontend) ────────────────────────────────
FIREBASE_CLIENT_CONFIG = {
    'apiKey':            os.environ.get('FB_API_KEY', ''),
    'authDomain':        os.environ.get('FB_AUTH_DOMAIN', ''),
    'projectId':         os.environ.get('FB_PROJECT_ID', ''),
    'storageBucket':     os.environ.get('FB_STORAGE_BUCKET', ''),
    'messagingSenderId': os.environ.get('FB_MESSAGING_SENDER_ID', ''),
    'appId':             os.environ.get('FB_APP_ID', ''),
    'vapidKey':          os.environ.get('FB_VAPID_KEY', ''),
}

# ── Alert state ────────────────────────────────────────────────────────────────
alert_state = {
    'active': False,
    'pair': '',
    'target': 0.0,
    'tolerance_pips': 5,
    'current_price': None,
    'last_updated': None,
    'triggered': False,
    'source': '',
    'log': []
}

fcm_tokens = set()
monitor_thread = None
stop_event = threading.Event()


# ── Pip value ──────────────────────────────────────────────────────────────────
def get_pip_value(pair):
    return 0.01 if 'JPY' in pair.upper() else 0.0001


# ── Yahoo Finance symbol ───────────────────────────────────────────────────────
def to_yahoo_symbol(pair):
    idx = {'SPX':'^GSPC','NAS100':'^NDX','US30':'^DJI','GER40':'^GDAXI','UK100':'^FTSE','JP225':'^N225','AUS200':'^AXJO'}
    upper = pair.upper().replace('/','').replace('-','')
    if upper in idx: return idx[upper]
    if '/' in pair:
        b, q = pair.upper().split('/')
        return f'{b}{q}=X'
    if 'XAUUSD' in upper: return 'GC=F'
    if 'XAGUSD' in upper: return 'SI=F'
    return pair


# ── Fetch price ────────────────────────────────────────────────────────────────
def fetch_price(pair):
    try:
        price = yf.Ticker(to_yahoo_symbol(pair)).fast_info.last_price
        if price and price == price:
            alert_state['source'] = 'Yahoo Finance'
            return float(price)
        raise Exception('No price')
    except Exception as e:
        add_log(f'Yahoo failed ({e}), trying Twelve Data...')
        if not TWELVE_DATA_API_KEY:
            raise Exception('No backup API key')
        sym = pair.replace('/','%2F')
        res = requests.get(f'https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_DATA_API_KEY}', timeout=10).json()
        if res.get('status') == 'error': raise Exception(res.get('message'))
        alert_state['source'] = 'Twelve Data'
        return float(res['price'])


# ── Send FCM push notification ────────────────────────────────────────────────
def send_fcm(pair, price, target):
    if not firebase_ok or not fcm_tokens:
        return
    title = f'🚨 POI HIT — {pair}'
    body  = f'Price touched your level!\nCurrent: {price}\nYour POI: {target}'
    for token in list(fcm_tokens):
        try:
            msg = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default',
                        priority='max',
                        default_vibrate_timings=True,
                    )
                ),
                token=token,
            )
            messaging.send(msg)
            print(f'FCM sent to {token[:20]}...')
        except Exception as e:
            print(f'FCM error: {e}')
            fcm_tokens.discard(token)


# ── Monitor loop ───────────────────────────────────────────────────────────────
def monitor_loop():
    pair = alert_state['pair']
    target = alert_state['target']
    tol_pips = alert_state['tolerance_pips']
    pip = get_pip_value(pair)
    tolerance = tol_pips * pip

    add_log(f'Watching {pair} — POI: {target} (±{tol_pips} pips)')

    while not stop_event.is_set():
        try:
            price = fetch_price(pair)
            alert_state['current_price'] = price
            alert_state['last_updated'] = datetime.now().strftime('%H:%M:%S')

            if abs(price - target) <= tolerance and not alert_state['triggered']:
                alert_state['triggered'] = True
                alert_state['active'] = False
                add_log(f'🚨 POI HIT! {pair} touched {price:.5f} (POI: {target})')
                threading.Thread(target=send_fcm, args=(pair, round(price,5), target), daemon=True).start()
                break

        except Exception as e:
            add_log(f'Error: {e}')

        stop_event.wait(30)

    add_log('Monitor stopped.')


def add_log(msg):
    alert_state['log'].insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    alert_state['log'] = alert_state['log'][:50]


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)

@app.route('/api/firebase-config')
def firebase_config():
    return jsonify(FIREBASE_CLIENT_CONFIG)

@app.route('/api/register-token', methods=['POST'])
def register_token():
    token = request.json.get('token')
    if token:
        fcm_tokens.add(token)
        print(f'Token registered: {token[:20]}...')
    return jsonify({'status': 'ok'})

@app.route('/api/start', methods=['POST'])
def start_alert():
    global monitor_thread, stop_event
    data = request.json
    pair = data.get('pair','').strip().upper()
    target = float(data.get('target', 0))
    tol = int(data.get('tolerance_pips', 5))
    token = data.get('fcm_token')

    if not pair: return jsonify({'error': 'Pair required'}), 400
    if not target: return jsonify({'error': 'Target required'}), 400
    if token: fcm_tokens.add(token)

    stop_event.set()
    if monitor_thread and monitor_thread.is_alive():
        monitor_thread.join(timeout=5)

    stop_event = threading.Event()
    alert_state.update({'active':True,'pair':pair,'target':target,'tolerance_pips':tol,
                        'current_price':None,'last_updated':None,'triggered':False,'log':[]})

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()
    return jsonify({'status':'started','pair':pair,'target':target})

@app.route('/api/stop', methods=['POST'])
def stop_alert():
    global stop_event
    stop_event.set()
    alert_state['active'] = False
    add_log('Alert stopped by user.')
    return jsonify({'status':'stopped'})

@app.route('/api/status')
def get_status():
    return jsonify(alert_state)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
