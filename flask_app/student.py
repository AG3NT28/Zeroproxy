import base64
import json
import math
import re
import time
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from .auth import current_user, role_required
from .extensions import db
from .models import (Alert, Announcement, AttendanceRecord, Holiday, Leave,
                     ProxyLog, Session, Settings, TimetableEntry, User)
from .nav import NAV_MAP, ROLE_LABELS, ROLE_AVATAR_CLASS
from .utils import (avatar_initials, gen_id, get_att_pct_color, now_date,
                    now_ms, now_time)

bp = Blueprint('student', __name__, url_prefix='/student')

# Hardcoded campus geofence — mirrors the COLLEGE_LAT/LNG/RADIUS constants in
# Student.js (kept separate from Settings.campus_radius, same as the original).
COLLEGE_LAT = 10.0517
COLLEGE_LNG = 76.3290
COLLEGE_RADIUS = 600

DEFAULT_PRIVATE_RANGES = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']

DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def _shell_ctx(page_title, **extra):
    user = current_user()
    return dict(user=user, page_title=page_title, nav_sections=NAV_MAP['student'],
                role_labels=ROLE_LABELS, role_avatar_class=ROLE_AVATAR_CLASS, **extra)


def _settings():
    return db.session.get(Settings, 1)


# ─── Scan QR ──────────────────────────────────────────────────────────────────
@bp.route('/scan')
@role_required('student')
def scan():
    settings = _settings()
    allowed_college_ips = (settings.college_wifi_ips if settings and settings.college_wifi_ips
                           else DEFAULT_PRIVATE_RANGES)
    active_sessions = Session.query.filter_by(active=True).all()
    active_hotspot_ips = [s.hotspot_ip for s in active_sessions if s.hotspot_ip]
    scan_config = {
        'collegeLat': COLLEGE_LAT, 'collegeLng': COLLEGE_LNG, 'collegeRadius': COLLEGE_RADIUS,
        'allowedPatterns': [p for p in (list(allowed_college_ips) + active_hotspot_ips) if p],
        'activeSessions': [{'id': s.id, 'code': s.code, 'dept': s.dept, 'cls': s.cls,
                            'currentCode': s.current_code, 'currentToken': s.current_token}
                           for s in active_sessions],
        'markUrl': url_for('student.scan_mark'),
    }
    return render_template('student/scan.html', **_shell_ctx('Scan QR', scan_config=scan_config))


def _decode_v2_payload(token):
    try:
        raw = base64.b64decode(token[len('ATTX_V2_'):])
        return json.loads(raw.decode('utf-8'))
    except Exception:
        return None


def _resolve_scan_token(raw_token):
    """Port of the token-parsing logic shared by startScanning()/mark-btn in
    Student.js — unwraps QR-link URLs, then matches 4-digit codes, ATTX_V2_
    payloads, or legacy ATTX_sess_<ts>_<rand> tokens to a session."""
    token = (raw_token or '').strip()
    if re.match(r'^https?://', token, re.I):
        try:
            qs = parse_qs(urlparse(token).query)
            unwrapped = (qs.get('scan') or qs.get('token') or [None])[0]
            if unwrapped:
                token = unwrapped.strip()
        except ValueError:
            pass

    sess = None
    if re.match(r'^\d{4}$', token):
        sess = Session.query.filter_by(active=True).filter(
            (Session.current_code == token) | (Session.current_token == token)).first()
    elif token.startswith('ATTX_V2_'):
        payload = _decode_v2_payload(token)
        if payload and payload.get('id'):
            sess = db.session.get(Session, payload['id'])
    else:
        parts = token.split('_')
        if len(parts) >= 4 and parts[0] == 'ATTX' and parts[1] == 'sess':
            sess = db.session.get(Session, f"{parts[1]}_{parts[2]}_{parts[3]}")

    return sess, token


def _check_threshold(user):
    """Port of checkThreshold() — flags subjects below 75% and records a parent
    alert (rate-limited to one per hour) the first time they're detected."""
    completed = Session.query.filter_by(active=False).all()
    completed_ids = [s.id for s in completed]
    # Only count attendance from sessions that have actually finished — an
    # in-progress session shouldn't count toward (or mask) a low-attendance alert.
    records = (AttendanceRecord.query.filter_by(username=user.username)
               .filter(AttendanceRecord.session_id.in_(completed_ids)).all())
    by_subj = {}
    for s in completed:
        by_subj.setdefault(s.code, {'total': 0, 'present': 0})
        by_subj[s.code]['total'] += 1
    for r in records:
        if r.code in by_subj:
            by_subj[r.code]['present'] += 1
    low = [code for code, v in by_subj.items() if v['total'] > 0 and v['present'] / v['total'] * 100 < 75]
    if not low:
        return None
    recent = Alert.query.filter_by(student_username=user.username).filter(Alert.ts > now_ms() - 3600000).first()
    if recent:
        return None
    parent_email = user.parent_email or ''
    db.session.add(Alert(student_username=user.username, student=user.name,
                         roll=user.roll or user.username, parent_email=parent_email or 'Not set',
                         subjects=', '.join(low), ts=now_ms(), time=now_time(), date=now_date()))
    db.session.commit()
    return {'parentEmail': parent_email}


@bp.route('/scan/mark', methods=['POST'])
@role_required('student')
def scan_mark():
    user = current_user()
    payload = request.get_json(silent=True) or {}
    raw_token = (payload.get('token') or request.form.get('token') or '').strip()
    if not raw_token:
        return jsonify(ok=False, message='No token provided')

    sess, token = _resolve_scan_token(raw_token)
    if not sess:
        return jsonify(ok=False, message='Session not found')
    if not sess.active:
        return jsonify(ok=False, message='Session has ended')

    valid_token = token == sess.current_token or token == sess.current_code
    if not valid_token:
        db.session.add(ProxyLog(student=user.name, roll=user.roll or user.username, session=sess.code,
                                time=now_time(), reason='Invalid or expired QR token', ts=now_ms()))
        db.session.commit()
        return jsonify(ok=False, message='Invalid or expired token')

    if AttendanceRecord.query.filter_by(session_id=sess.id, username=user.username).first():
        return jsonify(ok=False, message='Already marked for this session')

    # Capture the marking instant once so the stored record, the response time,
    # and what the student sees on screen are all the exact same value.
    marked_time = now_time()
    marked_date = now_date()
    rec = AttendanceRecord(session_id=sess.id, username=user.username, name=user.name,
                           roll=user.roll or user.username, code=sess.code, dept=sess.dept,
                           sem=sess.sem, date=marked_date, time=marked_time, scan_ts=now_ms())
    db.session.add(rec)
    db.session.commit()

    alert = _check_threshold(user)
    return jsonify(ok=True, message='Attendance marked!',
                   detail=f'{sess.code} · {sess.dept}', time=marked_time, date=marked_date,
                   alert=alert)


# ─── My Attendance ────────────────────────────────────────────────────────────
@bp.route('/attendance')
@role_required('student')
def attendance():
    user = current_user()
    records = (AttendanceRecord.query.filter_by(username=user.username)
               .order_by(AttendanceRecord.id).all())
    completed = Session.query.filter_by(active=False).all()
    completed_ids = {s.id for s in completed}
    # Subject-wise % and the overall figure are both denominated in finished
    # sessions, so the numerator must only count records from those same
    # sessions — otherwise showing up to an in-progress class inflates the %.
    completed_records = [r for r in records if r.session_id in completed_ids]

    by_subj = {}
    for s in completed:
        by_subj.setdefault(s.code, {'total': 0, 'present': 0, 'name': s.name or s.code,
                                     'dept': s.dept, 'sem': s.sem})
        by_subj[s.code]['total'] += 1
    for r in completed_records:
        if r.code in by_subj:
            by_subj[r.code]['present'] += 1

    subjects = []
    for code, d in by_subj.items():
        pct = round(d['present'] / d['total'] * 100) if d['total'] else 0
        needed = (max(0, math.ceil((0.75 * d['total'] - d['present']) / 0.25))
                  if pct < 75 and d['total'] > 0 else 0)
        safe = math.floor((d['present'] - 0.75 * d['total']) / 0.75) if pct >= 75 else 0
        subjects.append({'code': code, **d, 'pct': pct, 'color': get_att_pct_color(pct),
                         'needed': needed, 'safe': safe})

    any_low = any(s['total'] > 0 and s['present'] / s['total'] * 100 < 75 for s in subjects)
    at_risk_count = sum(1 for s in subjects if s['total'] > 0 and s['present'] / s['total'] * 100 < 75)
    overall = round(len(completed_records) / len(completed) * 100) if completed else None
    alerts = Alert.query.filter_by(student_username=user.username).order_by(Alert.ts.desc()).all()
    anns = (Announcement.query.filter(Announcement.target.in_(['all', 'student']))
            .order_by(Announcement.id.desc()).all())

    return render_template(
        'student/attendance.html',
        **_shell_ctx('My Attendance', subjects=subjects, records=list(reversed(records))[:20],
                     alerts=alerts, any_low=any_low, overall=overall,
                     total_classes=len(records), at_risk_count=at_risk_count, announcements=anns)
    )


# ─── Leave Request ────────────────────────────────────────────────────────────
@bp.route('/leave', methods=['GET', 'POST'])
@role_required('student')
def leave():
    user = current_user()
    # Original filtered on `s.section`, a field Session never had — `cls` is the
    # session's section, so match on that instead (otherwise the list is always empty).
    subject_sessions = (Session.query.filter_by(dept=user.dept, cls=user.section)
                        .filter(Session.sem == str(user.sem)).all())
    subjects = sorted({s.code for s in subject_sessions})

    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip()
        from_date = (request.form.get('from_date') or '').strip()
        to_date = (request.form.get('to_date') or '').strip()
        reason = (request.form.get('reason') or '').strip()
        if not subject or not from_date or not to_date or not reason:
            flash('Fill all fields', 'err')
            return redirect(url_for('student.leave'))

        matching = next((s for s in subject_sessions if s.code == subject), None)
        teacher_username = matching.teacher_username if matching else ''
        if not teacher_username:
            for t in User.query.filter_by(role='teacher').all():
                if subject in (t.subjects or []):
                    teacher_username = t.username
                    break

        db.session.add(Leave(id=gen_id('leave'), student_username=user.username, student_name=user.name,
                             roll=user.roll or user.username, teacher_username=teacher_username or '',
                             subject=subject, from_date=from_date, to_date=to_date, reason=reason,
                             status='pending', date=now_date(), ts=now_ms()))
        db.session.commit()
        flash('Leave request submitted', 'ok')
        return redirect(url_for('student.leave'))

    leaves = Leave.query.filter_by(student_username=user.username).order_by(Leave.ts.desc()).all()
    return render_template('student/leave.html', **_shell_ctx('Leave Request', subjects=subjects, leaves=leaves))


# ─── Profile ──────────────────────────────────────────────────────────────────
@bp.route('/profile')
@role_required('student')
def profile():
    return render_template('student/profile.html',
                           **_shell_ctx('Profile & Parents', avatar_initials=avatar_initials))


@bp.route('/profile/password', methods=['POST'])
@role_required('student')
def update_password():
    user = current_user()
    current = request.form.get('current') or ''
    new = request.form.get('new') or ''
    confirm = request.form.get('confirm') or ''
    if not current or not new or not confirm:
        flash('Fill all password fields', 'err')
    elif new != confirm:
        flash('Passwords do not match', 'err')
    elif user.password != current:
        flash('Current password incorrect', 'err')
    else:
        user.password = new
        db.session.commit()
        flash('Password updated successfully', 'ok')
    return redirect(url_for('student.profile'))


# ─── Timetable ────────────────────────────────────────────────────────────────
@bp.route('/timetable')
@role_required('student')
def timetable():
    user = current_user()
    entries = (TimetableEntry.query.filter_by(dept=user.dept, section=user.section)
               .filter(TimetableEntry.sem == str(user.sem)).all())
    by_day = {e.day: e for e in entries}
    today = time.strftime('%Y-%m-%d')
    holidays = [h for h in Holiday.query.order_by(Holiday.date).all() if h.date >= today][:5]
    return render_template('student/timetable.html',
                           **_shell_ctx('Timetable', days=DAYS, entries=entries, by_day=by_day, holidays=holidays))
