import os
import json
import requests

from flask import Flask, request, jsonify
from flask_mqtt import Mqtt

API_KEY = 
RASP_API_KEY = 
RASP_URL =   

app = Flask(__name__)

app.config['MQTT_BROKER_URL'] = 'localhost' 
app.config['MQTT_BROKER_PORT'] = 1883 
app.config['MQTT_USERNAME'] = ''  # Set this item when you need to verify username and password
app.config['MQTT_PASSWORD'] = ''  # Set this item when you need to verify username and password
app.config['MQTT_KEEPALIVE'] = 5  # Set KeepAlive time in seconds
app.config['MQTT_TLS_ENABLED'] = False  # If your server supports TLS, set it True

mqtt_client = Mqtt(app)

connection_status = {
    0: "connection succeeded",
    1: "connection failed - incorrect protocol version",
    2: "connection failed - invalid client identifier",
    3: "connection failed - the broker is not available",
    4: "connection failed - wrong username or password",
    5: "connection failed - unauthorized",
    6: "undefined"
}

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
        request_data = subscribe_to_topics()
        print("Initializing sensors..")
        
        response = send_request("init_sensors", request_data)
        if response[1] == 200:
            return jsonify({"status": "success", "message": "Sensors initialized."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to handle sensor initialization."}), 500

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to handle sensor initialization."}), 500


@app.route('/open_water', methods=['POST'])
def open_water():
    
    try:
        request_data = request.json
        sensor_id = request_data.get('sensor_id')
        print(f"Send request for {sensor_id} to open water")

        response = send_request("open_water", request_data)
        if response[1] == 200:
            return jsonify({"status": "success", "message": "open_water request handled."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to handle open_water request."}), 500

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to handle open_water request."}), 500

@app.route('/close_water', methods=['POST'])
def close_water():
    
    try:
        request_data = request.json
        sensor_id = request_data.get('sensor_id')
        print(f"Send request for {sensor_id} to close water")

        response = send_request("close_water", request_data)
        if response[1] == 200:
            return jsonify({"status": "success", "message": "close_water request handled."}), 200
        else:
            return jsonify({"status": "error", "message": "Failed to handle close_water request."}), 500

    except Exception as e:
       return jsonify({"status": "error", "message": "Failed to handle close_water request."}), 500

def send_request(request, data):
    
    url = RASP_URL + request
    bearer = {"Bearer": f"{RASP_API_KEY}"}
    header = {'authorization': json.dumps(bearer)}
   
    try:
        response = requests.post(url, json=data, verify=False, headers=header)# , timeout=360)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        print(response)  # Handle the response response.content
        return response, 200

    except requests.exceptions.ConnectionError as e:

        error = f"Error connecting to the server: {e}"
        print(error)
        return jsonify({"status": "error", "message": error}), 400


    except requests.exceptions.HTTPError as e:

        error = f"HTTP error occurred: {e}"
        print(error)
        return jsonify({"status": "error", "message": error}), 400

    except requests.exceptions.RequestException as e:

        error = f"An error occurred: {e}"
        print(error)
        return jsonify({"status": "error", "message": error}), 400

def subscribe_to_topics():

    path = os.path.dirname(os.path.abspath(__file__)) + "/sensors.config"

    with open(path, 'r') as file:
        request_data = json.load(file)

    for sensor_data in request_data.get('sensors'):
        topic = "raspberry/" + sensor_data['name']
        mqtt_client.subscribe(topic)

    return request_data

if __name__ == '__main__':

    subscribe_to_topics()

    app.run(host="0.0.0.0", port=5000, debug=True)
