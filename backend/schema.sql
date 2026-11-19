CREATE TABLE IF NOT EXISTS games (
    id TEXT PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    pgn TEXT NOT NULL,
    metadata JSONB NOT NULL,
    end_time BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS games_date ON games(end_time DESC);
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
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
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
