from fastapi import APIRouter, HTTPException
from httpx import TimeoutException

from app.exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate, NotFoundException
from app.models.delivery import Delivery, CreateDeliveryRequest
from app.services import delivery_service

router = APIRouter(prefix='/deliveries', tags=['deliveries'])

@router.post('', status_code=201)
async def create_delivery(request: CreateDeliveryRequest) -> Delivery:
    try:
        delivery = await delivery_service.create_delivery(request)
    except InvalidClient as e:
        raise HTTPException(status_code=400, detail=str(e))
    except SameLocationsException as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidCargo as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidRequestedDate as e:
        raise HTTPException(status_code=400, detail=str(e))
    except TimeoutException as e:
        raise HTTPException(status_code=503, detail=str(e))

    return delivery

@router.get('')
async def list_deliveries() -> list[Delivery]:
    return delivery_service.get_deliveries()

@router.get('/{delivery_id}')
async def get_delivery(delivery_id: str) -> Delivery:
    try:
        delivery = delivery_service.get_delivery_by_id(delivery_id)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))

    return delivery
