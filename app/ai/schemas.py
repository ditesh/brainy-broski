from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import AnswerType
from app.techniques import TECHNIQUE_TAGS


class Part(BaseModel):
    name: str
    points: int
    first_question: int
    last_question: int


class Section(BaseModel):
    category: str
    language: Literal["en", "ms", "other"]
    first_page: int
    last_page: int
    parts: list[Part] = Field(default_factory=list)


class AnswerEntry(BaseModel):
    question: int
    answer: str


class AnswerKey(BaseModel):
    category: str
    page: int
    answers: list[AnswerEntry]


class PdfStructure(BaseModel):
    sections: list[Section]
    answer_keys: list[AnswerKey]


class QuestionAnalysis(BaseModel):
    transcription: str
    answer_type: AnswerType
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, v: list[str]) -> list[str]:
        return [t for t in v if t in TECHNIQUE_TAGS][:3]


class Box(BaseModel):
    number: int
    x0: float
    y0: float
    x1: float
    y1: float


class PageBoxes(BaseModel):
    boxes: list[Box]


class ReferenceSolution(BaseModel):
    steps: list[str]
    final_answer: str


class Diagnosis(BaseModel):
    label: Literal["careless", "technique", "unsure"]
    wrong_step: str | None = None
    technique_tag: str | None = None
    hint: str
    explanation: str
