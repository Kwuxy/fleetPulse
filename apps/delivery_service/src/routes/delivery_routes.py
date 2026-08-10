from fastapi import APIRouter, HTTPException
from httpx import TimeoutException

from exceptions import InvalidClient, SameLocationsException, InvalidCargo, InvalidRequestedDate
from models.delivery import Delivery, CreateDeliveryRequest
from services import delivery_service

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
