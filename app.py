import logging
import matplotlib
matplotlib.use('Agg')
import sqlite3
import requests
from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import io
import base64

app = Flask(__name__)

# Weather API configuration
API_KEY = 'c249fbaeaa284c88ac752036242109' 
BASE_URL = 'http://api.weatherapi.com/v1'


DATABASE = 'weather_data.db'

#logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Scheduler data fetching
scheduler = BackgroundScheduler()

#Creates tables
def create_tables():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS weather_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            location_name TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            temperature REAL,
            humidity REAL,
            wind_speed REAL,
            condition TEXT,
            UNIQUE(location_name, timestamp)
        )
    ''')
    conn.commit()
    conn.close()

#get current weather
def fetch_weather_data(location):
    logger.info(f"Fetching current weather data for {location}")
    params = {
        'key': API_KEY,
        'q': location
    }
    try:
        response = requests.get(f"{BASE_URL}/current.json", params=params)
        response.raise_for_status()
        weather_data = response.json()

        temperature = weather_data['current']['temp_c']
        humidity = weather_data['current']['humidity']
        wind_speed = weather_data['current']['wind_kph']
        condition = weather_data['current']['condition']['text']

        store_weather_data(location, temperature, humidity, wind_speed, condition)
        logger.info(f"Stored current weather data for {location}: Temp={temperature}°C, Humidity={humidity}%, Wind={wind_speed} kph")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch weather data: {e}")

#get historical weather 
def fetch_historical_weather_data(location, date):
    logger.info(f"Fetching historical weather data for {location} on {date}")
    params = {
        'key': API_KEY,
        'q': location,
        'dt': date
    }
    try:
        response = requests.get(f"{BASE_URL}/history.json", params=params)
        response.raise_for_status()
        weather_data = response.json()

        temperature = weather_data['forecast']['forecastday'][0]['day']['avgtemp_c']
        humidity = weather_data['forecast']['forecastday'][0]['day']['avghumidity']
        wind_speed = weather_data['forecast']['forecastday'][0]['day']['maxwind_kph']
        condition = weather_data['forecast']['forecastday'][0]['day']['condition']['text']

        store_weather_data(location, temperature, humidity, wind_speed, condition, date)
        logger.info(f"Stored historical weather data for {location} on {date}: Temp={temperature}°C, Humidity={humidity}%, Wind={wind_speed} kph")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch historical weather data: {e}")

# Store Data
def store_weather_data(location_name, temperature, humidity, wind_speed, condition, date=None):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    timestamp = date or datetime.now()  
    cursor.execute('''
        INSERT INTO weather_data (location_name, temperature, humidity, wind_speed, condition, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (location_name, temperature, humidity, wind_speed, condition, timestamp))
    conn.commit()
    conn.close()
    logger.info(f"Stored weather data for {location_name} at {timestamp}")

#scheduling data fetching every hour
scheduler.add_job(lambda: fetch_weather_data('Pune'), 'interval', hours=1)  #defalut location 
scheduler.start()

# Analyze weather data from the database
def analyze_data(date):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    query = '''
        SELECT AVG(temperature), AVG(humidity), AVG(wind_speed)
        FROM weather_data
        WHERE DATE(timestamp) = ?
    '''
    
    cursor.execute(query, (date,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        logger.info(f"Analysis result for {date}: Avg Temp={result[0]}°C, Avg Humidity={result[1]}%, Avg Wind Speed={result[2]} kph")
        return {
            "avg_temperature": result[0],
            "avg_humidity": result[1],
            "avg_wind_speed": result[2]
        }
    else:
        logger.warning(f"No data found for {date}.")
        return {
            "avg_temperature": None,
            "avg_humidity": None,
            "avg_wind_speed": None
        }

# Generate weather trend plots
def generate_plot(start_date=None, end_date=None):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    
    # get data for the given date range
    cursor.execute('''
        SELECT timestamp, temperature, humidity FROM weather_data
        WHERE DATE(timestamp) BETWEEN ? AND ?
    ''', (start_date, end_date))
    data = cursor.fetchall()
    conn.close()

    if not data:
        logger.warning("No data found for the specified date range.")
        return None

    timestamps, temperatures, humidities = zip(*data)

    # Create temperature trend plot
    plt.figure(figsize=(10, 5))
    plt.plot(timestamps, temperatures, marker='o', label='Temperature (°C)', color='orange')
    plt.title('Temperature Trend')
    plt.xlabel('Date')
    plt.ylabel('Temperature (°C)')
    plt.xticks(rotation=45)
    plt.grid()
    plt.legend()
    
   
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plot_url = base64.b64encode(img.getvalue()).decode('utf8')
    plt.close() 

    return f"data:image/png;base64,{plot_url}"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/fetch', methods=['POST'])
def fetch():
    location = request.form.get('location', 'Pune')  # Default to 'Pune'
    fetch_weather_data(location)
    return jsonify({"status": "Weather data fetched successfully"})

@app.route('/fetch_historical', methods=['POST'])
def fetch_historical():
    location = request.form.get('location', 'Pune')
    date = request.form.get('date')
    fetch_historical_weather_data(location, date)
    return jsonify({"status": "Historical weather data fetched successfully"})

@app.route('/analyze', methods=['GET'])
def analyze():
    date = request.args.get('date')
    data = analyze_data(date)
    return jsonify(data)

@app.route('/visualize', methods=['GET'])
def visualize():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    plot_url = generate_plot(start_date, end_date)
    return render_template('visualize.html', plot_url=plot_url)

if __name__ == '__main__':
    create_tables()
    app.run(debug=True)
