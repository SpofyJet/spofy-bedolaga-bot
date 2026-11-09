"""Remove landing pages.

Guest purchases and gifts stay: only the landing configuration goes. If a landing
page is active or a purchase references one, nothing is removed and a warning is
logged. Inactive landing rows are dropped with the table.

Idempotent. Downgrade recreates the empty table, the column, its index and FK.

Revision ID: 0147
Revises: 0146
"""

import logging

import sqlalchemy as sa
from alembic import op


revision = '0147'
down_revision = '0146'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

_DDL = r"""
CREATE TABLE landing_pages (
    id integer NOT NULL,
    slug character varying(100) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    title json DEFAULT '{}'::jsonb NOT NULL,
    subtitle json,
    features json DEFAULT '[]'::json NOT NULL,
    footer_text json,
    allowed_tariff_ids json DEFAULT '[]'::json NOT NULL,
    allowed_periods json DEFAULT '{}'::json NOT NULL,
    payment_methods json DEFAULT '[]'::json NOT NULL,
    gift_enabled boolean DEFAULT true NOT NULL,
    custom_css text,
    meta_title json,
    meta_description json,
    display_order integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    discount_percent integer,
    discount_overrides json,
    discount_starts_at timestamp with time zone,
    discount_ends_at timestamp with time zone,
    discount_badge_text json,
    background_config json,
    sticky_pay_button boolean DEFAULT false NOT NULL,
    analytics_view_enabled boolean DEFAULT false NOT NULL,
    analytics_view_goal character varying(64),
    analytics_click_enabled boolean DEFAULT false NOT NULL,
    analytics_click_goal character varying(64),
    CONSTRAINT chk_landing_discount_dates_order CHECK (((discount_starts_at IS NULL) OR (discount_ends_at IS NULL) OR (discount_starts_at < discount_ends_at))),
    CONSTRAINT chk_landing_discount_percent_range CHECK (((discount_percent IS NULL) OR ((discount_percent >= 1) AND (discount_percent <= 99))))
);

CREATE SEQUENCE landing_pages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE landing_pages_id_seq OWNED BY landing_pages.id;

ALTER TABLE ONLY landing_pages ALTER COLUMN id SET DEFAULT nextval('landing_pages_id_seq'::regclass);

ALTER TABLE ONLY landing_pages
    ADD CONSTRAINT landing_pages_pkey PRIMARY KEY (id);

CREATE UNIQUE INDEX ix_landing_pages_slug ON landing_pages USING btree (slug);
"""


def upgrade() -> None:
    bind = op.get_bind()
    if 'landing_pages' not in sa.inspect(bind).get_table_names():
        return

    active = bind.execute(sa.text('SELECT 1 FROM landing_pages WHERE is_active LIMIT 1')).first()
    referenced = bind.execute(sa.text('SELECT 1 FROM guest_purchases WHERE landing_id IS NOT NULL LIMIT 1')).first()
    if active or referenced:
        logger.warning('Keeping landing pages: active=%s referenced=%s', bool(active), bool(referenced))
        return

    op.execute('DROP INDEX IF EXISTS ix_guest_purchases_landing_status_paid')
    op.execute('ALTER TABLE guest_purchases DROP COLUMN IF EXISTS landing_id')
    op.execute('DROP TABLE IF EXISTS landing_pages')


def downgrade() -> None:
    if 'landing_pages' not in sa.inspect(op.get_bind()).get_table_names():
        for statement in (part.strip() for part in _DDL.split(';')):
            if statement:
                op.execute(statement)

    op.execute('ALTER TABLE guest_purchases ADD COLUMN IF NOT EXISTS landing_id INTEGER')
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'guest_purchases_landing_id_fkey') THEN
                ALTER TABLE guest_purchases ADD CONSTRAINT guest_purchases_landing_id_fkey
                    FOREIGN KEY (landing_id) REFERENCES landing_pages(id) ON DELETE SET NULL;
            END IF;
        END $$
        """
    )
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_guest_purchases_landing_status_paid '
        'ON guest_purchases USING btree (landing_id, status, paid_at)'
    )
