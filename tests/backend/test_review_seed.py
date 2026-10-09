"""Every generated choice question must be answerable using its UI options."""
import json
import random
from pathlib import Path
from types import SimpleNamespace
from app.modules.assessments.instantiate import instantiate_question, is_correct
from app.modules.assessments.models import QuestionType

def test_all_seed_variations_have_selectable_correct_answers():
    for path in Path("app/modules/assessments/seed").glob("*.json"):
        for item in json.loads(path.read_text(encoding="utf-8"))["questions"]:
            question = SimpleNamespace(id=1, topic=item.get("topic"), difficulty=item["difficulty"],
                                       type=QuestionType(item["type"]), payload=item["payload"], correct_answer=item.get("correct_answer"))
            for seed in range(100):
                snapshot = instantiate_question(question, random.Random(seed))
                if snapshot["type"] == "single_choice":
                    assert snapshot["correct"] in snapshot["options"], (path.name, item["topic"], seed)
                    assert is_correct(snapshot, {"value": snapshot["correct"]})
