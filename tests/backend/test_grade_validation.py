import pytest
from pydantic import ValidationError
from app.modules.assessments.schemas import StartAttemptRequest
from app.modules.assessments.service import _get_grade, AssessmentError

@pytest.mark.parametrize('grade', ['intern', 'junior', 'middle', 'senior'])
def test_canonical_grade(grade):
    assert StartAttemptRequest(specialization='backend', grade=grade).grade == grade

@pytest.mark.parametrize('grade', ['lead', ' arbitrary ', '', 'Junior'])
def test_reject_arbitrary_grade(grade):
    with pytest.raises(ValidationError):
        StartAttemptRequest(specialization='backend', grade=grade)
    with pytest.raises(AssessmentError):
        _get_grade(None, grade)
