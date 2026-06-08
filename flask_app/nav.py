"""Sidebar navigation maps — a direct port of the `navMap` object built in
main.js's showDashboard(), now keyed to Flask endpoints instead of SPA page keys."""

NAV_MAP = {
    'teacher': [
        {'label': 'Attendance', 'items': [
            {'icon': '▶', 'label': 'Session Manager', 'endpoint': 'teacher.session'},
            {'icon': '📋', 'label': 'Records', 'endpoint': 'teacher.records'},
            {'icon': '📄', 'label': 'Leave Requests', 'endpoint': 'teacher.leaves'},
        ]},
        {'label': 'Communication', 'items': [
            {'icon': '📢', 'label': 'Announcements', 'endpoint': 'teacher.announcements'},
        ]},
        {'label': 'Account', 'items': [
            {'icon': '👤', 'label': 'Profile', 'endpoint': 'teacher.profile'},
        ]},
    ],
    'student': [
        {'label': 'Attendance', 'items': [
            {'icon': '📷', 'label': 'Scan QR', 'endpoint': 'student.scan'},
            {'icon': '📊', 'label': 'My Attendance', 'endpoint': 'student.attendance'},
            {'icon': '📄', 'label': 'Leave Request', 'endpoint': 'student.leave'},
            {'icon': '🗓', 'label': 'Timetable', 'endpoint': 'student.timetable'},
        ]},
        {'label': 'Account', 'items': [
            {'icon': '👤', 'label': 'Profile & Parents', 'endpoint': 'student.profile'},
        ]},
    ],
    'admin': [
        {'label': 'Overview', 'items': [
            {'icon': '📊', 'label': 'Dashboard', 'endpoint': 'admin.dashboard'},
        ]},
        {'label': 'People', 'items': [
            {'icon': '👨‍🎓', 'label': 'Students', 'endpoint': 'admin.students'},
            {'icon': '👨‍🏫', 'label': 'Teachers', 'endpoint': 'admin.teachers'},
        ]},
        {'label': 'Attendance', 'items': [
            {'icon': '✅', 'label': 'Attendance Report', 'endpoint': 'admin.attendance'},
            {'icon': '⏱', 'label': 'All Sessions', 'endpoint': 'admin.sessions'},
        ]},
        {'label': 'Monitoring', 'items': [
            {'icon': '📧', 'label': 'Parent Alerts', 'endpoint': 'admin.alerts'},
            {'icon': '🚨', 'label': 'Proxy Log', 'endpoint': 'admin.proxy'},
        ]},
        {'label': 'Administration', 'items': [
            {'icon': '🗓', 'label': 'Timetable', 'endpoint': 'admin.timetable'},
            {'icon': '🏖', 'label': 'Holidays', 'endpoint': 'admin.holidays'},
            {'icon': '📢', 'label': 'Announcements', 'endpoint': 'admin.announcements'},
            {'icon': '⚙️', 'label': 'Settings', 'endpoint': 'admin.settings'},
        ]},
    ],
}

ROLE_LABELS = {'admin': 'Administrator', 'teacher': 'Teacher', 'student': 'Student'}
ROLE_AVATAR_CLASS = {'admin': 'av-red', 'teacher': 'av-accent', 'student': 'av-green'}
