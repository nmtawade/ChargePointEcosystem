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
YELP_API_KEY = 'vRtpcL5mv9chRIGSCVINtXdYTL_ZVg-n6uMi7_ir5nWDIdwqVN-Df2cHXccJrYX9oCmc5qP0sy3a1ZM7BKKfi8OY25xMGDfkI19DuypUR4GNGX1r2ChUSzT7wPxSZ3Yx'

print(PROJECT_ID)
print(FIREBASE_CREDENTIALS_JSON)
print(GOOGLE_PLACES_API_KEY)


# Initialize Firebase Admin SDK
firebase_credentials = json.loads(FIREBASE_CREDENTIALS_JSON)
cred = credentials.Certificate(firebase_credentials)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)


def get_nearby_places(latitude, longitude, radius=1000):
    """
    Fetches nearby places using Google Places API.
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
        'key': GOOGLE_PLACES_API_KEY
    }

    response = requests.get(url, params=params)
    if response.status_code != 200:
        logging.error(f"Google Places API error: {response.status_code}")
        return []

    results = response.json().get('results', [])
    return results

def get_local_offers(latitude, longitude, place_name):
    """
    Fetches local offers for a given place using Yelp Fusion API
    :return: List of offers
    """
    url = 'https://api.yelp.com/v3/businesses/search'
    headers = {
        'Authorization': 'Bearer ' + YELP_API_KEY
    }
    params = { 
		'latitude': latitude, 
		'longitude': longitude, 
		'term': place_name, 
		'attributes': 'deals'
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        logging.error(f"Yelp Fusion API error: {response.status_code}")
        return []

    businesses = response.json().get('businesses', [])
    offers = []

    for business in businesses:
        name = business.get('name')
        deal = business.get('deals', [])
        if deal:
            offer_details = [d['title'] for d in deal]  # Get the title of the deals
            offers.append(f"{name} - Deals: {', '.join(offer_details)}")
        else:
            offers.append(f"{name} - No deals available")

    return offers

def get_nearby_offers_with_discounts(latitude, longitude, radius=1000):
    """
    Fetches nearby places and their offers/discounts.
    :param latitude: Latitude of the location
    :param longitude: Longitude of the location
    :param radius: Search radius in meters
    :return: List of place names and their offers
    """
    places = get_nearby_places(latitude, longitude, radius)
    offers_with_discounts = []

    for place in places[:10]:  # Limit to top 10 places
       
        place_name = place.get('name')
        place_offers = get_local_offers(latitude, longitude, place_name)
        if place_offers:
            offers_with_discounts.append(f"{place_name} - Offers: {', '.join(place_offers)}")
        else:
            offers_with_discounts.append(f"{place_name} - No offers available")

    return offers_with_discounts

def format_offers(offers):
    """
    Formats the list of offers into a single string.
    :param offers: List of offer strings
    :return: Formatted offer summary
    """
    if not offers:
        return "No offers available at this time."

    offer_summary = "\n".join(offers)
    return offer_summary

def get_data_from_snowflake(query):
    # Get Snowflake connection parameters from environment variables
    SNOWFLAKE_USER = os.getenv('SNOWFLAKE_USER')
    SNOWFLAKE_PASSWORD = os.getenv('SNOWFLAKE_PASSWORD')
    SNOWFLAKE_ACCOUNT = os.getenv('SNOWFLAKE_ACCOUNT')
    SNOWFLAKE_WAREHOUSE = os.getenv('SNOWFLAKE_WAREHOUSE')
    SNOWFLAKE_DATABASE = os.getenv('SNOWFLAKE_DATABASE')
    SNOWFLAKE_SCHEMA = os.getenv('SNOWFLAKE_SCHEMA')
    SNOWFLAKE_ROLE = os.getenv('SNOWFLAKE_ROLE')

    conn = snowflake.connector.connect(
    	  user=SNOWFLAKE_USER,
    	  password=SNOWFLAKE_PASSWORD,
    	  account=SNOWFLAKE_ACCOUNT,
    	  warehouse=SNOWFLAKE_WAREHOUSE,
    	  database='PROCESSED',
    	  schema=SNOWFLAKE_SCHEMA,
    	  role=SNOWFLAKE_ROLE
    )
    data = pd.read_sql_query(query, conn)
    print("INFO:- Done Fetching Data from Snowflake...")
    return data

def get_cheaper_stations(station_id):
    cheaper_station_data = get_data_from_snowflake("""
	with test_pool as (
	SELECT STATION_ID  
	, is_pricing_applied
	, CASE WHEN STATION_ID = 11546721 THEN 'TARGET' ELSE 'ALT' END AS record_type
	, CASE WHEN (SELECT NUM_PORTS_L2 FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 11546721) = 0 THEN 0 ELSE 10 END AS alt_L2_port_filter
	, CASE WHEN (SELECT NUM_PORTS_DC FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 11546721) = 0 THEN 0 ELSE 10 END AS alt_DC_port_filter
	, CASE WHEN record_type = 'ALT' THEN (SELECT LAT FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 11546721) ELSE LAT END AS a_lat
	, CASE WHEN record_type = 'ALT' THEN (SELECT LON FROM PROCESSED.NOS.CHARGING_STATIONS WHERE STATION_ID = 11546721)  ELSE LON END AS a_lon
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
	nd b_lon != 0
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
	select STATION_ID
	, DISTANCE
	, station_name 
	, PRICE_PER_KWH
	, (select est_session_fee from test_pool where record_type = 'TARGET') - est_session_fee as est_savings
	from test_pool 
	order by record_type desc, is_pricing_applied asc, est_savings desc, distance asc ;
	;"""

    return cheaper_station_data)


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
    offers = get_nearby_offers_with_discounts(latitude, longitude)
    formatted_offers = format_offers(offers)

    # Prepare notification content
    title = "Nearby attractions!"
    body = formatted_offers

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
        data = cheaper_stations_df.to.dict(orient='records')
        return jsonify(data)
    except Exception as e:
        logging.error(f"Error fetching cheaper stations: {e}")
        return jsonify({'error': 'Failed to fetch cheaper stations.'}), 500

    # Prepare notification content
    #title = "Nearby attractions!"
    #body = formatted_offers

    # Create the message
    #message = messaging.Message(
    #   notification=messaging.Notification(
    #      title=title,
    #       body=body
    #   ),
    #   token=device_token,
    #)

    #try:
    #    # Send the notification
    #   response = messaging.send(message)
    #    logging.info(f"Successfully sent message: {response}")
    #    return jsonify({'message': 'Notification sent successfully.'}), 200
    #except Exception as e:
    #    logging.error(f"Error sending notification: {e}")
    #    return jsonify({'error': 'Failed to send notification.'}), 500

if __name__ == '__main__':
    # Run the Flask app
    #app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)




