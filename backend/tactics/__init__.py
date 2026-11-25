"""Engine-line tactic classification, independent of the coach's labels."""

from .classification import classify_review, with_tactic_classification

__all__ = ["classify_review", "with_tactic_classification"]
