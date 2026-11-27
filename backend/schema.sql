-- Clean replacement of the retired JSON storage, once, in the startup transaction.
-- Only this application's named tables in the current schema are affected.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema=current_schema() AND table_name='games' AND column_name='id') THEN
        DROP TABLE IF EXISTS multi_game_analysis, game_engine_analysis, coach_feedback, profile_games,
                             http_cache, profiles, schema_migrations, games;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_game_id TEXT,
    source_url TEXT NOT NULL,
    white_username TEXT NOT NULL,
    white_rating INTEGER,
    black_username TEXT NOT NULL,
    black_rating INTEGER,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    rated BOOLEAN,
    variant TEXT NOT NULL CHECK (variant='standard'),
    result TEXT NOT NULL CHECK (result IN ('1-0','0-1','1/2-1/2')),
    termination TEXT NOT NULL,
    termination_raw TEXT,
    time_class TEXT NOT NULL,
    time_control_raw TEXT NOT NULL,
    initial_seconds DOUBLE PRECISION CHECK (initial_seconds>=0),
    increment_seconds DOUBLE PRECISION CHECK (increment_seconds>=0),
    time_control_status TEXT NOT NULL CHECK (time_control_status IN ('parsed','unsupported','missing')),
    opening_name TEXT,
    opening_family TEXT,
    eco_code TEXT,
    initial_fen TEXT NOT NULL,
    raw_pgn TEXT NOT NULL,
    raw_metadata JSONB NOT NULL,
    pgn_hash TEXT NOT NULL,
    ingestion_version INTEGER NOT NULL,
    white_accuracy DOUBLE PRECISION CHECK (white_accuracy BETWEEN 0 AND 100),
    black_accuracy DOUBLE PRECISION CHECK (black_accuracy BETWEEN 0 AND 100),
    -- Operational generation guard and derived-policy version, not source facts.
    analysis_revision BIGINT NOT NULL DEFAULT 0,
    statistics_version INTEGER,
    UNIQUE (source, source_game_id),
    UNIQUE (source, source_url)
);
CREATE INDEX IF NOT EXISTS games_date ON games(ended_at DESC);

CREATE TABLE IF NOT EXISTS game_moves (
    move_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    decision_ply INTEGER NOT NULL CHECK (decision_ply>=0),
    move_number INTEGER NOT NULL CHECK (move_number>=1),
    color TEXT NOT NULL CHECK (color IN ('white','black')),
    uci TEXT NOT NULL,
    san TEXT NOT NULL,
    fen_before TEXT NOT NULL,
    fen_after TEXT NOT NULL,
    clock_before_seconds DOUBLE PRECISION,
    clock_after_seconds DOUBLE PRECISION,
    time_spent_seconds DOUBLE PRECISION CHECK (time_spent_seconds>=0),
    timing_source TEXT NOT NULL CHECK (timing_source IN ('pgn_elapsed','clock_calculation','unavailable')),
    timing_status TEXT NOT NULL CHECK (timing_status IN ('valid','missing','unsupported','inconsistent')),
    piece_moved TEXT NOT NULL,
    is_capture BOOLEAN NOT NULL,
    captured_piece TEXT,
    gives_check BOOLEAN NOT NULL,
    is_castling BOOLEAN NOT NULL,
    promotion_piece TEXT,
    legal_moves_before INTEGER NOT NULL CHECK (legal_moves_before>0),
    piece_counts_before JSONB NOT NULL,
    material_balance_before INTEGER NOT NULL,
    phase_before TEXT NOT NULL CHECK (phase_before IN ('opening','middlegame','endgame')),
    engine_status TEXT NOT NULL DEFAULT 'not_run' CHECK (engine_status IN ('not_run','running','completed','failed')),
    engine_analyzed_at TIMESTAMPTZ,
    engine_name TEXT,
    engine_pgn_hash TEXT,
    engine_evidence_version INTEGER,
    engine_search_metadata JSONB,
    engine_error TEXT,
    played_cp INTEGER,
    played_mate INTEGER,
    played_depth INTEGER,
    played_bound TEXT CHECK (played_bound IN ('exact','lower','upper')),
    played_pv_uci JSONB,
    played_evaluation_source TEXT CHECK (played_evaluation_source IN ('candidate_reuse','separate_search','comparison')),
    engine_comparison_evidence JSONB,
    engine_final_position JSONB,
    sharpness_score DOUBLE PRECISION CHECK (sharpness_score BETWEEN 0 AND 100),
    sharpness_classification TEXT CHECK (sharpness_classification IN ('Forgiving','Flexible','Selective','Demanding','Critical')),
    move_quality TEXT CHECK (move_quality IN ('Best','Excellent','Good','Inaccuracy','Mistake','Blunder','Uncertain')),
    coach_position_overview TEXT,
    coach_position_explanation TEXT,
    coach_candidate_moves JSONB,
    coach_move_explanation TEXT,
    coach_error_category TEXT CHECK (coach_error_category IN ('tactical_miss','tactical_allowed','positional')),
    coach_error_subcategory TEXT CHECK (coach_error_subcategory IN ('hanging_piece','fork','pin_skewer','discovered_attack','Attack','Defend','Improve','Convert')),
    coach_output_raw TEXT,
    coach_metadata JSONB,
    top_1_uci TEXT,
    top_1_cp INTEGER,
    top_1_mate INTEGER,
    top_1_depth INTEGER,
    top_1_bound TEXT CHECK (top_1_bound IN ('exact','lower','upper')),
    top_1_pv_uci JSONB,
    top_2_uci TEXT,
    top_2_cp INTEGER,
    top_2_mate INTEGER,
    top_2_depth INTEGER,
    top_2_bound TEXT CHECK (top_2_bound IN ('exact','lower','upper')),
    top_2_pv_uci JSONB,
    top_3_uci TEXT,
    top_3_cp INTEGER,
    top_3_mate INTEGER,
    top_3_depth INTEGER,
    top_3_bound TEXT CHECK (top_3_bound IN ('exact','lower','upper')),
    top_3_pv_uci JSONB,
    top_4_uci TEXT,
    top_4_cp INTEGER,
    top_4_mate INTEGER,
    top_4_depth INTEGER,
    top_4_bound TEXT CHECK (top_4_bound IN ('exact','lower','upper')),
    top_4_pv_uci JSONB,
    top_5_uci TEXT,
    top_5_cp INTEGER,
    top_5_mate INTEGER,
    top_5_depth INTEGER,
    top_5_bound TEXT CHECK (top_5_bound IN ('exact','lower','upper')),
    top_5_pv_uci JSONB,
    UNIQUE (game_id, decision_ply),
    CHECK (num_nonnulls(played_cp,played_mate)<=1),
    CHECK (engine_status<>'completed' OR num_nonnulls(played_cp,played_mate)=1),
    CHECK ((top_1_uci IS NULL AND num_nonnulls(top_1_cp,top_1_mate,top_1_depth,top_1_bound,top_1_pv_uci)=0)
        OR (top_1_uci IS NOT NULL AND num_nonnulls(top_1_cp,top_1_mate)=1)),
    CHECK ((top_2_uci IS NULL AND num_nonnulls(top_2_cp,top_2_mate,top_2_depth,top_2_bound,top_2_pv_uci)=0)
        OR (top_2_uci IS NOT NULL AND num_nonnulls(top_2_cp,top_2_mate)=1)),
    CHECK ((top_3_uci IS NULL AND num_nonnulls(top_3_cp,top_3_mate,top_3_depth,top_3_bound,top_3_pv_uci)=0)
        OR (top_3_uci IS NOT NULL AND num_nonnulls(top_3_cp,top_3_mate)=1)),
    CHECK ((top_4_uci IS NULL AND num_nonnulls(top_4_cp,top_4_mate,top_4_depth,top_4_bound,top_4_pv_uci)=0)
        OR (top_4_uci IS NOT NULL AND num_nonnulls(top_4_cp,top_4_mate)=1)),
    CHECK ((top_5_uci IS NULL AND num_nonnulls(top_5_cp,top_5_mate,top_5_depth,top_5_bound,top_5_pv_uci)=0)
        OR (top_5_uci IS NOT NULL AND num_nonnulls(top_5_cp,top_5_mate)=1))
);
CREATE INDEX IF NOT EXISTS game_moves_coaching ON game_moves(game_id, coach_error_category) WHERE coach_metadata IS NOT NULL;
CREATE TABLE IF NOT EXISTS review_attempts (
    review_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    move_id BIGINT NOT NULL REFERENCES game_moves(move_id) ON DELETE CASCADE,
    review_number INTEGER NOT NULL CHECK (review_number>0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    status TEXT NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress','completed','abandoned')),
    tried_moves JSONB NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(tried_moves)='array'),
    UNIQUE (move_id, review_number)
);
CREATE UNIQUE INDEX IF NOT EXISTS review_attempts_active ON review_attempts(move_id) WHERE status='in_progress';

-- Supporting storage: jobs contain progress, not duplicate move evidence.
CREATE TABLE IF NOT EXISTS analysis_jobs (
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    player_color TEXT NOT NULL CHECK (player_color IN ('white','black')),
    pgn_hash TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued','running','completed','failed','interrupted')),
    total INTEGER NOT NULL CHECK (total>=0),
    opponent_total INTEGER,
    coach_completed INTEGER NOT NULL DEFAULT 0,
    coach_version INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (game_id, player_color)
);
CREATE TABLE IF NOT EXISTS profiles (username TEXT PRIMARY KEY, last_synced BIGINT NOT NULL);
CREATE TABLE IF NOT EXISTS profile_games (
    username TEXT NOT NULL REFERENCES profiles(username) ON DELETE CASCADE,
    game_id TEXT NOT NULL REFERENCES games(game_id) ON DELETE CASCADE,
    PRIMARY KEY(username,game_id)
);
CREATE TABLE IF NOT EXISTS http_cache (
    url TEXT PRIMARY KEY, body TEXT NOT NULL, etag TEXT, modified TEXT, fetched DOUBLE PRECISION NOT NULL
);
-- Standalone FEN coaching / final-board commentary has no recorded move owner.
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
ALTER TABLE coach_feedback ADD COLUMN IF NOT EXISTS game_id TEXT REFERENCES games(game_id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS coach_feedback_game ON coach_feedback(game_id);
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
-- Move saved positional objectives into the classification itself. Keep raw
-- model responses, piece metadata, and reviews; never infer missing objectives.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM schema_migrations WHERE name = 'coach_positional_objectives_v1') THEN
        ALTER TABLE game_moves DROP CONSTRAINT game_moves_coach_error_category_check;
        ALTER TABLE game_moves DROP CONSTRAINT game_moves_coach_error_subcategory_check;
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema=current_schema() AND table_name='game_moves' AND column_name='coach_decision_context') THEN
            UPDATE game_moves SET coach_error_subcategory=coach_decision_context
            WHERE coach_error_category IN ('other','positional');
        END IF;
        UPDATE game_moves SET coach_error_category='positional' WHERE coach_error_category='other';
        UPDATE game_moves
        SET coach_metadata=jsonb_set(coach_metadata, '{normalized_classification}',
            CASE WHEN jsonb_typeof(coach_metadata -> 'normalized_classification')='object'
                THEN coach_metadata -> 'normalized_classification' ELSE '{}'::jsonb END ||
            jsonb_build_object('category', 'positional', 'subcategory', coach_error_subcategory))
        WHERE coach_error_category='positional' AND coach_metadata IS NOT NULL;

        -- Standalone saved reviews carry their structured fields as JSON.
        UPDATE coach_feedback
        SET position_analysis=jsonb_set(position_analysis, '{structured,move_evaluation,mistake_classification}',
            (position_analysis #> '{structured,move_evaluation,mistake_classification}') ||
            jsonb_build_object('category', 'positional', 'subcategory', position_analysis #>> '{structured,decision_context}'))
        WHERE position_analysis #>> '{structured,move_evaluation,mistake_classification,category}' IN ('other','positional')
          AND position_analysis #>> '{structured,decision_context}' IN ('Attack','Defend','Improve','Convert');
        UPDATE coach_feedback SET position_analysis=position_analysis #- '{structured,decision_context}'
        WHERE jsonb_typeof(position_analysis -> 'structured')='object';

        ALTER TABLE game_moves DROP COLUMN IF EXISTS coach_decision_context;
        ALTER TABLE game_moves ADD CONSTRAINT game_moves_coach_error_category_check
            CHECK (coach_error_category IN ('tactical_miss','tactical_allowed','positional'));
        ALTER TABLE game_moves ADD CONSTRAINT game_moves_coach_error_subcategory_check
            CHECK (coach_error_subcategory IN ('hanging_piece','fork','pin_skewer','discovered_attack','Attack','Defend','Improve','Convert'));
        ALTER TABLE game_moves ADD CONSTRAINT game_moves_coach_error_pair_check CHECK (
            (coach_error_category IS NULL AND coach_error_subcategory IS NULL)
            OR (coach_error_category IS NOT NULL AND coach_error_category IN ('tactical_miss','tactical_allowed') AND coach_error_subcategory IS NOT NULL
                AND coach_error_subcategory IN ('hanging_piece','fork','pin_skewer','discovered_attack'))
            OR (coach_error_category IS NOT NULL AND coach_error_category='positional' AND
                (coach_error_subcategory IS NULL OR coach_error_subcategory IN ('Attack','Defend','Improve','Convert')))
        );
        INSERT INTO schema_migrations(name) VALUES ('coach_positional_objectives_v1');
    END IF;
END
$$;
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

INSERT INTO schema_migrations(name) VALUES ('analytics_relational_v1') ON CONFLICT DO NOTHING;
