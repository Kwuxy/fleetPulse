from app.models.truck_departure import TruckDepartureScheduled
from app.models.journey import Journey
from app.repositories import journey_repository


async def create_journey(departure: TruckDepartureScheduled) -> None:
    journey = _build_journey_from_truck_departure(departure)

    await journey_repository.save_journey(journey)


def _build_journey_from_truck_departure(departure: TruckDepartureScheduled) -> Journey:
    return Journey(
        delivery_id=departure.delivery_id,
        truck_id=departure.truck_id,
        pickup_location=departure.pickup_location,
        dropoff_location=departure.dropoff_location,
        departure_time=departure.departure_time,
    )
