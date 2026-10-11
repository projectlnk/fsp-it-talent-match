from collections import Counter
from random import Random
from types import SimpleNamespace
from app.modules.assessments.models import QuestionType
from app.modules.assessments.service import structured_sample

def test_same_blueprint_different_items_and_no_repeats():
    pool=[SimpleNamespace(id=i,topic='API' if i<20 else 'SQL',type=QuestionType.SINGLE_CHOICE,difficulty=1) for i in range(40)]
    first=structured_sample(pool,10,Random(1));second=structured_sample(pool,10,Random(2))
    assert Counter(q.topic for q in first)==Counter(q.topic for q in second)=={'API':5,'SQL':5}
    assert len({q.id for q in first})==10
    assert {q.id for q in first}!={q.id for q in second}
