import os
from datetime import timedelta

import httpx

from app.exceptions import OSRMRequestFailed, UnknownCity

OSRM_URL = os.environ.get('OSRM_URL', "https://router.project-osrm.org")

CITY_POS_BY_NAME = {
    'Paris': {'lat': 48.8566, 'lon': 2.3522},
    'Berlin': {'lat': 52.5200, 'lon': 13.4050},
    'Brussels': {'lat': 50.8503, 'lon': 4.3517},
    'Lyon': {'lat': 45.7640, 'lon': 4.8357},
    'Madrid': {'lat': 40.4168, 'lon': -3.7038},
    'Rome': {'lat': 41.9028, 'lon': 12.4964},
    'Nantes': {'lat': 47.2184, 'lon': -1.5536},
    'Toulouse': {'lat': 43.6047, 'lon': 1.4442},
    'Strasbourg': {'lat': 48.5734, 'lon': 7.7521},
    'Marseille': {'lat': 43.2965, 'lon': 5.3698},
    'Bordeaux': {'lat': 44.8378, 'lon': -0.5792},
}


def get_city_coordinates(city_name: str) -> dict:
    try:
        return CITY_POS_BY_NAME[city_name]
    except KeyError:
        raise UnknownCity(city_name)


async def get_route_duration(start_city: str, end_city: str) -> timedelta:
    async with httpx.AsyncClient() as client:
        start_city_pos = get_city_coordinates(start_city)
        end_city_pos = get_city_coordinates(end_city)
        response = await client.get(
            f'{OSRM_URL}/route/v1/driving/{start_city_pos["lon"]},{start_city_pos["lat"]};{end_city_pos["lon"]},{end_city_pos["lat"]}?overview=false')

        if response.status_code != 200:
            raise OSRMRequestFailed(f'OSRM request failed with status code {response.status_code}')

        json_response = response.json()
        if json_response['code'] != 'Ok':
            raise OSRMRequestFailed(f'OSRM request failed with code `{json_response["code"]}`')

        return timedelta(seconds=json_response['routes'][0]['duration'])
