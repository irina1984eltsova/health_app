from flask import Flask, render_template, request, redirect, url_for, jsonify
from datetime import datetime, date
import sqlite3
import os
from menu_data import get_menu_day

app = Flask(__name__)
app.secret_key = 'health_secret_key'

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Создаёт таблицы в SQLite, если их нет"""
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS measurements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        time TEXT,
        pressure TEXT,
        pulse INTEGER,
        saturation INTEGER,
        sleep_hours REAL,
        deep_sleep INTEGER,
        awakenings INTEGER,
        weight REAL,
        waist REAL,
        hips REAL,
        cycle_day INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS medications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        dosage TEXT,
        time TEXT,
        date TEXT,
        taken INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    # Стартовая дата (сегодня), если ещё не задана
    c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("start_date", ?)',
              (date.today().strftime('%Y-%m-%d'),))
    conn.commit()
    conn.close()

# ========== ПОЛУЧЕНИЕ НОМЕРА ДНЯ МЕНЮ ==========
def get_menu_day_number():
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = "start_date"')
    row = c.fetchone()
    conn.close()
    if row:
        start_date = datetime.strptime(row[0], '%Y-%m-%d').date()
        diff = (date.today() - start_date).days
        return diff + 1  # день 1 = первый день
    return 1

# ========== ТЕКУЩИЙ ВЕС ==========
def get_current_weight():
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT weight FROM measurements ORDER BY id DESC LIMIT 1')
    row = c.fetchone()
    conn.close()
    return row[0] if row else 89.0

# ========== КОРРЕКЦИЯ МЕНЮ ==========
def apply_corrections(menu, pressure, pulse, saturation, sleep_hours, deep_sleep, cycle_day):
    corrected = []
    salt_factor = 1
    sugar_remove = False
    add_magnesium = False
    water_add = 0
    add_iron = False
    protein_add = 0
    carb_add = 0

    try:
        sys, dia = map(int, pressure.split('/'))
        if sys > 130 or dia > 80:
            salt_factor = 0.7
        if sys < 100 or dia < 60:
            salt_factor = 1.2
    except:
        pass

    if pulse > 80:
        sugar_remove = True
    if saturation < 96:
        water_add = 50
    if sleep_hours < 6 or deep_sleep < 25:
        add_magnesium = True

    if 1 <= cycle_day <= 5:
        add_iron = True
        water_add += 50
        add_magnesium = True
    if 14 <= cycle_day <= 15:
        salt_factor *= 0.8
    if 16 <= cycle_day <= 28:
        protein_add = 20
        carb_add = 15

    for item in menu:
        new_item = dict(item)
        if salt_factor != 1:
            new_item['salt'] = int(new_item['salt'] * salt_factor)
        if sugar_remove and ('мёд' in new_item['dish'] or 'сахар' in new_item['dish']):
            new_item['sugar'] = 0
        if add_magnesium and new_item['meal'] in ['Завтрак', 'Ужин']:
            new_item['dry_weight'] = new_item['dry_weight'] + ' + 5 г семечек'
            new_item['fiber'] += 1
        if water_add > 0 and new_item['meal'] == 'Завтрак':
            new_item['water'] += water_add
        if protein_add > 0 and new_item['meal'] in ['Обед', 'Ужин']:
            new_item['dry_weight'] = new_item['dry_weight'] + f' + {protein_add} г белка'
            new_item['calories'] = int(new_item['calories'] + protein_add * 1.5)
        if carb_add > 0 and new_item['meal'] == 'Завтрак':
            new_item['ready_weight'] += carb_add
            new_item['calories'] = int(new_item['calories'] + carb_add * 3.5)
        if add_iron and new_item['meal'] == 'Обед' and 'курица' in new_item['dish'].lower():
            new_item['dish'] = 'Говядина (вместо курицы)'
        corrected.append(new_item)
    return corrected

# ========== СТРАНИЦЫ ==========
@app.route('/')
def index():
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT * FROM measurements ORDER BY id DESC LIMIT 1')
    last = c.fetchone()
    conn.close()
    return render_template('index.html',
                         today=date.today().strftime('%d.%m.%Y'),
                         last=last,
                         menu_day=get_menu_day_number())

@app.route('/save_measurements', methods=['POST'])
def save_measurements():
    data = request.form
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('''INSERT INTO measurements 
        (date, time, pressure, pulse, saturation, sleep_hours, deep_sleep, awakenings, weight, waist, hips, cycle_day)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (data['date'], data['time'], data['pressure'], int(data['pulse']),
         int(data['saturation']), float(data['sleep']), int(data['deep_sleep']),
         int(data['awakenings']), float(data['weight']), float(data['waist']),
         float(data['hips']), int(data['cycle_day'])))
    conn.commit()
    conn.close()
    return redirect(url_for('menu'))

@app.route('/menu')
def menu():
    day_num = get_menu_day_number()
    current_weight = get_current_weight()
    raw_menu = get_menu_day(day_num, current_weight)

    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT * FROM measurements ORDER BY id DESC LIMIT 1')
    last = c.fetchone()
    conn.close()

    if last:
        pressure = last[3]
        pulse = last[4]
        saturation = last[5]
        sleep_hours = last[6]
        deep_sleep = last[7]
        cycle_day = last[12]
        corrected_menu = apply_corrections(raw_menu, pressure, pulse, saturation, sleep_hours, deep_sleep, cycle_day)
    else:
        corrected_menu = raw_menu

    return render_template('menu.html',
                         menu=corrected_menu,
                         day_num=day_num,
                         today=date.today().strftime('%d.%m.%Y'),
                         weight=current_weight)

@app.route('/history')
def history():
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT * FROM measurements ORDER BY id DESC LIMIT 30')
    measurements = c.fetchall()
    conn.close()
    return render_template('history.html', measurements=measurements)

@app.route('/medications', methods=['GET', 'POST'])
def medications():
    if request.method == 'POST':
        conn = sqlite3.connect('health.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO medications (name, dosage, time, date, taken) VALUES (?, ?, ?, ?, ?)',
            (request.form['name'], request.form['dosage'], request.form['time'],
             date.today().strftime('%Y-%m-%d'), 1 if 'taken' in request.form else 0))
        conn.commit()
        conn.close()
        return redirect(url_for('medications'))

    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    c.execute('SELECT * FROM medications ORDER BY id DESC')
    meds = c.fetchall()
    conn.close()
    return render_template('medications.html', medications=meds)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    conn = sqlite3.connect('health.db')
    c = conn.cursor()
    if 'start_date' in data:
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("start_date", ?)', (data['start_date'],))
    conn.commit()
    conn.close()
    return jsonify({'status': 'ok'})

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
