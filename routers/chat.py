import json
import os
from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_engine, get_daily_stats_range, get_readings_range

router = APIRouter()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_daily_summaries",
            "description": "Get daily glucose summary statistics (TIR, average, SD, data availability) for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_glucose_readings",
            "description": "Get individual 15-minute glucose readings for a date range. Use for detailed analysis or spotting spikes/lows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
]

SYSTEM_PROMPT = """You are a helpful diabetes data assistant for a personal CGM (continuous glucose monitor) app. Use the available tools to answer questions about the user's glucose data.

Key facts:
- Glucose values are in mmol/L
- Time in Range (TIR): % of readings between 4–9 mmol/L (target ≥70%)
- Low: below 4 mmol/L, High: above 9 mmol/L, Very High: above 13.3 mmol/L
- SD measures variability (good: <1.5, moderate: 1.5–2.5, high: >2.5)
- Data availability: % of expected readings (96 per day, one every 15 min)

Be concise. Flag anything concerning. Always include mmol/L units.
Avoid LaTeX formatting unless the formula is genuinely complex. For simple expressions, write them as plain text (e.g. "HbA1c ≈ avg / 1.59"). If you do use math, use $$ ... $$ for block equations and $ ... $ for inline math. Never use \\[ \\] or \\( \\) LaTeX delimiters."""


class ChatRequest(BaseModel):
    message: str
    history: list = []


@router.post("/chat")
async def chat(body: ChatRequest):
    from openai import OpenAI

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    engine = get_engine()

    messages = [{"role": "system", "content": SYSTEM_PROMPT + f"\nToday is {date.today().isoformat()}."}]
    messages += body.history
    messages.append({"role": "user", "content": body.message})

    for _ in range(5):
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
        )
        choice = response.choices[0]
        messages.append(choice.message)

        if choice.finish_reason == "tool_calls":
            for tool_call in choice.message.tool_calls:
                args = json.loads(tool_call.function.arguments)
                start = date.fromisoformat(args["start_date"])
                end = date.fromisoformat(args["end_date"])

                with Session(engine) as session:
                    if tool_call.function.name == "get_daily_summaries":
                        rows = get_daily_stats_range(session, start, end)
                        result = [{"date": str(r.date), "tir": r.tir, "avg": r.avg, "sd": r.sd, "avail": r.avail} for r in rows]
                    elif tool_call.function.name == "get_glucose_readings":
                        rows = get_readings_range(session, start, end)
                        result = [{"timestamp": r.sensor_timestamp, "value": r.value, "trend": r.trend} for r in rows]
                    else:
                        result = []

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                })
        else:
            return {"reply": choice.message.content}

    return {"reply": "Sorry, I couldn't process that request."}
