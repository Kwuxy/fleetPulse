from sqlalchemy import select, delete

from app.models.delivery import Delivery
from app.models.orm.delivery import Delivery as DeliveryORM
from app.clients import db_client


async def save(delivery: Delivery) -> None:
    orm_delivery = _to_orm(delivery)
    async with db_client.get_session() as session:
        await session.merge(orm_delivery)


async def clear() -> None:
    async with db_client.get_session() as session:
        await session.execute(delete(DeliveryORM))


async def get_deliveries() -> list[Delivery]:
    async with db_client.get_session() as session:
        result = await session.execute(select(DeliveryORM))
        orm_deliveries = result.scalars().all()
        return [_from_orm(orm_delivery) for orm_delivery in orm_deliveries]


async def get_delivery_by_id(delivery_id: str) -> Delivery | None:
    async with db_client.get_session() as session:
        orm_delivery = await session.get(DeliveryORM, delivery_id)
        return _from_orm(orm_delivery) if orm_delivery else None


def _to_orm(delivery: Delivery) -> DeliveryORM:
    return DeliveryORM(
        id=delivery.id,
        client_id=delivery.client_id,
        pickup_location=delivery.pickup_location,
        dropoff_location=delivery.dropoff_location,
        cargo_weight_kg=delivery.cargo_weight_kg,
        requested_date=delivery.requested_date,
        status=delivery.status,
        assigned_truck_id=delivery.assigned_truck_id,
        denial_reason=delivery.denial_reason,
        denial_description=delivery.denial_description,
    )

def _from_orm(orm_delivery: DeliveryORM) -> Delivery:
    return Delivery(
        id=orm_delivery.id,
        client_id=orm_delivery.client_id,
        pickup_location=orm_delivery.pickup_location,
        dropoff_location=orm_delivery.dropoff_location,
        cargo_weight_kg=orm_delivery.cargo_weight_kg,
        requested_date=orm_delivery.requested_date,
        status=orm_delivery.status,
        assigned_truck_id=orm_delivery.assigned_truck_id,
        denial_reason=orm_delivery.denial_reason,
        denial_description=orm_delivery.denial_description,
    )