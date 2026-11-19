from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import AnswerType
from app.techniques import TECHNIQUE_TAGS


class Part(BaseModel):
    name: str
    points: int
    first_question: int
    last_question: int
    wrong_points: int = 0  # points lost for a wrong answer (SASMO Section A: 1); blanks never lose points

    @field_validator("wrong_points")
    @classmethod
    def _non_negative(cls, v: int) -> int:
        return abs(v)


class Section(BaseModel):
    category: str
    language: Literal["en", "ms", "other"]
    first_page: int
    last_page: int
    parts: list[Part] = Field(default_factory=list)
    year: int | None = None  # set when one PDF holds several years' papers
    solutions_first_page: int | None = None  # worked solutions for this section, if the PDF has them
    solutions_last_page: int | None = None


class AnswerEntry(BaseModel):
    question: int
    answer: str


class AnswerKey(BaseModel):
    category: str
    page: int
    year: int | None = None
    answers: list[AnswerEntry]


class PdfStructure(BaseModel):
    sections: list[Section]
    answer_keys: list[AnswerKey]
    year: int | None = None  # the contest year printed on the paper, if any


class QuestionAnalysis(BaseModel):
    transcription: str
    answer_type: AnswerType
    tags: list[str] = Field(default_factory=list)
    picture_based: bool = False  # the question only makes sense as the original picture

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
