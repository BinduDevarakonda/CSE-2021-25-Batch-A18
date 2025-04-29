import serial
import time
import mcp3208_sensor
import spidev
import Adafruit_DHT
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
import RPi.GPIO as GPIO
import os
import requests  # For ThingSpeak

# ThingSpeak configuration
THINGSPEAK_API_KEY ="EE4Z29T4VIV5SAK1" # Replace with your ThingSpeak Write API Key
THINGSPEAK_URL = "https://api.thingspeak.com/update"

# Load data and train models
data = pd.read_excel("data.xlsx", engine="openpyxl")
feature_1 = data['x']
feature_2 = data['y']
label_1 = data['x_label']
label_2 = data['y_label']
X_train_1, X_test_1, y_train_1, y_test_1 = train_test_split(feature_1, label_1, test_size=0.2, random_state=42)
X_train_2, X_test_2, y_train_2, y_test_2 = train_test_split(feature_2, label_2, test_size=0.2, random_state=42)

model_1 = RandomForestClassifier(random_state=42)
model_1.fit(X_train_1.values.reshape(-1, 1), y_train_1)

model_2 = RandomForestClassifier(random_state=42)
model_2.fit(X_train_2.values.reshape(-1, 1), y_train_2)

DHT_SENSOR = Adafruit_DHT.DHT11
DHT_PIN = 4

port = "/dev/ttyS0"
ser = serial.Serial(port, baudrate=9600, timeout=0.5)
GPIO.setwarnings(False)

GPIO.setmode(GPIO.BCM)
BUZZER_PIN = 18
GPIO.setup(BUZZER_PIN, GPIO.OUT)

user_number = input("Enter your mobile number: ")

def send_sms(number, message):
    ser.write(b'AT\r')
    time.sleep(1)
    ser.write(b'AT+CMGF=1\r')
    time.sleep(1)
    ser.write(f'AT+CMGS="{number}"\r'.encode())
    time.sleep(1)
    ser.write(message.encode() + b'\x1A')
    time.sleep(3)
    print(f"Message sent to {number}: {message}")

def activate_buzzer():
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    time.sleep(3)
    GPIO.output(BUZZER_PIN, GPIO.LOW)

def upload_to_thingspeak(moisture, temperature, humidity):
    try:
        payload = {
            'api_key': THINGSPEAK_API_KEY,
            'field1': moisture,
            'field2': temperature,
            'field3': humidity
        }
        response = requests.get(THINGSPEAK_URL, params=payload, timeout=5)
        if response.status_code == 200:
            print("ThingSpeak update successful.")
        else:
            print(f"ThingSpeak update failed. Status code: {response.status_code}")
    except Exception as e:
        print(f"ThingSpeak error: {e}")

while True:
    try:
        adc_channel_1 = mcp3208_sensor.read_adc(1)
        humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)

        if humidity is not None and temperature is not None:
            dht_message = f"Temp: {temperature:.1f}C, Humidity: {humidity:.1f}%"
        else:
            dht_message = "DHT11 reading failed"

        message = f"Moisture: {adc_channel_1}, {dht_message}\n"
        print(message.strip())

        if ser:
            ser.write(message.encode())

        x_prediction = model_1.predict([[adc_channel_1]])[0]
        y_prediction = model_2.predict([[temperature]])[0]

        print(f"x_prediction: {x_prediction}")
        print(f"y_prediction: {y_prediction}")

        if humidity is not None and temperature is not None:
            speak_message = f"Moisture {adc_channel_1}. Temperature {temperature:.1f} degrees Celsius. Humidity {humidity:.1f} percent."
        else:
            speak_message = "Sensor reading failed."
        os.system(f'espeak "{speak_message}"')

        # Upload data to ThingSpeak
        if humidity is not None and temperature is not None:
            upload_to_thingspeak(adc_channel_1, temperature, humidity)

        if x_prediction == 0:
            # If moisture detected, send message with detailed information
            full_message = (f"Moisture detected!\n"
                            f"Moisture: {adc_channel_1}\n"
                            f"Temperature: {temperature:.1f}C\n"
                            f"Humidity: {humidity:.1f}%\n"
                            f"Termites are about to form, Take appropriate precautions")
            send_sms(user_number, full_message)
            activate_buzzer()

        time.sleep(15)  # ThingSpeak has a 15-second minimum update interval

    except KeyboardInterrupt:
        print("\nExiting...")
        if ser:
            ser.close()
        GPIO.cleanup()
        break
    except Exception as e:
        print(f"Error: {e}")
