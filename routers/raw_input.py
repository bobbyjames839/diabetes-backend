import os
import re
import tempfile
from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import delete_raw_input, get_engine, get_raw_inputs, save_raw_input

router = APIRouter()

NO_SPEECH_PHRASES = {
    "thank you for watching",
    "thanks for watching",
}


def _normalize_transcript(value: str) -> str:
    lowered = value.lower()
    alnum_space = re.sub(r"[^a-z0-9\s]", "", lowered)
    return re.sub(r"\s+", " ", alnum_space).strip()


class TextInput(BaseModel):
    content: str


class RawInputResponse(BaseModel):
    id: int
    content: str
    source: str
    created_at: datetime | None


@router.get("/raw-input", response_model=list[RawInputResponse])
def list_raw_inputs(limit: int = 200):
    engine = get_engine()
    with Session(engine) as session:
        entries = get_raw_inputs(session, limit=limit)

    return [
        RawInputResponse(
            id=entry.id,
            content=entry.content,
            source=entry.source or "text",
            created_at=entry.created_at,
        )
        for entry in entries
    ]


@router.post("/raw-input/text")
def submit_text(body: TextInput):
    engine = get_engine()
    with Session(engine) as session:
        entry = save_raw_input(session, body.content, "text")
    return {"ok": True, "id": entry.id}


@router.post("/raw-input/voice")
async def submit_voice(audio: UploadFile = File(...)):
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    audio_bytes = await audio.read()
    filename = audio.filename or "recording.webm"
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                temperature=0,
                prompt="Transcribe spoken words only. If no speech is present, return an empty string.",
            )
        transcript = transcription.text.strip()
    finally:
        os.unlink(tmp_path)

    normalized_transcript = _normalize_transcript(transcript)
    if not normalized_transcript or normalized_transcript in NO_SPEECH_PHRASES:
        raise HTTPException(status_code=400, detail="No speech detected.")

    engine = get_engine()
    with Session(engine) as session:
        entry = save_raw_input(session, transcript, "voice")

    return {"ok": True, "id": entry.id, "transcript": transcript}


@router.delete("/raw-input/{entry_id}")
def remove_raw_input(entry_id: int):
    engine = get_engine()
    with Session(engine) as session:
        deleted = delete_raw_input(session, entry_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Message not found.")

    return {"ok": True}
