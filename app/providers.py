"""Model providers. The agent only knows `generate`."""
from dataclasses import dataclass, field
from typing import Any


class AgentError(Exception):
    """A run could not finish. `retryable` says whether trying again later could work."""

    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: Any = None


class GeminiProvider:
    def __init__(self, model: str):
        from google import genai

        self.client = genai.Client()        # reads GEMINI_API_KEY from environment
        self.model = model

    def _to_gemini(self, contents: list[dict]):
        from google.genai import types

        out: list = []
        for c in contents:
            if c["role"] == "user":
                out.append(types.Content(role="user", parts=[types.Part.from_text(text=c["text"])]))
            elif c["role"] == "model":
                if c.get("raw") is not None:
                    out.append(c["raw"])
                    continue
                parts = [types.Part.from_text(text=c["text"])] if c.get("text") else []
                parts += [types.Part.from_function_call(name=t["name"], args=t["args"])
                          for t in c.get("tool_calls", [])]
                out.append(types.Content(role="model", parts=parts))
            elif c["role"] == "tool":
                part = types.Part.from_function_response(name=c["name"], response=c["result"])
                if out and out[-1].role == "user" and all(p.function_response for p in out[-1].parts):
                    out[-1].parts.append(part)
                else:
                    out.append(types.Content(role="user", parts=[part]))
        return out

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=tools,
            temperature=0,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            resp = self.client.models.generate_content(
                model=self.model, contents=self._to_gemini(contents), config=config)
        except errors.APIError as e:
            if e.code == 429:
                raise AgentError("provider_rate_limited", "Model quota exhausted. Wait a minute.", True) from e
            if e.code and e.code >= 500:
                raise AgentError("provider_unavailable", "Model provider failed.", True) from e
            raise AgentError("provider_error", str(e), False) from e

        content = resp.candidates[0].content if resp.candidates else None
        parts = (content.parts or []) if content else []
        text = "".join(p.text for p in parts if p.text and not p.thought) or None
        calls = [ToolCall(fc.name, dict(fc.args or {})) for fc in (resp.function_calls or [])]
        usage = resp.usage_metadata
        return ModelTurn(text=text, tool_calls=calls,
                         tokens_in=(usage.prompt_token_count or 0) if usage else 0,
                         tokens_out=(usage.candidates_token_count or 0) if usage else 0,
                         raw=content)


class ScriptedProvider:
    """Replays a fixed list of turns in call order. No network, no quota. Used by the tests."""

    model = "mock"

    def __init__(self, script: list, loop: bool = False):
        self.original, self.script, self.loop = list(script), list(script), loop
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        self.calls.append([dict(c) for c in contents])
        if not self.script and self.loop:
            self.script = list(self.original)
        if not self.script:
            return ModelTurn(text="(mock) script exhausted")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class PositionalMock:
    """A scripted model that answers by position in the current turn.
    A fresh process that resumes a half-finished run gets the NEXT turn, not the first one.
    `slow` sleeps before each answer, so crash recovery can kill the worker mid-run.
    """

    model = "mock"

    def __init__(self, turns: list[ModelTurn], slow: float = 0.0):
        self.turns, self.slow = turns, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        if position >= len(self.turns):
            return ModelTurn(text="(mock) nothing more to do.")
        return self.turns[position]


class RoutedMock:
    """Several scripted conversations in one mock: picks a script by a phrase in the current request,
    then answers by position. Used by demo and tests.
    """

    model = "mock"

    def __init__(self, routes: dict[str, list[ModelTurn]], slow: float = 0.0):
        self.routes, self.slow = routes, slow
        self.calls: list[list[dict]] = []

    def generate(self, system: str, contents: list[dict], tools: list) -> ModelTurn:
        import time

        self.calls.append([dict(c) for c in contents])
        last_user = max(i for i, c in enumerate(contents) if c["role"] == "user")
        request = contents[last_user]["text"]
        position = sum(1 for c in contents[last_user:] if c["role"] == "model")
        if self.slow:
            time.sleep(self.slow)
        for phrase, turns in self.routes.items():
            if phrase.lower() in request.lower():
                return turns[position] if position < len(turns) else ModelTurn(text="(mock) done.")
        return ModelTurn(text="(mock) I have no script for that request.")


def _call(name, **args):
    return ModelTurn(text=None, tool_calls=[ToolCall(name, args)], tokens_in=100, tokens_out=10)


def demo_providers(slow: float = 0.0) -> dict:
    """Scripted deterministic models for the supervisor and specialists, covering the demo questions."""
    return {
        "supervisor": RoutedMock({
            "slot 2": [
                _call("ask_inventory", question="Check SEM equipment details and slot 2."),
                _call("ask_booking_desk", request="Check eligibility and book slot 2 for equipment 1 for the researcher."),
                ModelTurn(text="(mock) The SEM is operational in Central Lab 101, but the booking desk refused: your Safety Level is 1, but SEM requires Safety Level 3."),
            ],
            "Electron Microscope": [
                _call("ask_inventory", question="Find Scanning Electron Microscope (SEM) and list available slots for 2026-09-21."),
                _call("ask_booking_desk", request="Check eligibility and book slot 1 for equipment 1 (SEM) on 2026-09-21, then notify the researcher."),
                ModelTurn(text="(mock) Great! The Scanning Electron Microscope (SEM) was available in Central Lab 101. Slot 1 (09:00 - 12:00) has been confirmed and booked, and a notification text has been queued."),
            ],
            "SEM": [
                _call("ask_inventory", question="Find Scanning Electron Microscope (SEM) and list available slots for 2026-09-21."),
                _call("ask_booking_desk", request="Check eligibility and book slot 1 for equipment 1 (SEM) on 2026-09-21, then notify the researcher."),
                ModelTurn(text="(mock) Great! The Scanning Electron Microscope (SEM) was available in Central Lab 101. Slot 1 (09:00 - 12:00) has been confirmed and booked, and a notification text has been queued."),
            ],
            "Oscilloscope": [
                _call("ask_inventory", question="Check Digital Phosphor Oscilloscope 4GHz details and slots."),
                _call("ask_booking_desk", request="Check eligibility and book slot 4 for Oscilloscope (equipment 2) for the researcher."),
                ModelTurn(text="(mock) The Oscilloscope is operational in Circuits Lab 204, but your booking request could not proceed because your safety level is insufficient."),
            ],
        }, slow),

        "inventory": RoutedMock({
            "slot 2": [
                _call("get_equipment_details", equipment_id=1),
                ModelTurn(text="(mock) Equipment 1, SEM in Central Lab 101 requires Safety Level 3. Slot 2 is available on 2026-09-21.")
            ],
            "Electron Microscope": [
                _call("search_equipment", text="SEM"),
                ModelTurn(text=None, tool_calls=[ToolCall("get_available_slots", {"equipment_id": 1, "slot_date": "2026-09-21"})], tokens_in=120, tokens_out=20),
                ModelTurn(text="(mock) Equipment 1, Scanning Electron Microscope (SEM) in Central Lab 101 requires Safety Level 3. Available slots for 2026-09-21: Slot 1 (09:00 - 12:00) and Slot 2 (14:00 - 17:00).")
            ],
            "SEM": [
                _call("search_equipment", text="SEM"),
                ModelTurn(text=None, tool_calls=[ToolCall("get_available_slots", {"equipment_id": 1, "slot_date": "2026-09-21"})], tokens_in=120, tokens_out=20),
                ModelTurn(text="(mock) Equipment 1, Scanning Electron Microscope (SEM) in Central Lab 101 requires Safety Level 3. Available slots for 2026-09-21: Slot 1 (09:00 - 12:00) and Slot 2 (14:00 - 17:00).")
            ],
            "Oscilloscope": [
                _call("search_equipment", text="Oscilloscope"),
                ModelTurn(text="(mock) Equipment 2, Digital Phosphor Oscilloscope 4GHz in Circuits Lab 204 requires Safety Level 2. Slot 4 is open.")
            ],
            "details": [
                _call("get_equipment_details", equipment_id=1),
                ModelTurn(text="(mock) SEM requires Safety Level 3 and is operational in Room 101.")
            ]
        }, slow),

        "booking_desk": RoutedMock({
            "book slot 1": [
                _call("check_eligibility", equipment_id=1, slot_id=1),
                ModelTurn(text=None, tool_calls=[
                    ToolCall("book_slot", {"equipment_id": 1, "slot_id": 1}),
                    ToolCall("notify_researcher", {"message": "Booking confirmed for SEM Slot 1 (09:00 - 12:00) on 2026-09-21."})
                ], tokens_in=180, tokens_out=30),
                ModelTurn(text="(mock) Successfully booked SEM slot 1 for researcher and dispatched confirmation notification.")
            ],
            "slot 2": [
                _call("check_eligibility", equipment_id=1, slot_id=2),
                ModelTurn(text="(mock) Booking refused: Safety Level 1 insufficient. Scanning Electron Microscope (SEM) requires Safety Level 3.")
            ],
            "slot 4": [
                _call("check_eligibility", equipment_id=2, slot_id=4),
                ModelTurn(text="(mock) Booking refused: Safety Level 1 insufficient. Digital Phosphor Oscilloscope 4GHz requires Safety Level 2.")
            ]
        }, slow),
    }
