"""Strict report contract. No position or supporting-move IDs are required."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Foundation = Literal["pawn_structures", "piece_play", "tactics", "attacking", "defending", "converting_advantages", "endgames"]


class StrictOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DecisionPattern(StrictOutput):
    id: Text
    title: Text
    description: Text
    consequence: Text
    thinking_adjustment: Text
    confidence: Literal["high", "medium", "low"]


class FoundationPriority(StrictOutput):
    foundation: Foundation
    priority: int = Field(ge=1, le=3)
    reason: Text
    related_pattern_ids: list[Text] = Field(min_length=1, max_length=4)
    practice_focus: Text


class MultiGameReport(StrictOutput):
    profile_summary: Text
    decision_patterns: list[DecisionPattern] = Field(max_length=4)
    foundation_priorities: list[FoundationPriority] = Field(max_length=3)

    @model_validator(mode="after")
    def consistent_references(self):
        ids = [pattern.id for pattern in self.decision_patterns]
        if len(ids) != len(set(ids)):
            raise ValueError("Pattern IDs must be unique.")
        foundations = [item.foundation for item in self.foundation_priorities]
        if len(foundations) != len(set(foundations)):
            raise ValueError("Foundation priorities must be distinct.")
        for rank, item in enumerate(self.foundation_priorities, 1):
            if item.priority != rank or not set(item.related_pattern_ids) <= set(ids):
                raise ValueError("Foundation priorities must be ranked and reference existing patterns.")
        return self
