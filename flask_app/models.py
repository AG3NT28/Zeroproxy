from .extensions import db


class User(db.Model):
    """A login account: admin, teacher, or student. Mirrors the JS USERS store."""
    username = db.Column(db.String, primary_key=True)
    role = db.Column(db.String, nullable=False)  # admin | teacher | student
    name = db.Column(db.String, default='')
    email = db.Column(db.String, default='')
    phone = db.Column(db.String, default='')
    dept = db.Column(db.String, default='')
    password = db.Column(db.String, default='')

    # Teacher-only
    subjects = db.Column(db.JSON, default=list)

    # Student-only
    roll = db.Column(db.String, default='')
    sem = db.Column(db.Integer, default=4)
    section = db.Column(db.String, default='A')
    parent_name = db.Column(db.String, default='')
    parent_email = db.Column(db.String, default='')
    parent_phone = db.Column(db.String, default='')

    def to_dict(self):
        return {
            'username': self.username, 'role': self.role, 'name': self.name,
            'email': self.email, 'phone': self.phone, 'dept': self.dept,
            'subjects': self.subjects or [], 'roll': self.roll, 'sem': self.sem,
            'section': self.section, 'parentName': self.parent_name,
            'parentEmail': self.parent_email, 'parentPhone': self.parent_phone,
        }


class Session(db.Model):
    """A teacher-started QR attendance session. Mirrors the JS SESSIONS store."""
    id = db.Column(db.String, primary_key=True)
    code = db.Column(db.String, nullable=False)
    name = db.Column(db.String, default='')
    cls = db.Column(db.String, default='')       # section
    sem = db.Column(db.String, default='')
    dept = db.Column(db.String, default='')
    teacher = db.Column(db.String, default='')   # display name
    teacher_username = db.Column(db.String, default='')
    hotspot_ip = db.Column(db.String, default='')
    start_time = db.Column(db.BigInteger, default=0)   # epoch ms
    active = db.Column(db.Boolean, default=True)
    date = db.Column(db.String, default='')
    current_token = db.Column(db.String, default='')
    current_code = db.Column(db.String, default='')
    token_updated_at = db.Column(db.BigInteger, default=0)  # epoch ms, drives QR rotation

    attendance = db.relationship('AttendanceRecord', backref='session', lazy='dynamic',
                                 cascade='all, delete-orphan')

    def to_dict(self):
        entries = {a.username: a.to_entry_dict() for a in self.attendance}
        return {
            'id': self.id, 'code': self.code, 'name': self.name, 'cls': self.cls,
            'sem': self.sem, 'dept': self.dept, 'teacher': self.teacher,
            'teacherUsername': self.teacher_username, 'hotspotIp': self.hotspot_ip,
            'startTime': self.start_time, 'active': self.active, 'date': self.date,
            'currentToken': self.current_token, 'currentCode': self.current_code,
            'attendance': entries,
        }


class AttendanceRecord(db.Model):
    """One student's presence in one session. Also serves as the per-student
    attendance history (JS kept these in two stores; one table is enough here)."""
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.String, db.ForeignKey('session.id'), nullable=False)
    username = db.Column(db.String, db.ForeignKey('user.username'), nullable=False)
    name = db.Column(db.String, default='')
    roll = db.Column(db.String, default='')
    code = db.Column(db.String, default='')   # subject code, denormalized for per-student lookups
    dept = db.Column(db.String, default='')
    sem = db.Column(db.String, default='')
    date = db.Column(db.String, default='')
    time = db.Column(db.String, default='')
    manual = db.Column(db.Boolean, default=False)
    absent = db.Column(db.Boolean, default=False)
    scan_ts = db.Column(db.BigInteger, default=0)

    def to_entry_dict(self):
        return {'name': self.name, 'roll': self.roll, 'time': self.time, 'manual': self.manual}


class Alert(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_username = db.Column(db.String, default='')
    student = db.Column(db.String, default='')
    roll = db.Column(db.String, default='')
    parent_email = db.Column(db.String, default='')
    subjects = db.Column(db.String, default='')
    ts = db.Column(db.BigInteger, default=0)
    time = db.Column(db.String, default='')
    date = db.Column(db.String, default='')


class ProxyLog(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student = db.Column(db.String, default='')
    roll = db.Column(db.String, default='')
    session = db.Column(db.String, default='')
    time = db.Column(db.String, default='')
    reason = db.Column(db.String, default='')
    ts = db.Column(db.BigInteger, default=0)


class Leave(db.Model):
    id = db.Column(db.String, primary_key=True)
    student_username = db.Column(db.String, default='')
    student_name = db.Column(db.String, default='')
    roll = db.Column(db.String, default='')
    teacher_username = db.Column(db.String, default='')
    subject = db.Column(db.String, default='')
    from_date = db.Column(db.String, default='')
    to_date = db.Column(db.String, default='')
    reason = db.Column(db.String, default='')
    status = db.Column(db.String, default='pending')
    date = db.Column(db.String, default='')
    ts = db.Column(db.BigInteger, default=0)


class TimetableEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    dept = db.Column(db.String, default='')
    sem = db.Column(db.String, default='')
    section = db.Column(db.String, default='')
    day = db.Column(db.String, default='')
    periods = db.Column(db.JSON, default=list)  # [{time, subject, teacher}, ...]


class Announcement(db.Model):
    id = db.Column(db.String, primary_key=True)
    title = db.Column(db.String, default='')
    body = db.Column(db.Text, default='')
    author = db.Column(db.String, default='')
    target = db.Column(db.String, default='all')  # all | student | teacher
    date = db.Column(db.String, default='')


class Holiday(db.Model):
    date = db.Column(db.String, primary_key=True)
    name = db.Column(db.String, default='')


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True, default=1)
    college_name = db.Column(db.String, default='Demo Engineering College')
    threshold = db.Column(db.Integer, default=75)
    campus_wifi_ssid = db.Column(db.String, default='CollegeNet')
    campus_radius = db.Column(db.Integer, default=600)
    college_wifi_ips = db.Column(db.JSON, default=list)
