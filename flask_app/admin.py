import csv
import io
import time

from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)

from .auth import current_user, role_required
from .extensions import db
from .models import (Alert, Announcement, AttendanceRecord, Holiday, Leave,
                     ProxyLog, Session, Settings, TimetableEntry, User)
from .nav import NAV_MAP, ROLE_LABELS, ROLE_AVATAR_CLASS
from .seed import seed_if_empty
from .utils import (avatar_initials, export_csv, export_json, gen_id,
                    get_att_pct_color, now_date, now_ms, now_time)

bp = Blueprint('admin', __name__, url_prefix='/admin')

DEPTS = ['CSE', 'ECE', 'EEE', 'ME', 'CE', 'IT']
DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']


def _shell_ctx(page_title, **extra):
    user = current_user()
    return dict(user=user, page_title=page_title, nav_sections=NAV_MAP['admin'],
                role_labels=ROLE_LABELS, role_avatar_class=ROLE_AVATAR_CLASS, **extra)


def _safe_int(val, default):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _settings_row():
    s = db.session.get(Settings, 1)
    if not s:
        s = Settings(id=1)
        db.session.add(s)
        db.session.commit()
    return s


# ─── Dashboard ────────────────────────────────────────────────────────────────
@bp.route('/')
@role_required('admin')
def dashboard():
    students = User.query.filter_by(role='student').all()
    teachers = User.query.filter_by(role='teacher').all()
    sessions_all = Session.query.order_by(Session.start_time).all()
    completed = [s for s in sessions_all if not s.active]
    completed_ids = {s.id for s in completed}
    alerts_all = Alert.query.order_by(Alert.ts.desc()).all()
    proxy_all = ProxyLog.query.all()

    by_subj_totals = {}
    for s in completed:
        by_subj_totals.setdefault(s.code, 0)
        by_subj_totals[s.code] += 1

    # Every percentage below is denominated in finished sessions, so the
    # numerators must come from the same set — a record from a session that's
    # still running would otherwise inflate the count without a matching slot
    # in the denominator.
    total_present = 0
    risk_students = []
    for u in students:
        records = (AttendanceRecord.query.filter_by(username=u.username)
                   .filter(AttendanceRecord.session_id.in_(completed_ids)).all())
        total_present += len(records)
        present_by_subj = {}
        for r in records:
            if r.code in by_subj_totals:
                present_by_subj[r.code] = present_by_subj.get(r.code, 0) + 1
        if any(present_by_subj.get(code, 0) / total * 100 < 75 for code, total in by_subj_totals.items() if total > 0):
            risk_students.append(u)

    total_possible = len(students) * len(completed)
    overall_pct = round(total_present / total_possible * 100) if total_possible else 0

    depts = sorted({u.dept for u in students if u.dept})
    dept_pcts = []
    for dept in depts:
        dept_students = [u for u in students if u.dept == dept]
        p = sum(AttendanceRecord.query.filter_by(username=u.username)
                .filter(AttendanceRecord.session_id.in_(completed_ids)).count() for u in dept_students)
        t = len(dept_students) * len(completed)
        dept_pcts.append(round(p / t * 100) if t else 0)
    chart_data = {'labels': depts or ['CSE', 'ECE', 'ME', 'CE'],
                  'data': dept_pcts if depts else [82, 78, 74, 88]}

    return render_template(
        'admin/dashboard.html',
        **_shell_ctx('Dashboard', overall_pct=overall_pct, total_students=len(students),
                     total_teachers=len(teachers), total_sessions=len(sessions_all),
                     risk_count=len(risk_students), risk_students=risk_students,
                     proxy_count=len(proxy_all), alerts=alerts_all[:5],
                     recent_sessions=list(reversed(sessions_all))[:8],
                     live_count=sum(1 for s in sessions_all if s.active),
                     chart_data=chart_data, avatar_initials=avatar_initials)
    )


# ─── Manage Students ──────────────────────────────────────────────────────────
@bp.route('/students')
@role_required('admin')
def students():
    search = (request.args.get('q') or '').strip().lower()
    dept_f = request.args.get('dept') or ''
    completed_ids = [s.id for s in Session.query.filter_by(active=False).all()]
    completed_count = len(completed_ids)

    query = User.query.filter_by(role='student')
    if dept_f:
        query = query.filter_by(dept=dept_f)
    rows = []
    for u in query.order_by(User.name).all():
        haystack = ' '.join([u.name or '', u.roll or '', u.dept or '', u.username]).lower()
        if search and search not in haystack:
            continue
        att_count = (AttendanceRecord.query.filter_by(username=u.username)
                     .filter(AttendanceRecord.session_id.in_(completed_ids)).count())
        pct = round(att_count / completed_count * 100) if completed_count else None
        rows.append({'user': u, 'pct': pct, 'color': get_att_pct_color(pct) if pct is not None else 'gray'})

    return render_template('admin/students.html',
                           **_shell_ctx('Students', rows=rows, search=search, dept_f=dept_f,
                                        depts=DEPTS, avatar_initials=avatar_initials))


def _save_student(existing):
    name = (request.form.get('name') or '').strip()
    roll = (request.form.get('roll') or '').strip()
    password = request.form.get('password') or 'pass123'
    dept = request.form.get('dept') or 'CSE'
    sem = _safe_int(request.form.get('sem'), 4)
    section = (request.form.get('section') or 'A').strip()
    email = (request.form.get('email') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    parent_name = (request.form.get('parent_name') or '').strip()
    parent_email = (request.form.get('parent_email') or '').strip()
    parent_phone = (request.form.get('parent_phone') or '').strip()

    if existing:
        existing.name, existing.roll, existing.password = name, roll, password
        existing.dept, existing.sem, existing.section = dept, sem, section
        existing.email, existing.phone = email, phone
        existing.parent_name, existing.parent_email, existing.parent_phone = parent_name, parent_email, parent_phone
        db.session.commit()
        flash('Student updated', 'ok')
        return redirect(url_for('admin.students'))

    uname = (request.form.get('username') or '').strip().lower().replace(' ', '.')
    if not uname:
        flash('Username required', 'err')
        return redirect(url_for('admin.new_student'))
    if db.session.get(User, uname):
        flash('Username already exists', 'err')
        return redirect(url_for('admin.new_student'))
    db.session.add(User(username=uname, role='student', name=name, roll=roll, password=password,
                        dept=dept, sem=sem, section=section, email=email, phone=phone,
                        parent_name=parent_name, parent_email=parent_email, parent_phone=parent_phone))
    db.session.commit()
    flash('Student added', 'ok')
    return redirect(url_for('admin.students'))


@bp.route('/students/new', methods=['GET', 'POST'])
@role_required('admin')
def new_student():
    if request.method == 'POST':
        return _save_student(None)
    return render_template('admin/student_form.html', **_shell_ctx('Add Student', student=None, depts=DEPTS))


@bp.route('/students/<uname>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_student(uname):
    user = User.query.filter_by(username=uname, role='student').first_or_404()
    if request.method == 'POST':
        return _save_student(user)
    return render_template('admin/student_form.html', **_shell_ctx('Edit Student', student=user, depts=DEPTS))


@bp.route('/students/<uname>/delete', methods=['POST'])
@role_required('admin')
def delete_student(uname):
    user = User.query.filter_by(username=uname, role='student').first_or_404()
    db.session.delete(user)
    db.session.commit()
    flash('Student deleted', 'ok')
    return redirect(url_for('admin.students'))


@bp.route('/students/<uname>/alert', methods=['POST'])
@role_required('admin')
def alert_student(uname):
    user = User.query.filter_by(username=uname, role='student').first_or_404()
    db.session.add(Alert(student_username=uname, student=user.name, roll=user.roll,
                         parent_email=user.parent_email or 'Not set', subjects='Manual alert',
                         ts=now_ms(), time=now_time(), date=now_date()))
    db.session.commit()
    flash(f"Alert queued for {user.parent_email or 'no email set'}", 'ok' if user.parent_email else 'warn')
    return redirect(url_for('admin.students'))


def _parse_csv_text(text):
    reader = csv.reader(io.StringIO(text.strip()))
    rows = [[c.strip().strip('"') for c in row] for row in reader if row]
    if not rows:
        return [], []
    headers = [h.lower().replace(' ', '') for h in rows[0]]
    return headers, [dict(zip(headers, row)) for row in rows[1:]]


@bp.route('/students/bulk', methods=['GET', 'POST'])
@role_required('admin')
def bulk_import_students():
    preview = None
    csv_text = ''
    if request.method == 'POST':
        action = request.form.get('action') or 'import'
        upload = request.files.get('csv_file')
        if upload and upload.filename:
            csv_text = upload.read().decode('utf-8', errors='replace')
        else:
            csv_text = request.form.get('csv_text') or ''
        csv_text = csv_text.strip()
        if not csv_text:
            flash('No data to ' + ('preview' if action == 'preview' else 'import'), 'err')
            return render_template('admin/bulk_import.html',
                                   **_shell_ctx('Bulk Import Students', preview=None, csv_text=csv_text))

        headers, rows = _parse_csv_text(csv_text)
        if action == 'preview':
            preview = {'headers': headers, 'rows': rows[:10], 'total': len(rows)}
            return render_template('admin/bulk_import.html',
                                   **_shell_ctx('Bulk Import Students', preview=preview, csv_text=csv_text))

        added = skipped = 0
        for row in rows:
            uname = (row.get('username') or row.get('roll') or '').strip().lower().replace(' ', '.')
            if not uname or db.session.get(User, uname):
                skipped += 1
                continue
            db.session.add(User(
                username=uname, role=(row.get('role') or 'student').lower(),
                name=row.get('name') or '', roll=row.get('roll') or '',
                email=row.get('email') or '', phone=row.get('phone') or '',
                dept=row.get('dept') or row.get('department') or 'CSE',
                sem=_safe_int(row.get('sem') or row.get('semester'), 4),
                section=row.get('section') or 'A',
                parent_name=row.get('parentname') or '', parent_email=row.get('parentemail') or '',
                parent_phone=row.get('parentphone') or '', password=row.get('password') or 'pass123',
            ))
            added += 1
        db.session.commit()
        flash(f'Imported {added} students, skipped {skipped}', 'ok')
        return redirect(url_for('admin.students'))

    return render_template('admin/bulk_import.html',
                           **_shell_ctx('Bulk Import Students', preview=preview, csv_text=csv_text))


@bp.route('/students/export.csv')
@role_required('admin')
def export_students():
    rows = [{'username': u.username, 'name': u.name, 'roll': u.roll, 'dept': u.dept,
             'semester': u.sem, 'section': u.section, 'email': u.email, 'phone': u.phone,
             'parentName': u.parent_name, 'parentEmail': u.parent_email, 'parentPhone': u.parent_phone}
            for u in User.query.filter_by(role='student').all()]
    return export_csv(rows, 'students.csv')


# ─── Manage Teachers ──────────────────────────────────────────────────────────
@bp.route('/teachers')
@role_required('admin')
def teachers():
    search = (request.args.get('q') or '').strip().lower()
    rows = []
    for u in User.query.filter_by(role='teacher').order_by(User.name).all():
        haystack = ' '.join([u.name or '', u.dept or '', u.username]).lower()
        if search and search not in haystack:
            continue
        rows.append({'user': u, 'sess_count': Session.query.filter_by(teacher_username=u.username).count()})
    return render_template('admin/teachers.html',
                           **_shell_ctx('Teachers', rows=rows, search=search, avatar_initials=avatar_initials))


def _save_teacher(existing):
    name = (request.form.get('name') or '').strip()
    dept = request.form.get('dept') or 'CSE'
    password = request.form.get('password') or 'pass123'
    email = (request.form.get('email') or '').strip()
    phone = (request.form.get('phone') or '').strip()
    subjects = [s.strip() for s in (request.form.get('subjects') or '').split(',') if s.strip()]

    if existing:
        existing.name, existing.dept, existing.password = name, dept, password
        existing.email, existing.phone, existing.subjects = email, phone, subjects
        db.session.commit()
        flash('Teacher updated', 'ok')
        return redirect(url_for('admin.teachers'))

    uname = (request.form.get('username') or '').strip().lower().replace(' ', '.')
    if not uname:
        flash('Username required', 'err')
        return redirect(url_for('admin.new_teacher'))
    if db.session.get(User, uname):
        flash('Username exists', 'err')
        return redirect(url_for('admin.new_teacher'))
    db.session.add(User(username=uname, role='teacher', name=name, dept=dept, password=password,
                        email=email, phone=phone, subjects=subjects))
    db.session.commit()
    flash('Teacher added', 'ok')
    return redirect(url_for('admin.teachers'))


@bp.route('/teachers/new', methods=['GET', 'POST'])
@role_required('admin')
def new_teacher():
    if request.method == 'POST':
        return _save_teacher(None)
    return render_template('admin/teacher_form.html', **_shell_ctx('Add Teacher', teacher=None, depts=DEPTS))


@bp.route('/teachers/<uname>/edit', methods=['GET', 'POST'])
@role_required('admin')
def edit_teacher(uname):
    user = User.query.filter_by(username=uname, role='teacher').first_or_404()
    if request.method == 'POST':
        return _save_teacher(user)
    return render_template('admin/teacher_form.html', **_shell_ctx('Edit Teacher', teacher=user, depts=DEPTS))


@bp.route('/teachers/<uname>/delete', methods=['POST'])
@role_required('admin')
def delete_teacher(uname):
    user = User.query.filter_by(username=uname, role='teacher').first_or_404()
    db.session.delete(user)
    db.session.commit()
    flash('Teacher deleted', 'ok')
    return redirect(url_for('admin.teachers'))


@bp.route('/teachers/export.csv')
@role_required('admin')
def export_teachers():
    rows = [{'username': u.username, 'name': u.name, 'dept': u.dept, 'email': u.email,
             'subjects': ';'.join(u.subjects or [])} for u in User.query.filter_by(role='teacher').all()]
    return export_csv(rows, 'teachers.csv')


# ─── Attendance Report ────────────────────────────────────────────────────────
def _attendance_report_rows(dept_f, sub_f, thresh):
    query = User.query.filter_by(role='student')
    if dept_f:
        query = query.filter_by(dept=dept_f)
    students_list = query.all()
    sessions_all = Session.query.all()
    subjects = sorted({s.code for s in sessions_all})
    completed = [s for s in sessions_all if not s.active]
    completed_ids = {s.id for s in completed}

    rows = []
    for u in students_list:
        # `present` is compared against subj_sessions (completed-only), so it
        # must not include attendance from a same-subject session that's still
        # running — otherwise a student could look "Safe" on a subject whose
        # one finished session they actually skipped.
        records = (AttendanceRecord.query.filter_by(username=u.username)
                   .filter(AttendanceRecord.session_id.in_(completed_ids)).all())
        for code in ([sub_f] if sub_f else subjects):
            subj_sessions = [s for s in completed if s.code == code]
            if not subj_sessions:
                continue
            present = sum(1 for r in records if r.code == code)
            pct = round(present / len(subj_sessions) * 100)
            if thresh == 'below75' and pct >= 75:
                continue
            if thresh == 'below60' and pct >= 60:
                continue
            if thresh == 'above75' and pct < 75:
                continue
            rows.append({'student': u.name, 'roll': u.roll or u.username, 'dept': u.dept, 'subject': code,
                         'present': present, 'total': len(subj_sessions), 'pct': pct,
                         'parent_email': u.parent_email or '', 'color': get_att_pct_color(pct),
                         'status': 'Safe' if pct >= 75 else ('Warning' if pct >= 60 else 'Critical'),
                         'status_color': 'green' if pct >= 75 else ('amber' if pct >= 60 else 'red')})
    return rows, subjects, sorted({u.dept for u in User.query.filter_by(role='student').all() if u.dept})


@bp.route('/attendance')
@role_required('admin')
def attendance():
    dept_f = request.args.get('dept') or ''
    sub_f = request.args.get('subject') or ''
    thresh = request.args.get('thresh') or ''
    rows, subjects, depts = _attendance_report_rows(dept_f, sub_f, thresh)
    return render_template('admin/attendance.html',
                           **_shell_ctx('Attendance Report', rows=rows, subjects=subjects, depts=depts,
                                        dept_f=dept_f, sub_f=sub_f, thresh=thresh))


@bp.route('/attendance/export.csv')
@role_required('admin')
def export_attendance():
    dept_f = request.args.get('dept') or ''
    sub_f = request.args.get('subject') or ''
    thresh = request.args.get('thresh') or ''
    rows, _, _ = _attendance_report_rows(dept_f, sub_f, thresh)
    if not rows:
        flash('No data', 'err')
        return redirect(url_for('admin.attendance'))
    out = [{'student': r['student'], 'roll': r['roll'], 'dept': r['dept'], 'subject': r['subject'],
            'present': r['present'], 'total': r['total'], 'pct': r['pct'], 'parentEmail': r['parent_email']}
           for r in rows]
    return export_csv(out, 'attendance_report.csv')


@bp.route('/attendance/send-alerts', methods=['POST'])
@role_required('admin')
def send_all_alerts():
    students_list = User.query.filter_by(role='student').all()
    completed = Session.query.filter_by(active=False).all()
    completed_ids = {s.id for s in completed}
    by_subj_totals = {}
    for s in completed:
        by_subj_totals[s.code] = by_subj_totals.get(s.code, 0) + 1

    sent = 0
    for u in students_list:
        records = (AttendanceRecord.query.filter_by(username=u.username)
                   .filter(AttendanceRecord.session_id.in_(completed_ids)).all())
        present_by_subj = {}
        for r in records:
            if r.code in by_subj_totals:
                present_by_subj[r.code] = present_by_subj.get(r.code, 0) + 1
        low = [code for code, total in by_subj_totals.items()
               if total > 0 and present_by_subj.get(code, 0) / total * 100 < 75]
        if low:
            db.session.add(Alert(student_username=u.username, student=u.name, roll=u.roll,
                                 parent_email=u.parent_email or 'Not set', subjects=', '.join(low),
                                 ts=now_ms(), time=now_time(), date=now_date()))
            sent += 1
    db.session.commit()
    flash(f'{sent} parent alerts sent' if sent else 'No at-risk students', 'ok' if sent else 'info')
    return redirect(url_for('admin.attendance'))


# ─── Sessions (all) ───────────────────────────────────────────────────────────
@bp.route('/sessions')
@role_required('admin')
def sessions():
    search = (request.args.get('q') or '').strip().lower()
    rows = Session.query.order_by(Session.start_time.desc()).all()
    if search:
        rows = [s for s in rows if search in ' '.join([s.code or '', s.teacher or '', s.dept or '']).lower()]
    detail_id = request.args.get('detail')
    detail = db.session.get(Session, detail_id) if detail_id else None
    return render_template('admin/sessions.html',
                           **_shell_ctx('All Sessions', sessions=rows, search=search, detail=detail))


@bp.route('/sessions/export.csv')
@role_required('admin')
def export_sessions():
    rows = []
    for s in Session.query.all():
        for a in s.attendance:
            rows.append({'date': s.date, 'subject': s.code, 'teacher': s.teacher, 'dept': s.dept,
                         'section': s.cls, 'sem': s.sem, 'student': a.name, 'roll': a.roll, 'time': a.time})
    if not rows:
        flash('No data', 'err')
        return redirect(url_for('admin.sessions'))
    return export_csv(rows, 'all_sessions.csv')


# ─── Proxy / Alerts ───────────────────────────────────────────────────────────
@bp.route('/alerts')
@role_required('admin')
def alerts():
    rows = Alert.query.order_by(Alert.ts.desc()).all()
    return render_template('admin/alerts.html', **_shell_ctx('Parent Alerts', alerts=rows))


@bp.route('/alerts/export.csv')
@role_required('admin')
def export_alerts():
    rows = Alert.query.order_by(Alert.ts.desc()).all()
    if not rows:
        flash('No data', 'err')
        return redirect(url_for('admin.alerts'))
    out = [{'student': a.student, 'roll': a.roll, 'parentEmail': a.parent_email,
            'subjects': a.subjects, 'date': a.date} for a in rows]
    return export_csv(out, 'parent_alerts.csv')


@bp.route('/proxy')
@role_required('admin')
def proxy():
    rows = ProxyLog.query.order_by(ProxyLog.ts.desc()).all()
    return render_template('admin/proxy.html', **_shell_ctx('Proxy Log', logs=rows))


@bp.route('/proxy/export.csv')
@role_required('admin')
def export_proxy():
    rows = ProxyLog.query.order_by(ProxyLog.ts.desc()).all()
    if not rows:
        flash('No data', 'err')
        return redirect(url_for('admin.proxy'))
    out = [{'student': p.student, 'roll': p.roll, 'session': p.session, 'time': p.time, 'reason': p.reason}
           for p in rows]
    return export_csv(out, 'proxy_log.csv')


# ─── Timetable ────────────────────────────────────────────────────────────────
@bp.route('/timetable')
@role_required('admin')
def timetable():
    entries = TimetableEntry.query.order_by(TimetableEntry.id).all()
    return render_template('admin/timetable.html',
                           **_shell_ctx('Timetable', entries=entries, depts=DEPTS, days=DAYS))


@bp.route('/timetable/add', methods=['POST'])
@role_required('admin')
def add_timetable():
    parts = [p.strip() for p in (request.form.get('period') or '').strip().split('|')]
    if len(parts) < 2:
        flash('Invalid period format', 'err')
        return redirect(url_for('admin.timetable'))
    db.session.add(TimetableEntry(
        dept=request.form.get('dept') or 'CSE', sem=request.form.get('sem') or '4',
        section=(request.form.get('section') or 'A').strip(), day=request.form.get('day') or 'Monday',
        periods=[{'time': parts[0], 'subject': parts[1], 'teacher': parts[2] if len(parts) > 2 else ''}],
    ))
    db.session.commit()
    flash('Entry added', 'ok')
    return redirect(url_for('admin.timetable'))


@bp.route('/timetable/<int:entry_id>/delete', methods=['POST'])
@role_required('admin')
def delete_timetable(entry_id):
    entry = db.session.get(TimetableEntry, entry_id)
    if entry:
        db.session.delete(entry)
        db.session.commit()
        flash('Entry removed', 'ok')
    return redirect(url_for('admin.timetable'))


@bp.route('/timetable/export.json')
@role_required('admin')
def export_timetable():
    entries = TimetableEntry.query.order_by(TimetableEntry.id).all()
    data = [{'dept': e.dept, 'sem': e.sem, 'section': e.section, 'day': e.day, 'periods': e.periods}
            for e in entries]
    return export_json(data, 'timetable.json')


# ─── Holidays ─────────────────────────────────────────────────────────────────
@bp.route('/holidays')
@role_required('admin')
def holidays():
    rows = Holiday.query.order_by(Holiday.date).all()
    today = time.strftime('%Y-%m-%d')
    return render_template('admin/holidays.html', **_shell_ctx('Holidays', holidays=rows, today=today))


@bp.route('/holidays/add', methods=['POST'])
@role_required('admin')
def add_holiday():
    date = (request.form.get('date') or '').strip()
    name = (request.form.get('name') or '').strip()
    if not date or not name:
        flash('Fill date and name', 'err')
    elif db.session.get(Holiday, date):
        flash('A holiday already exists on that date', 'err')
    else:
        db.session.add(Holiday(date=date, name=name))
        db.session.commit()
        flash('Holiday added', 'ok')
    return redirect(url_for('admin.holidays'))


@bp.route('/holidays/<date>/delete', methods=['POST'])
@role_required('admin')
def delete_holiday(date):
    h = db.session.get(Holiday, date)
    if h:
        db.session.delete(h)
        db.session.commit()
        flash('Holiday removed', 'ok')
    return redirect(url_for('admin.holidays'))


# ─── Announcements ────────────────────────────────────────────────────────────
@bp.route('/announcements')
@role_required('admin')
def announcements():
    rows = Announcement.query.order_by(Announcement.id.desc()).all()
    return render_template('admin/announcements.html', **_shell_ctx('Announcements', announcements=rows))


@bp.route('/announcements/add', methods=['POST'])
@role_required('admin')
def add_announcement():
    title = (request.form.get('title') or '').strip()
    body = (request.form.get('body') or '').strip()
    if not title or not body:
        flash('Fill title and message', 'err')
    else:
        db.session.add(Announcement(id=gen_id('ann'), title=title, body=body, author='admin',
                                    target=request.form.get('target') or 'all', date=now_date()))
        db.session.commit()
        flash('Announcement posted!', 'ok')
    return redirect(url_for('admin.announcements'))


@bp.route('/announcements/<aid>/delete', methods=['POST'])
@role_required('admin')
def delete_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if ann:
        db.session.delete(ann)
        db.session.commit()
        flash('Announcement deleted', 'ok')
    return redirect(url_for('admin.announcements'))


# ─── Settings ─────────────────────────────────────────────────────────────────
@bp.route('/settings', methods=['GET', 'POST'])
@role_required('admin')
def settings():
    s = _settings_row()
    if request.method == 'POST':
        s.college_name = (request.form.get('college_name') or '').strip() or 'Demo Engineering College'
        s.threshold = _safe_int(request.form.get('threshold'), 75)
        s.campus_wifi_ssid = (request.form.get('campus_wifi_ssid') or '').strip() or 'CollegeNet'
        s.campus_radius = _safe_int(request.form.get('campus_radius'), 600)
        s.college_wifi_ips = [v.strip() for v in (request.form.get('college_wifi_ips') or '').split(',') if v.strip()]
        db.session.commit()
        flash('Settings saved', 'ok')
        return redirect(url_for('admin.settings'))
    return render_template('admin/settings.html', **_shell_ctx('Settings', settings=s))


@bp.route('/settings/reset-attendance', methods=['POST'])
@role_required('admin')
def reset_attendance():
    AttendanceRecord.query.delete()
    Alert.query.delete()
    ProxyLog.query.delete()
    db.session.commit()
    flash('Attendance reset', 'ok')
    return redirect(url_for('admin.settings'))


@bp.route('/settings/factory-reset', methods=['POST'])
@role_required('admin')
def factory_reset():
    for model in (AttendanceRecord, Alert, ProxyLog, Leave, Session, TimetableEntry,
                  Announcement, Holiday, User, Settings):
        model.query.delete()
    db.session.commit()
    seed_if_empty()
    session.clear()
    flash('Reset complete — please sign in again', 'ok')
    return redirect(url_for('auth.login'))


@bp.route('/settings/export/<kind>')
@role_required('admin')
def export_data(kind):
    if kind == 'attendance':
        rows = []
        for s in Session.query.all():
            for a in s.attendance:
                rows.append({'date': s.date, 'subject': s.code, 'dept': s.dept, 'section': s.cls,
                             'teacher': s.teacher, 'student': a.name, 'roll': a.roll, 'time': a.time})
        if not rows:
            flash('No data', 'err')
            return redirect(url_for('admin.settings'))
        return export_csv(rows, 'all_attendance.csv')
    if kind == 'users':
        return export_json({u.username: u.to_dict() for u in User.query.all()}, 'users.json')
    if kind == 'sessions':
        return export_json([s.to_dict() for s in Session.query.all()], 'sessions.json')
    flash('Unknown export', 'err')
    return redirect(url_for('admin.settings'))
