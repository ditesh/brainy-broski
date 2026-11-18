import re

from app.ai.schemas import QuestionAnalysis
from tests.fixtures.make_pdf import question_text

CROP_RE = re.compile(r"/(?P<cat>[^/]+)/q(?P<n>\d{3})-0\.png$")

# tag each synthetic question so follow-up tests have overlap: tag cycles through a few techniques
TAG_CYCLE = ["parity", "algebra", "areas", "casework"]


def analysis_responder(call):
    m = CROP_RE.search(str(call.images[0]))
    cat, n = m["cat"], int(m["n"])
    base_n = n + 5 if (cat == "Junior" and n <= 5) else n
    return QuestionAnalysis(transcription=question_text(cat, n), answer_type="integer",
                            tags=[TAG_CYCLE[base_n % len(TAG_CYCLE)]])
