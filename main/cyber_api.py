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
