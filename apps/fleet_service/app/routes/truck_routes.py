from fastapi import APIRouter, HTTPException

from app.exceptions import InvalidPlateNumber, InvalidTruckCapacity, DuplicatePlateNumber
from app.models.truck import Truck, CreateTruckRequest
from app.services import truck_service

router = APIRouter(prefix='/trucks', tags=['trucks'])

@router.post('', status_code=201)
async def create_truck(request: CreateTruckRequest):
    try:
        truck = await truck_service.create_truck(request)
    except InvalidPlateNumber as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidTruckCapacity as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DuplicatePlateNumber as e:
        raise HTTPException(status_code=409, detail=str(e))

    return truck

@router.get('')
async def get_trucks() -> list[Truck]:
    return await truck_service.get_trucks()