import os
import json
import time
import atexit
# import gpiozero

from threading import Thread, Timer
from datetime import datetime

from btlewrap.bluepy import BluepyBackend
from miflora.miflora_poller import MiFloraPoller, MI_BATTERY, MI_CONDUCTIVITY, MI_LIGHT, MI_MOISTURE, MI_TEMPERATURE

from apscheduler.schedulers.blocking import BlockingScheduler

from flask import Flask, request, jsonify
from flask_mqtt import Mqtt

# import RPi.GPIO as GPIO

HOST= 
CONFIG_PATH = path = os.path.dirname(os.path.abspath(__file__)) + "/sensors.config"
API_KEY = 

class SensorInfo:
  def __init__(self, name, mac_address, measurement_interval, lower_limit, watering_interval, relay_pin, poller, topic):
    self.name = name
    self.mac_address = mac_address
    self.measurement_interval = measurement_interval
    self.lower_limit = lower_limit
    self.watering_interval = watering_interval
    self.relay_pin = relay_pin
    self.poller = poller
    self.topic = topic

app = Flask(__name__)

app.config['MQTT_BROKER_URL'] = 
app.config['MQTT_BROKER_PORT'] = 1883
app.config['MQTT_USERNAME'] = ''  # Set this item when you need to verify username and password
app.config['MQTT_PASSWORD'] = ''  # Set this item when you need to verify username and password
app.config['MQTT_KEEPALIVE'] = 120  # Set KeepAlive time in seconds
app.config['MQTT_TLS_ENABLED'] = False  # If your server supports TLS, set it True

mqtt_client = Mqtt(app)

sensors_dict = {}
threads = []

connection_status = {
    0: "connection succeeded",
    1: "connection failed - incorrect protocol version",
    2: "connection failed - invalid client identifier",
    3: "connection failed - the broker is not available",
    4: "connection failed - wrong username or password",
    5: "connection failed - unauthorized",
    6: "undefined"
}
pin_status = {}

@mqtt_client.on_connect()
def handle_connect(client, userdata, flags, rc):
    if rc <= 6:
        print(connection_status[rc])
    else:
        print(connection_status[rc] + ": " + rc)

@mqtt_client.on_message()
def handle_mqtt_message(client, userdata, message):
    data = dict(
        topic=message.topic,
        payload=message.payload.decode()
    )
    print('Received message on topic: {topic} with payload: {payload}'.format(**data))

def publish_message(topic, message):
   
    print("Publishing message..")

    # QoS 2: ensure message is delivered exactly once
    publish_result = mqtt_client.publish(topic, payload=message, qos=2, retain=False)
    print(f"Publish message to topic {topic} with code: `{publish_result[0]}`")

def authenticate_api_key(api_key):
    return API_KEY == api_key["Bearer"]

@app.before_request
def before_request():
    api_key = request.headers.get("authorization")
    if not api_key or not authenticate_api_key(json.loads(api_key)):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

@app.route('/init_sensors', methods=['POST'])
def init_sensors():

    try:
        request_data = request.json

        if not os.path.isfile(path):
            file = open(path, "x")
       
        with open(path, 'w') as file:
            json.dump(request_data.get('sensors'), file)
        file.close()

        initialize_sensors_and_motors(request_data.get('sensors'))

        return jsonify({"status": "success", "message": "Sensors initialized."}), 200

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to initialize sensors."}), 500

def initialize_sensors_and_motors(data):

    print("Sensors initialization started..")

    # GPIO.cleanup()

    for sensor_data in data:
        name = sensor_data['name']
        mac_address = sensor_data['mac_address']
        measurement_interval = sensor_data['measurement_interval']
        lower_limit = sensor_data['lower_limit']  
        watering_interval = sensor_data['watering_interval']  
        relay_pin = int(sensor_data['relay_pin'])

        poller = MiFloraPoller(mac_address, BluepyBackend)
        topic = "raspberry/" + name

        # GPIO.setup(relay_pin, GPIO.OUT)
        # GPIO.output(relay_pin, GPIO.HIGH)
        pin_status[relay_pin] = "OFF"

        sensor = SensorInfo(name, mac_address, measurement_interval, lower_limit, watering_interval, relay_pin, poller, topic)
        sensors_dict[name] = sensor

        mqtt_client.subscribe(topic)

    print("Sensors initialization ended..")
            
    # Start scheduling thread
    schedule_sensor_monitoring()

# Set when scheduler should wake up to read data from sensors
def schedule_sensor_monitoring():

    print("Scheduling jobs..")

    for thread in threads:
        thread.terminate()
        thread.join()

    scheduler.remove_all_jobs()

    for sensor_name, sensor in sensors_dict.items():
        scheduler.add_job(read_sensor, 'interval', args=[sensor_name], minutes=sensor.measurement_interval)

    thread = Thread(target=scheduler.start())
    thread.start()
    threads.append(thread)
    
# Read data from specified sensor
def read_sensor(sensor_name):
    
    sensor_info = sensors_dict[sensor_name]
    poller = sensor_info.poller

    print(f"Reading data from {sensor_name}...")
    
    current_dt = str(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    battery_lever = poller.parameter_value(MI_BATTERY)
    light_intensity = poller.parameter_value(MI_LIGHT)
    temperature = poller.parameter_value(MI_TEMPERATURE)
    soil_moisture = poller.parameter_value(MI_MOISTURE)
    soil_fertility = poller.parameter_value(MI_CONDUCTIVITY)

    sensor_values = {
        "time_of_reading": current_dt,
        "battery_lever": battery_lever,
        "light_intensity": light_intensity,
        "temperature": temperature,
        "soil_moisture": soil_moisture,
        "soil_fertility": soil_fertility
    }

    publish_message(sensor_info.topic, json.dumps(sensor_values))
    check_moisture_level(sensor_name, soil_moisture)
    
def check_moisture_level(sensor_name, soil_moisture):

    print(f"Checking moisture levels for {sensor_name}..")

    sensor_info = sensors_dict[sensor_name]
    if (soil_moisture < sensor_info.lower_limit):
        open_water_pump(sensor_name, sensor_info.relay_pin) 

@app.route('/open_water', methods=['POST'])
def open_water():
    
    try:
        request_data = request.json
        sensor_name = request_data.get('sensor_id')
        sensor_info = sensors_dict[sensor_name]

        open_water_pump(sensor_name, sensor_info.relay_pin)

        return jsonify({"status": "success", "message": "Handled open_water request"}), 200

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to handle open_water request"}), 500

def open_water_pump(sensor_name, relay_pin):

    sensor_info = sensors_dict[sensor_name]
    print(f"Opening water for sensor {sensor_name} for {sensor_info.watering_interval} seconds...")
    
    if pin_status[relay_pin] == "OFF":
        # GPIO.output(relay_pin, GPIO.LOW) # Relay turns ON
        pin_status[relay_pin] = "ON"
   
        t = Timer(sensor_info.watering_interval, close_water_pump, args=[sensor_name, relay_pin])
        t.start()


@app.route('/close_water', methods=['POST'])
def close_water():
    
    try:
        request_data = request.json
        sensor_name = request_data.get('sensor_id')
        sensor_info = sensors_dict[sensor_name]

        close_water_pump(sensor_name, sensor_info.relay_pin)

        return jsonify({"status": "success", "message": "Handled close_water request"}), 200

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to handle close_water request"}), 500

def close_water_pump(sensor_name, relay_pin):

    print(f"Closing water for sensor {sensor_name}...")
    # GPIO.output(relay_pin, GPIO.HIGH) # Relay turns OFF
    pin_status[relay_pin] = "OFF"

if __name__ == '__main__':

    scheduler = BlockingScheduler()
    # GPIO.setmode(GPIO.BCM) 

    # atexit.register(lambda: GPIO.cleanup())
    atexit.register(lambda: scheduler.shutdown())

    if os.path.isfile(path):
        with open(path, 'r') as file:
            data = json.load(file)

        thread = Thread(target=initialize_sensors_and_motors, args=[data])
        thread.start()

    app.run(host="0.0.0.0", port=5500, debug=True)