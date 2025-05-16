from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, session
#import RPi.GPIO as GPIO
# import Adafruit_DHT # Eger Pi-de däl bolsaňyz ýa-da sensor ýok bolsa kommentariýa alyň
#import cv2
#import threading
import time
import os
from functools import wraps # Dekorator üçin

app = Flask(__name__)
# GOWY DÄL, eger bu kod Git-e ýa-da başga ýere köpçülige açyk ýüklenjek bolsa:
app.secret_key = '0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f' # Hakyky, uzyn, tötänleýin setir bilen çalşyň
# GOWUSY (daşky gurşaw üýtgeýjisi bilen):
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'eger_tapylmasa_yerine_goyuljak_howpsuz_acar_local_test_ucin') # Ikinji parametr diňe lokal test üçin. Production-da hökman os.environ.get('FLASK_SECRET_KEY') bolmaly.
if not app.secret_key or app.secret_key == 'eger_tapylmasa_yerine_goyuljak_howpsuz_acar_local_test_ucin':
    if os.environ.get('FLASK_ENV') == 'production': # Eger production bolsa we açar ýok bolsa, programma işini togtatmaly
        raise ValueError("FLASK_SECRET_KEY produkşiýa üçin hökmany kesgitlenmeli!")
    else: # Development üçin
        print("WARNING: FLASK_SECRET_KEY kesgitlenmedik ýa-da adaty gymmatlygy ulanýar. Produkşiýa üçin üýtgediň!")
        app.secret_key = os.urandom(24).hex() # Development üçin wagtlaýyn döretmek
# --- Ulanyjy maglumatlary (ýönekeý mysal) ---
# Hakyky ulgamda maglumatlar bazasyny ulanyň!
USERS = {
    "admin": "123",
    "user": " "
}
MAX_LOGIN_ATTEMPTS = 3
LOCKOUT_DURATION_SECONDS = 30 # 30 sekunt blok

# --- GPIO setup ---
RELAY_PIN = 17
DHT_PIN = 4 # Adafruit_DHT ulanylsa
#GPIO.setwarnings(False) # GPIO kanallary eýýäm ulanylýan bolsa duýduryşlary aýyrmak üçin
#GPIO.setmode(GPIO.BCM)
#GPIO.setup(RELAY_PIN, GPIO.OUT)
#GPIO.output(RELAY_PIN, GPIO.LOW)

# --- DHT sensor setup (Eger ulanylsa) ---
# DHT_SENSOR = Adafruit_DHT.DHT11 # Eger Pi-de däl bolsaňyz ýa-da sensor ýok bolsa kommentariýa alyň

# --- Camera setup ---
camera = None
#camera_lock = threading.Lock()

def initialize_camera():
    global camera
    with camera_lock:
        if camera is None:
            try:
                camera = cv2.VideoCapture(0) # USB kamera üçin 0, Pi Kamera üçin başga san bolup biler
                if not camera.isOpened():
                    print("Kamera tapylmady ýa-da açylmady!")
                    camera = None # Ýalňyşlyk bolsa None edeliň
            except Exception as e:
                print(f"Kamera başlangyçda ýalňyşlyk: {e}")
                camera = None

#initialize_camera() # Programma başlanda kamerany işe girizmäge synanyşalyň

def generate_frames():
    global camera
    while True:
        with camera_lock:
            if camera is None or not camera.isOpened():
                # Eger kamera ýok bolsa, boş kadr ýa-da habar görkezmek üçin bir zat taýýarlaň
                # Mysal üçin, ýazgyly surat
                img = cv2.imread("static/no_camera.png") # "static" papkada "no_camera.png" suraty ýerleşdiriň
                if img is None: # Surat ýok bolsa, ak surat dörediň
                    import numpy as np
                    img = np.ones((480, 640, 3), dtype=np.uint8) * 255
                    cv2.putText(img, "Kamera elýeterli dal", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,0), 2)
                
                ret, buffer = cv2.imencode('.jpg', img)
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                cv2.waitKey(1000) # Her sekuntda bir gezek barlamak
                continue # Kamerany täzeden barlamak üçin loop-y dowam etdirýäris

            success, frame_data = camera.read()
        
        if not success:
            print("Kameradan kadr alynyp bilinmedi.")
            # Kamerany täzeden işe girizmäge synanyşalyň
            initialize_camera()
            cv2.waitKey(1000) # Garaşalyň
            continue
        else:
            try:
                ret, buffer = cv2.imencode('.jpg', frame_data)
                if not ret:
                    print("Kadr JPG formatyna öwrülip bilinmedi.")
                    continue
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            except Exception as e:
                print(f"Kadr generirlenende ýalňyşlyk: {e}")
                # Belki kamerany täzeden başlatmaly
                initialize_camera()
                cv2.waitKey(1000)

# --- Login üçin dekorator ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# --- Marşrutlar (Routes) ---
@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    blocked = False
    remaining_time = 0
    
    username_value = request.form.get('username', '') # Ýalňyşlykdan soň ulanyjy adyny saklamak üçin

    # Blok ýagdaýyny barla (hem GET, hem POST üçin)
    if 'block_until' in session and time.time() < session['block_until']:
        blocked = True
        remaining_time = int(session['block_until'] - time.time())
        if remaining_time <= 0: # Eger wagt gutaran bolsa, ýöne sessiýa arassalanmadyk bolsa
            session.pop('block_until', None)
            session.pop('login_attempts', None)
            blocked = False
        else:
            # GET haýyşynda ýa-da POST haýyşynda blok wagtynda error habaryny döret
            error_message_html = f"Siz köp gezek nädogry synanyşyk etdiňiz. <br>Giriş <strong><span id='countdown_value'>{remaining_time}</span></strong> sekuntdan soň mümkin bolar."
            # Eger POST haýyşy bolsa we bloklanan bolsa, başga error goşma.
            # Eger GET haýyşy bolsa, bu error ýeterlik.
            if request.method == 'GET' or (request.method == 'POST' and blocked):
                 error = error_message_html

    if request.method == 'POST':

        # Eger entek bloklanan bolsa, forma işleme
        if blocked:
            print('birinji login')
            # Error eýýäm ýokarda kesgitlenipdi
            return render_template('login.html', 
                                   error=error, 
                                   blocked=True, 
                                   remaining_time_for_js=remaining_time,
                                   username_value=username_value)

        username = request.form.get('username')
        password = request.form.get('password')
        
        session.setdefault('login_attempts', 0) # Ilkinji gezek üçin

        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            session.pop('login_attempts', None) # Üstünlikli bolsa synanyşyklary nolla
            session.pop('block_until', None)    # Üstünlikli bolsa bloky aýyr
            
            next_url = request.args.get('next')
            return redirect(next_url or url_for('index'))
        else:
            session['login_attempts'] += 1
            attempts_left = MAX_LOGIN_ATTEMPTS - session['login_attempts']
            
            if session['login_attempts'] >= MAX_LOGIN_ATTEMPTS:
                session['block_until'] = time.time() + LOCKOUT_DURATION_SECONDS
                blocked = True
                remaining_time = LOCKOUT_DURATION_SECONDS
                error_message_html = f"Siz köp gezek nädogry synanyşyk etdiňiz. <br>Giriş <strong><span id='countdown_value'>{remaining_time}</span></strong> sekuntdan soň mümkin bolar."
                error = error_message_html
            elif attempts_left > 0:
                error = f"Nädogry ulanyjy ady ýa-da parol! <br>Galan synanyşyk: {attempts_left}"
                username_value = username
            else: # attempts_left == 0, ýöne heniz bloklanmadyk ýagdaýy (bu ýere düşmeli däl)
                error = "Nädogry ulanyjy ady ýa-da parol!"
                username_value = username


    # Eger eýýäm giren bolsa, esasy sahypa ugrat (GET üçin)
    if 'logged_in' in session and not blocked: # Eger bloklanan bolsa, giriş sahypasynda galmaly
        return redirect(url_for('index'))
        
    return render_template('login.html', 
                           error=error, 
                           blocked=blocked, 
                           remaining_time_for_js=remaining_time,
                           username_value=username_value)


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('username', None)
    session.pop('login_attempts', None) # Çykanda synanyşyklary arassala
    session.pop('block_until', None)    # Çykanda bloky arassala
    return redirect(url_for('login'))


@app.route('/video_feed')
@login_required
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/relay', methods=['POST'])
@login_required
def control_relay():
    action = request.json.get('action')
    if action == 'on':
        GPIO.output(RELAY_PIN, GPIO.HIGH)
        return jsonify({'status': 'Relay turned ON'})
    elif action == 'off':
        GPIO.output(RELAY_PIN, GPIO.LOW)
        return jsonify({'status': 'Relay turned OFF'})
    else:
        return jsonify({'error': 'Invalid action'}), 400

DHT_SENSOR_TYPE = None
DHT_PIN = None
ADAFRUIT_DHT_AVAILABLE = False

try:
    import Adafruit_DHT
    # DHT_SENSOR_TYPE = Adafruit_DHT.DHT11
    DHT_SENSOR_TYPE = Adafruit_DHT.DHT22 # DHT22 более точный, если он у вас
    DHT_PIN = 4  # Замените на ваш GPIO пин
    ADAFRUIT_DHT_AVAILABLE = True
    print("Adafruit_DHT library loaded successfully.")
except ImportError:
    print("WARNING: Adafruit_DHT library not found. /temperature endpoint will return N/A or dummy data.")
except RuntimeError as e: # Может быть ошибка при инициализации библиотеки на некоторых системах (например, нет прав)
    ADAFRUIT_DHT_AVAILABLE = False
    print(f"WARNING: Could not initialize Adafruit_DHT: {e}. /temperature endpoint will return N/A or dummy data.")

# --- /НАСТРОЙКИ ДАТЧИКА ---

@app.route('/temperature')
@login_required
def temperature():
    if ADAFRUIT_DHT_AVAILABLE and DHT_SENSOR_TYPE is not None and DHT_PIN is not None:
        try:
            # Используем read_retry для большей надежности
            humidity, temp = Adafruit_DHT.read_retry(DHT_SENSOR_TYPE, DHT_PIN, retries=3, delay_seconds=1)
            
            if humidity is not None and temp is not None:
                return jsonify({
                    'temperature': round(temp, 2),
                    'humidity': round(humidity, 2)
                })
            else:
                # Логирование здесь было бы полезно
                print(f"Failed to retrieve data from DHT sensor (pin {DHT_PIN}). read_retry returned None.")
                return jsonify({'error': 'Failed to retrieve data from DHT sensor'}), 500
        except RuntimeError as e: # Ошибки во время выполнения чтения, например, проблемы с доступом к GPIO
            print(f"Runtime error reading DHT sensor: {str(e)}")
            return jsonify({'error': f'Runtime error reading DHT sensor: {str(e)}'}), 500
        except Exception as e: # Другие непредвиденные ошибки
            print(f"Unexpected error reading DHT sensor: {str(e)}")
            return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500
    else:
        # Возвращаем dummy data если датчик не настроен/недоступен
        # или ошибку, если это предпочтительнее для вашего API
        print("DHT sensor not available or not configured. Returning dummy data for /temperature.")
        return jsonify({
            'temperature': 25.5, # Dummy data
            'humidity': 60.1,    # Dummy data
            'status': 'dummy_data (sensor_not_available)'
        })
        # Альтернатива: вернуть ошибку
        # return jsonify({'error': 'DHT sensor not configured or library not available'}), 503 # 503 Service Unavailable

# --- Programmanyň soňunda GPIO arassalamak ---
def cleanup_gpio():
    print("GPIO arassalanýar...")
    GPIO.cleanup()
    with camera_lock:
        if camera is not None:
            camera.release()
            print("Kamera goýberildi.")
    cv2.destroyAllWindows()

#atexit.register(cleanup_gpio)

if __name__ == '__main__':
    # SSL sertifikatlaryňyz bar bolsa:
     app.run(host='0.0.0.0', port=8443, debug=True, ssl_context=('cert/cert.pem', 'cert/key.pem'))
    # Eger SSL ýok bolsa (ýerli test üçin):
    #app.run(host='0.0.0.0', port=5000, debug=True)
