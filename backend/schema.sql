CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    pgn TEXT NOT NULL,
    metadata JSONB NOT NULL,
    end_time BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS games_date ON games(end_time DESC);
-- A reset advances the cache identity without changing the source game.
ALTER TABLE games ADD COLUMN IF NOT EXISTS analysis_revision BIGINT NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS profiles (
    username TEXT PRIMARY KEY,
    last_synced BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_games (
    username TEXT NOT NULL REFERENCES profiles(username),
    game_id TEXT NOT NULL REFERENCES games(id),
    PRIMARY KEY (username, game_id)
);
CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    etag TEXT,
    modified TEXT,
    fetched DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS coach_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    fen VARCHAR(256) NOT NULL,
    text TEXT NOT NULL CHECK (length(btrim(text)) > 0),
    model TEXT NOT NULL,
    response_id TEXT NOT NULL,
    usage JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS coach_feedback_position ON coach_feedback(fen, created_at DESC, id DESC);
-- Additive upgrade: existing answers remain position-only (empty played_move).
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS played_move VARCHAR(5) NOT NULL DEFAULT '';
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS position_analysis JSONB;
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS move_analysis JSONB;
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS stockfish JSONB;
CREATE INDEX IF NOT EXISTS coach_feedback_move ON coach_feedback(fen, played_move, created_at DESC, id DESC);
-- Previous-move history changes the instructional context, not the engine position.
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS context_key VARCHAR(64) NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS coach_feedback_context ON coach_feedback(fen, played_move, context_key, created_at DESC, id DESC);
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS game_id TEXT REFERENCES games(id);
CREATE INDEX IF NOT EXISTS coach_feedback_game ON coach_feedback(game_id);
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
-- Remove the retired teaching field once, preserving review history, raw text,
-- engine evidence, classifications, and all other structured fields.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE name = 'coach_remove_needs_of_position_v1') THEN
        UPDATE coach_feedback
        SET position_analysis = position_analysis #- '{structured,needs_of_position}'
        WHERE jsonb_typeof(position_analysis -> 'structured') = 'object'
          AND (position_analysis -> 'structured') ? 'needs_of_position';
        INSERT INTO schema_migrations (name) VALUES ('coach_remove_needs_of_position_v1');
    END IF;
END
$$;
-- Engine-only work is separate from paid coach feedback. Each key in moves is
-- the zero-based pre-move ply, so UI markers open the decision before the move.
CREATE TABLE IF NOT EXISTS game_engine_analysis (
    game_id TEXT NOT NULL REFERENCES games(id),
    player_color TEXT NOT NULL CHECK (player_color IN ('white', 'black')),
    pgn_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'interrupted')),
    total INTEGER NOT NULL CHECK (total >= 0),
    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed >= 0),
    counts JSONB NOT NULL DEFAULT '{}',
    moves JSONB NOT NULL DEFAULT '{}',
    error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (game_id, player_color)
);
-- Coaching is resumable separately from engine progress; feedback itself stays
-- in coach_feedback, keyed by the full pre-move FEN and played move.
ALTER TABLE game_engine_analysis ADD COLUMN IF NOT EXISTS coach_completed INTEGER NOT NULL DEFAULT 0 CHECK (coach_completed >= 0);

-- Keep engine results when refreshing reviews for a new coaching contract.
ALTER TABLE game_engine_analysis ADD COLUMN IF NOT EXISTS coach_version INTEGER NOT NULL DEFAULT 0;

-- Keep opponent engine evidence separate from the selected player's lesson counts.
-- NULL total identifies older runs that have not checked opponent coverage yet.
ALTER TABLE game_engine_analysis ADD COLUMN IF NOT EXISTS opponent_total INTEGER CHECK (opponent_total >= 0);
ALTER TABLE game_engine_analysis ADD COLUMN IF NOT EXISTS opponent_moves JSONB NOT NULL DEFAULT '{}';

-- Cross-game runs are append-only history, independent of position coaching.
CREATE TABLE IF NOT EXISTS multi_game_analysis (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'interrupted')),
    input_snapshot JSONB NOT NULL,
    report JSONB,
    model TEXT NOT NULL,
    reasoning_effort TEXT NOT NULL,
    response_id TEXT,
    usage JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS multi_game_analysis_history ON multi_game_analysis(username, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS multi_game_analysis_active ON multi_game_analysis(username)
    WHERE status IN ('queued', 'running');
