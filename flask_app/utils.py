"""Server-side ports of src/utils/helpers.js — id/token generation, geofencing
math, IP allow-list matching, and CSV/JSON export. (Camera capture, GPS and
WebRTC IP discovery are intrinsically browser APIs; their client-side
counterparts live in static/js/.)"""
import base64
import csv
import io
import json
import math
import random
import time

from flask import Response


def now_ms():
    return int(time.time() * 1000)


def now_time():
    return time.strftime('%I:%M %p').lstrip('0')


def now_date():
    return time.strftime('%-m/%-d/%Y')


def gen_id(prefix='id'):
    return f"{prefix}_{now_ms()}_{''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=4))}"


def gen_token():
    return str(random.randint(0, 9999)).zfill(4)


def encode_session_payload(sess, token):
    """sess is a models.Session row. Mirrors encodeSessionPayload() in helpers.js —
    produces the same `ATTX_V2_<base64 json>` token embedded in the QR image."""
    payload = {
        'id': sess.id, 'code': sess.code, 'name': sess.name or sess.code,
        'cls': sess.cls, 'sem': sess.sem, 'dept': sess.dept,
        'duration': 0, 'teacher': sess.teacher, 'teacherUsername': sess.teacher_username,
        'startTime': sess.start_time, 'date': sess.date, 'token': token,
    }
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return 'ATTX_V2_' + base64.b64encode(raw).decode('ascii')


def haversine(lat1, lng1, lat2, lng2):
    r = 6371000
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lng / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_ipv4(ip):
    parts = [int(o) for o in ip.split('.')]
    val = 0
    for o in parts:
        val = (val << 8) + o
    return val & 0xffffffff


def match_ip_pattern(ip, pattern):
    if not ip or not pattern:
        return False
    ip = ip.strip()
    pattern = pattern.strip()
    try:
        if '/' in pattern:
            base, mask = pattern.split('/')
            prefix = int(mask)
            if prefix < 0 or prefix > 32:
                return False
            mask_val = 0 if prefix == 0 else (0xffffffff << (32 - prefix)) & 0xffffffff
            return (_parse_ipv4(ip) & mask_val) == (_parse_ipv4(base) & mask_val)
        if '*' in pattern:
            import re
            regex = '^' + pattern.replace('.', r'\.').replace('*', '.*') + '$'
            return re.match(regex, ip) is not None
        return ip == pattern
    except (ValueError, IndexError):
        return False


def is_ip_allowed(ip, allowed_patterns):
    if not ip or not allowed_patterns:
        return False
    return any(match_ip_pattern(ip, p) for p in allowed_patterns)


def get_att_pct_color(pct):
    if pct is None:
        return 'gray'
    if pct >= 75:
        return 'green'
    if pct >= 60:
        return 'amber'
    return 'red'


def format_pct(pct):
    return '—' if pct is None else f'{pct}%'


def avatar_initials(name):
    name = name or 'U'
    return ''.join(w[0] for w in name.split(' ') if w)[:2].upper()


def export_csv(rows, filename):
    """rows: list[dict] with identical keys. Mirrors exportCSV() in helpers.js."""
    if not rows:
        return Response('', mimetype='text/csv')
    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in rows:
        writer.writerow({h: ('' if row.get(h) is None else row.get(h)) for h in headers})
    resp = Response(buf.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp


def export_json(data, filename):
    resp = Response(json.dumps(data, indent=2), mimetype='application/json')
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp
