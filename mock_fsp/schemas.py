from pydantic import BaseModel

class Participant(BaseModel):
    id: str
    display_name: str
    email: str

class Achievement(BaseModel):
    id: str
    participant_id: str
    title: str
    year: int
