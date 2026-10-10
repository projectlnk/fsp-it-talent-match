"""Questions contribute equally regardless of difficulty."""
from types import SimpleNamespace
import pytest
from app.modules.assessments.service import _answer_ratio

@pytest.mark.parametrize('correct,total,percent', [(0,10,0),(1,10,10),(5,10,50),(9,10,90),(10,10,100),(3,4,75)])
def test_exact_percent(correct, total, percent):
    answers = [SimpleNamespace(is_correct=i < correct, question_snapshot={'difficulty': i % 5 + 1}) for i in range(total)]
    assert _answer_ratio(answers) * 100 == percent

def test_empty_and_unanswered():
    assert _answer_ratio([]) == 0
    assert _answer_ratio([SimpleNamespace(is_correct=None), SimpleNamespace(is_correct=True)]) == .5
