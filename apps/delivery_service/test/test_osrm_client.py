import os
from datetime import timedelta

import pytest
import respx
from httpx import Response

from app.clients import osrm_client
from app.exceptions import UnknownCity, OSRMRequestFailed

OSRM_URL = os.environ.get('OSRM_URL', "https://router.project-osrm.org")

@pytest.mark.unit
class TestOSRMClient:
    class TestGetCityCoordinates:
        def test_get_city_coordinates_succeed_on_known_city(self):
            # - Arrange -
            city = 'Nantes'
            expected_coordinates = {'lat': 47.2184, 'lon': -1.5536}

            # - Act -
            coordinates = osrm_client.get_city_coordinates(city)

            # - Assert -
            assert coordinates == expected_coordinates

        def test_get_city_coordinates_fails_on_unknown_city(self):
            # - Arrange -
            city = 'Unknown City'

            # - Act -
            with pytest.raises(UnknownCity):
                osrm_client.get_city_coordinates(city)

            # - Assert -
            # Exception was raised - No assert needed


    class TestGetRouteDuration:
        @pytest.mark.asyncio
        @respx.mock
        async def test_get_route_duration_succeed_on_known_city(self):
            # - Arrange -
            def mock_osrm_call(_):
                return Response(200, json={"code": "Ok", "routes": [{"duration": expected_duration}]})

            expected_duration = 120
            origin_city = 'Nantes'
            destination_city = 'Paris'

            route = respx.get(url__startswith=f'{OSRM_URL}/route/v1/driving/') \
                .mock(side_effect=mock_osrm_call)

            # - Act -
            duration = await osrm_client.get_route_duration(origin_city, destination_city)

            # - Assert -
            assert duration == timedelta(seconds=expected_duration)
            assert route.call_count == 1

        @pytest.mark.asyncio
        @respx.mock
        async def test_get_route_duration_raise_exception_on_http_code_401(self):
            # - Arrange -
            origin_city = 'Nantes'
            destination_city = 'Paris'
            route = respx.get(url__startswith=f'{OSRM_URL}/route/v1/driving/') \
                .mock(return_value=Response(status_code=401))

            # - Act -
            with pytest.raises(OSRMRequestFailed):
                await osrm_client.get_route_duration(origin_city, destination_city)

            # - Assert -
            assert route.call_count == 1

        @pytest.mark.asyncio
        @respx.mock
        async def test_get_route_duration_raise_exception_on_non_ok_code(self):
            # - Arrange -
            origin_city = 'Nantes'
            destination_city = 'Paris'
            route = respx.get(url__startswith=f'{OSRM_URL}/route/v1/driving/') \
                .mock(return_value=Response(status_code=200, json={"code": "InvalidOptions", "routes": []}))

            # - Act -
            with pytest.raises(OSRMRequestFailed):
                await osrm_client.get_route_duration(origin_city, destination_city)

            # - Assert -
            assert route.call_count == 1
