import io

import qrcode
from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)

from .auth import current_user, role_required
from .extensions import db
from .models import AttendanceRecord, Leave, Announcement, Session
from .nav import NAV_MAP, ROLE_LABELS, ROLE_AVATAR_CLASS
from .utils import (avatar_initials, encode_session_payload, export_csv, export_json,
                    gen_id, gen_token, get_att_pct_color, now_date, now_ms, now_time)

bp = Blueprint('teacher', __name__, url_prefix='/teacher')

QR_ROTATE_MS = 5000


def _shell_ctx(page_title, **extra):
    user = current_user()
    return dict(user=user, page_title=page_title, nav_sections=NAV_MAP['teacher'],
                role_labels=ROLE_LABELS, role_avatar_class=ROLE_AVATAR_CLASS, **extra)


def _teacher_sessions(user):
    return Session.query.filter_by(teacher_username=user.username).order_by(Session.start_time.desc()).all()


def _active_session(user):
    return Session.query.filter_by(teacher_username=user.username, active=True).first()


def _compute_at_risk(sessions, threshold):
    """Port of computeAtRiskStudents() — tallies presence across this teacher's
    completed sessions and flags students below the threshold."""
    tally = {}
    for sess in sessions:
        for entry in sess.attendance:
            key = entry.roll or entry.name
            tally.setdefault(key, {'name': entry.name, 'roll': entry.roll, 'count': 0})
            tally[key]['count'] += 1
    total = len(sessions)
    out = []
    for s in tally.values():
        pct = round(s['count'] / total * 100) if total else 0
        if pct < threshold:
            out.append({**s, 'pct': pct})
    return sorted(out, key=lambda s: s['pct'])


def _ensure_token_fresh(sess):
    """Rotate the session's QR token if QR_ROTATE_MS has elapsed. Mirrors the
    setTimeout(rotateQR, 5000) loop in Teacher.js, but driven lazily by polling
    requests instead of a server-side timer (Flask handles one request at a time)."""
    if not sess.active:
        return
    now = now_ms()
    if not sess.current_token or now - (sess.token_updated_at or 0) >= QR_ROTATE_MS:
        code = gen_token()
        sess.current_code = code
        sess.current_token = encode_session_payload(sess, code)
        sess.token_updated_at = now
        db.session.commit()


# ─── Session Manager ──────────────────────────────────────────────────────────
@bp.route('/session')
@role_required('teacher')
def session():
    user = current_user()
    active = _active_session(user)
    sessions = _teacher_sessions(user)
    today_sessions = [s for s in sessions if s.date == now_date()]
    avg = round(sum(s.attendance.count() for s in sessions) / len(sessions)) if sessions else None

    if active:
        _ensure_token_fresh(active)

    return render_template(
        'teacher/session.html',
        **_shell_ctx('Session Manager', active=active, today_sessions=today_sessions,
                     total_sessions=len(sessions), avg_attendance=avg,
                     qr_rotate_ms=QR_ROTATE_MS, avatar_initials=avatar_initials)
    )


@bp.route('/session/start', methods=['POST'])
@role_required('teacher')
def start_session():
    user = current_user()
    if _active_session(user):
        return _bounce_with_error('You already have an active session — end it before starting a new one')
    code = (request.form.get('code') or '').strip()
    cls = (request.form.get('cls') or '').strip()
    if not code or not cls:
        return _bounce_with_error('Fill in subject code and section')

    sess = Session(
        id=gen_id('sess'), code=code, name=(request.form.get('name') or '').strip() or code,
        cls=cls, sem=request.form.get('sem') or '4', dept=request.form.get('dept') or 'CSE',
        teacher=user.name, teacher_username=user.username,
        hotspot_ip=(request.form.get('hotspot') or '').strip(),
        start_time=now_ms(), active=True, date=now_date(),
    )
    db.session.add(sess)
    db.session.commit()
    return redirect_with_toast('teacher.session', 'Session started!', 'ok')


@bp.route('/session/<sid>/end', methods=['POST'])
@role_required('teacher')
def end_session(sid):
    sess = _own_session_or_404(sid)
    sess.active = False
    db.session.commit()
    return redirect_with_toast('teacher.session', 'Session ended', 'ok')


@bp.route('/session/<sid>/add-manual', methods=['POST'])
@role_required('teacher')
def add_manual(sid):
    sess = _own_session_or_404(sid)
    name = (request.form.get('name') or '').strip()
    roll = (request.form.get('roll') or '').strip() or 'Manual'
    if not name:
        return _bounce_with_error('Student name is required')
    rec = AttendanceRecord(session_id=sess.id, username='manual_' + str(now_ms()),
                           name=name, roll=roll, code=sess.code, dept=sess.dept, sem=sess.sem,
                           date=sess.date, time=now_time(), manual=True)
    db.session.add(rec)
    db.session.commit()
    return redirect_with_toast('teacher.session', 'Student added', 'ok')


@bp.route('/session/<sid>/qr.png')
@role_required('teacher')
def session_qr(sid):
    sess = _own_session_or_404(sid)
    _ensure_token_fresh(sess)
    # Encode the bare token, not a full scan URL. The URL wrapper added ~45 chars
    # (and its `?scan=` param was never read server-side — scan() ignores
    # request.args), needlessly inflating QR density. The student scanner and
    # _resolve_scan_token both already accept a bare ATTX_V2_ token.
    img = qrcode.make(sess.current_token, border=2)
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    resp = send_file(buf, mimetype='image/png')
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@bp.route('/session/<sid>/live')
@role_required('teacher')
def session_live(sid):
    sess = _own_session_or_404(sid)
    _ensure_token_fresh(sess)
    entries = [{'name': a.name, 'roll': a.roll, 'time': a.time, 'manual': a.manual}
               for a in sess.attendance.order_by(AttendanceRecord.id)]
    elapsed = max(0, (now_ms() - sess.start_time) // 1000)
    next_rotation_in = max(0, QR_ROTATE_MS - (now_ms() - (sess.token_updated_at or 0)))
    return jsonify({
        'active': sess.active, 'elapsed': elapsed, 'present': len(entries),
        'attendees': entries, 'currentCode': sess.current_code,
        'nextRotationMs': next_rotation_in,
    })


def _own_session_or_404(sid):
    user = current_user()
    sess = db.session.get(Session, sid)
    if not sess or sess.teacher_username != user.username:
        abort(404)
    return sess


# ─── Profile ──────────────────────────────────────────────────────────────────
@bp.route('/profile')
@role_required('teacher')
def profile():
    return render_template('teacher/profile.html', **_shell_ctx('Profile', avatar_initials=avatar_initials))


@bp.route('/profile/password', methods=['POST'])
@role_required('teacher')
def update_password():
    user = current_user()
    current = request.form.get('current') or ''
    new = request.form.get('new') or ''
    confirm = request.form.get('confirm') or ''
    if not current or not new or not confirm:
        return _bounce_with_error('Fill all password fields', 'teacher.profile')
    if new != confirm:
        return _bounce_with_error('Passwords do not match', 'teacher.profile')
    if user.password != current:
        return _bounce_with_error('Current password incorrect', 'teacher.profile')
    user.password = new
    db.session.commit()
    return redirect_with_toast('teacher.profile', 'Password updated successfully', 'ok')


# ─── Records ──────────────────────────────────────────────────────────────────
@bp.route('/records')
@role_required('teacher')
def records():
    user = current_user()
    sessions = _teacher_sessions(user)
    threshold = _settings_threshold()
    # Exclude the in-progress session — its near-empty attendance would otherwise
    # drag every student's percentage down for the few minutes it's running.
    at_risk = _compute_at_risk([s for s in sessions if not s.active], threshold)
    subjects = sorted({s.code for s in sessions})
    filter_sub = request.args.get('subject') or ''
    filtered = [s for s in sessions if not filter_sub or s.code == filter_sub]
    detail_id = request.args.get('detail')
    detail = next((s for s in filtered if s.id == detail_id), None) if detail_id else None
    return render_template(
        'teacher/records.html',
        **_shell_ctx('Records', threshold=threshold, at_risk=at_risk, subjects=subjects,
                     sessions=list(reversed(filtered)), filter_sub=filter_sub, detail=detail,
                     avatar_initials=avatar_initials)
    )


@bp.route('/records/export.<fmt>')
@role_required('teacher')
def export_records(fmt):
    user = current_user()
    sessions = _teacher_sessions(user)
    filter_sub = request.args.get('subject') or ''
    rows = []
    for s in sessions:
        if filter_sub and s.code != filter_sub:
            continue
        for a in s.attendance:
            rows.append({'subject': s.code, 'section': s.cls, 'semester': s.sem, 'department': s.dept,
                         'date': s.date, 'student': a.name, 'roll': a.roll, 'time': a.time,
                         'type': 'manual' if a.manual else 'qr'})
    if fmt == 'csv':
        return export_csv(rows, 'attendance_records.csv')
    return export_json(rows, 'attendance_records.json')


# ─── Leaves ───────────────────────────────────────────────────────────────────
@bp.route('/leaves')
@role_required('teacher')
def leaves():
    user = current_user()
    rows = Leave.query.filter(
        (Leave.teacher_username == user.username) | (Leave.teacher_username == '') | (Leave.teacher_username.is_(None))
    ).order_by(Leave.ts.desc()).all()
    return render_template('teacher/leaves.html', **_shell_ctx('Leave Requests', leaves=rows))


@bp.route('/leaves/<lid>/<action>', methods=['POST'])
@role_required('teacher')
def update_leave(lid, action):
    if action not in ('approved', 'rejected'):
        abort(400)
    leave = db.session.get(Leave, lid)
    if leave:
        leave.status = action
        db.session.commit()
    return redirect_with_toast('teacher.leaves', f'Leave {action}', 'ok')


# ─── Announcements ────────────────────────────────────────────────────────────
@bp.route('/announcements')
@role_required('teacher')
def announcements():
    user = current_user()
    rows = Announcement.query.filter(
        (Announcement.author == user.username) | (Announcement.author == 'admin')
    ).order_by(Announcement.id.desc()).all()
    return render_template('teacher/announcements.html', **_shell_ctx('Announcements', announcements=rows))


@bp.route('/announcements', methods=['POST'])
@role_required('teacher')
def post_announcement():
    user = current_user()
    title = (request.form.get('title') or '').strip()
    body = (request.form.get('body') or '').strip()
    if not title or not body:
        return _bounce_with_error('Fill in title and message', 'teacher.announcements')
    db.session.add(Announcement(id=gen_id('ann'), title=title, body=body, author=user.username,
                                target=request.form.get('target') or 'all', date=now_date()))
    db.session.commit()
    return redirect_with_toast('teacher.announcements', 'Announcement posted!', 'ok')


def _settings_threshold():
    from .models import Settings
    s = db.session.get(Settings, 1)
    return (s.threshold if s else 75) or 75


# ─── small redirect helpers used by this blueprint's POST handlers ────────────
def redirect_with_toast(endpoint, message, category='ok', **kwargs):
    flash(message, category)
    return redirect(url_for(endpoint, **kwargs))


def _bounce_with_error(message, endpoint='teacher.session'):
    flash(message, 'err')
    return redirect(url_for(endpoint))
