"""Small, explicit configuration for the initial coach integration."""

import math
import os
from dataclasses import dataclass
from typing import ClassVar, Literal, get_args

CoachModel = Literal["gpt-6-astra", "gpt-6.1-terra"]
DEFAULT_COACH_MODEL: CoachModel = "gpt-6-astra"


class CoachConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class CoachSettings:
    reasoning_effort: ClassVar[Literal["xhigh"]] = "xhigh"
    max_output_tokens: int = 32768
    timeout_seconds: float = 600.0
    model: CoachModel = DEFAULT_COACH_MODEL

    def __post_init__(self):
        if self.model not in get_args(CoachModel):
            raise CoachConfigurationError("Unsupported coach model. Choose gpt-6-astra or gpt-6.1-terra.")
        if not 1 <= self.max_output_tokens <= 128000:
            raise CoachConfigurationError("COACH_MAX_OUTPUT_TOKENS must be between 1 and 128000.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise CoachConfigurationError("COACH_TIMEOUT_SECONDS must be a positive finite number.")

    @classmethod
    def from_env(cls, *, model: CoachModel = DEFAULT_COACH_MODEL) -> "CoachSettings":
        try:
            return cls(
                model=model,
                max_output_tokens=int(os.getenv("COACH_MAX_OUTPUT_TOKENS", "32768")),
                timeout_seconds=float(os.getenv("COACH_TIMEOUT_SECONDS", "600")),
            )
        except ValueError as exc:
            raise CoachConfigurationError(f"Invalid coach configuration: {exc}") from exc


def require_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise CoachConfigurationError("Set OPENAI_API_KEY in the backend environment before requesting coaching.")
    return key
