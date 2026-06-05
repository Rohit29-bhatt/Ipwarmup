import os
import json
import time
import threading
import uuid
import csv
import io
import hashlib
import secrets
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, Response, session, redirect, url_for
import pandas as pd
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ─── Secret key for sessions (auto-generated each restart) ──────────────────
app.secret_key = secrets.token_hex(32)

# ─── Dynamic daily password — today's date in DDMMYY format ─────────────────
#     e.g. 5th June 2026 → 050626, 6th June 2026 → 060626
#     Override anytime via environment variable: ACCESS_PASSWORD=custom
def get_access_password():
    override = os.environ.get('ACCESS_PASSWORD')
    if override:
        return override
    return datetime.now().strftime('%d%m%y')   # 050626, 060626, etc.

# ─── In-memory job store ─────────────────────────────────────────────────────
jobs = {}

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_authenticated():
    return session.get('authenticated') is True

def require_auth(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            if request.is_json or request.path.startswith('/api/'):
                return jsonify({'error': 'Unauthorized', 'redirect': '/login'}), 401
            return redirect('/login')
        return fn(*args, **kwargs)
    return wrapper

# ─── Domain → provider mapping ───────────────────────────────────────────────
DOMAIN_MAP = {
    'gmail.com':       {'provider': 'Gmail',       'login_url': 'https://mail.google.com', 'type': 'gmail'},
    'googlemail.com':  {'provider': 'Gmail',       'login_url': 'https://mail.google.com', 'type': 'gmail'},
    'outlook.com':     {'provider': 'Outlook',     'login_url': 'https://outlook.live.com', 'type': 'outlook'},
    'hotmail.com':     {'provider': 'Outlook',     'login_url': 'https://outlook.live.com', 'type': 'outlook'},
    'live.com':        {'provider': 'Outlook',     'login_url': 'https://outlook.live.com', 'type': 'outlook'},
    'msn.com':         {'provider': 'Outlook',     'login_url': 'https://outlook.live.com', 'type': 'outlook'},
    'yahoo.com':       {'provider': 'Yahoo Mail',  'login_url': 'https://mail.yahoo.com',   'type': 'yahoo'},
    'yahoo.co.in':     {'provider': 'Yahoo Mail',  'login_url': 'https://mail.yahoo.com',   'type': 'yahoo'},
    'yahoo.co.uk':     {'provider': 'Yahoo Mail',  'login_url': 'https://mail.yahoo.com',   'type': 'yahoo'},
    'ymail.com':       {'provider': 'Yahoo Mail',  'login_url': 'https://mail.yahoo.com',   'type': 'yahoo'},
    'icloud.com':      {'provider': 'iCloud Mail', 'login_url': 'https://www.icloud.com/mail', 'type': 'icloud'},
    'me.com':          {'provider': 'iCloud Mail', 'login_url': 'https://www.icloud.com/mail', 'type': 'icloud'},
    'mac.com':         {'provider': 'iCloud Mail', 'login_url': 'https://www.icloud.com/mail', 'type': 'icloud'},
    'protonmail.com':  {'provider': 'ProtonMail',  'login_url': 'https://mail.proton.me',   'type': 'proton'},
    'proton.me':       {'provider': 'ProtonMail',  'login_url': 'https://mail.proton.me',   'type': 'proton'},
    'zoho.com':        {'provider': 'Zoho Mail',   'login_url': 'https://mail.zoho.com',    'type': 'zoho'},
    'aol.com':         {'provider': 'AOL Mail',    'login_url': 'https://mail.aol.com',     'type': 'aol'},
}

def get_domain_info(email):
    domain = email.split('@')[-1].lower().strip() if '@' in email else ''
    if domain in DOMAIN_MAP:
        return domain, DOMAIN_MAP[domain]
    return domain, {'provider': 'Corporate / Custom', 'login_url': f'https://mail.{domain}', 'type': 'custom'}

# ─── Auth routes ─────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET'])
def login_page():
    if is_authenticated():
        return redirect('/')
    return render_template('login.html')

@app.route('/api/login', methods=['POST'])
def do_login():
    data = request.json or {}
    entered = data.get('password', '').strip()
    if entered == get_access_password():
        session['authenticated'] = True
        session.permanent = True
        return jsonify({'ok': True})
    return jsonify({'error': 'Incorrect password. Please try again.'}), 401

@app.route('/api/logout', methods=['POST'])
def do_logout():
    session.clear()
    return jsonify({'ok': True})

# ─── App routes (all protected) ───────────────────────────────────────────────

@app.route('/')
@require_auth
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    if not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Use .xlsx, .xls, or .csv'}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        df.columns = [c.lower().strip() for c in df.columns]
        email_col = next((c for c in df.columns if 'email' in c), None)
        pass_col  = next((c for c in df.columns if 'pass' in c or c == 'pwd'), None)
        subj_col  = next((c for c in df.columns if 'subject' in c), None)

        if not email_col or not pass_col:
            return jsonify({'error': 'File must contain "email" and "password" columns'}), 400

        accounts = []
        for _, row in df.iterrows():
            email = str(row[email_col]).strip()
            pwd   = str(row[pass_col]).strip()
            subj  = str(row[subj_col]).strip() if subj_col and pd.notna(row.get(subj_col, '')) else ''
            if email and pwd and '@' in email:
                domain, info = get_domain_info(email)
                accounts.append({
                    'email': email, 'password': pwd, 'subject': subj,
                    'domain': domain, 'provider': info['provider'],
                    'type': info['type'], 'login_url': info['login_url'],
                })

        preview = [{**a, 'password': a['password'][:2] + '•' * max(2, len(a['password'])-2)} for a in accounts[:8]]
        domains = {}
        for a in accounts:
            d = a['domain']
            if d not in domains:
                domains[d] = {'provider': a['provider'], 'count': 0, 'type': a['type']}
            domains[d]['count'] += 1

        session_id = str(uuid.uuid4())
        jobs[session_id] = {'accounts': accounts, 'status': 'ready'}

        return jsonify({
            'session_id': session_id, 'total': len(accounts),
            'preview': preview, 'domains': domains, 'has_subjects': subj_col is not None,
        })
    except Exception as e:
        return jsonify({'error': f'Failed to parse file: {str(e)}'}), 500

@app.route('/api/run', methods=['POST'])
@require_auth
def run_warmup():
    data = request.json
    session_id = data.get('session_id')
    if not session_id or session_id not in jobs:
        return jsonify({'error': 'Invalid session'}), 400

    job = jobs[session_id]
    if job['status'] == 'running':
        return jsonify({'error': 'Already running'}), 400

    config = {
        'global_subject': data.get('global_subject', ''),
        'min_clicks':     int(data.get('min_clicks', 2)),
        'delay_seconds':  int(data.get('delay_seconds', 5)),
        'folder':         data.get('folder', 'inbox'),
        'move_from_spam': data.get('move_from_spam', True),
        'headless':       data.get('headless', True),
    }
    job['config']   = config
    job['status']   = 'running'
    job['progress'] = 0
    job['logs']     = []
    job['results']  = []
    job['started']  = datetime.now().isoformat()

    thread = threading.Thread(target=run_automation, args=(session_id,), daemon=True)
    thread.start()
    return jsonify({'ok': True})

def add_log(job_id, msg, level='info'):
    ts = datetime.now().strftime('%H:%M:%S')
    jobs[job_id]['logs'].append({'ts': ts, 'msg': msg, 'level': level})

def run_automation(job_id):
    job      = jobs[job_id]
    accounts = job['accounts']
    config   = job['config']
    total    = len(accounts)

    add_log(job_id, f'Warmup run started — {total} accounts to process', 'info')
    add_log(job_id, f'Config: min {config["min_clicks"]} clicks, {config["delay_seconds"]}s delay, folder={config["folder"]}', 'info')
    add_log(job_id, '─' * 60, 'sep')

    try:
        from automation import warm_account
        use_real = True
    except Exception as e:
        add_log(job_id, f'Playwright not available ({e}) — running in simulation mode', 'warn')
        use_real = False

    for idx, acc in enumerate(accounts):
        job['progress'] = round((idx / total) * 100)
        subj = acc['subject'] or config['global_subject']
        add_log(job_id, f'[{idx+1}/{total}] {acc["email"]} ({acc["provider"]})', 'account')

        if use_real:
            result = warm_account(acc, subj, config, lambda msg, lvl='info': add_log(job_id, '  ' + msg, lvl))
        else:
            result = simulate_account(acc, subj, config, lambda msg, lvl='info': add_log(job_id, '  ' + msg, lvl))

        result['email']    = acc['email']
        result['domain']   = acc['domain']
        result['provider'] = acc['provider']
        result['subject']  = subj
        job['results'].append(result)

        if idx < total - 1:
            add_log(job_id, f'  Waiting {config["delay_seconds"]}s before next account…', 'info')
            time.sleep(config['delay_seconds'])

    job['progress'] = 100
    job['status']   = 'done'
    job['finished'] = datetime.now().isoformat()

    s  = sum(1 for r in job['results'] if r['status'] == 'success')
    p  = sum(1 for r in job['results'] if r['status'] == 'partial')
    f  = sum(1 for r in job['results'] if r['status'] == 'fail')
    tc = sum(r['clicks'] for r in job['results'])
    add_log(job_id, '─' * 60, 'sep')
    add_log(job_id, f'Run complete ✓  Success: {s}  Partial: {p}  Failed: {f}  Total clicks: {tc}', 'success')

def simulate_account(acc, subject, config, log):
    import random
    time.sleep(0.3)
    login_ok = random.random() > 0.08
    if not login_ok:
        log('✗ Login failed — check credentials or 2FA', 'error')
        return {'status': 'fail', 'login': False, 'found': False, 'clicks': 0,
                'in_spam': False, 'note': 'Login failed — invalid credentials or 2FA blocked',
                'links': [], 'screenshot': None}
    log('✓ Logged in successfully', 'success')

    time.sleep(0.2)
    found   = random.random() > 0.07
    in_spam = found and random.random() > 0.65
    if not found:
        log(f'✗ Email not found — subject: "{subject}"', 'error')
        return {'status': 'partial', 'login': True, 'found': False, 'clicks': 0,
                'in_spam': False, 'note': f'Email not found in {config["folder"]}',
                'links': [], 'screenshot': None}

    if in_spam:
        log('⚠ Found in spam folder', 'warn')
        if config['move_from_spam']:
            log('→ Moved to inbox (marked not spam)', 'info')
    else:
        log(f'✓ Email found in {config["folder"]}', 'success')

    time.sleep(0.15)
    available = random.randint(3, 6)
    to_click  = min(available, config['min_clicks'] + random.randint(0, 2))
    links = []
    for i in range(to_click):
        time.sleep(0.1)
        url = f'https://example-link-{i+1}.com/track?id={uuid.uuid4().hex[:8]}'
        links.append(url)
        log(f'✓ Clicked link {i+1}/{to_click}', 'success')

    note = 'Moved from spam to inbox' if in_spam and config['move_from_spam'] else ('Found in spam' if in_spam else 'Inbox')
    return {'status': 'success', 'login': True, 'found': True, 'clicks': to_click,
            'in_spam': in_spam, 'note': note, 'links': links, 'screenshot': None}

@app.route('/api/status/<job_id>')
@require_auth
def job_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    job = jobs[job_id]
    return jsonify({
        'status':   job.get('status', 'unknown'),
        'progress': job.get('progress', 0),
        'logs':     job.get('logs', []),
        'results':  job.get('results', []),
        'total':    len(job.get('accounts', [])),
    })

@app.route('/api/report/<job_id>/csv')
@require_auth
def download_csv(job_id):
    if job_id not in jobs or jobs[job_id]['status'] != 'done':
        return jsonify({'error': 'Report not ready'}), 404
    job    = jobs[job_id]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Email', 'Domain', 'Provider', 'Subject', 'Login OK', 'Email Found',
                     'In Spam', 'Links Clicked', 'Status', 'Note', 'Timestamp'])
    ts = job.get('finished', datetime.now().isoformat())
    for r in job['results']:
        writer.writerow([
            r['email'], r['domain'], r['provider'], r.get('subject', ''),
            'Yes' if r['login'] else 'No', 'Yes' if r['found'] else 'No',
            'Yes' if r.get('in_spam') else 'No',
            r['clicks'], r['status'], r['note'], ts,
        ])
    output.seek(0)
    date_str = datetime.now().strftime('%Y%m%d_%H%M')
    return Response(output.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': f'attachment; filename=warmup_report_{date_str}.csv'})

@app.route('/api/report/<job_id>/json')
@require_auth
def download_json(job_id):
    if job_id not in jobs or jobs[job_id]['status'] != 'done':
        return jsonify({'error': 'Report not ready'}), 404
    return jsonify(jobs[job_id]['results'])

if __name__ == '__main__':
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('reports', exist_ok=True)
    print('\n' + '='*60)
    print('  IP Warmup Tool — Starting server')
    print(f'  Today\'s password: {get_access_password()}  (changes daily at midnight)')
    print('  Open: http://localhost:5000')
    print('='*60 + '\n')
    app.run(debug=False, host='0.0.0.0', port=5000, threaded=True)
