from flask import Flask, request, jsonify, send_from_directory
import requests
import threading
import time
import os
from datetime import datetime
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, messaging
import json

app = Flask(__name__, static_folder='static')

# ── Environment variables ──────────────────────────────────────────────────────
TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')
FIREBASE_CREDS = os.environ.get('FIREBASE_CREDS', '')

# ── Init Firebase Admin ────────────────────────────────────────────────────────
firebase_ok = False
try:
    if FIREBASE_CREDS:
        cred_dict = json.loads(FIREBASE_CREDS)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        firebase_ok = True
        print('Firebase Admin initialized')
except Exception as e:
    print(f'Firebase Admin init failed: {e}')

# ── Firebase client config ─────────────────────────────────────────────────────
FIREBASE_CLIENT_CONFIG = {
    'apiKey':            os.environ.get('FB_API_KEY', ''),
    'authDomain':        os.environ.get('FB_AUTH_DOMAIN', ''),
    'projectId':         os.environ.get('FB_PROJECT_ID', ''),
    'storageBucket':     os.environ.get('FB_STORAGE_BUCKET', ''),
    'messagingSenderId': os.environ.get('FB_MESSAGING_SENDER_ID', ''),
    'appId':             os.environ.get('FB_APP_ID', ''),
    'vapidKey':          os.environ.get('FB_VAPID_KEY', ''),
}

# ── State ──────────────────────────────────────────────────────────────────────
# alerts = { id: { pair, target, tolerance_pips, active, triggered, current_price, last_updated, source } }
alerts = {}
alert_lock = threading.Lock()
fcm_tokens = set()
monitor_thread = None
stop_event = threading.Event()
log_entries = []


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_pip(pair):
    return 0.01 if 'JPY' in pair.upper() else 0.0001

def to_yahoo(pair):
    idx = {'SPX':'^GSPC','NAS100':'^NDX','US30':'^DJI','GER40':'^GDAXI',
           'UK100':'^FTSE','JP225':'^N225','AUS200':'^AXJO'}
    upper = pair.upper().replace('/','').replace('-','')
    if upper in idx: return idx[upper]
    if '/' in pair:
        b,q = pair.upper().split('/')
        return f'{b}{q}=X'
    if 'XAUUSD' in upper: return 'GC=F'
    if 'XAGUSD' in upper: return 'SI=F'
    return pair

def fetch_price(pair):
    try:
        p = yf.Ticker(to_yahoo(pair)).fast_info.last_price
        if p and p == p:
            return float(p), 'Yahoo Finance'
        raise Exception('No price')
    except:
        if not TWELVE_DATA_API_KEY:
            raise Exception('No backup API key')
        sym = pair.replace('/','%2F')
        res = requests.get(
            f'https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_DATA_API_KEY}',
            timeout=10).json()
        if res.get('status') == 'error': raise Exception(res.get('message'))
        return float(res['price']), 'Twelve Data'

def add_log(msg):
    log_entries.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    del log_entries[50:]

def send_fcm(pair, price, target):
    if not firebase_ok or not fcm_tokens: return
    title = f'🚨 POI HIT — {pair}'
    body  = f'Price touched your level!\nCurrent: {price}\nYour POI: {target}'
    for token in list(fcm_tokens):
        try:
            messaging.send(messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        sound='default', priority='max',
                        default_vibrate_timings=True)),
                token=token))
        except Exception as e:
            print(f'FCM error: {e}')
            fcm_tokens.discard(token)


# ── Monitor loop (watches ALL alerts) ─────────────────────────────────────────
def monitor_loop():
    add_log('Monitor started — watching all pairs')
    while not stop_event.is_set():
        with alert_lock:
            active_ids = [aid for aid, a in alerts.items() if a['active'] and not a['triggered']]

        for aid in active_ids:
            with alert_lock:
                if aid not in alerts: continue
                alert = alerts[aid]
                pair = alert['pair']
                target = alert['target']
                tol = alert['tolerance_pips'] * get_pip(pair)

            try:
                price, source = fetch_price(pair)
                with alert_lock:
                    if aid in alerts:
                        alerts[aid]['current_price'] = price
                        alerts[aid]['last_updated'] = datetime.now().strftime('%H:%M:%S')
                        alerts[aid]['source'] = source

                if abs(price - target) <= tol:
                    with alert_lock:
                        if aid in alerts:
                            alerts[aid]['triggered'] = True
                            alerts[aid]['active'] = False
                    add_log(f'🚨 POI HIT! {pair} touched {price:.5f} (POI: {target})')
                    threading.Thread(
                        target=send_fcm,
                        args=(pair, round(price,5), target),
                        daemon=True).start()

            except Exception as e:
                add_log(f'Error fetching {pair}: {e}')

            time.sleep(1)  # small gap between pair fetches

        stop_event.wait(28)  # ~30s total per cycle

    add_log('Monitor stopped.')


def ensure_monitor():
    global monitor_thread, stop_event
    if monitor_thread is None or not monitor_thread.is_alive():
        stop_event = threading.Event()
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index(): return send_from_directory('static', 'index.html')

@app.route('/static/<path:path>')
def static_files(path): return send_from_directory('static', path)

@app.route('/api/firebase-config')
def firebase_config(): return jsonify(FIREBASE_CLIENT_CONFIG)

@app.route('/api/register-token', methods=['POST'])
def register_token():
    token = request.json.get('token')
    if token: fcm_tokens.add(token)
    return jsonify({'status': 'ok'})

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    with alert_lock:
        return jsonify({'alerts': alerts, 'log': log_entries})

@app.route('/api/alerts/add', methods=['POST'])
def add_alert():
    data = request.json
    pair = data.get('pair','').strip().upper()
    target = float(data.get('target', 0))
    tol = int(data.get('tolerance_pips', 5))
    token = data.get('fcm_token')

    if not pair: return jsonify({'error': 'Pair required'}), 400
    if not target: return jsonify({'error': 'Target required'}), 400
    if token: fcm_tokens.add(token)

    # Check for duplicate pair
    with alert_lock:
        for aid, a in alerts.items():
            if a['pair'] == pair and a['active']:
                # Update existing
                alerts[aid]['target'] = target
                alerts[aid]['tolerance_pips'] = tol
                alerts[aid]['triggered'] = False
                add_log(f'Updated {pair} POI → {target}')
                ensure_monitor()
                return jsonify({'status': 'updated', 'id': aid})

        aid = str(int(time.time() * 1000))
        alerts[aid] = {
            'pair': pair, 'target': target, 'tolerance_pips': tol,
            'active': True, 'triggered': False,
            'current_price': None, 'last_updated': None, 'source': ''
        }
        add_log(f'Added {pair} POI → {target} (±{tol} pips)')

    ensure_monitor()
    return jsonify({'status': 'added', 'id': aid})

@app.route('/api/alerts/remove', methods=['POST'])
def remove_alert():
    aid = request.json.get('id')
    with alert_lock:
        if aid in alerts:
            pair = alerts[aid]['pair']
            del alerts[aid]
            add_log(f'Removed alert for {pair}')
    return jsonify({'status': 'removed'})

@app.route('/api/alerts/clear', methods=['POST'])
def clear_alerts():
    with alert_lock:
        alerts.clear()
    add_log('All alerts cleared')
    return jsonify({'status': 'cleared'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
