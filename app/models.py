import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Role(str, enum.Enum):
    parent = "parent"
    child = "child"


class ImportStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    needs_review = "needs_review"
    failed = "failed"
    done = "done"


class AnswerType(str, enum.Enum):
    integer = "integer"
    fraction = "fraction"
    mcq = "mcq"
    text = "text"


class Label(str, enum.Enum):
    careless_self_corrected = "careless_self_corrected"
    careless = "careless"
    technique = "technique"
    unsure = "unsure"


class DiagnosisStatus(str, enum.Enum):
    none = "none"
    pending = "pending"
    done = "done"
    failed = "failed"


class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(64))
    role: Mapped[Role] = mapped_column(Enum(Role))
    password_hash: Mapped[str] = mapped_column(String(256))
    session_gen: Mapped[int | None] = mapped_column(Integer, nullable=True)  # bumped to sign out other devices
    profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # a child's fun "all about me" answers

    @property
    def avatar(self) -> str:
        return (self.profile or {}).get("avatar", "")


class SourcePdf(Base):
    __tablename__ = "source_pdf"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(256))
    path: Mapped[str] = mapped_column(String(512))
    contest: Mapped[str] = mapped_column(String(64))
    year: Mapped[int] = mapped_column(Integer)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[ImportStatus] = mapped_column(Enum(ImportStatus), default=ImportStatus.pending)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    structure: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    papers: Mapped[list["Paper"]] = relationship(back_populates="source_pdf")

    @property
    def label(self) -> str:
        years = sorted({s.get("year") for s in (self.structure or {}).get("sections", []) if s.get("year")})
        if len(years) > 1:
            return f"{self.contest} {years[0]}–{years[-1]}"
        return f"{self.contest} {self.year}" if self.year else f"{self.contest} (year unknown)"


class Paper(Base):
    __tablename__ = "paper"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_pdf_id: Mapped[int] = mapped_column(ForeignKey("source_pdf.id"))
    category: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(String(8), default="en")
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # only when the PDF holds several years
    source_pdf: Mapped[SourcePdf] = relationship(back_populates="papers")
    questions: Mapped[list["PaperQuestion"]] = relationship(
        back_populates="paper", order_by="PaperQuestion.number")

    @property
    def title(self) -> str:
        s = self.source_pdf
        year = self.year or s.year
        return f"{s.contest} {year} {self.category}" if year else f"{s.contest} {self.category}"

    @property
    def choice_key(self) -> str:
        """How this paper's section is named when choosing what to import."""
        return f"{self.category} · {self.year}" if self.year else self.category


class Problem(Base):
    __tablename__ = "problem"
    id: Mapped[int] = mapped_column(primary_key=True)
    transcription: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(String(128))
    answer_type: Mapped[AnswerType] = mapped_column(Enum(AnswerType), default=AnswerType.integer)
    reference_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)


class PaperQuestion(Base):
    __tablename__ = "paper_question"
    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper.id"))
    number: Mapped[int] = mapped_column(Integer)
    part: Mapped[str] = mapped_column(String(32), default="")
    points: Mapped[int] = mapped_column(Integer, default=1)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    crop_paths: Mapped[list] = mapped_column(JSON, default=list)
    crop_boxes: Mapped[list] = mapped_column(JSON, default=list)
    figure_paths: Mapped[list | None] = mapped_column(JSON(none_as_null=True), nullable=True)  # None = not extracted yet
    penalty: Mapped[int | None] = mapped_column(Integer, nullable=True)  # points lost for a wrong answer
    show_original: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # show the crop, not the text
    paper: Mapped[Paper] = relationship(back_populates="questions")
    problem: Mapped[Problem] = relationship()


class Attempt(Base):
    __tablename__ = "attempt"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper.id"))
    mode: Mapped[str] = mapped_column(String(16), default="practice")
    question_numbers: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    redo_of_id: Mapped[int | None] = mapped_column(ForeignKey("attempt.id"), nullable=True)
    paper: Mapped[Paper] = relationship()
    user: Mapped[User] = relationship()
    responses: Mapped[list["Response"]] = relationship(back_populates="attempt")


class Response(Base):
    __tablename__ = "response"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("attempt.id"))
    paper_question_id: Mapped[int] = mapped_column(ForeignKey("paper_question.id"))
    first_answer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retry_answer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    correct_first: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    correct_retry: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    diagnosis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diagnosis_status: Mapped[DiagnosisStatus] = mapped_column(
        Enum(DiagnosisStatus), default=DiagnosisStatus.none)
    label: Mapped[Label | None] = mapped_column(Enum(Label), nullable=True)
    parent_override: Mapped[Label | None] = mapped_column(Enum(Label), nullable=True)
    attempt: Mapped[Attempt] = relationship(back_populates="responses")
    paper_question: Mapped[PaperQuestion] = relationship()


class UploadToken(Base):
    __tablename__ = "upload_token"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_id: Mapped[int] = mapped_column(ForeignKey("response.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class FollowupResponse(Base):
    __tablename__ = "followup_response"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    problem_id: Mapped[int] = mapped_column(ForeignKey("problem.id"))
    from_response_id: Mapped[int] = mapped_column(ForeignKey("response.id"))
    answer: Mapped[str] = mapped_column(String(128))
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Technique(Base):
    __tablename__ = "technique"
    tag: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    kid_description: Mapped[str] = mapped_column(Text)


class WeeklyGoal(Base):
    """A child's problems-per-week target, in force from week_start until a later row."""
    __tablename__ = "weekly_goal"
    __table_args__ = (UniqueConstraint("user_id", "week_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    week_start: Mapped[date] = mapped_column(Date)
    target: Mapped[int] = mapped_column(Integer)
