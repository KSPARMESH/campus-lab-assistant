import pytest

from app.lab_db import LabDb
from app.memory import RunStore


class FakeClock:
    def __init__(self, start: float = 1_790_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SimulatedCrash(BaseException):
    """Simulates an unhandled process termination."""


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def db(clock):
    d = LabDb(":memory:", clock=clock)
    d.migrate()
    return d


@pytest.fixture
def store(clock):
    s = RunStore(":memory:", clock)
    s.migrate()
    return s
