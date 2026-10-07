import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from mock_fsp.schemas import Participant, Achievement

DATA = Path(__file__).parent / "data"
participants = [Participant.model_validate(item) for item in json.loads((DATA / "participants.json").read_text(encoding="utf-8"))]
achievements = [Achievement.model_validate(item) for item in json.loads((DATA / "achievements.json").read_text(encoding="utf-8"))]
app = FastAPI(title="Mini FSP ID", version="0.1.0", description="Локальный мок, не официальный API ФСП ID. Только вымышленные данные.")

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

@app.get("/participants", response_model=list[Participant], tags=["profiles"])
def list_participants():
    return participants

@app.get("/participants/{participant_id}", response_model=Participant, tags=["profiles"])
def get_participant(participant_id: str):
    for participant in participants:
        if participant.id == participant_id:
            return participant
    raise HTTPException(404, "Participant not found")

@app.get("/participants/{participant_id}/achievements", response_model=list[Achievement], tags=["achievements"])
def get_achievements(participant_id: str):
    get_participant(participant_id)
    return [item for item in achievements if item.participant_id == participant_id]
