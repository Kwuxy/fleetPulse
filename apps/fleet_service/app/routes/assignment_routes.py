from fastapi import APIRouter, HTTPException

from app.models.assignment import TruckAssignmentRequest, TruckAssignmentCompleted, TruckAssignmentFailureReason
from app.services import assignment_service
from app.exceptions import UnknownDelivery, InvalidCargoWeight, NoTruckAvailable

router = APIRouter(prefix='/internal/truck-assignments', tags=['truck-assignments'])

@router.post('')
async def assign_truck(request: TruckAssignmentRequest) -> TruckAssignmentCompleted:
    try:
        truck = assignment_service.assign_truck_to_delivery(request)
    except UnknownDelivery as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InvalidCargoWeight as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NoTruckAvailable as e:
        return TruckAssignmentCompleted(
            truck_id=None,
            assigned=False,
            reason=TruckAssignmentFailureReason.NO_AVAILABLE_TRUCK
        )

    return TruckAssignmentCompleted(truck_id=truck.id, assigned=True)