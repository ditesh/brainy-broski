from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class Call:
    schema: type
    system: str
    images: list[Path]
    text: str
    effort: str


@dataclass
class FakeAI:
    """Test double for AIClient: queued results (or exceptions) per schema, or a responder."""
    queues: dict[type, list[Any]] = field(default_factory=dict)
    responders: dict[type, Callable[[Call], Any]] = field(default_factory=dict)
    log: list[Call] = field(default_factory=list)

    def add(self, schema: type, *results: Any) -> "FakeAI":
        self.queues.setdefault(schema, []).extend(results)
        return self

    def respond(self, schema: type, fn: Callable[[Call], Any]) -> "FakeAI":
        self.responders[schema] = fn
        return self

    def structured(self, schema, system, images, text, effort):
        call = Call(schema, system, list(images), text, effort)
        self.log.append(call)
        q = self.queues.get(schema)
        if q:
            r = q.pop(0)
        elif schema in self.responders:
            r = self.responders[schema](call)
        else:
            raise AssertionError(f"FakeAI: no result queued for {schema.__name__}")
        if isinstance(r, BaseException):
            raise r
        return r

    def calls(self, schema: type) -> int:
        return sum(1 for c in self.log if c.schema is schema)

    @property
    def last_call(self) -> Call:
        return self.log[-1]
