from dotenv import load_dotenv
load_dotenv()

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from collector import poll_loop
from db import get_engine, init_db
from daily import daily_job
from mobile_libre import mobile_poll_loop
from routers import readings, chat, raw_input, mobile_live, mobile_alerts

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(readings.router)
app.include_router(chat.router)
app.include_router(raw_input.router)
app.include_router(mobile_live.router)
app.include_router(mobile_alerts.router)


@app.on_event("startup")
async def startup():
    init_db(get_engine())
    asyncio.create_task(poll_loop())
    asyncio.create_task(mobile_poll_loop())
    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_job, "cron", hour=3)
    scheduler.start()
