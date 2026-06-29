from flask import Flask, request, jsonify, send_from_directory
import requests
import threading
import time
import os
import json
from datetime import datetime, timezone
import yfinance as yf
import firebase_admin
from firebase_admin import credentials, messaging

app = Flask(__name__, static_folder='static')

# ── Environment variables ──────────────────────────────────────────────────────
TWELVE_DATA_API_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')
FIREBASE_CREDS      = os.environ.get('FIREBASE_CREDS', '')

# ── Firebase Admin ─────────────────────────────────────────────────────────────
firebase_ok = False
try:
    if FIREBASE_CREDS:
        cred = credentials.Certificate(json.loads(FIREBASE_CREDS))
        firebase_admin.initialize_app(cred)
        firebase_ok = True
        print('✅ Firebase Admin initialized')
except Exception as e:
    print(f'Firebase init failed: {e}')

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

# ── Persistent storage ─────────────────────────────────────────────────────────
ALERTS_FILE = '/tmp/poi_alerts.json'
TOKENS_FILE = '/tmp/fcm_tokens.json'

def save_alerts():
    try:
        with open(ALERTS_FILE, 'w') as f:
            # Only save config fields, not live price data
            to_save = {}
            for aid, a in alerts.items():
                to_save[aid] = {
                    'pair':           a['pair'],
                    'target':         a['target'],
                    'tolerance_pips': a['tolerance_pips'],
                    'active':         a['active'],
                    'triggered':      a['triggered'],
                }
            json.dump(to_save, f)
    except Exception as e:
        print(f'Save alerts error: {e}')

def load_alerts():
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE) as f:
                saved = json.load(f)
            for aid, a in saved.items():
                alerts[aid] = {
                    'pair':           a['pair'],
                    'target':         a['target'],
                    'tolerance_pips': a.get('tolerance_pips', 5),
                    'active':         a.get('active', True),
                    'triggered':      a.get('triggered', False),
                    'current_price':  None,
                    'last_updated':   None,
                    'source':         '',
                    'market_open':    True,
                }
            print(f'✅ Loaded {len(alerts)} saved alerts')
    except Exception as e:
        print(f'Load alerts error: {e}')

def save_tokens():
    try:
        with open(TOKENS_FILE, 'w') as f:
            json.dump(list(fcm_tokens), f)
    except Exception as e:
        print(f'Save tokens error: {e}')

def load_tokens():
    try:
        if os.path.exists(TOKENS_FILE):
            with open(TOKENS_FILE) as f:
                for t in json.load(f):
                    fcm_tokens.add(t)
            print(f'✅ Loaded {len(fcm_tokens)} FCM tokens')
    except Exception as e:
        print(f'Load tokens error: {e}')

# ── State ──────────────────────────────────────────────────────────────────────
alerts     = {}
alert_lock = threading.Lock()
fcm_tokens = set()
log_entries = []
monitor_thread = None
stop_event = threading.Event()

# Source rotation per pair: tracks which source to try first
source_rotation = {}  # pair -> index 0,1,2

# Load persisted data on startup
load_alerts()
load_tokens()


# ── Helpers ────────────────────────────────────────────────────────────────────
def get_pip(pair):
    return 0.01 if 'JPY' in pair.upper() else 0.0001

def to_yahoo(pair):
    idx = {'SPX':'^GSPC','NAS100':'^NDX','US30':'^DJI',
           'GER40':'^GDAXI','UK100':'^FTSE','JP225':'^N225','AUS200':'^AXJO'}
    upper = pair.upper().replace('/','').replace('-','')
    if upper in idx: return idx[upper]
    if '/' in pair:
        b, q = pair.upper().split('/')
        return f'{b}{q}=X'
    if 'XAUUSD' in upper: return 'GC=F'
    if 'XAGUSD' in upper: return 'SI=F'
    return pair

def add_log(msg):
    log_entries.insert(0, {'time': datetime.now().strftime('%H:%M:%S'), 'msg': msg})
    del log_entries[50:]


# ── 3 Price Sources ────────────────────────────────────────────────────────────

def fetch_yahoo(pair):
    """Source 1: Yahoo Finance — free, no key"""
    p = yf.Ticker(to_yahoo(pair)).fast_info.last_price
    if p and p == p:  # not None, not NaN
        return float(p)
    raise Exception('No price from Yahoo')

def fetch_twelvedata(pair):
    """Source 2: Twelve Data — your API key"""
    if not TWELVE_DATA_API_KEY:
        raise Exception('No Twelve Data key')
    sym = pair.replace('/', '%2F')
    res = requests.get(
        f'https://api.twelvedata.com/price?symbol={sym}&apikey={TWELVE_DATA_API_KEY}',
        timeout=10).json()
    if res.get('status') == 'error':
        raise Exception(res.get('message', 'Twelve Data error'))
    return float(res['price'])

def fetch_frankfurter(pair):
    """Source 3: Frankfurter API — free, no key, Forex only"""
    if '/' not in pair:
        raise Exception('Frankfurter only supports Forex pairs')
    base, quote = pair.upper().split('/')
    # Handle gold/silver — not supported
    if base in ['XAU', 'XAG']:
        raise Exception('Frankfurter does not support metals')
    res = requests.get(
        f'https://api.frankfurter.app/latest?from={base}&to={quote}',
        timeout=10).json()
    if 'rates' not in res or quote not in res['rates']:
        raise Exception('No rate from Frankfurter')
    return float(res['rates'][quote])

SOURCES = [
    ('Yahoo Finance',  fetch_yahoo),
    ('Twelve Data',    fetch_twelvedata),
    ('Frankfurter',    fetch_frankfurter),
]

def fetch_price(pair):
    """Rotate through 3 sources — try each, move to next on failure"""
    start = source_rotation.get(pair, 0)
    errors = []
    for i in range(len(SOURCES)):
        idx = (start + i) % len(SOURCES)
        name, fn = SOURCES[idx]
        try:
            price = fn(pair)
            # Rotate to next source next time to spread load
            source_rotation[pair] = (idx + 1) % len(SOURCES)
            return price, name
        except Exception as e:
            errors.append(f'{name}: {e}')
            continue
    raise Exception(' | '.join(errors))


# ── Market hours ───────────────────────────────────────────────────────────────
def is_market_open(pair):
    now_utc = datetime.now(timezone.utc)
    weekday = now_utc.weekday()  # 0=Mon, 6=Sun
    upper = pair.upper().replace('/','')
    indices = ['SPX','NAS100','US30','GER40','UK100','JP225','AUS200']
    if any(x in upper for x in indices):
        if weekday >= 5: return False
        ng_hour = (now_utc.hour + 1) % 24
        return 8 <= ng_hour <= 22
    # Forex
    if weekday == 5: return False  # Saturday
    if weekday == 6: return now_utc.hour >= 21  # Sunday after 9pm UTC
    if weekday == 4: return now_utc.hour < 21   # Friday before 9pm UTC
    return True


# ── FCM push notification ──────────────────────────────────────────────────────
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
            print(f'FCM sent ✅')
        except Exception as e:
            print(f'FCM error: {e}')
            fcm_tokens.discard(token)
            save_tokens()


# ── Monitor loop ───────────────────────────────────────────────────────────────
def monitor_loop():
    add_log('✅ Monitor started — watching all pairs')
    while not stop_event.is_set():
        with alert_lock:
            active_ids = [aid for aid, a in alerts.items()
                         if a['active'] and not a['triggered']]

        for aid in active_ids:
            with alert_lock:
                if aid not in alerts: continue
                a     = alerts[aid]
                pair  = a['pair']
                target= a['target']
                tol   = a['tolerance_pips'] * get_pip(pair)

            try:
                price, source = fetch_price(pair)
                mkt_open = is_market_open(pair)

                with alert_lock:
                    if aid in alerts:
                        alerts[aid]['current_price'] = price
                        alerts[aid]['last_updated']  = datetime.now().strftime('%H:%M:%S')
                        alerts[aid]['source']        = source
                        alerts[aid]['market_open']   = mkt_open

                if abs(price - target) <= tol:
                    if mkt_open:
                        with alert_lock:
                            if aid in alerts:
                                alerts[aid]['triggered'] = True
                                alerts[aid]['active']    = False
                        add_log(f'🚨 POI HIT! {pair} @ {price:.5f} (POI: {target})')
                        save_alerts()
                        threading.Thread(
                            target=send_fcm,
                            args=(pair, round(price,5), target),
                            daemon=True).start()
                    else:
                        add_log(f'⏸ {pair} near POI but market CLOSED')

            except Exception as e:
                add_log(f'⚠️ {pair} fetch error: {e}')

            time.sleep(2)  # gap between pairs

        stop_event.wait(28)  # ~30s per cycle

    add_log('Monitor stopped.')

def ensure_monitor():
    global monitor_thread, stop_event
    if monitor_thread is None or not monitor_thread.is_alive():
        stop_event = threading.Event()
        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()

# Auto-start monitor if we have saved alerts
if any(a['active'] for a in alerts.values()):
    ensure_monitor()


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
    if token:
        fcm_tokens.add(token)
        save_tokens()
    return jsonify({'status': 'ok'})

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    with alert_lock:
        return jsonify({'alerts': alerts, 'log': log_entries})

@app.route('/api/alerts/add', methods=['POST'])
def add_alert():
    data   = request.json
    pair   = data.get('pair','').strip().upper()
    target = float(data.get('target', 0))
    tol    = int(data.get('tolerance_pips', 5))
    token  = data.get('fcm_token')

    if not pair:   return jsonify({'error': 'Pair required'}), 400
    if not target: return jsonify({'error': 'Target required'}), 400
    if token:
        fcm_tokens.add(token)
        save_tokens()

    with alert_lock:
        # Update if same active pair exists
        for aid, a in alerts.items():
            if a['pair'] == pair and a['active']:
                alerts[aid].update({'target': target, 'tolerance_pips': tol, 'triggered': False})
                add_log(f'Updated {pair} POI → {target}')
                save_alerts()
                ensure_monitor()
                return jsonify({'status': 'updated', 'id': aid})

        aid = str(int(time.time() * 1000))
        alerts[aid] = {
            'pair': pair, 'target': target, 'tolerance_pips': tol,
            'active': True, 'triggered': False,
            'current_price': None, 'last_updated': None,
            'source': '', 'market_open': True,
        }
        add_log(f'➕ Added {pair} POI → {target} (±{tol} pips)')

    save_alerts()
    ensure_monitor()
    return jsonify({'status': 'added', 'id': aid})

@app.route('/api/alerts/remove', methods=['POST'])
def remove_alert():
    aid = request.json.get('id')
    with alert_lock:
        if aid in alerts:
            pair = alerts[aid]['pair']
            del alerts[aid]
            add_log(f'🗑 Removed {pair} alert')
    save_alerts()
    return jsonify({'status': 'removed'})

@app.route('/api/alerts/clear', methods=['POST'])
def clear_alerts():
    with alert_lock:
        alerts.clear()
    save_alerts()
    add_log('🗑 All alerts cleared')
    return jsonify({'status': 'cleared'})

@app.route('/ping')
def ping():
    """UptimeRobot pings this to keep server alive"""
    return jsonify({'status': 'alive', 'alerts': len(alerts), 'time': datetime.now().strftime('%H:%M:%S')})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
