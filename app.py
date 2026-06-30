import os
import pymysql
from markupsafe import Markup
pymysql.install_as_MySQLdb()

# ========== IMPORTS ==========
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
import MySQLdb.cursors
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import re
import secrets
from datetime import datetime, timedelta
from flask_mail import Message # Make sure this is imported
from functools import wraps
from flask_mail import Mail, Message
from apscheduler.schedulers.background import BackgroundScheduler
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

# ========== FLASK APP CONFIGURATION ==========
app = Flask(__name__)

# Secret key for session management (Loaded from Render Environment Variables)
app.secret_key = os.environ.get('SECRET_KEY', '202005')

# MySQL configuration (Loaded from Render Environment Variables)
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'sql.freedb.tech')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'u_p42gKM')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', 'hw9BfmF4w29g')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB', 'hospital_db')

# Custom MySQL wrapper to avoid mysqlclient C-extension issues on Render
class MySQL:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)
            
    def init_app(self, app):
        self.app = app
        
    @property
    def connection(self):
        # Reuses the same connection for the duration of the web request
        if 'mysql_db' not in g:
            g.mysql_db = pymysql.connect(
                host=self.app.config['MYSQL_HOST'],
                user=self.app.config['MYSQL_USER'],
                password=self.app.config['MYSQL_PASSWORD'],
                database=self.app.config['MYSQL_DB'],
                cursorclass=MySQLdb.cursors.DictCursor
            )
        return g.mysql_db

mysql = MySQL(app)

# Automatically close the database connection when the web request ends
@app.teardown_appcontext
def close_connection(exception):
    db = g.pop('mysql_db', None)
    if db is not None:
        db.close()

# Email configuration (Loaded from Render Environment Variables)
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'your_app_password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'your_email@gmail.com')

mail = Mail(app)
scheduler = BackgroundScheduler()
scheduler.start()

# ========== WEB DECORATORS ==========
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            flash('Please login first!', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'admin':
            flash('Admin access required!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'doctor':
            flash('Doctor access required!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'patient':
            flash('Patient access required!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ========== API DECORATORS ==========
def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session:
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def api_patient_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'patient':
            return jsonify({'success': False, 'message': 'Patient access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def api_doctor_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'doctor':
            return jsonify({'success': False, 'message': 'Doctor access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

def api_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'loggedin' not in session or session.get('user_type') != 'admin':
            return jsonify({'success': False, 'message': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ========== HOME ROUTE ==========
@app.route('/')
def index():
    return render_template('index.html')

# ========== AUTHENTICATION ROUTES ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        
        # Try to find user in Patient table first
        cursor.execute('SELECT * FROM Patient WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['patient_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'patient'
            flash('Login successful!', 'success')
            cursor.close()
            return redirect(url_for('patient_dashboard'))
        
        # Try Doctor table
        cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['doctor_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'doctor'
            flash('Login successful!', 'success')
            cursor.close()
            return redirect(url_for('doctor_dashboard'))
        
        # Try Admin table
        cursor.execute('SELECT * FROM Admin WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['admin_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'admin'
            flash('Login successful!', 'success')
            cursor.close()
            return redirect(url_for('admin_dashboard'))
        
        # If no match found
        flash('Invalid email or password!', 'danger')
        cursor.close()
    
    return render_template('login.html')
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        age = request.form['age']
        gender = request.form['gender']
        address = request.form.get('address', '')  # Add this
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Patient WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            flash('Account already exists!', 'warning')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!', 'warning')
        elif not password:
            flash('Password is required!', 'warning')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO Patient (name, email, password, phone, age, gender, address) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (name, email, hashed_password, phone, age, gender, address)
            )
            mysql.connection.commit()
            cursor.close()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        cursor.close()
    
    return render_template('register.html')
@app.route('/doctor/register', methods=['GET', 'POST'])
def doctor_register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        specialization = request.form['specialization']
        experience = request.form['experience']
        available_slots = request.form['available_slots']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            flash('Doctor account already exists!', 'warning')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!', 'warning')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                'INSERT INTO Doctor (name, email, password, phone, specialization, experience, available_slots) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                (name, email, hashed_password, phone, specialization, experience, available_slots)
            )
            mysql.connection.commit()
            cursor.close()
            flash('Doctor registration successful! Please login.', 'success')
            return redirect(url_for('doctor_login'))
        
        cursor.close()
    
    return render_template('doctor/register.html')

@app.route('/doctor/login', methods=['GET', 'POST'])
def doctor_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['doctor_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'doctor'
            flash('Login successful!', 'success')
            cursor.close()
            return redirect(url_for('doctor_dashboard'))
        else:
            flash('Invalid email or password!', 'danger')
        
        cursor.close()
    
    return render_template('doctor/login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out!', 'info')
    return redirect(url_for('index'))
# ========== FORGOT PASSWORD ROUTES ==========

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip()
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        user_found = False
        user_type = ''
        user_id_col = ''
        table_name = ''

        # Check Patient
        cursor.execute('SELECT * FROM Patient WHERE email = %s', (email,))
        user = cursor.fetchone()
        if user:
            user_found = True
            user_type = 'patient'
            user_id_col = 'patient_id'
            table_name = 'Patient'
        else:
            # Check Doctor
            cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
            user = cursor.fetchone()
            if user:
                user_found = True
                user_type = 'doctor'
                user_id_col = 'doctor_id'
                table_name = 'Doctor'

        if user_found:
            # Generate secure token and expiry (1 hour)
            token = secrets.token_urlsafe(32)
            expiry = datetime.utcnow() + timedelta(hours=1)
            
            # Save to database
            cursor.execute(
                f'UPDATE {table_name} SET reset_token = %s, reset_token_expiry = %s WHERE {user_id_col} = %s',
                (token, expiry, user[user_id_col])
            )
            mysql.connection.commit()

            # Generate reset link
            reset_url = url_for('reset_password', token=token, _external=True)

            # Send Email
            try:
                msg = Message('Password Reset Request', 
                              sender=app.config['MAIL_DEFAULT_SENDER'], 
                              recipients=[email])
                msg.body = f'''Hello {user['name']},

You have requested to reset your password. Click the link below to set a new password:

{reset_url}

This link will expire in 1 hour. If you did not make this request, please ignore this email.

Best regards,
Smart Hospital Team'''
                mail.send(msg)
                flash('A password reset link has been sent to your email.', 'success')
            except Exception as e:
                flash(f'Error sending email: {str(e)}', 'danger')
        else:
            # Don't reveal if email exists or not for security, but show generic message
            flash('If an account with that email exists, a reset link has been sent.', 'info')

        cursor.close()
        return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check token in Patient table
    cursor.execute('SELECT * FROM Patient WHERE reset_token = %s AND reset_token_expiry > %s', (token, datetime.utcnow()))
    user = cursor.fetchone()
    user_type = 'patient'
    id_col = 'patient_id'
    table = 'Patient'

    # If not found in Patient, check Doctor
    if not user:
        cursor.execute('SELECT * FROM Doctor WHERE reset_token = %s AND reset_token_expiry > %s', (token, datetime.utcnow()))
        user = cursor.fetchone()
        user_type = 'doctor'
        id_col = 'doctor_id'
        table = 'Doctor'

    if not user:
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
        elif len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute(
                f'UPDATE {table} SET password = %s, reset_token = NULL, reset_token_expiry = NULL WHERE {id_col} = %s',
                (hashed_password, user[id_col])
            )
            mysql.connection.commit()
            flash('Password updated successfully! Please login.', 'success')
            return redirect(url_for('login'))

    cursor.close()
    return render_template('reset_password.html', token=token)

# ========== PATIENT ROUTES ==========
@app.route('/patient/dashboard')
@patient_required
def patient_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('''
        SELECT a.*, d.name as doctor_name, d.specialization 
        FROM Appointment a 
        JOIN Doctor d ON a.doctor_id = d.doctor_id 
        WHERE a.patient_id = %s AND a.status IN ('Pending', 'Approved')
        ORDER BY a.date, a.time
    ''', (session['id'],))
    upcoming_appointments = cursor.fetchall()
    
    cursor.execute('''
        SELECT a.*, d.name as doctor_name, d.specialization 
        FROM Appointment a 
        JOIN Doctor d ON a.doctor_id = d.doctor_id 
        WHERE a.patient_id = %s AND a.status IN ('Completed', 'Rejected', 'Cancelled')
        ORDER BY a.date DESC, a.time DESC
    ''', (session['id'],))
    appointment_history = cursor.fetchall()
    
    cursor.close()
    
    # Convert times to 12-hour AM/PM format
        # Convert times to 12-hour AM/PM format
    def format_time_12hr(time_obj):
        if time_obj is None:
            return ''
        
        # Handle timedelta objects (MySQL sometimes returns these)
        from datetime import timedelta
        if isinstance(time_obj, timedelta):
            # Convert timedelta to time object
            total_seconds = int(time_obj.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            from datetime import time
            time_obj = time(hours, minutes)
        
        # Handle string time values
        if isinstance(time_obj, str):
            time_obj = datetime.strptime(time_obj, '%H:%M:%S').time()
        
        # Now format as 12-hour time
        return time_obj.strftime('%I:%M %p')  # e.g., "09:30 AM" or "02:00 PM"
    
    for appt in upcoming_appointments:
        appt['time_formatted'] = format_time_12hr(appt['time'])
    
    for appt in appointment_history:
        appt['time_formatted'] = format_time_12hr(appt['time'])
    
    return render_template('patient/dashboard.html', 
                         upcoming_appointments=upcoming_appointments,
                         appointment_history=appointment_history)

@app.route('/patient/doctors')
@patient_required
def view_doctors():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    specialization = request.args.get('specialization')
    
    if specialization:
        cursor.execute('SELECT * FROM Doctor WHERE specialization = %s', (specialization,))
    else:
        cursor.execute('SELECT * FROM Doctor')
    
    doctors = cursor.fetchall()
    
    cursor.execute('SELECT DISTINCT specialization FROM Doctor')
    specializations = [row['specialization'] for row in cursor.fetchall()]
    
    cursor.close()
    return render_template('patient/view_doctors.html', doctors=doctors, specializations=specializations)

@app.route('/patient/book/<int:doctor_id>', methods=['GET', 'POST'])
@patient_required
def book_appointment(doctor_id):
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('SELECT * FROM Doctor WHERE doctor_id = %s', (doctor_id,))
    doctor = cursor.fetchone()
    
    if not doctor:
        flash('Doctor not found!', 'danger')
        cursor.close()
        return redirect(url_for('view_doctors'))
    
    if request.method == 'POST':
        date = request.form['date']
        time = request.form['time']
        
        cursor.execute('''
            SELECT * FROM Appointment 
            WHERE doctor_id = %s AND date = %s AND time = %s 
            AND status IN ('Pending', 'Approved')
        ''', (doctor_id, date, time))
        
        existing = cursor.fetchone()
        
        if existing:
            # Create a helpful message with a link to find other doctors
            message = Markup(
                f'<strong>Dr. {doctor["name"]} is busy at this time.</strong> '
                f'Please choose another time slot or '
                f'<a href="{url_for("view_doctors", specialization=doctor["specialization"])}">find another {doctor["specialization"]} doctor</a>.'
            )
            flash(message, 'warning')
            cursor.close()
            return redirect(url_for('book_appointment', doctor_id=doctor_id))
        else:
            cursor.execute(
                'INSERT INTO Appointment (patient_id, doctor_id, date, time, status) VALUES (%s, %s, %s, %s, %s)',
                (session['id'], doctor_id, date, time, 'Pending')
            )
            mysql.connection.commit()
            cursor.close()
            flash('Appointment booked successfully! Waiting for doctor approval.', 'success')
            return redirect(url_for('patient_dashboard'))
    
    cursor.close()
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('patient/book_appointment.html', doctor=doctor, today=today)

@app.route('/patient/book_appointment', methods=['GET', 'POST'])
@patient_required
def patient_book_appointment_page():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == 'POST':
        doctor_id = request.form['doctor_id']
        date = request.form['date']
        time = request.form['time']
        
        cursor.execute('''
            SELECT * FROM Appointment 
            WHERE doctor_id = %s AND date = %s AND time = %s 
            AND status IN ('Pending', 'Approved')
        ''', (doctor_id, date, time))
        
        existing = cursor.fetchone()
        
        if existing:
            # Get the doctor's name and specialization for the message
            cursor.execute('SELECT name, specialization FROM Doctor WHERE doctor_id = %s', (doctor_id,))
            busy_doc = cursor.fetchone()
            
            message = Markup(
                f'<strong>Dr. {busy_doc["name"]} is not available at this time.</strong> '
                f'Please choose another slot or '
                f'<a href="{url_for("view_doctors", specialization=busy_doc["specialization"])}">find another {busy_doc["specialization"]} doctor</a>.'
            )
            flash(message, 'warning')
            cursor.close()
            return redirect(url_for('patient_book_appointment_page'))
        else:
            cursor.execute(
                'INSERT INTO Appointment (patient_id, doctor_id, date, time, status) VALUES (%s, %s, %s, %s, %s)',
                (session['id'], doctor_id, date, time, 'Pending')
            )
            mysql.connection.commit()
            cursor.close()
            flash('Appointment booked successfully! Waiting for doctor approval.', 'success')
            return redirect(url_for('patient_dashboard'))
    
    cursor.execute('SELECT * FROM Doctor')
    doctors = cursor.fetchall()
    cursor.close()
    
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('patient/book_appointment_page.html', doctors=doctors, today=today)

@app.route('/patient/cancel/<int:appointment_id>')
@patient_required
def cancel_appointment(appointment_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        'UPDATE Appointment SET status = "Cancelled" WHERE appointment_id = %s AND patient_id = %s',
        (appointment_id, session['id'])
    )
    mysql.connection.commit()
    cursor.close()
    flash('Appointment cancelled successfully!', 'info')
    return redirect(url_for('patient_dashboard'))

@app.route('/patient/cancel/<int:appointment_id>')
@patient_required
def cancel_appointment(appointment_id):
    cursor = mysql.connection.cursor()
    
    # Only allow cancellation if the appointment belongs to this patient
    # and is currently Pending or Approved
    cursor.execute('''
        UPDATE Appointment 
        SET status = 'Cancelled' 
        WHERE appointment_id = %s AND patient_id = %s AND status IN ('Pending', 'Approved')
    ''', (appointment_id, session['id']))
    
    mysql.connection.commit()
    
    if cursor.rowcount > 0:
        flash('Appointment cancelled successfully!', 'success')
    else:
        flash('Could not cancel appointment. It may have already been completed or cancelled.', 'warning')
    
    cursor.close()
    return redirect(url_for('patient_dashboard'))

# ========== DOCTOR ROUTES ==========
@app.route('/doctor/dashboard')
@doctor_required
def doctor_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    today = datetime.now().date()
    
    # 1. Get Today's Appointments
        # Get today's appointments with FULL patient details
    # CHANGED 'JOIN' TO 'LEFT JOIN' TO PREVENT MISSING ROWS
    cursor.execute('''
        SELECT a.*, 
               p.name as patient_name, 
               p.email as patient_email, 
               p.phone as patient_phone,
               p.age as patient_age,
               p.gender as patient_gender,
               p.address as patient_address,
               d.specialization
        FROM Appointment a 
        LEFT JOIN Patient p ON a.patient_id = p.patient_id
        LEFT JOIN Doctor d ON a.doctor_id = d.doctor_id
        WHERE a.doctor_id = %s AND a.date = %s AND a.status = 'Approved'
        ORDER BY a.time
    ''', (session['id'], today))
    today_appointments = cursor.fetchall()
    
    # 2. Get Pending Appointments
    cursor.execute('''
        SELECT a.*, p.name as patient_name, p.email as patient_email, 
               p.phone as patient_phone, d.specialization
        FROM Appointment a 
        JOIN Patient p ON a.patient_id = p.patient_id
        JOIN Doctor d ON a.doctor_id = d.doctor_id
        WHERE a.doctor_id = %s AND a.status = 'Pending'
        ORDER BY a.date, a.time
    ''', (session['id'],))
    pending_appointments = cursor.fetchall()
    
    # 3. Get Completed Appointments
    cursor.execute('''
        SELECT a.*, p.name as patient_name, p.email as patient_email, 
               p.phone as patient_phone, p.age as patient_age, 
               p.gender as patient_gender, p.address as patient_address,
               d.specialization
        FROM Appointment a 
        JOIN Patient p ON a.patient_id = p.patient_id
        JOIN Doctor d ON a.doctor_id = d.doctor_id
        WHERE a.doctor_id = %s AND a.status = 'Completed'
        ORDER BY a.date DESC, a.time DESC
    ''', (session['id'],))
    completed_appointments = cursor.fetchall()
    
    cursor.close()
    
    # ==========================================
    # DEFINE THE FUNCTION ONLY ONCE HERE
    # ==========================================
    def format_time_12hr(time_obj):
        if time_obj is None:
            return ''
        from datetime import timedelta, time as dt_time
        if isinstance(time_obj, timedelta):
            total_seconds = int(time_obj.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            time_obj = dt_time(hours, minutes)
        if isinstance(time_obj, str):
            time_obj = datetime.strptime(time_obj, '%H:%M:%S').time()
        return time_obj.strftime('%I:%M %p')

    # Apply formatting to ALL lists using the SAME function
    for appt in today_appointments:
        appt['time_formatted'] = format_time_12hr(appt['time'])
        
    for appt in pending_appointments:
        appt['time_formatted'] = format_time_12hr(appt['time'])
        
    for appt in completed_appointments:
        appt['time_formatted'] = format_time_12hr(appt['time'])
    
    return render_template('doctor/dashboard.html', 
                         today_appointments=today_appointments,
                         pending_appointments=pending_appointments,
                         completed_appointments=completed_appointments)

@app.route('/doctor/complete/<int:appointment_id>')
@doctor_required
def complete_appointment(appointment_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        'UPDATE Appointment SET status = "Completed" WHERE appointment_id = %s AND doctor_id = %s',
        (appointment_id, session['id'])
    )
    mysql.connection.commit()
    cursor.close()
    flash('Appointment marked as completed!', 'success')
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/appointments')
@doctor_required
def doctor_appointments():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('''
        SELECT a.*, p.name as patient_name, p.email as patient_email, p.phone as patient_phone
        FROM Appointment a 
        JOIN Patient p ON a.patient_id = p.patient_id 
        WHERE a.doctor_id = %s
        ORDER BY a.date DESC, a.time DESC
    ''', (session['id'],))
    
    appointments = cursor.fetchall()
    cursor.close()
    return render_template('doctor/appointments.html', appointments=appointments)

@app.route('/doctor/approve/<int:appointment_id>')
@doctor_required
def approve_appointment(appointment_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        'UPDATE Appointment SET status = "Approved" WHERE appointment_id = %s AND doctor_id = %s',
        (appointment_id, session['id'])
    )
    mysql.connection.commit()
    cursor.close()
    flash('Appointment approved!', 'success')
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/reject/<int:appointment_id>')
@doctor_required
def reject_appointment(appointment_id):
    cursor = mysql.connection.cursor()
    cursor.execute(
        'UPDATE Appointment SET status = "Rejected" WHERE appointment_id = %s AND doctor_id = %s',
        (appointment_id, session['id'])
    )
    mysql.connection.commit()
    cursor.close()
    flash('Appointment rejected!', 'info')
    return redirect(url_for('doctor_dashboard'))

@app.route('/doctor/schedule', methods=['GET', 'POST'])
@doctor_required
def manage_schedule():
    if request.method == 'POST':
        available_slots = request.form['available_slots']
        cursor = mysql.connection.cursor()
        cursor.execute(
            'UPDATE Doctor SET available_slots = %s WHERE doctor_id = %s',
            (available_slots, session['id'])
        )
        mysql.connection.commit()
        cursor.close()
        flash('Schedule updated successfully!', 'success')
        return redirect(url_for('manage_schedule'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM Doctor WHERE doctor_id = %s', (session['id'],))
    doctor = cursor.fetchone()
    cursor.close()
    
    return render_template('doctor/schedule.html', doctor=doctor)

# ========== ADMIN ROUTES ==========
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('SELECT COUNT(*) as total FROM Patient')
    total_patients = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM Doctor')
    total_doctors = cursor.fetchone()['total']
    
    today = datetime.now().date()
    cursor.execute('SELECT COUNT(*) as total FROM Appointment WHERE date = %s', (today,))
    today_appointments = cursor.fetchone()['total']
    
    cursor.execute('SELECT COUNT(*) as total FROM Appointment WHERE status = "Pending"')
    pending_requests = cursor.fetchone()['total']
    
    cursor.close()
    
    stats = {
        'total_patients': total_patients,
        'total_doctors': total_doctors,
        'today_appointments': today_appointments,
        'pending_requests': pending_requests
    }
    
    return render_template('admin/dashboard.html', stats=stats)

@app.route('/admin/doctors')
@admin_required
def admin_doctors():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM Doctor')
    doctors = cursor.fetchall()
    cursor.close()
    return render_template('admin/doctors.html', doctors=doctors)

@app.route('/admin/patients')
@admin_required
def admin_patients():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM Patient')
    patients = cursor.fetchall()
    cursor.close()
    return render_template('admin/patients.html', patients=patients)

@app.route('/admin/reports')
@admin_required
def admin_reports():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    cursor.execute('''
        SELECT a.*, p.name as patient_name, d.name as doctor_name 
        FROM Appointment a 
        JOIN Patient p ON a.patient_id = p.patient_id 
        JOIN Doctor d ON a.doctor_id = d.doctor_id
        ORDER BY a.date DESC, a.time DESC
    ''')
    appointments = cursor.fetchall()
    
    cursor.close()
    return render_template('admin/reports.html', appointments=appointments)
# ========== NEW FEATURES ==========

@app.route('/patient/nearby_doctors')
@patient_required
def nearby_doctors():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get all doctors with location
    cursor.execute('SELECT * FROM Doctor WHERE latitude IS NOT NULL AND longitude IS NOT NULL')
    doctors = cursor.fetchall()
    
    # Get patient's location (you can store this in session or get from their profile)
    cursor.execute('SELECT * FROM Patient WHERE patient_id = %s', (session['id'],))
    patient = cursor.fetchone()
    
    cursor.close()
    
    # Calculate distance for each doctor (Haversine formula)
    import math
    
    def calculate_distance(lat1, lon1, lat2, lon2):
        R = 6371  # Earth's radius in km
        
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    # Add distance to each doctor
    if patient and patient.get('latitude') and patient.get('longitude'):
        for doctor in doctors:
            if doctor.get('latitude') and doctor.get('longitude'):
                doctor['distance'] = round(calculate_distance(
                    float(patient['latitude']), 
                    float(patient['longitude']),
                    float(doctor['latitude']), 
                    float(doctor['longitude'])
                ), 2)
        # Sort by distance
        doctors.sort(key=lambda x: x.get('distance', 9999))
    
    return render_template('patient/nearby_doctors.html', doctors=doctors, patient=patient)

@app.route('/patient/update_location', methods=['POST'])
@patient_required
def update_location():
    latitude = request.form.get('latitude')
    longitude = request.form.get('longitude')
    address = request.form.get('address')
    
    cursor = mysql.connection.cursor()
    cursor.execute(
        'UPDATE Patient SET latitude = %s, longitude = %s, address = %s WHERE patient_id = %s',
        (latitude, longitude, address, session['id'])
    )
    mysql.connection.commit()
    cursor.close()
    
    flash('Location updated successfully!', 'success')
    return redirect(url_for('nearby_doctors'))

# ========== UPDATED SYMPTOM CHECKER WITH MORE DISEASES ==========

SYMPTOM_DEPARTMENT_MAP = {
    'fever': ['General Medicine', 'Infectious Disease'],
    'cough': ['General Medicine', 'Pulmonology'],
    'cold': ['General Medicine', 'ENT'],
    'headache': ['General Medicine', 'Neurology'],
    'migraine': ['Neurology'],
    'chest pain': ['Cardiology', 'Emergency'],
    'heart attack': ['Cardiology', 'Emergency'],
    'stomach pain': ['Gastroenterology', 'General Medicine'],
    'abdominal pain': ['Gastroenterology'],
    'back pain': ['Orthopedics', 'Neurology'],
    'skin rash': ['Dermatology'],
    'acne': ['Dermatology'],
    'eye pain': ['Ophthalmology'],
    'blurry vision': ['Ophthalmology'],
    'ear pain': ['ENT'],
    'hearing loss': ['ENT'],
    'tooth pain': ['Dental'],
    'toothache': ['Dental'],
    'joint pain': ['Orthopedics', 'Rheumatology'],
    'arthritis': ['Rheumatology', 'Orthopedics'],
    'diabetes': ['Endocrinology'],
    'high blood sugar': ['Endocrinology'],
    'high blood pressure': ['Cardiology'],
    'hypertension': ['Cardiology'],
    'anxiety': ['Psychiatry', 'Psychology'],
    'depression': ['Psychiatry', 'Psychology'],
    'stress': ['Psychiatry', 'Psychology'],
    'pregnancy': ['Gynecology', 'Obstetrics'],
    'period pain': ['Gynecology'],
    'menstrual cramps': ['Gynecology'],
    'pediatric': ['Pediatrics'],
    'child': ['Pediatrics'],
    'baby': ['Pediatrics'],
    'bone fracture': ['Orthopedics'],
    'broken bone': ['Orthopedics'],
    'allergy': ['Allergy & Immunology'],
    'asthma': ['Pulmonology', 'Allergy & Immunology'],
    'urinary': ['Urology', 'Nephrology'],
    'kidney': ['Nephrology', 'Urology'],
    'kidney stones': ['Urology', 'Nephrology'],
    'heart': ['Cardiology'],
    'palpitations': ['Cardiology'],
    'brain': ['Neurology'],
    'seizure': ['Neurology'],
    'mental health': ['Psychiatry'],
    'insomnia': ['Neurology', 'Psychiatry'],
    'sleep problems': ['Neurology', 'Psychiatry'],
    'dizziness': ['Neurology', 'ENT'],
    'vertigo': ['ENT', 'Neurology'],
    'nausea': ['Gastroenterology', 'General Medicine'],
    'vomiting': ['Gastroenterology', 'General Medicine'],
    'diarrhea': ['Gastroenterology'],
    'constipation': ['Gastroenterology'],
    'weight loss': ['Endocrinology', 'General Medicine'],
    'weight gain': ['Endocrinology', 'General Medicine'],
    'fatigue': ['General Medicine', 'Endocrinology'],
    'tiredness': ['General Medicine', 'Endocrinology'],
    'shortness of breath': ['Pulmonology', 'Cardiology'],
    'breathing problems': ['Pulmonology'],
    'throat pain': ['ENT', 'General Medicine'],
    'sore throat': ['ENT', 'General Medicine'],
    'sinus': ['ENT'],
    'sinusitis': ['ENT'],
    'hair loss': ['Dermatology', 'Endocrinology'],
    'eczema': ['Dermatology'],
    'psoriasis': ['Dermatology'],
    'thyroid': ['Endocrinology'],
    'thyroid problems': ['Endocrinology'],
    'anemia': ['Hematology', 'General Medicine'],
    'bleeding': ['Hematology', 'Emergency'],
    'urine infection': ['Urology', 'Nephrology'],
    'UTI': ['Urology'],
    'prostate': ['Urology'],
    'cancer': ['Oncology'],
    'tumor': ['Oncology'],
    'liver': ['Gastroenterology', 'Hepatology'],
    'jaundice': ['Gastroenterology', 'Hepatology'],
    'hepatitis': ['Gastroenterology', 'Hepatology'],
}



def suggest_department(symptoms):
    symptoms_lower = symptoms.lower()
    department_scores = {}
    
    for symptom, departments in SYMPTOM_DEPARTMENT_MAP.items():
        if symptom in symptoms_lower:
            for dept in departments:
                department_scores[dept] = department_scores.get(dept, 0) + 1
    
    if not department_scores:
        return 'General Medicine'
    
    suggested_dept = max(department_scores, key=department_scores.get)
    return suggested_dept

@app.route('/symptom_checker', methods=['GET', 'POST'])
def symptom_checker():
    suggested_department = None
    symptoms = ''
    
    if request.method == 'POST':
        symptoms = request.form.get('symptoms', '')
        if symptoms:
            suggested_department = suggest_department(symptoms)
    
    return render_template('symptom_checker.html', 
                         suggested_department=suggested_department,
                         symptoms=symptoms)

# ========== EMAIL REMINDER SYSTEM ==========
def send_appointment_reminder():
    """Send email reminders 30 minutes before appointments"""
    # Create a direct connection for the background thread
    conn = pymysql.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB'],
        cursorclass=MySQLdb.cursors.DictCursor
    )
    cursor = conn.cursor()
    
    try:
        # Calculate the exact time 30 minutes from now
        now = datetime.now()
        target_time = now + timedelta(minutes=30)
        
        # Format for MySQL query
        target_date = target_time.date()
        # MySQL TIME format is HH:MM:00
        target_time_str = target_time.strftime('%H:%M:00') 
        
        # Find approved appointments happening in ~30 mins that haven't been reminded yet
        cursor.execute('''
            SELECT a.*, p.name as patient_name, p.email as patient_email,
                   d.name as doctor_name, d.email as doctor_email
            FROM Appointment a
            JOIN Patient p ON a.patient_id = p.patient_id
            JOIN Doctor d ON a.doctor_id = d.doctor_id
            WHERE a.date = %s AND a.time = %s AND a.status = 'Approved' AND a.reminder_sent = 0
        ''', (target_date, target_time_str))
        
        appointments = cursor.fetchall()
        
        for appointment in appointments:
            # 1. Send email to patient
            send_email_reminder(
                to_email=appointment['patient_email'],
                patient_name=appointment['patient_name'],
                doctor_name=appointment['doctor_name'],
                appointment_date=appointment['date'],
                appointment_time=appointment['time'],
                recipient_type='patient'
            )
            
            # 2. Send email to doctor
            send_email_reminder(
                to_email=appointment['doctor_email'],
                patient_name=appointment['patient_name'],
                doctor_name=appointment['doctor_name'],
                appointment_date=appointment['date'],
                appointment_time=appointment['time'],
                recipient_type='doctor'
            )

            # 3. Mark as reminded so it doesn't send again
            cursor.execute(
                'UPDATE Appointment SET reminder_sent = 1 WHERE appointment_id = %s', 
                (appointment['appointment_id'],)
            )
            conn.commit()
            
    except Exception as e:
        print(f"Error in reminder scheduler: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# ... (Keep your send_email_reminder function exactly as it is) ...
def send_email_reminder(to_email, patient_name, doctor_name, appointment_date, appointment_time, recipient_type='patient'):
    try:
        if recipient_type == 'patient':
            subject = f"Appointment Reminder - Dr. {doctor_name} - Tomorrow at {appointment_time}"
            body = f"""
            Dear {patient_name},
            
            This is a reminder about your upcoming appointment:
            Doctor: Dr. {doctor_name}
            Date: {appointment_date}
            Time: {appointment_time}
            
            Best regards,
            Smart Hospital Team
            """
        else:
            subject = f"Appointment Reminder - {patient_name} - Tomorrow at {appointment_time}"
            body = f"""
            Dear Dr. {doctor_name},
            
            You have an appointment scheduled for tomorrow:
            Patient: {patient_name}
            Date: {appointment_date}
            Time: {appointment_time}
            
            Best regards,
            Smart Hospital System
            """
        
        msg = MIMEMultipart()
        msg['From'] = app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(app.config['MAIL_SERVER'], app.config['MAIL_PORT'])
        server.starttls()
        server.login(app.config['MAIL_USERNAME'], app.config['MAIL_PASSWORD'])
        server.send_message(msg)
        server.quit()
        
    except Exception as e:
        print(f"Failed to send email: {str(e)}")

# Schedule the reminder to run EVERY MINUTE
scheduler.add_job(
    func=send_appointment_reminder,
    trigger="cron",
    minute='*' 
)
# ========== REST APIs (All unchanged) ==========
@app.route('/api/patient/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        phone = data.get('phone', '').strip()
        age = data.get('age')
        gender = data.get('gender', '')
        
        if not all([name, email, password, phone, age, gender]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            return jsonify({'success': False, 'message': 'Invalid email address'}), 400
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Patient WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account:
            cursor.close()
            return jsonify({'success': False, 'message': 'Account already exists'}), 409
        
        hashed_password = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO Patient (name, email, password, phone, age, gender) VALUES (%s, %s, %s, %s, %s, %s)',
            (name, email, hashed_password, phone, age, gender)
        )
        mysql.connection.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Registration successful', 'patient': {'name': name, 'email': email}}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/patient/login', methods=['POST'])
def api_patient_login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Patient WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['patient_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'patient'
            cursor.close()
            return jsonify({'success': True, 'message': 'Login successful', 'patient': {'id': account['patient_id'], 'name': account['name'], 'email': account['email']}}), 200
        else:
            cursor.close()
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/doctors', methods=['GET'])
def api_get_doctors():
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        specialization = request.args.get('specialization')
        
        if specialization:
            cursor.execute('SELECT * FROM Doctor WHERE specialization = %s', (specialization,))
        else:
            cursor.execute('SELECT * FROM Doctor')
        
        doctors = cursor.fetchall()
        cursor.execute('SELECT DISTINCT specialization FROM Doctor')
        specializations = [row['specialization'] for row in cursor.fetchall()]
        cursor.close()
        
        return jsonify({'success': True, 'doctors': doctors, 'specializations': specializations, 'count': len(doctors)}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/patient/bookAppointment', methods=['POST'])
@api_patient_required
def api_book_appointment():
    try:
        data = request.get_json()
        doctor_id = data.get('doctor_id')
        date = data.get('date')
        time = data.get('time')
        
        if not all([doctor_id, date, time]):
            return jsonify({'success': False, 'message': 'Doctor ID, date, and time are required'}), 400
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Doctor WHERE doctor_id = %s', (doctor_id,))
        doctor = cursor.fetchone()
        
        if not doctor:
            cursor.close()
            return jsonify({'success': False, 'message': 'Doctor not found'}), 404
        
        cursor.execute('''
            SELECT * FROM Appointment WHERE doctor_id = %s AND date = %s AND time = %s AND status IN ('Pending', 'Approved')
        ''', (doctor_id, date, time))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('SELECT name, specialization FROM Doctor WHERE doctor_id = %s', (doctor_id,))
            busy_doc = cursor.fetchone()
            
            cursor.close()
            return jsonify({
                'success': False, 
                'message': f'Dr. {busy_doc["name"]} is busy at this time. Please find another {busy_doc["specialization"]} doctor.',
                'suggested_action': 'search_other_doctors',
                'specialization': busy_doc['specialization']
            }), 409
        
        cursor.execute(
            'INSERT INTO Appointment (patient_id, doctor_id, date, time, status) VALUES (%s, %s, %s, %s, %s)',
            (session['id'], doctor_id, date, time, 'Pending')
        )
        mysql.connection.commit()
        appointment_id = cursor.lastrowid
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Appointment booked successfully', 'appointment': {'appointment_id': appointment_id, 'doctor_id': doctor_id, 'date': date, 'time': time, 'status': 'Pending'}}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/patient/appointments', methods=['GET'])
@api_patient_required
def api_get_patient_appointments():
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('''
            SELECT a.*, d.name as doctor_name, d.specialization FROM Appointment a JOIN Doctor d ON a.doctor_id = d.doctor_id WHERE a.patient_id = %s ORDER BY a.date DESC, a.time DESC
        ''', (session['id'],))
        appointments = cursor.fetchall()
        cursor.close()
        return jsonify({'success': True, 'appointments': appointments, 'count': len(appointments)}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/doctor/login', methods=['POST'])
def api_doctor_login():
    try:
        data = request.get_json()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['doctor_id']
            session['email'] = account['email']
            session['name'] = account['name']
            session['user_type'] = 'doctor'
            cursor.close()
            return jsonify({'success': True, 'message': 'Login successful', 'doctor': {'id': account['doctor_id'], 'name': account['name'], 'email': account['email'], 'specialization': account['specialization']}}), 200
        else:
            cursor.close()
            return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/doctor/appointments', methods=['GET'])
@api_doctor_required
def api_get_doctor_appointments():
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        status_filter = request.args.get('status')
        
        if status_filter:
            cursor.execute('''
                SELECT a.*, p.name as patient_name, p.email as patient_email, p.phone as patient_phone FROM Appointment a JOIN Patient p ON a.patient_id = p.patient_id WHERE a.doctor_id = %s AND a.status = %s ORDER BY a.date, a.time
            ''', (session['id'], status_filter))
        else:
            cursor.execute('''
                SELECT a.*, p.name as patient_name, p.email as patient_email, p.phone as patient_phone FROM Appointment a JOIN Patient p ON a.patient_id = p.patient_id WHERE a.doctor_id = %s ORDER BY a.date DESC, a.time DESC
            ''', (session['id'],))
        
        appointments = cursor.fetchall()
        cursor.close()
        return jsonify({'success': True, 'appointments': appointments, 'count': len(appointments)}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/approveAppointment', methods=['PUT'])
@api_doctor_required
def api_approve_appointment():
    try:
        data = request.get_json()
        appointment_id = data.get('appointment_id')
        action = data.get('action')
        
        if not appointment_id or not action:
            return jsonify({'success': False, 'message': 'Appointment ID and action required'}), 400
        if action not in ['approve', 'reject']:
            return jsonify({'success': False, 'message': 'Action must be "approve" or "reject"'}), 400
        
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM Appointment WHERE appointment_id = %s AND doctor_id = %s', (appointment_id, session['id']))
        appointment = cursor.fetchone()
        
        if not appointment:
            cursor.close()
            return jsonify({'success': False, 'message': 'Appointment not found'}), 404
        
        new_status = 'Approved' if action == 'approve' else 'Rejected'
        cursor.execute('UPDATE Appointment SET status = %s WHERE appointment_id = %s AND doctor_id = %s', (new_status, appointment_id, session['id']))
        mysql.connection.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': f'Appointment {action}d successfully', 'new_status': new_status}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/admin/dashboard', methods=['GET'])
@api_admin_required
def api_admin_dashboard():
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT COUNT(*) as total FROM Patient')
        total_patients = cursor.fetchone()['total']
        cursor.execute('SELECT COUNT(*) as total FROM Doctor')
        total_doctors = cursor.fetchone()['total']
        today = datetime.now().date()
        cursor.execute('SELECT COUNT(*) as total FROM Appointment WHERE date = %s', (today,))
        today_appointments = cursor.fetchone()['total']
        cursor.execute('SELECT COUNT(*) as total FROM Appointment WHERE status = "Pending"')
        pending_requests = cursor.fetchone()['total']
        cursor.close()
        
        return jsonify({'success': True, 'dashboard': {'total_patients': total_patients, 'total_doctors': total_doctors, 'today_appointments': today_appointments, 'pending_requests': pending_requests}}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/admin/addDoctor', methods=['POST'])
@api_admin_required
def api_add_doctor():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        specialization = data.get('specialization', '').strip()
        experience = data.get('experience')
        email = data.get('email', '').strip()
        password = data.get('password', '')
        phone = data.get('phone', '').strip()
        available_slots = data.get('available_slots', '')
        
        if not all([name, specialization, experience, email, password, phone]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM Doctor WHERE email = %s', (email,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.close()
            return jsonify({'success': False, 'message': 'Doctor with this email already exists'}), 409
        
        hashed_password = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO Doctor (name, specialization, experience, email, password, phone, available_slots) VALUES (%s, %s, %s, %s, %s, %s, %s)',
            (name, specialization, experience, email, hashed_password, phone, available_slots)
        )
        mysql.connection.commit()
        doctor_id = cursor.lastrowid
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Doctor added successfully', 'doctor': {'id': doctor_id, 'name': name, 'email': email, 'specialization': specialization}}), 201
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/admin/removeDoctor', methods=['DELETE'])
@api_admin_required
def api_remove_doctor():
    try:
        data = request.get_json()
        doctor_id = data.get('doctor_id')
        
        if not doctor_id:
            return jsonify({'success': False, 'message': 'Doctor ID required'}), 400
        
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM Doctor WHERE doctor_id = %s', (doctor_id,))
        doctor = cursor.fetchone()
        
        if not doctor:
            cursor.close()
            return jsonify({'success': False, 'message': 'Doctor not found'}), 404
        
        cursor.execute('DELETE FROM Doctor WHERE doctor_id = %s', (doctor_id,))
        mysql.connection.commit()
        cursor.close()
        
        return jsonify({'success': True, 'message': 'Doctor removed successfully'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

@app.route('/api/health', methods=['GET'])
def api_health_check():
    return jsonify({'status': 'OK', 'message': 'Hospital API is running', 'timestamp': datetime.now().isoformat()}), 200
@app.route('/run_reminders')
def run_reminders_route():
    send_appointment_reminder()
    return "Reminders checked!"

# ========== MAIN EXECUTION ==========
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)