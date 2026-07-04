from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import engine, Base
import models
from routers import auth_router, clients_router
from trading_accounts_router import router as trading_accounts_router
from ib_router import router as ib_router
from transactions_router import router as transactions_router
from settings_router import router as settings_router
from users_router import router as users_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Broker CRM API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(clients_router.router)
app.include_router(trading_accounts_router)
app.include_router(ib_router)
app.include_router(transactions_router)
app.include_router(settings_router)
app.include_router(users_router)

@app.get("/")
def root():
    return {"message": "Broker CRM API is running!"}

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}
