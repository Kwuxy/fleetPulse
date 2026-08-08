from fastapi import APIRouter, HTTPException

from services.fleet_service.app.exceptions import InvalidPlateNumber, InvalidTruckCapacity
from services.fleet_service.app.models.truck import Truck, CreateTruckRequest
from services.fleet_service.app.services import truck_service

router = APIRouter(prefix='/trucks', tags=['trucks'])

@router.post('')
async def create_truck(request: CreateTruckRequest):
    try:
        truck = truck_service.create_truck(request)
    except InvalidPlateNumber as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidTruckCapacity as e:
        raise HTTPException(status_code=400, detail=str(e))

    return truck

@router.get('/')
async def get_trucks() -> list[Truck]:
    return truck_service.get_trucks()