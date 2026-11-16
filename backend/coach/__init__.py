"""Position coaching service, CLI, and a separate FastAPI route adapter."""

from .position import CoachPosition, InvalidPositionError
from .service import Coach, CoachAnalysis, CoachResponseError, build_request, open_coach
from .settings import CoachConfigurationError, CoachSettings

__all__ = [
    "Coach", "CoachAnalysis", "CoachConfigurationError", "CoachPosition",
    "CoachResponseError", "CoachSettings", "InvalidPositionError",
    "build_request", "open_coach",
]
