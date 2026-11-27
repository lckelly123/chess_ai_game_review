"""Combined coaching output contract and evidence-dependent validation."""

import re
from typing import Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .classification import positional_details

PieceType = Literal["pawn", "knight", "bishop", "rook", "queen", "king"]
MOVE_REFERENCE = re.compile(r"\[\[([a-h][1-8][a-h][1-8][qrbn]?)\]\]")
PV_REFERENCE = re.compile(r"\[\[([^\[\]]+)\]\]")


def no_move_references(value: str) -> str:
    if "[[" in value or "]]" in value:
        raise ValueError("The position overview cannot contain clickable references.")
    return value


def validate_pv_references(value: str) -> str:
    remainder = PV_REFERENCE.sub("", value)
    if "[[" in remainder or "]]" in remainder:
        raise ValueError("Malformed inline PV sequence.")
    for sequence in PV_REFERENCE.findall(value):
        notation = re.sub(r"0-0(?:-0)?", lambda match: match[0].replace("0", "O"), sequence.replace("…", "..."))
        notation = re.sub(r"\d+\.(?:\.\.)?", " ", notation).strip()
        notation = re.sub(r"^\.{3}", "", notation)
        moves = notation.split()
        if not moves or any(
            re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?", move)
            or not (chess.SAN_REGEX.fullmatch(move.rstrip("!?"))
                    or re.fullmatch(r"O-O(?:-O)?[+#]?[!?]*", move))
            for move in moves
        ):
            raise ValueError("Inline PV sequences must contain uninterrupted SAN moves, not UCI references.")
    return value


def plain_pv_text(value: str) -> str:
    return PV_REFERENCE.sub(lambda match: match[1].strip(), value)


class TacticalMistake(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["tactical_miss", "tactical_allowed"]
    subcategory: Literal["hanging_piece", "fork", "pin_skewer", "discovered_attack"]


class PositionalError(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["positional"]
    subcategory: Literal["Attack", "Defend", "Improve", "Convert"]


class LegacyPositionalMistake(BaseModel):
    """Version 2 records remain readable without fabricating piece metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["positional"]
    subcategory: PieceType


class PositionalMistake(PositionalError):
    """Backend-derived metadata, excluded from the LLM output schema."""

    best_move_piece: PieceType
    played_piece: PieceType
    same_piece: bool


class LegacyEnrichedPositionalMistake(LegacyPositionalMistake):
    """Preserve the piece metadata in older, piece-grouped reviews."""

    best_move_piece: PieceType
    played_piece: PieceType
    same_piece: bool


MistakeClassification = TacticalMistake | PositionalError


class MoveEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    explanation: str | None = Field(min_length=1)
    mistake_classification: MistakeClassification | None

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Move feedback must not be blank.")
        if value is not None:
            validate_pv_references(value)
        return value


class CandidateMove(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("Candidate reasoning must not be blank.")
        return validate_pv_references(value)


class TeachingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    position_overview: str = Field(min_length=1)
    position_explanation: str = Field(min_length=1)
    # Zero is valid in terminal positions or when no engine moves are approved.
    candidate_moves: list[CandidateMove] = Field(max_length=3)
    move_evaluation: MoveEvaluation

    @field_validator("position_overview", "position_explanation")
    @classmethod
    def nonblank_paragraph(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Teaching paragraphs must not be blank.")
        return value

    @field_validator("position_overview")
    @classmethod
    def overview_has_no_links(cls, value):
        return no_move_references(value) if value is not None else None

    def validate_references(self, *, played_move: str | None) -> "TeachingOutput":
        candidates = {item.uci for item in self.candidate_moves}
        references = set(MOVE_REFERENCE.findall(self.position_explanation))
        remainder = MOVE_REFERENCE.sub("", self.position_explanation)
        if "[[" in remainder or "]]" in remainder:
            raise ValueError("Malformed inline move reference.")
        allowed = candidates | ({played_move} if played_move else set())
        if not references <= allowed:
            raise ValueError("Inline move references must name a candidate or the original played move.")
        if not candidates <= references:
            raise ValueError("The position explanation must reference each selected candidate.")
        return self

    def validate_position(self, fen: str, *, permitted_moves: list[str] | None = None) -> "TeachingOutput":
        board = chess.Board(fen)
        if not self.candidate_moves and not board.is_game_over() and permitted_moves != []:
            raise ValueError("A position with legal moves requires at least one candidate.")
        if self.candidate_moves and board.is_game_over():
            raise ValueError("A terminal position must not recommend candidate moves.")
        seen = set()
        for candidate in self.candidate_moves:
            move = chess.Move.from_uci(candidate.uci)
            if move not in board.legal_moves:
                raise ValueError(f"Illegal candidate move: {candidate.uci}.")
            if candidate.uci in seen:
                raise ValueError("Candidate moves must be distinct.")
            if permitted_moves is not None and candidate.uci not in permitted_moves:
                raise ValueError("Candidate move is outside the supplied Stockfish pool.")
            seen.add(candidate.uci)
        if permitted_moves is not None and [candidate.uci for candidate in self.candidate_moves] != permitted_moves:
            raise ValueError("Candidates must match every supplied move in the supplied order.")
        return self

    def validate_move_evaluation(self, *, played_move: str | None, evidence: dict | None) -> "TeachingOutput":
        from .player_move_quality import ACCEPTABLE_STATUSES, ERROR_STATUSES

        evaluation = self.move_evaluation
        candidates = {candidate.uci for candidate in self.candidate_moves}
        quality = evidence.get("move_quality", {}).get("status") if evidence else None
        if evaluation.mistake_classification is not None and (played_move is None or quality not in ERROR_STATUSES):
            raise ValueError("Mistake classification requires a recorded move with a reliable error severity.")
        if played_move is not None and quality in ERROR_STATUSES and evaluation.mistake_classification is None:
            raise ValueError("A recorded error requires a mistake classification.")
        if played_move in candidates and quality in ACCEPTABLE_STATUSES and evaluation.explanation is not None:
            raise ValueError("An acceptable selected move must reuse its candidate explanation without correction.")
        if evaluation.explanation is None and not (
            played_move in candidates and quality in ACCEPTABLE_STATUSES
        ):
            raise ValueError("Only a best, excellent, or good supplied candidate may omit its explanation.")
        return self

    def as_analysis(self, fen: str, *, played_move: str | None, evidence: dict | None) -> "TeachingAnalysis":
        """Normalize the model verdict before it reaches storage or the UI."""
        data = self.model_dump()
        if isinstance(self.move_evaluation.mistake_classification, PositionalError):
            details = positional_details(fen, played_move, evidence)
            classification = PositionalMistake(**self.move_evaluation.mistake_classification.model_dump(), **details)
            data["move_evaluation"]["mistake_classification"] = classification.model_dump()
        return TeachingAnalysis.model_validate(data)

    def candidate_san(self, fen: str) -> dict[str, str]:
        board = chess.Board(fen)
        return {item.uci: board.san(chess.Move.from_uci(item.uci)) for item in self.candidate_moves}

    def as_markdown(self, fen: str) -> str:
        """Readable CLI/export fallback; the UI uses the structured fields."""
        names = self.candidate_san(fen)
        candidates = "\n".join(f"- **{names[item.uci]}**: {plain_pv_text(item.reason)}" for item in self.candidate_moves)
        board = chess.Board(fen)
        explanation = MOVE_REFERENCE.sub(lambda match: board.san(chess.Move.from_uci(match[1])), self.position_explanation)
        text = (
            "### 1. Understand the Position\n\n"
            + (f"**Position overview**\n\n{self.position_overview}\n\n" if self.position_overview else "")
            + f"**Position explanation**\n\n{explanation}\n\n"
            + "### 2. Move Exploration\n\n" + (candidates or "No approved candidate moves are available.")
        )
        if self.move_evaluation is not None:
            feedback = plain_pv_text(self.move_evaluation.explanation or "Your move follows the recommended idea.")
            text += f"\n\n### 3. Your Move\n\n{feedback}"
        return text


class SavedMoveEvaluation(MoveEvaluation):
    """Keep historical coaching readable without translating obsolete labels."""

    mistake_classification: TacticalMistake | PositionalMistake | PositionalError | LegacyEnrichedPositionalMistake | LegacyPositionalMistake | None = None

    @model_validator(mode="before")
    @classmethod
    def omit_retired_fields(cls, value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key not in ("plan_alignment", "better_candidate_uci")}
        return value

    @field_validator("mistake_classification", mode="before")
    @classmethod
    def omit_legacy_classification(cls, value):
        if isinstance(value, dict) and (
            value.get("category") == "tactical" or
            (value.get("category") == "positional" and value.get("subcategory") in
             (None, "pawn_structure", "piece_play", "defending", "attacking"))
        ):
            return None
        return value


class TeachingAnalysis(TeachingOutput):
    """Read saved teaching while omitting obsolete fields and labels."""

    position_character: Literal["quiet", "tense", "forcing"] | None = Field(default=None, exclude=True)
    # A legacy thesis can reveal the answer, so it is never used as a hint.
    position_overview: str | None = Field(default=None, min_length=1)
    move_evaluation: SavedMoveEvaluation | None = None

    @field_validator("candidate_moves", mode="before")
    @classmethod
    def omit_saved_highlights(cls, value):
        if isinstance(value, list):
            return [{key: item for key, item in candidate.items() if key != "highlight_squares"}
                    if isinstance(candidate, dict) else candidate for candidate in value]
        return value

    @model_validator(mode="before")
    @classmethod
    def omit_legacy_needs(cls, value):
        if isinstance(value, dict):
            result = {key: item for key, item in value.items() if key not in ("needs_of_position", "positional_thesis", "decision_context")}
            evaluation = result.get("move_evaluation")
            classification = evaluation.get("mistake_classification") if isinstance(evaluation, dict) else None
            if isinstance(classification, dict) and classification.get("category") in ("other", "positional"):
                context = value.get("decision_context")
                if context in ("Attack", "Defend", "Improve", "Convert"):
                    result["move_evaluation"] = {**evaluation, "mistake_classification": {
                        **classification, "category": "positional", "subcategory": context}}
                elif classification.get("category") == "other":
                    result["move_evaluation"] = {**evaluation, "mistake_classification": None}
            if "position_explanation" not in result and "positional_thesis" in value:
                result["position_explanation"] = value["positional_thesis"]
            return result
        return value
