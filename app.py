# app.py
# -*- coding: utf-8 -*-
"""Driver saving Genie local offers
V6
"""

import os
from flask import Flask, request, jsonify
import firebase_admin
from firebase_admin import credentials, messaging
import requests
import logging
from flask_cors import CORS
from google.cloud import secretmanager
import json
import pathlib
import pandas as pd
import numpy as np
import snowflake.connector

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes or configure as needed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# Retrieve project ID from environment variable
PROJECT_ID = os.environ.get('GOOGLE_CLOUD_PROJECT')
FIREBASE_CREDENTIALS_JSON= os.environ.get('FIREBASE_CREDENTIALS_JSON')
GOOGLE_PLACES_API_KEY=os.environ.get('GOOGLE_PLACES_API_KEY')
GOOGLE_PLACES_NEW_API_KEY=os.environ.get('GOOGLE_PLACES_NEW_API_KEY')
GOOGLE_MY_BUSINESS_API_KEY=os.environ.get('GOOGLE_MY_BUSINESS_API_KEY')


print(PROJECT_ID)
print(FIREBASE_CREDENTIALS_JSON)
print("GOOGLE_PLACES_API_KEY  = ", GOOGLE_PLACES_API_KEY)
print("GOOGLE_PLACES_NEW_API_KEY  = ", GOOGLE_PLACES_NEW_API_KEY)
print("GOOGLE_MY_BUSINESS_API_KEY  = ", GOOGLE_MY_BUSINESS_API_KEY)

# Initialize Firebase Admin SDK
firebase_credentials = json.loads(FIREBASE_CREDENTIALS_JSON)
cred = credentials.Certificate(firebase_credentials)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)


def get_nearby_places_new_api(latitude, longitude, radius=2000):
    """
    Fetches nearby places using Google Places API New.
    :param latitude: Latitude of the location
    :param longitude: Longitude of the location
    :param radius: Search radius in meters
    :return: List of place dictionaries
    """
    url = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
    params = {
        'location': f'{latitude},{longitude}',
        'radius': radius,
        'type': 'cafe|restaurant|store',  # Adjust types as needed
        'key': GOOGLE_PLACES_NEW_API_KEY
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        logging.error(f"Google Places API error: {response.status_code}")
        return []

    results = response.json().get('results', [])
    print ("Nearby places = ", results)
    return results

from googleapiclient.discovery import build


def get_nearby_offers(latitude, longitude, radius=2000):
    """
    Fetches nearby places and their local offers using Google Places API New and Google My Business API.
    :param latitude: Latitude of the location
    :param longitude: Longitude of the location
    :param radius: Search radius in meters
    :return: List of dictionaries containing place information and offers
    """
    places = get_nearby_places_new_api(latitude, longitude, radius)
    print ("places inside get _nearby_offers = ", places)

    places_info = []
    for place in places:
        place_id = place['place_id']
        place_name = place['name']
        place_description = place.get('description', '')  # Get description if available
        place_address = place.get('formatted_address', '')  # Get formatted address if available

        places_info.append(f"Place: {place_name}\nDescription: {place_description}\nAddress: {place_address}\n")

    print( "places info =", places_info) 

    ##Get Offers
    offers = []

    for place in places[:20]:
        place_id = place['place_id']

        # Get Business Profile location ID
        service = build('mybusinessaccountmanagement', 'v1', developerKey=GOOGLE_MY_BUSINESS_API_KEY)
        accounts = service.accounts().list().execute()
        for account in accounts['accounts']:
            locations = service.accounts().locations().list(parent=account['name']).execute()
            for location in locations['locations']:
                if location['locationKey'] == place_id:
                    business_profile_id = location['name']
                    break

        # Retrieve local offers
        if business_profile_id:
            service = build('mybusinessaccountmanagement', 'v1', developerKey=GOOGLE_MY_BUSINESS_API_KEY)
            posts = service.accounts().locations().localPosts().list(parent=business_profile_id).execute()
            for post in posts['localPosts']:
                if post['topicType'] == 'OFFER':
                    offers.append({
                        'place_id': place_id,
                        'place_name': place['name'],
                        'offer': post['body'],
                        'offer_type': post['topicType']
                    })

    notification_message = "\n".join(places_info)
    if offers:
        notification_message += "\nOffers:\n"
        for offer in offers:
            notification_message += f"Offer at {offer['place_name']}: {offer['offer']}\n"

    print("notification_message with offers ", notification_message)
    return notification_message


def get_data_from_snowflake(query):
    # Get Snowflake connection parameters from environment variables
    SNOWFLAKE_USER = os.environ.get('SNOWFLAKE_USER')
    SNOWFLAKE_PASSWORD = os.environ.get('SNOWFLAKE_PASSWORD')
    SNOWFLAKE_ACCOUNT = os.environ.get('SNOWFLAKE_ACCOUNT')
    SNOWFLAKE_WAREHOUSE = os.environ.get('SNOWFLAKE_WAREHOUSE')
    SNOWFLAKE_DATABASE = os.environ.get('SNOWFLAKE_DATABASE')
    SNOWFLAKE_SCHEMA = os.environ.get('SNOWFLAKE_SCHEMA')
    SNOWFLAKE_ROLE = os.environ.get('SNOWFLAKE_ROLE')

    print (SNOWFLAKE_USER)
    print (SNOWFLAKE_PASSWORD)
    print (SNOWFLAKE_ACCOUNT)
    print (SNOWFLAKE_WAREHOUSE)
    print (SNOWFLAKE_DATABASE)
    print (SNOWFLAKE_SCHEMA)
    print (SNOWFLAKE_ROLE)

    logging.info(f"Connecting to Snowflake with user: {SNOWFLAKE_USER}, account: {SNOWFLAKE_ACCOUNT}")

    conn = snowflake.connector.connect(
    	  user=SNOWFLAKE_USER,
    	  password=SNOWFLAKE_PASSWORD,
    	  account=SNOWFLAKE_ACCOUNT,
    	  warehouse=SNOWFLAKE_WAREHOUSE,
    	  database= SNOWFLAKE_DATABASE,
    	  schema=SNOWFLAKE_SCHEMA,
    	  role=SNOWFLAKE_ROLE
    )
  
	
    data = pd.read_sql_query(query, conn)
    print("INFO:- Done Fetching Data from Snowflake...")
    return data

def get_cheaper_stations(station_id):
    cheaper_station_data = get_data_from_snowflake("""
	with test_pool as (
	SELECT 
     STATION_ID  
	, is_pricing_applied
	, CASE WHEN STATION_ID = 13881711 THEN 'TARGET' ELSE 'ALT' END AS record_type
	, CASE WHEN (SELECT NUM_PORTS_L2 FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 13881711) = 0 THEN 0 ELSE 10 END AS alt_L2_port_filter
	, CASE WHEN (SELECT NUM_PORTS_DC FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 13881711) = 0 THEN 0 ELSE 10 END AS alt_DC_port_filter
	, CASE WHEN record_type = 'ALT' THEN (SELECT LAT FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 13881711) ELSE LAT END AS a_lat
	, CASE WHEN record_type = 'ALT' THEN (SELECT LON FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 13881711)  ELSE LON END AS a_lon
	, case when alt_L2_port_filter = 10 then 'L2' when alt_DC_port_filter = 10 then 'DC' else 'other' end as port_type
	, case when port_type = 'L2' then (SELECT round(sum(TOTAL_ENERGY_DISPENSED) / count(*),2) FROM PROCESSED.NOS.CHARGING_SESSIONS WHERE PORT_LEVEL = 'L2' AND 
	SESSION_START_TIME_LOCAL > dateadd(DAY,-90,current_date) AND IS_HOME = 0 AND IS_MFHS_ENABLED = 0) when port_type = 'DC' then (SELECT 
	round(sum(TOTAL_ENERGY_DISPENSED) / count(*),2) 
	FROM PROCESSED.NOS.CHARGING_SESSIONS WHERE PORT_LEVEL = 'DC' AND SESSION_START_TIME_LOCAL > dateadd(DAY,-90,current_date) AND IS_HOME = 0 AND IS_MFHS_ENABLED 	= 0) else 0 end as kwh_multiplier
	, LAT AS b_lat
	, LON AS b_lon
	, station_name
	, round(CASE WHEN (a_lon = b_lon) AND (a_lat = b_lat) THEN 0 
	ELSE 3987 * ACOS(COS(RADIANS(a_lat)) * COS(RADIANS(b_lat)) * COS(RADIANS(b_lon) - RADIANS(a_lon)) + SIN(RADIANS(a_lat)) * SIN(RADIANS(b_lat))) END,2) as 	
	distance
	, case when  (SELECT round(sum(AMOUNT_CHARGED_TO_DRIVER) / sum(TOTAL_ENERGY_DISPENSED),2)  FROM PROCESSED.NOS.CHARGING_SESSIONS 
	WHERE TOTAL_ENERGY_DISPENSED > 0 AND AMOUNT_CHARGED_TO_DRIVER > 0 AND SESSION_START_TIME_LOCAL > dateadd(DAY,-90,current_date) AND 
	STATION_ID = a.STATION_ID) is null then '0' else (SELECT round(sum(AMOUNT_CHARGED_TO_DRIVER) / sum(TOTAL_ENERGY_DISPENSED),2)  
	FROM PROCESSED.NOS.CHARGING_SESSIONS WHERE TOTAL_ENERGY_DISPENSED > 0 AND AMOUNT_CHARGED_TO_DRIVER > 0 AND SESSION_START_TIME_LOCAL > 	
	dateadd(DAY,-90,current_date) 
	AND STATION_ID = a.STATION_ID) end AS Price_Per_KWH
	, round(Price_Per_KWH * kwh_multiplier,2) as est_session_fee
	FROM PROCESSED.NOS.CHARGING_STATIONS a
	where b_lat != 0
	AND b_lon != 0
	AND CONTAINS(b_lat, '0000') = FALSE 
	AND CONTAINS(b_lon, '0000') = FALSE
	AND LENGTH(b_lat) > 13
	AND LENGTH(b_lon) > 13
	AND NUM_PORTS_L2 <= alt_L2_port_filter
	AND NUM_PORTS_DC <= alt_DC_port_filter
	and is_obsolete = 0
	and PROVISION_STATUS = 'PROVISIONED'
	AND IS_HOME = 0
	AND IS_MFHS_ENABLED = 0
	AND USABLE_BY = 'All Drivers'
	AND VISIBLE_TO = 'All Drivers'
	AND TOTAL_NUM_PORTS > 0
	ORDER BY record_type DESC, distance ASC limit 21)
	select 
	distance
	, station_name 
	, (select est_session_fee from test_pool where record_type = 'TARGET') - est_session_fee as est_savings
	from test_pool 
	order by record_type desc, is_pricing_applied asc, est_savings desc, distance asc ;
	;""")

    return cheaper_station_data


@app.route('/')
def hello():
    return jsonify({"message": "Welcome to EV Charging"})

@app.route('/start_charging', methods=['POST'])
def start_charging():
    """
    Endpoint to handle when a user starts charging.
    Expects JSON data with:
    - device_token (str): FCM device token of the user.
    - station_id (str): ID of the charging station.
    - latitude (float): Latitude of the charging station.
    - longitude (float): Longitude of the charging station.
    """
    data = request.get_json()

    device_token = data.get('device_token')
    station_id = data.get('station_id')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    logging.info(f"Received data: device_token={device_token}, station_id={station_id}, latitude={latitude}, longitude={longitude}")

    if not all([device_token, station_id, latitude, longitude]):
        logging.error("Missing required parameters.")
        return jsonify({'error': 'Missing required parameters.'}), 400

    # Fetch nearby offers
    notification_message = get_nearby_offers(latitude, longitude)
    print("notification message in start_charging = ", notification_message)
    ##formatted_offers = format_offers(offers)
    ##print(formatted_offers)

    # Prepare notification content
    title = "Nearby attractions!"
    body = notification_message

    # Create the message
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body
        ),
        token=device_token,
    )

    try:
        # Send the notification
        response = messaging.send(message)
        logging.info(f"Successfully sent message: {response}")
        return jsonify({'message': 'Notification sent successfully.'}), 200
    except Exception as e:
        logging.error(f"Error sending notification: {e}")
        return jsonify({'error': 'Failed to send notification.'}), 500


##########################
#### GET CHEAPER STATIONS
##########################

@app.route('/cheaper_stations', methods=['POST'])
def cheaper_stations():
    """
    Endpoint to handle when a user starts charging.
    Expects JSON data with:
    - device_token (str): FCM device token of the user.
    - station_id (str): ID of the charging station.
    - latitude (float): Latitude of the charging station.
    - longitude (float): Longitude of the charging station.
    """
    try:
        data = request.get_json()

        device_token = data.get('device_token')
        station_id = data.get('station_id')
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        logging.info(f"Received data: device_token={device_token}, station_id={station_id}, latitude={latitude}, longitude={longitude}")

        if not all([device_token, station_id, latitude, longitude]):
            logging.error("Missing required parameters.")
            return jsonify({'error': 'Missing required parameters.'}), 400

        # Fetch cheaper stations
        cheaper_stations_df = get_cheaper_stations(station_id)
        data = cheaper_stations_df.to_dict(orient='records')
        print (data)
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error fetching cheaper stations: {e}")
        return jsonify({'error': 'Failed to fetch cheaper stations.'}), 500

    # Prepare notification content
    #title = "Nearby attractions!"
    #body = formatted_offers


if __name__ == '__main__':
    # Run the Flask app
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)




