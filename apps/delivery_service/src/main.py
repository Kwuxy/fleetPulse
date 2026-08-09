from fastapi import FastAPI
from routes import delivery_routes
app = FastAPI()

app.include_router(delivery_routes.router)
