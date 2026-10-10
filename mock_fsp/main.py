import os
import hmac
from fastapi import FastAPI, HTTPException, Header, Depends
from mock_fsp.schemas import Participant, Achievement
from mock_fsp.storage import rows, save

app = FastAPI(title="Mini FSP ID", version="0.1.0", description="Локальный мок, не официальный API ФСП ID. Только вымышленные данные.")

@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}

@app.get("/participants", response_model=list[Participant], tags=["profiles"])
def list_participants():
    return rows('participants')

@app.get("/participants/{participant_id}", response_model=Participant, tags=["profiles"])
def get_participant(participant_id: str):
    for participant in [Participant.model_validate(p) for p in rows('participants')]:
        if participant.id == participant_id:
            return participant
    raise HTTPException(404, "Participant not found")

@app.get("/participants/{participant_id}/achievements", response_model=list[Achievement], tags=["achievements"])
def get_achievements(participant_id: str):
    get_participant(participant_id)
    return [item for item in rows('achievements') if item['participant_id'] == participant_id]

def operator(x_demo_key: str = Header('')):
    expected = os.getenv('DEMO_MOCK_KEY', '')
    if os.getenv('MOCK_DEMO_MODE') != 'true' or not expected or not hmac.compare_digest(expected, x_demo_key):
        raise HTTPException(403, 'Mock management disabled or unauthorized')

@app.put('/operator/participants', dependencies=[Depends(operator)], response_model=Participant)
def edit_participant(payload: Participant):
    save('participants', payload.model_dump(mode='json'))
    return payload

@app.put('/operator/achievements', dependencies=[Depends(operator)], response_model=Achievement)
def edit_achievement(payload: Achievement):
    get_participant(payload.participant_id)
    save('achievements', payload.model_dump(mode='json'))
    return payload

@app.delete('/operator/sets/{sid}', dependencies=[Depends(operator)])
def remove_set(sid: str):
    import re
    from mock_fsp.storage import database
    if not re.fullmatch(r'scenario-[0-9a-f]{12}', sid):
        raise HTTPException(422, 'Invalid demonstration set')
    with database() as db:
        for kind in ('participants','achievements'):
            for row in rows(kind):
                if row['id'].startswith(sid+'-'):
                    db.execute('DELETE FROM records WHERE kind=? AND id=?',(kind,row['id']))
    return {'reset':sid}
