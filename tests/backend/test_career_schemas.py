import pytest
from pydantic import ValidationError
from app.modules.career.schemas import OpportunityInput, MeetingInput

BASE=dict(title='Разработчик',description='Задачи и условия работы',specialization='backend',grade='junior',salary_from=100000,salary_to=200000,work_format='remote',contact_method='Внутренний канал')

@pytest.mark.parametrize('update',[{'grade':'arbitrary'},{'salary_from':-1},{'salary_to':999999999999},{'salary_from':300000},{'contact_method':'   '}])
def test_invalid_opportunity_fields(update):
    with pytest.raises(ValidationError):OpportunityInput.model_validate({**BASE,**update})

def test_valid_and_empty_meeting_channel():
    assert OpportunityInput.model_validate(BASE).grade=='junior'
    with pytest.raises(ValidationError):MeetingInput(scheduled_at='2026-10-20T10:00:00',channel='   ')
