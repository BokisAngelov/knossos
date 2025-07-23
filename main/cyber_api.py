import requests

API_URL = "https://knossostravel-webapi.cyberlogic.cloud/api"

def get_token():
    response = requests.post(API_URL + "/token", data={
        'grant_type': 'password',  
        'scope': 'read',
        'username': 'innov',
        'password': 'innov'
    })

    return response.json()["access_token"]

def get_groups():
    response = requests.get(API_URL + "/excursionPickupGroups" )
    return response.json()

def get_hotels():
    token = get_token()
    response = requests.get(API_URL + "/hotels", headers={'Authorization': 'Bearer ' + token})
    return response.json()

def get_pickup_points():
    response = requests.get(API_URL + "/excursionPickupPoints" )
    return response.json()

def get_bookings():
    token = get_token()
    booking_id = 49941 # need to update to get all bookings
    response = requests.get(API_URL + "/bookings/" + str(booking_id) + "/itinerary", headers={'Authorization': 'Bearer ' + token})

    return response.json()

def get_excursions():
    token = get_token()
    response = requests.get(API_URL + "/excursionsList", headers={'Authorization': 'Bearer ' + token})
    # print('response:', response.json(), type(response.json()))
    return response.json()

def get_excursion_description(excursion_id):
    token = get_token()

    response = requests.get(API_URL + "/excursion/" + str(excursion_id) + "/description/en", headers={'Authorization': 'Bearer ' + token})
    return response.json()

def get_providers():
    token = get_token()
    response = requests.get(API_URL + "/vendors", headers={'Authorization': 'Bearer ' + token})
    return response.json()

def get_excursion_availabilities(excursion_id):
    # token = get_token()
    data = {
        "DateFrom": "2025-01-01",
        "DateTo": "2025-12-30",
        "TariffId": 1,
        "ExcursionId": excursion_id, #3914
        "SellerId": 1980
    }
    response = requests.post(API_URL + "/excursion/datesPerLanguage", json=data)
    # print('response: ' + str(response.json()))
    return response.json()

def get_reservation(booking_id):
    token = get_token()
    # booking_id = 49941
    response = requests.get(API_URL + "/bookings/" + str(booking_id) + "/itinerary", headers={'Authorization': 'Bearer ' + token})

    return response.json()




