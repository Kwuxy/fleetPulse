from models.delivery import Delivery


_deliveries: dict[str, Delivery] = {}

def save(delivery: Delivery) -> None:
    _deliveries[delivery.id] = delivery

def clear() -> None:
    _deliveries.clear()
