"""Combined coaching output contract and evidence-dependent validation."""

from typing import Annotated, Literal

import chess
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .classification import positional_details

Square = Annotated[str, Field(pattern=r"^[a-h][1-8]$")]
Uci = Annotated[str, Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")]
PieceType = Literal["pawn", "knight", "bishop", "rook", "queen", "king"]


class TacticalMistake(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["tactical_miss", "tactical_allowed"]
    subcategory: Literal["hanging_piece", "fork", "pin_skewer", "discovered_attack"]


class OtherMistake(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Literal["other"]
    subcategory: None


class LegacyPositionalMistake(BaseModel):
    """Version 2 records remain readable without fabricating piece metadata."""

    model_config = ConfigDict(extra="forbid", strict=True)
    category: Literal["positional"]
    subcategory: PieceType


class PositionalMistake(LegacyPositionalMistake):
    """Backend-derived metadata, excluded from the LLM output schema."""

    best_move_piece: PieceType
    played_piece: PieceType
    same_piece: bool


MistakeClassification = TacticalMistake | OtherMistake


class MoveEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_alignment: Literal["aligned", "partially_aligned", "alternative_plan", "not_aligned", "unclear"]
    explanation: str | None = Field(min_length=1)
    better_candidate_uci: Uci | None
    mistake_classification: MistakeClassification | None

    @field_validator("explanation")
    @classmethod
    def nonblank_explanation(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Move feedback must not be blank.")
        return value


class CandidateMove(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    uci: str = Field(pattern=r"^[a-h][1-8][a-h][1-8][qrbn]?$")
    reason: str = Field(min_length=1)
    highlight_squares: list[Square] = Field(min_length=2, max_length=2)

    @field_validator("highlight_squares")
    @classmethod
    def distinct_squares(cls, squares):
        if squares[0] == squares[1]:
            raise ValueError("Highlight squares must be distinct.")
        return squares

    @field_validator("reason")
    @classmethod
    def nonblank_reason(cls, value):
        if not value.strip():
            raise ValueError("Candidate reasoning must not be blank.")
        return value


class TeachingOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    positional_thesis: str = Field(min_length=1)
    # Zero is valid only in terminal positions; that depends on the input FEN.
    candidate_moves: list[CandidateMove] = Field(max_length=3)
    move_evaluation: MoveEvaluation

    @field_validator("positional_thesis")
    @classmethod
    def nonblank_paragraph(cls, value):
        if not value.strip():
            raise ValueError("Teaching paragraphs must not be blank.")
        return value

    def validate_position(self, fen: str, *, permitted_moves: list[str] | None = None) -> "TeachingOutput":
        board = chess.Board(fen)
        if not self.candidate_moves and not board.is_game_over():
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
        return self

    def validate_move_evaluation(self, *, played_move: str | None, evidence: dict | None) -> "TeachingOutput":
        from .player_move_quality import ERROR_STATUSES, assess_player_move

        evaluation = self.move_evaluation
        candidates = {candidate.uci for candidate in self.candidate_moves}
        quality = evidence.get("move_quality", {}).get("status") if evidence else None
        if evaluation.mistake_classification is not None and (played_move is None or quality not in ERROR_STATUSES):
            raise ValueError("Mistake classification requires a recorded move with a reliable error severity.")
        if played_move is not None and quality in ERROR_STATUSES and evaluation.mistake_classification is None:
            raise ValueError("A recorded error requires a mistake classification.")
        if played_move in candidates and quality == "good" and (
            evaluation.plan_alignment != "aligned" or evaluation.explanation is not None
            or evaluation.better_candidate_uci is not None
        ):
            raise ValueError("An acceptable selected move must reuse its candidate explanation without correction.")
        if evaluation.explanation is None and not (
            played_move in candidates and quality == "good" and evaluation.plan_alignment == "aligned"
        ):
            raise ValueError("Only an aligned, acceptable recommended move may omit its explanation.")
        if played_move is None and (evaluation.plan_alignment != "unclear" or evaluation.better_candidate_uci is not None):
            raise ValueError("No played move is available to assess.")
        if evaluation.better_candidate_uci is not None:
            better = next((move for move in evidence.get("top_moves", [])
                           if move["uci"] == evaluation.better_candidate_uci), None) if evidence else None
            comparison = assess_player_move(better, evidence["played_move"]) if better else None
            if (evaluation.better_candidate_uci not in candidates or quality not in ERROR_STATUSES
                    or comparison is None or comparison["status"] not in ERROR_STATUSES):
                raise ValueError("A better candidate must be selected and demonstrably stronger than the played move.")
        return self

    def as_analysis(self, fen: str, *, played_move: str | None, evidence: dict | None) -> "TeachingAnalysis":
        """Normalize the model verdict before it reaches storage or the UI."""
        data = self.model_dump()
        if isinstance(self.move_evaluation.mistake_classification, OtherMistake):
            details = positional_details(fen, played_move, evidence)
            classification = PositionalMistake(category="positional", subcategory=details["best_move_piece"], **details)
            data["move_evaluation"]["mistake_classification"] = classification.model_dump()
        return TeachingAnalysis.model_validate(data)

    def candidate_san(self, fen: str) -> dict[str, str]:
        board = chess.Board(fen)
        return {item.uci: board.san(chess.Move.from_uci(item.uci)) for item in self.candidate_moves}

    def as_markdown(self, fen: str) -> str:
        """Readable CLI/export fallback; the UI uses the structured fields."""
        names = self.candidate_san(fen)
        candidates = "\n".join(f"- **{names[item.uci]}**: {item.reason}" for item in self.candidate_moves)
        text = (
            "### 1. Understand the Position\n\n"
            f"**Positional Thesis**\n\n{self.positional_thesis}\n\n"
            "### 2. Move Exploration\n\n" + (candidates or "No legal moves are available.")
        )
        if self.move_evaluation is not None:
            feedback = self.move_evaluation.explanation or "Your move follows the recommended idea."
            text += f"\n\n### 3. Your Move\n\n{feedback}"
        return text


class SavedMoveEvaluation(MoveEvaluation):
    """Keep historical coaching readable without translating obsolete labels."""

    mistake_classification: TacticalMistake | PositionalMistake | LegacyPositionalMistake | None = None

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
    move_evaluation: SavedMoveEvaluation | None = None

    @model_validator(mode="before")
    @classmethod
    def omit_legacy_needs(cls, value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "needs_of_position"}
        return value
