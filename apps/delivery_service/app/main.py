from fastapi import FastAPI
from apps.delivery_service.app.routes import delivery_routes
app = FastAPI()

app.include_router(delivery_routes.router)
