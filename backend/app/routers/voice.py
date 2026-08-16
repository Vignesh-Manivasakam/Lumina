"""Voice transcription and synthesis endpoints."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from app.services.voice_service import VoiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["Voice"])
voice_service = VoiceService()


class SynthesizeRequest(BaseModel):
    text: str
    voice: Optional[str] = "en-US"


@router.post("/transcribe")
async def transcribe_audio(
    file: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    format: Optional[str] = Form(None),
):
    """Transcribe an uploaded audio file using NVIDIA Whisper-large-v3."""
    upload = file or audio
    if not upload:
        raise HTTPException(status_code=400, detail="No audio file provided (use 'audio' or 'file' form field).")

    try:
        audio_bytes = await upload.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file provided.")

        fmt = format
        if not fmt and upload.filename:
            ext = Path(upload.filename).suffix.lower().lstrip(".")
            if ext:
                fmt = ext
        fmt = fmt or "wav"

        text = voice_service.transcribe(audio_bytes, format=fmt)
        return {"text": text}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Audio transcription endpoint failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/synthesize")
async def synthesize_speech(request: SynthesizeRequest):
    """Synthesize text into speech audio bytes using NVIDIA Magpie TTS."""
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty.")

        audio_bytes = voice_service.synthesize(
            text=request.text,
            voice=request.voice or "en-US",
        )
        if not audio_bytes:
            # If API is unconfigured or failed, return empty audio with status 200 or 503
            return Response(content=b"", media_type="audio/wav")

        return Response(content=audio_bytes, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Audio synthesis endpoint failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
