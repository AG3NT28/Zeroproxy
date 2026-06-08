"""Seed the database with the same demo data the original JS app shipped with."""
from .extensions import db
from .models import (User, Holiday, TimetableEntry, Announcement, Settings)
from .utils import now_date

USERS = {
    'admin': dict(role='admin', name='Administrator', email='admin@college.edu', phone='9000000000', dept='Admin', password='admin'),
    'prof.sharma': dict(role='teacher', name='Prof. Ravi Sharma', email='ravi.sharma@college.edu', phone='9100000001', dept='CSE', subjects=['CS301', 'CS401'], password='pass123'),
    'prof.rao': dict(role='teacher', name='Prof. Anita Rao', email='anita.rao@college.edu', phone='9100000002', dept='ECE', subjects=['EC301', 'EC401'], password='pass123'),
    'prof.kumar': dict(role='teacher', name='Prof. Suresh Kumar', email='suresh.kumar@college.edu', phone='9100000003', dept='ME', subjects=['ME301'], password='pass123'),
    'prof.iyer': dict(role='teacher', name='Prof. Meena Iyer', email='meena.iyer@college.edu', phone='9100000002', dept='ECE', subjects=['EC201', 'EC305'], password='pass234'),
    'prof.verma': dict(role='teacher', name='Prof. Ankit Verma', email='ankit.verma@college.edu', phone='9100000003', dept='ME', subjects=['ME101', 'ME402'], password='pass345'),
    'prof.reddy': dict(role='teacher', name='Prof. Sushma Reddy', email='sushma.reddy@college.edu', phone='9100000004', dept='Civil', subjects=['CE210', 'CE450'], password='pass456'),
    'prof.khan': dict(role='teacher', name='Prof. Aamir Khan', email='aamir.khan@college.edu', phone='9100000005', dept='EEE', subjects=['EE220', 'EE330'], password='pass567'),
    'prof.nair': dict(role='teacher', name='Prof. Priya Nair', email='priya.nair@college.edu', phone='9100000006', dept='Mathematics', subjects=['MA101', 'MA302'], password='pass678'),
    'prof.das': dict(role='teacher', name='Prof. Rohit Das', email='rohit.das@college.edu', phone='9100000007', dept='Physics', subjects=['PH201', 'PH310'], password='pass789'),
    'prof.patel': dict(role='teacher', name='Prof. Neha Patel', email='neha.patel@college.edu', phone='9100000008', dept='Chemistry', subjects=['CH101', 'CH205'], password='pass890'),
    'prof.singh': dict(role='teacher', name='Prof. Arjun Singh', email='arjun.singh@college.edu', phone='9100000009', dept='Biotechnology', subjects=['BT210', 'BT415'], password='pass901'),
    'prof.joseph': dict(role='teacher', name='Prof. Maria Joseph', email='maria.joseph@college.edu', phone='9100000010', dept='MBA', subjects=['MB101', 'MB402'], password='pass012'),

    'john.doe': dict(role='student', name='John Doe', roll='CS21001', email='john.doe@student.edu', phone='9200000001', dept='CSE', sem=4, section='A', parent_name='Robert Doe', parent_email='robert.doe@gmail.com', parent_phone='9300000001', password='pass123'),
    'jane.smith': dict(role='student', name='Jane Smith', roll='CS21002', email='jane.smith@student.edu', phone='9200000002', dept='CSE', sem=4, section='A', parent_name='Mary Smith', parent_email='mary.smith@gmail.com', parent_phone='9300000002', password='pass123'),
    'amit.k': dict(role='student', name='Amit Kumar', roll='CS21003', email='amit.k@student.edu', phone='9200000003', dept='CSE', sem=4, section='A', parent_name='Suresh Kumar', parent_email='suresh.k@gmail.com', parent_phone='9300000003', password='pass123'),
    'sara.m': dict(role='student', name='Sara Menon', roll='CS21004', email='sara.m@student.edu', phone='9200000004', dept='CSE', sem=4, section='B', parent_name='Priya Menon', parent_email='priya.menon@gmail.com', parent_phone='9300000004', password='pass123'),
    'raj.v': dict(role='student', name='Raj Verma', roll='CS21005', email='raj.v@student.edu', phone='9200000005', dept='CSE', sem=4, section='B', parent_name='Ramesh Verma', parent_email='ramesh.v@gmail.com', parent_phone='9300000005', password='pass123'),
    'aarav.k': dict(role='student', name='Aarav Kumar', roll='CS22001', email='aarav.k@student.edu', phone='9200000001', dept='CSE', sem=4, section='A', parent_name='Rajesh Kumar', parent_email='rajesh.kumar@gmail.com', parent_phone='9300000001', password='pass123'),
    'diya.r': dict(role='student', name='Diya Reddy', roll='EC22002', email='diya.r@student.edu', phone='9200000002', dept='ECE', sem=4, section='B', parent_name='Suma Reddy', parent_email='suma.reddy@gmail.com', parent_phone='9300000002', password='pass234'),
    'vivaan.s': dict(role='student', name='Vivaan Sharma', roll='ME22003', email='vivaan.s@student.edu', phone='9200000003', dept='ME', sem=6, section='A', parent_name='Anil Sharma', parent_email='anil.sharma@gmail.com', parent_phone='9300000003', password='pass345'),
    'isha.p': dict(role='student', name='Isha Patel', roll='CV22004', email='isha.p@student.edu', phone='9200000004', dept='Civil', sem=2, section='C', parent_name='Rakesh Patel', parent_email='rakesh.patel@gmail.com', parent_phone='9300000004', password='pass456'),
    'aditya.n': dict(role='student', name='Aditya Nair', roll='EE22005', email='aditya.n@student.edu', phone='9200000005', dept='EEE', sem=8, section='A', parent_name='Sunita Nair', parent_email='sunita.nair@gmail.com', parent_phone='9300000005', password='pass567'),
    'priya.n': dict(role='student', name='Priya Nair', roll='EC21001', email='priya.n@student.edu', phone='9200000006', dept='ECE', sem=4, section='A', parent_name='Vijay Nair', parent_email='vijay.nair@gmail.com', parent_phone='9300000006', password='pass123'),
    'kiran.s': dict(role='student', name='Kiran Shah', roll='EC21002', email='kiran.s@student.edu', phone='9200000007', dept='ECE', sem=4, section='A', parent_name='Meena Shah', parent_email='meena.shah@gmail.com', parent_phone='9300000007', password='pass123'),
    'neha.j': dict(role='student', name='Neha Joseph', roll='BT22006', email='neha.j@student.edu', phone='9200000006', dept='Biotechnology', sem=5, section='B', parent_name='Maria Joseph', parent_email='maria.joseph@gmail.com', parent_phone='9300000006', password='pass678'),
    'rahul.d': dict(role='student', name='Rahul Das', roll='PH22007', email='rahul.d@student.edu', phone='9200000008', dept='Physics', sem=3, section='C', parent_name='Sanjay Das', parent_email='sanjay.das@gmail.com', parent_phone='9300000008', password='pass789'),
    'sneha.m': dict(role='student', name='Sneha Menon', roll='CH22008', email='sneha.m@student.edu', phone='9200000009', dept='Chemistry', sem=1, section='A', parent_name='Lakshmi Menon', parent_email='lakshmi.menon@gmail.com', parent_phone='9300000009', password='pass890'),
    'arjun.t': dict(role='student', name='Arjun Thomas', roll='MB22009', email='arjun.t@student.edu', phone='9200000010', dept='MBA', sem=2, section='B', parent_name='George Thomas', parent_email='george.thomas@gmail.com', parent_phone='9300000010', password='pass901'),
}

HOLIDAYS = [
    {'date': '2025-01-26', 'name': 'Republic Day'},
    {'date': '2025-08-15', 'name': 'Independence Day'},
    {'date': '2025-10-02', 'name': 'Gandhi Jayanti'},
    {'date': '2025-11-01', 'name': 'Kannada Rajyotsava'},
    {'date': '2025-12-25', 'name': 'Christmas'},
]

TIMETABLE = [
    {'dept': 'CSE', 'sem': '4', 'section': 'A', 'day': 'Monday', 'periods': [
        {'time': '09:00-10:00', 'subject': 'CS301', 'teacher': 'prof.sharma'},
        {'time': '10:00-11:00', 'subject': 'CS302', 'teacher': 'prof.rao'},
    ]},
    {'dept': 'CSE', 'sem': '4', 'section': 'A', 'day': 'Wednesday', 'periods': [
        {'time': '09:00-10:00', 'subject': 'CS401', 'teacher': 'prof.sharma'},
    ]},
    {'dept': 'ECE', 'sem': '4', 'section': 'A', 'day': 'Tuesday', 'periods': [
        {'time': '09:00-10:00', 'subject': 'EC301', 'teacher': 'prof.rao'},
    ]},
]


def seed_if_empty():
    if User.query.count() >= 37 and User.query.filter_by(role='student').count() >= 24:
        return

    for username, data in USERS.items():
        if User.query.get(username):
            continue
        db.session.add(User(username=username, **data))

    if not Holiday.query.first():
        for h in HOLIDAYS:
            db.session.add(Holiday(**h))

    if not TimetableEntry.query.first():
        for t in TIMETABLE:
            db.session.add(TimetableEntry(**t))

    if not Announcement.query.first():
        today = now_date()
        db.session.add(Announcement(id='ann1', title='Mid-semester exams schedule',
                                    body='Mid-semester exams will be held from Nov 15–20. Attendance mandatory.',
                                    author='admin', date=today, target='all'))
        db.session.add(Announcement(id='ann2', title='Minimum attendance reminder',
                                    body='Students below 75% attendance will not be allowed to appear in final exams.',
                                    author='admin', date=today, target='student'))

    if not Settings.query.get(1):
        db.session.add(Settings(id=1, college_name='Demo Engineering College', threshold=75,
                                campus_wifi_ssid='CollegeNet', campus_radius=600,
                                college_wifi_ips=['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16']))

    db.session.commit()
