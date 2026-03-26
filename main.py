from dotenv import load_dotenv
load_dotenv()

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from collector import poll_loop
from daily import daily_job
from routers import readings, chat

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(readings.router)
app.include_router(chat.router)


@app.on_event("startup")
async def startup():
    asyncio.create_task(poll_loop())
    scheduler = AsyncIOScheduler()
    scheduler.add_job(daily_job, "cron", hour=0, minute=5)
    scheduler.start()
