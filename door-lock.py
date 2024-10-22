from flask import Flask, request, Response
import RPi.GPIO as GPIO
import time
import threading
from functools import wraps

app = Flask(__name__)

# Suppress GPIO warnings
GPIO.setwarnings(False)

# Global variables
is_locked = True
auto_close_timer = None

# Basic Authentication
def check_auth(username, password):
    print(username, password, flush=True)
    return username == 'admin' and password == 'secret'

def authenticate():
    return Response('Could not verify your access level for that URL.\n'
                    'You have to login with proper credentials', 401,
                    {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

# Setup GPIO
servo_pin = 14  
GPIO.setmode(GPIO.BCM)
GPIO.setup(servo_pin, GPIO.OUT)
pwm = GPIO.PWM(servo_pin, 50)  # 50 Hz (standard for servos)
pwm.start(0)

# Constants for MG996R servo
SERVO_FREQ = 50     # 50Hz PWM frequency
MIN_DUTY = 2.5      # Duty cycle for 0 degrees
MAX_DUTY = 12.5     # Duty cycle for 180 degrees
last_angle = 0      # Global variable to track last position

def set_angle(angle):
    """
    Set servo to specified angle with improved control for MG996R
    Args:
        angle: Desired angle (0-180 degrees)
    Returns:
        bool: True if successful, False if failed
    """
    global last_angle
    
    # Validate angle
    if not 0 <= angle <= 180:
        print(f"Warning: Invalid angle {angle}. Must be between 0-180.")
        return False

    try:
        # Calculate duty cycle for MG996R
        # Instead of angle/18 + 2, we use proper range for MG996R
        duty = MIN_DUTY + (angle / 180) * (MAX_DUTY - MIN_DUTY)
        
        # Calculate movement time based on angle change
        # MG996R moves at 0.17s per 60 degrees
        angle_change = abs(angle - last_angle)
        move_time = (angle_change / 60) * 0.17 + 0.1  # Add 0.1s buffer
        
        # Move servo
        GPIO.output(servo_pin, True)
        pwm.ChangeDutyCycle(duty)
        time.sleep(move_time)    # Dynamic wait time based on movement
        GPIO.output(servo_pin, False)
        pwm.ChangeDutyCycle(0)   # Prevent jitter
        
        last_angle = angle       # Update position tracking
        return True
        
    except Exception as e:
        print(f"Error moving servo: {e}")
        return False

def auto_close():
    global is_locked, auto_close_timer
    print("Auto-close timer expired. Locking the door.")
    set_angle(0)  # Lock position
    is_locked = True
    auto_close_timer = None

@app.route('/control', methods=['POST'])
@requires_auth
def control_lock():
    global is_locked, auto_close_timer
    action = request.json.get('action')
    print(request, flush=True)
    
    if action == 'toggle':
        if is_locked:
            set_angle(180)  # Unlock position
            is_locked = False
            if auto_close_timer:
                auto_close_timer.cancel()
            auto_close_timer = threading.Timer(120, auto_close)  # 2 minutes
            auto_close_timer.start()
            print("unlocked")
            return "Door unlocked"
        else:
            set_angle(0)  # Lock position
            is_locked = True
            if auto_close_timer:
                auto_close_timer.cancel()
                auto_close_timer = None
            print("locked")
            return "Door locked"
    else:
        return "Invalid action", 400

if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000)
    finally:
        if auto_close_timer:
            auto_close_timer.cancel()
        GPIO.cleanup()
        print("Server shutting down...")