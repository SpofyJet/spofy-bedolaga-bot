"""Remove contests and polls.

All dropped tables were empty on production when this was written. If any of them
holds rows at upgrade time, every table is left in place and a warning is logged:
data is never deleted by this migration.

Idempotent. Downgrade recreates the empty tables from the DDL below.

Revision ID: 0146
Revises: 0145
"""

import logging
import re

import sqlalchemy as sa
from alembic import op


revision = '0146'
down_revision = '0145'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

TABLES = (
    'poll_answers',
    'poll_responses',
    'poll_options',
    'poll_questions',
    'polls',
    'contest_attempts',
    'contest_rounds',
    'contest_templates',
    'referral_contest_virtual_participants',
    'referral_contest_events',
    'referral_contests',
)

_DDL = r"""
CREATE TABLE contest_attempts (
    id integer NOT NULL,
    round_id integer NOT NULL,
    user_id integer NOT NULL,
    answer text,
    is_winner boolean NOT NULL,
    created_at timestamp with time zone
);

CREATE SEQUENCE contest_attempts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE contest_attempts_id_seq OWNED BY contest_attempts.id;

CREATE TABLE contest_rounds (
    id integer NOT NULL,
    template_id integer NOT NULL,
    starts_at timestamp with time zone NOT NULL,
    ends_at timestamp with time zone NOT NULL,
    status character varying(20) NOT NULL,
    payload json,
    winners_count integer NOT NULL,
    max_winners integer NOT NULL,
    attempts_per_user integer NOT NULL,
    message_id bigint,
    chat_id bigint,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);

CREATE SEQUENCE contest_rounds_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE contest_rounds_id_seq OWNED BY contest_rounds.id;

CREATE TABLE contest_templates (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    slug character varying(50) NOT NULL,
    description text,
    prize_type character varying(20) NOT NULL,
    prize_value character varying(50) NOT NULL,
    max_winners integer NOT NULL,
    attempts_per_user integer NOT NULL,
    times_per_day integer NOT NULL,
    schedule_times character varying(255),
    cooldown_hours integer NOT NULL,
    payload json,
    is_enabled boolean NOT NULL,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);

CREATE SEQUENCE contest_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE contest_templates_id_seq OWNED BY contest_templates.id;

CREATE TABLE poll_answers (
    id integer NOT NULL,
    response_id integer NOT NULL,
    question_id integer NOT NULL,
    option_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE poll_answers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE poll_answers_id_seq OWNED BY poll_answers.id;

CREATE TABLE poll_options (
    id integer NOT NULL,
    question_id integer NOT NULL,
    text text NOT NULL,
    "order" integer NOT NULL
);

CREATE SEQUENCE poll_options_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE poll_options_id_seq OWNED BY poll_options.id;

CREATE TABLE poll_questions (
    id integer NOT NULL,
    poll_id integer NOT NULL,
    text text NOT NULL,
    "order" integer NOT NULL
);

CREATE SEQUENCE poll_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE poll_questions_id_seq OWNED BY poll_questions.id;

CREATE TABLE poll_responses (
    id integer NOT NULL,
    poll_id integer NOT NULL,
    user_id integer NOT NULL,
    sent_at timestamp with time zone NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    reward_given boolean NOT NULL,
    reward_amount_kopeks integer NOT NULL
);

CREATE SEQUENCE poll_responses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE poll_responses_id_seq OWNED BY poll_responses.id;

CREATE TABLE polls (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    reward_enabled boolean NOT NULL,
    reward_amount_kopeks integer NOT NULL,
    created_by integer,
    created_at timestamp with time zone NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE polls_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE polls_id_seq OWNED BY polls.id;

CREATE TABLE referral_contest_events (
    id integer NOT NULL,
    contest_id integer NOT NULL,
    referrer_id integer NOT NULL,
    referral_id integer NOT NULL,
    event_type character varying(50) NOT NULL,
    amount_kopeks integer NOT NULL,
    occurred_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE referral_contest_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE referral_contest_events_id_seq OWNED BY referral_contest_events.id;

CREATE TABLE referral_contest_virtual_participants (
    id integer NOT NULL,
    contest_id integer NOT NULL,
    display_name character varying(255) NOT NULL,
    referral_count integer NOT NULL,
    total_amount_kopeks integer CONSTRAINT referral_contest_virtual_participa_total_amount_kopeks_not_null NOT NULL,
    created_at timestamp with time zone
);

CREATE SEQUENCE referral_contest_virtual_participants_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE referral_contest_virtual_participants_id_seq OWNED BY referral_contest_virtual_participants.id;

CREATE TABLE referral_contests (
    id integer NOT NULL,
    title character varying(255) NOT NULL,
    description text,
    prize_text text,
    contest_type character varying(50) NOT NULL,
    start_at timestamp with time zone NOT NULL,
    end_at timestamp with time zone NOT NULL,
    daily_summary_time time without time zone NOT NULL,
    daily_summary_times character varying(255),
    timezone character varying(64) NOT NULL,
    is_active boolean NOT NULL,
    last_daily_summary_date date,
    last_daily_summary_at timestamp with time zone,
    final_summary_sent boolean NOT NULL,
    created_by integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);

CREATE SEQUENCE referral_contests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE referral_contests_id_seq OWNED BY referral_contests.id;

ALTER TABLE ONLY contest_attempts ALTER COLUMN id SET DEFAULT nextval('contest_attempts_id_seq'::regclass);

ALTER TABLE ONLY contest_rounds ALTER COLUMN id SET DEFAULT nextval('contest_rounds_id_seq'::regclass);

ALTER TABLE ONLY contest_templates ALTER COLUMN id SET DEFAULT nextval('contest_templates_id_seq'::regclass);

ALTER TABLE ONLY poll_answers ALTER COLUMN id SET DEFAULT nextval('poll_answers_id_seq'::regclass);

ALTER TABLE ONLY poll_options ALTER COLUMN id SET DEFAULT nextval('poll_options_id_seq'::regclass);

ALTER TABLE ONLY poll_questions ALTER COLUMN id SET DEFAULT nextval('poll_questions_id_seq'::regclass);

ALTER TABLE ONLY poll_responses ALTER COLUMN id SET DEFAULT nextval('poll_responses_id_seq'::regclass);

ALTER TABLE ONLY polls ALTER COLUMN id SET DEFAULT nextval('polls_id_seq'::regclass);

ALTER TABLE ONLY referral_contest_events ALTER COLUMN id SET DEFAULT nextval('referral_contest_events_id_seq'::regclass);

ALTER TABLE ONLY referral_contest_virtual_participants ALTER COLUMN id SET DEFAULT nextval('referral_contest_virtual_participants_id_seq'::regclass);

ALTER TABLE ONLY referral_contests ALTER COLUMN id SET DEFAULT nextval('referral_contests_id_seq'::regclass);

ALTER TABLE ONLY contest_attempts
    ADD CONSTRAINT contest_attempts_pkey PRIMARY KEY (id);

ALTER TABLE ONLY contest_rounds
    ADD CONSTRAINT contest_rounds_pkey PRIMARY KEY (id);

ALTER TABLE ONLY contest_templates
    ADD CONSTRAINT contest_templates_pkey PRIMARY KEY (id);

ALTER TABLE ONLY poll_answers
    ADD CONSTRAINT poll_answers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY poll_options
    ADD CONSTRAINT poll_options_pkey PRIMARY KEY (id);

ALTER TABLE ONLY poll_questions
    ADD CONSTRAINT poll_questions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY poll_responses
    ADD CONSTRAINT poll_responses_pkey PRIMARY KEY (id);

ALTER TABLE ONLY polls
    ADD CONSTRAINT polls_pkey PRIMARY KEY (id);

ALTER TABLE ONLY referral_contest_events
    ADD CONSTRAINT referral_contest_events_pkey PRIMARY KEY (id);

ALTER TABLE ONLY referral_contest_virtual_participants
    ADD CONSTRAINT referral_contest_virtual_participants_pkey PRIMARY KEY (id);

ALTER TABLE ONLY referral_contests
    ADD CONSTRAINT referral_contests_pkey PRIMARY KEY (id);

ALTER TABLE ONLY poll_answers
    ADD CONSTRAINT uq_poll_answer_unique UNIQUE (response_id, question_id);

ALTER TABLE ONLY poll_responses
    ADD CONSTRAINT uq_poll_user UNIQUE (poll_id, user_id);

ALTER TABLE ONLY referral_contest_events
    ADD CONSTRAINT uq_referral_contest_referral UNIQUE (contest_id, referral_id);

ALTER TABLE ONLY contest_attempts
    ADD CONSTRAINT uq_round_user_attempt UNIQUE (round_id, user_id);

CREATE INDEX idx_contest_attempt_round ON contest_attempts USING btree (round_id);

CREATE INDEX idx_contest_round_status ON contest_rounds USING btree (status);

CREATE INDEX idx_contest_round_template ON contest_rounds USING btree (template_id);

CREATE INDEX idx_referral_contest_referrer ON referral_contest_events USING btree (contest_id, referrer_id);

CREATE INDEX ix_contest_attempts_id ON contest_attempts USING btree (id);

CREATE INDEX ix_contest_rounds_id ON contest_rounds USING btree (id);

CREATE INDEX ix_contest_templates_id ON contest_templates USING btree (id);

CREATE UNIQUE INDEX ix_contest_templates_slug ON contest_templates USING btree (slug);

CREATE INDEX ix_poll_answers_id ON poll_answers USING btree (id);

CREATE INDEX ix_poll_answers_option_id ON poll_answers USING btree (option_id);

CREATE INDEX ix_poll_answers_question_id ON poll_answers USING btree (question_id);

CREATE INDEX ix_poll_answers_response_id ON poll_answers USING btree (response_id);

CREATE INDEX ix_poll_options_id ON poll_options USING btree (id);

CREATE INDEX ix_poll_options_question_id ON poll_options USING btree (question_id);

CREATE INDEX ix_poll_questions_id ON poll_questions USING btree (id);

CREATE INDEX ix_poll_questions_poll_id ON poll_questions USING btree (poll_id);

CREATE INDEX ix_poll_responses_id ON poll_responses USING btree (id);

CREATE INDEX ix_poll_responses_poll_id ON poll_responses USING btree (poll_id);

CREATE INDEX ix_poll_responses_user_id ON poll_responses USING btree (user_id);

CREATE INDEX ix_polls_id ON polls USING btree (id);

CREATE INDEX ix_referral_contest_events_id ON referral_contest_events USING btree (id);

CREATE INDEX ix_referral_contest_virtual_participants_id ON referral_contest_virtual_participants USING btree (id);

CREATE INDEX ix_referral_contests_id ON referral_contests USING btree (id);

ALTER TABLE ONLY contest_attempts
    ADD CONSTRAINT contest_attempts_round_id_fkey FOREIGN KEY (round_id) REFERENCES contest_rounds(id) ON DELETE CASCADE;

ALTER TABLE ONLY contest_attempts
    ADD CONSTRAINT contest_attempts_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY contest_rounds
    ADD CONSTRAINT contest_rounds_template_id_fkey FOREIGN KEY (template_id) REFERENCES contest_templates(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_answers
    ADD CONSTRAINT poll_answers_option_id_fkey FOREIGN KEY (option_id) REFERENCES poll_options(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_answers
    ADD CONSTRAINT poll_answers_question_id_fkey FOREIGN KEY (question_id) REFERENCES poll_questions(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_answers
    ADD CONSTRAINT poll_answers_response_id_fkey FOREIGN KEY (response_id) REFERENCES poll_responses(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_options
    ADD CONSTRAINT poll_options_question_id_fkey FOREIGN KEY (question_id) REFERENCES poll_questions(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_questions
    ADD CONSTRAINT poll_questions_poll_id_fkey FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_responses
    ADD CONSTRAINT poll_responses_poll_id_fkey FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE;

ALTER TABLE ONLY poll_responses
    ADD CONSTRAINT poll_responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY polls
    ADD CONSTRAINT polls_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE ONLY referral_contest_events
    ADD CONSTRAINT referral_contest_events_contest_id_fkey FOREIGN KEY (contest_id) REFERENCES referral_contests(id) ON DELETE CASCADE;

ALTER TABLE ONLY referral_contest_events
    ADD CONSTRAINT referral_contest_events_referral_id_fkey FOREIGN KEY (referral_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY referral_contest_events
    ADD CONSTRAINT referral_contest_events_referrer_id_fkey FOREIGN KEY (referrer_id) REFERENCES users(id) ON DELETE CASCADE;

ALTER TABLE ONLY referral_contest_virtual_participants
    ADD CONSTRAINT referral_contest_virtual_participants_contest_id_fkey FOREIGN KEY (contest_id) REFERENCES referral_contests(id) ON DELETE CASCADE;

ALTER TABLE ONLY referral_contests
    ADD CONSTRAINT referral_contests_created_by_fkey FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL;
"""


def _statement_table(statement: str) -> str:
    match = re.search(r'(?:CREATE TABLE|CREATE SEQUENCE|ALTER TABLE ONLY|ALTER SEQUENCE|ON)\s+(\w+)', statement)
    if match is None:
        raise ValueError(f'Cannot find the table of statement: {statement[:80]}')
    return match.group(1).removesuffix('_id_seq')


def _statements() -> list[str]:
    return [part.strip() for part in _DDL.split(';') if part.strip()]


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    present = [table for table in TABLES if table in existing]

    non_empty = [table for table in present if bind.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first()]
    if non_empty:
        logger.warning('Keeping contests and polls because their tables hold rows: %s', ', '.join(non_empty))
        return
    if present:
        op.execute('DROP TABLE IF EXISTS ' + ', '.join(present))


def downgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for statement in _statements():
        if _statement_table(statement) not in existing:
            op.execute(statement)
