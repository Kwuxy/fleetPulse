from models.delivery import Delivery


_deliveries: dict[str, Delivery] = {}

def save(delivery: Delivery) -> None:
    _deliveries[delivery.id] = delivery

def clear() -> None:
    _deliveries.clear()

def get_deliveries() -> list[Delivery]:
    return list(_deliveries.values())

def get_delivery_by_id(delivery_id: str) -> Delivery | None:
    return _deliveries.get(delivery_id)