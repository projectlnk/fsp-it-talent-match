"""Existing grade codes shared by validation and candidate controls."""
from typing import Literal

GradeCode = Literal['intern', 'junior', 'middle', 'senior']
GRADE_LABELS = {
    'intern': 'Стажёр (Intern)',
    'junior': 'Младший специалист (Junior)',
    'middle': 'Специалист (Middle)',
    'senior': 'Старший специалист (Senior)',
}
