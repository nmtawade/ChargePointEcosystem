# app.py
# -*- coding: utf-8 -*-
"""Driver saving Genie local offers.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1RTChNmAl8YkhkW3l0bCzQMYduCe-pW1T
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


import requests
import logging

YELP_API_KEY = 'YOUR_YELP_API_KEY'

def get_local_offers(latitude, longitude, radius=1000):
    """
    Fetches local offers for nearby places using Yelp Fusion API.
    :param latitude: Latitude of the location
    :param longitude: Longitude of the location
    :param radius: Search radius in meters
    :return: List of offers
    """
    url = 'https://api.yelp.com/v3/businesses/search'
    headers = {
        'Authorization': 'Bearer ' + YELP_API_KEY
    }
    params = {
        #'latitude': latitude,
        #'longitude': longitude,
        #'radius': radius,
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
    offers = get_local_offers(latitude, longitude)
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

if __name__ == '__main__':
    # Run the Flask app
    #app.run(host='0.0.0.0', port=int(os.getenv('PORT', 8080)), debug=True)
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=True)




