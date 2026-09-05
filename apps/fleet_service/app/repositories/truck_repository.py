from sqlalchemy import select, delete

from app.models.truck import Truck
from app.models.orm.truck import Truck as TruckORM
from app.clients import db_client


async def save_truck(truck: Truck) -> None:
    orm_truck = _to_orm(truck)
    async with db_client.get_session() as session:
        await session.merge(orm_truck)


async def get_trucks() -> list[Truck]:
    async with db_client.get_session() as session:
        result = await session.execute(select(TruckORM))
        trucks = result.scalars().all()
        return [_from_orm(truck) for truck in trucks]


async def clear() -> None:
    async with db_client.get_session() as session:
        await session.execute(delete(TruckORM))


async def get_truck_by_plate_number(plate_number: str) -> Truck | None:
    async with db_client.get_session() as session:
        return await session.get(TruckORM, plate_number)


def _to_orm(truck: Truck) -> TruckORM:
    return TruckORM(
        id=truck.id,
        plate_number=truck.plate_number,
        capacity_kg=truck.capacity_kg,
        status=truck.status,
    )


def _from_orm(orm_truck: TruckORM) -> Truck:
    return Truck(
        id=orm_truck.id,
        plate_number=orm_truck.plate_number,
        capacity_kg=orm_truck.capacity_kg,
        status=orm_truck.status,
    )
