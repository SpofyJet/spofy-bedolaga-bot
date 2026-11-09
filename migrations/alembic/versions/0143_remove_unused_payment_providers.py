"""Remove the tables and column of payment providers that were cut from the bot.

All dropped tables were empty on production when this was written. If any of them
holds rows at upgrade time, every table is left in place and a warning is logged:
data is never deleted by this migration.

Idempotent. Downgrade recreates the empty tables from the DDL below and adds the
column back; the removed payment_method_configs rows are reseeded by the old code
at startup (ensure_payment_method_configs).

Revision ID: 0143
Revises: 0142
"""

import logging
import re

import sqlalchemy as sa
from alembic import op


revision = '0143'
down_revision = '0142'
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

TABLES = (
    'antilopay_payments',
    'apple_iap_abuse_events',
    'apple_iap_accounts',
    'apple_notifications',
    'apple_transactions',
    'aurapay_payments',
    'cashera_payments',
    'cashera_subscriptions',
    'cispay_payments',
    'cloudpayments_payments',
    'donut_payments',
    'etoplatezhi_payments',
    'freekassa_payments',
    'jupiter_payments',
    'kassa_ai_payments',
    'lava_payments',
    'lava_subscriptions',
    'mulenpay_payments',
    'overpay_payments',
    'pal24_payments',
    'paritypay_payments',
    'paypear_payments',
    'riopay_payments',
    'rollypay_payments',
    'saved_payment_methods',
    'severpay_payments',
    'tabpay_payments',
    'yookassa_payments',
)

REMOVED_METHODS = (
    'yookassa',
    'tribute',
    'mulenpay',
    'pal24',
    'cloudpayments',
    'freekassa',
    'freekassa_sbp',
    'freekassa_card',
    'kassa_ai',
    'riopay',
    'severpay',
    'paypear',
    'rollypay',
    'overpay',
    'aurapay',
    'etoplatezhi',
    'antilopay',
    'jupiter',
    'lava',
    'cispay',
    'cashera',
    'paritypay',
    'tabpay',
    'donut',
    'apple_iap',
)

_OWNER_RE = re.compile(r'public\.([a-z0-9_]+)')

_DDL = r"""
CREATE TABLE public.antilopay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    antilopay_payment_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.antilopay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.antilopay_payments_id_seq OWNED BY public.antilopay_payments.id;
CREATE TABLE public.apple_iap_abuse_events (
    id integer NOT NULL,
    user_id integer,
    event_type character varying(64) NOT NULL,
    severity character varying(16) DEFAULT 'warning'::character varying NOT NULL,
    transaction_id character varying(64),
    product_id character varying(128),
    ip_address character varying(64),
    details_json json,
    created_at timestamp with time zone DEFAULT now()
);
CREATE SEQUENCE public.apple_iap_abuse_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.apple_iap_abuse_events_id_seq OWNED BY public.apple_iap_abuse_events.id;
CREATE TABLE public.apple_iap_accounts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    account_token_uuid character varying(36) NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    rotated_at timestamp with time zone,
    disabled_at timestamp with time zone
);
CREATE SEQUENCE public.apple_iap_accounts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.apple_iap_accounts_id_seq OWNED BY public.apple_iap_accounts.id;
CREATE TABLE public.apple_notifications (
    id integer NOT NULL,
    notification_uuid character varying(64) NOT NULL,
    notification_type character varying(64) NOT NULL,
    subtype character varying(64),
    environment character varying(16),
    transaction_id character varying(64),
    original_transaction_id character varying(64),
    status character varying(32) DEFAULT 'received'::character varying NOT NULL,
    error text,
    payload_hash character varying(64) NOT NULL,
    metadata_json json,
    received_at timestamp with time zone DEFAULT now(),
    processed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE SEQUENCE public.apple_notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.apple_notifications_id_seq OWNED BY public.apple_notifications.id;
CREATE TABLE public.apple_transactions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    transaction_id character varying(64) NOT NULL,
    original_transaction_id character varying(64),
    product_id character varying(128) NOT NULL,
    bundle_id character varying(255) NOT NULL,
    amount_kopeks integer NOT NULL,
    environment character varying(16) NOT NULL,
    status character varying(50) DEFAULT 'verified'::character varying,
    is_paid boolean DEFAULT true,
    paid_at timestamp with time zone,
    refunded_at timestamp with time zone,
    transaction_id_fk integer,
    metadata_json json,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    app_account_token character varying(36),
    web_order_line_item_id character varying(64),
    storefront character varying(16),
    currency character varying(3),
    price_micros bigint,
    purchase_date timestamp with time zone,
    revocation_date timestamp with time zone,
    revocation_reason character varying(50),
    credited_at timestamp with time zone,
    refund_reversed_at timestamp with time zone,
    signed_transaction_hash character varying(64)
);
CREATE SEQUENCE public.apple_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.apple_transactions_id_seq OWNED BY public.apple_transactions.id;
CREATE TABLE public.aurapay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    aurapay_invoice_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.aurapay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.aurapay_payments_id_seq OWNED BY public.aurapay_payments.id;
CREATE TABLE public.cashera_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    cashera_uuid character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    cashera_status character varying(32),
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.cashera_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.cashera_payments_id_seq OWNED BY public.cashera_payments.id;
CREATE TABLE public.cashera_subscriptions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    subscription_id integer NOT NULL,
    tariff_id integer,
    cashera_subscription_uuid character varying(64),
    external_id character varying(255) NOT NULL,
    "interval" character varying(16) NOT NULL,
    charge_days integer NOT NULL,
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    remote_status character varying(32),
    redirect_url text,
    next_charge_at timestamp with time zone,
    last_charge_at timestamp with time zone,
    last_charge_external_id character varying(255),
    charges_success integer DEFAULT 0 NOT NULL,
    charges_failed integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE SEQUENCE public.cashera_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.cashera_subscriptions_id_seq OWNED BY public.cashera_subscriptions.id;
CREATE TABLE public.cispay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    cispay_payment_id character varying(64),
    amount_kopeks integer NOT NULL,
    charged_amount_kopeks integer,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.cispay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.cispay_payments_id_seq OWNED BY public.cispay_payments.id;
CREATE TABLE public.cloudpayments_payments (
    id integer NOT NULL,
    user_id integer,
    transaction_id_cp bigint,
    invoice_id character varying(255) NOT NULL,
    amount_kopeks integer NOT NULL,
    currency character varying(10) NOT NULL,
    description text,
    status character varying(50) NOT NULL,
    is_paid boolean,
    paid_at timestamp with time zone,
    card_first_six character varying(6),
    card_last_four character varying(4),
    card_type character varying(50),
    card_exp_date character varying(10),
    token character varying(255),
    payment_url text,
    email character varying(255),
    test_mode boolean,
    metadata_json json,
    callback_payload json,
    transaction_id integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);
CREATE SEQUENCE public.cloudpayments_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.cloudpayments_payments_id_seq OWNED BY public.cloudpayments_payments.id;
CREATE TABLE public.donut_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    donut_transaction_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.donut_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.donut_payments_id_seq OWNED BY public.donut_payments.id;
CREATE TABLE public.etoplatezhi_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    etoplatezhi_payment_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.etoplatezhi_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.etoplatezhi_payments_id_seq OWNED BY public.etoplatezhi_payments.id;
CREATE TABLE public.freekassa_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    freekassa_order_id character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) NOT NULL,
    description text,
    status character varying(32) NOT NULL,
    is_paid boolean,
    payment_url text,
    payment_system_id integer,
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    transaction_id integer
);
CREATE SEQUENCE public.freekassa_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.freekassa_payments_id_seq OWNED BY public.freekassa_payments.id;
CREATE TABLE public.jupiter_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    jupiter_transaction_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.jupiter_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.jupiter_payments_id_seq OWNED BY public.jupiter_payments.id;
CREATE TABLE public.kassa_ai_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    kassa_ai_order_id character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) NOT NULL,
    description text,
    status character varying(32) NOT NULL,
    is_paid boolean,
    payment_url text,
    payment_system_id integer,
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    transaction_id integer
);
CREATE SEQUENCE public.kassa_ai_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.kassa_ai_payments_id_seq OWNED BY public.kassa_ai_payments.id;
CREATE TABLE public.lava_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    lava_invoice_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.lava_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.lava_payments_id_seq OWNED BY public.lava_payments.id;
CREATE TABLE public.lava_subscriptions (
    id integer NOT NULL,
    user_id integer NOT NULL,
    subscription_id integer NOT NULL,
    tariff_id integer,
    lava_subscription_id character varying(255),
    lava_product_id character varying(255) NOT NULL,
    lava_consumer_id character varying(255),
    order_id character varying(255) NOT NULL,
    charge_days integer NOT NULL,
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    redirect_url text,
    next_charge_at timestamp with time zone,
    last_charge_at timestamp with time zone,
    last_charge_external_id character varying(255),
    charges_success integer DEFAULT 0 NOT NULL,
    charges_failed integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE SEQUENCE public.lava_subscriptions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.lava_subscriptions_id_seq OWNED BY public.lava_subscriptions.id;
CREATE TABLE public.mulenpay_payments (
    id integer NOT NULL,
    user_id integer,
    mulen_payment_id integer,
    uuid character varying(255) NOT NULL,
    amount_kopeks integer NOT NULL,
    currency character varying(10) NOT NULL,
    description text,
    status character varying(50) NOT NULL,
    is_paid boolean,
    paid_at timestamp with time zone,
    payment_url text,
    metadata_json json,
    callback_payload json,
    transaction_id integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);
CREATE SEQUENCE public.mulenpay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.mulenpay_payments_id_seq OWNED BY public.mulenpay_payments.id;
CREATE TABLE public.overpay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    overpay_payment_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.overpay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.overpay_payments_id_seq OWNED BY public.overpay_payments.id;
CREATE TABLE public.pal24_payments (
    id integer NOT NULL,
    user_id integer,
    bill_id character varying(255) NOT NULL,
    order_id character varying(255),
    amount_kopeks integer NOT NULL,
    currency character varying(10) NOT NULL,
    description text,
    type character varying(20) NOT NULL,
    status character varying(50) NOT NULL,
    is_active boolean,
    is_paid boolean,
    paid_at timestamp with time zone,
    last_status character varying(50),
    last_status_checked_at timestamp with time zone,
    link_url text,
    link_page_url text,
    metadata_json json,
    callback_payload json,
    payment_id character varying(255),
    payment_status character varying(50),
    payment_method character varying(50),
    balance_amount character varying(50),
    balance_currency character varying(10),
    payer_account character varying(255),
    ttl integer,
    expires_at timestamp with time zone,
    transaction_id integer,
    created_at timestamp with time zone,
    updated_at timestamp with time zone
);
CREATE SEQUENCE public.pal24_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.pal24_payments_id_seq OWNED BY public.pal24_payments.id;
CREATE TABLE public.paritypay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    paritypay_payment_id character varying(64),
    amount_kopeks integer NOT NULL,
    credited_kopeks integer,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    processed_events json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.paritypay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.paritypay_payments_id_seq OWNED BY public.paritypay_payments.id;
CREATE TABLE public.paypear_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    paypear_id character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.paypear_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.paypear_payments_id_seq OWNED BY public.paypear_payments.id;
CREATE TABLE public.riopay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    riopay_order_id character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.riopay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.riopay_payments_id_seq OWNED BY public.riopay_payments.id;
CREATE TABLE public.rollypay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    rollypay_payment_id character varying(128),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.rollypay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.rollypay_payments_id_seq OWNED BY public.rollypay_payments.id;
CREATE TABLE public.saved_payment_methods (
    id integer NOT NULL,
    user_id integer NOT NULL,
    yookassa_payment_method_id character varying(255) NOT NULL,
    method_type character varying(50) DEFAULT 'bank_card'::character varying NOT NULL,
    card_first6 character varying(6),
    card_last4 character varying(4),
    card_type character varying(50),
    card_expiry_month character varying(2),
    card_expiry_year character varying(4),
    title character varying(255),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);
CREATE SEQUENCE public.saved_payment_methods_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.saved_payment_methods_id_seq OWNED BY public.saved_payment_methods.id;
CREATE TABLE public.severpay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    severpay_id character varying(64),
    severpay_uid character varying(64),
    amount_kopeks integer NOT NULL,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.severpay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.severpay_payments_id_seq OWNED BY public.severpay_payments.id;
CREATE TABLE public.tabpay_payments (
    id integer NOT NULL,
    user_id integer,
    order_id character varying(64) NOT NULL,
    tabpay_payment_id character varying(64),
    amount_kopeks integer NOT NULL,
    commission_kopeks integer,
    currency character varying(10) DEFAULT 'RUB'::character varying NOT NULL,
    description text,
    status character varying(32) DEFAULT 'pending'::character varying NOT NULL,
    is_paid boolean DEFAULT false NOT NULL,
    is_test boolean DEFAULT false NOT NULL,
    payment_url text,
    payment_method character varying(32),
    metadata_json json,
    callback_payload json,
    processed_events json,
    paid_at timestamp with time zone,
    expires_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    transaction_id integer
);
CREATE SEQUENCE public.tabpay_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.tabpay_payments_id_seq OWNED BY public.tabpay_payments.id;
CREATE TABLE public.yookassa_payments (
    id integer NOT NULL,
    user_id integer,
    yookassa_payment_id character varying(255) NOT NULL,
    amount_kopeks integer NOT NULL,
    currency character varying(3) NOT NULL,
    description text,
    status character varying(50) NOT NULL,
    is_paid boolean,
    is_captured boolean,
    confirmation_url text,
    metadata_json json,
    transaction_id integer,
    payment_method_type character varying(50),
    refundable boolean,
    test_mode boolean,
    created_at timestamp with time zone,
    updated_at timestamp with time zone,
    yookassa_created_at timestamp with time zone,
    captured_at timestamp with time zone
);
CREATE SEQUENCE public.yookassa_payments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;
ALTER SEQUENCE public.yookassa_payments_id_seq OWNED BY public.yookassa_payments.id;
ALTER TABLE ONLY public.antilopay_payments ALTER COLUMN id SET DEFAULT nextval('public.antilopay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.apple_iap_abuse_events ALTER COLUMN id SET DEFAULT nextval('public.apple_iap_abuse_events_id_seq'::regclass);
ALTER TABLE ONLY public.apple_iap_accounts ALTER COLUMN id SET DEFAULT nextval('public.apple_iap_accounts_id_seq'::regclass);
ALTER TABLE ONLY public.apple_notifications ALTER COLUMN id SET DEFAULT nextval('public.apple_notifications_id_seq'::regclass);
ALTER TABLE ONLY public.apple_transactions ALTER COLUMN id SET DEFAULT nextval('public.apple_transactions_id_seq'::regclass);
ALTER TABLE ONLY public.aurapay_payments ALTER COLUMN id SET DEFAULT nextval('public.aurapay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.cashera_payments ALTER COLUMN id SET DEFAULT nextval('public.cashera_payments_id_seq'::regclass);
ALTER TABLE ONLY public.cashera_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.cashera_subscriptions_id_seq'::regclass);
ALTER TABLE ONLY public.cispay_payments ALTER COLUMN id SET DEFAULT nextval('public.cispay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.cloudpayments_payments ALTER COLUMN id SET DEFAULT nextval('public.cloudpayments_payments_id_seq'::regclass);
ALTER TABLE ONLY public.donut_payments ALTER COLUMN id SET DEFAULT nextval('public.donut_payments_id_seq'::regclass);
ALTER TABLE ONLY public.etoplatezhi_payments ALTER COLUMN id SET DEFAULT nextval('public.etoplatezhi_payments_id_seq'::regclass);
ALTER TABLE ONLY public.freekassa_payments ALTER COLUMN id SET DEFAULT nextval('public.freekassa_payments_id_seq'::regclass);
ALTER TABLE ONLY public.jupiter_payments ALTER COLUMN id SET DEFAULT nextval('public.jupiter_payments_id_seq'::regclass);
ALTER TABLE ONLY public.kassa_ai_payments ALTER COLUMN id SET DEFAULT nextval('public.kassa_ai_payments_id_seq'::regclass);
ALTER TABLE ONLY public.lava_payments ALTER COLUMN id SET DEFAULT nextval('public.lava_payments_id_seq'::regclass);
ALTER TABLE ONLY public.lava_subscriptions ALTER COLUMN id SET DEFAULT nextval('public.lava_subscriptions_id_seq'::regclass);
ALTER TABLE ONLY public.mulenpay_payments ALTER COLUMN id SET DEFAULT nextval('public.mulenpay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.overpay_payments ALTER COLUMN id SET DEFAULT nextval('public.overpay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.pal24_payments ALTER COLUMN id SET DEFAULT nextval('public.pal24_payments_id_seq'::regclass);
ALTER TABLE ONLY public.paritypay_payments ALTER COLUMN id SET DEFAULT nextval('public.paritypay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.paypear_payments ALTER COLUMN id SET DEFAULT nextval('public.paypear_payments_id_seq'::regclass);
ALTER TABLE ONLY public.riopay_payments ALTER COLUMN id SET DEFAULT nextval('public.riopay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.rollypay_payments ALTER COLUMN id SET DEFAULT nextval('public.rollypay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.saved_payment_methods ALTER COLUMN id SET DEFAULT nextval('public.saved_payment_methods_id_seq'::regclass);
ALTER TABLE ONLY public.severpay_payments ALTER COLUMN id SET DEFAULT nextval('public.severpay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.tabpay_payments ALTER COLUMN id SET DEFAULT nextval('public.tabpay_payments_id_seq'::regclass);
ALTER TABLE ONLY public.yookassa_payments ALTER COLUMN id SET DEFAULT nextval('public.yookassa_payments_id_seq'::regclass);
ALTER TABLE ONLY public.antilopay_payments
    ADD CONSTRAINT antilopay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_iap_abuse_events
    ADD CONSTRAINT apple_iap_abuse_events_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_iap_accounts
    ADD CONSTRAINT apple_iap_accounts_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_notifications
    ADD CONSTRAINT apple_notifications_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_transactions
    ADD CONSTRAINT apple_transactions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_transactions
    ADD CONSTRAINT apple_transactions_transaction_id_key UNIQUE (transaction_id);
ALTER TABLE ONLY public.aurapay_payments
    ADD CONSTRAINT aurapay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cashera_payments
    ADD CONSTRAINT cashera_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT cashera_subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cispay_payments
    ADD CONSTRAINT cispay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.cloudpayments_payments
    ADD CONSTRAINT cloudpayments_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.donut_payments
    ADD CONSTRAINT donut_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.etoplatezhi_payments
    ADD CONSTRAINT etoplatezhi_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.freekassa_payments
    ADD CONSTRAINT freekassa_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.jupiter_payments
    ADD CONSTRAINT jupiter_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.kassa_ai_payments
    ADD CONSTRAINT kassa_ai_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.lava_payments
    ADD CONSTRAINT lava_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT lava_subscriptions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mulenpay_payments
    ADD CONSTRAINT mulenpay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.overpay_payments
    ADD CONSTRAINT overpay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.pal24_payments
    ADD CONSTRAINT pal24_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.paritypay_payments
    ADD CONSTRAINT paritypay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.paypear_payments
    ADD CONSTRAINT paypear_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.riopay_payments
    ADD CONSTRAINT riopay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.rollypay_payments
    ADD CONSTRAINT rollypay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.saved_payment_methods
    ADD CONSTRAINT saved_payment_methods_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.severpay_payments
    ADD CONSTRAINT severpay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.tabpay_payments
    ADD CONSTRAINT tabpay_payments_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.apple_iap_accounts
    ADD CONSTRAINT uq_apple_iap_accounts_token UNIQUE (account_token_uuid);
ALTER TABLE ONLY public.apple_iap_accounts
    ADD CONSTRAINT uq_apple_iap_accounts_user_id UNIQUE (user_id);
ALTER TABLE ONLY public.apple_notifications
    ADD CONSTRAINT uq_apple_notifications_notification_uuid UNIQUE (notification_uuid);
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT uq_cashera_subscriptions_external_id UNIQUE (external_id);
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT uq_cashera_subscriptions_uuid UNIQUE (cashera_subscription_uuid);
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT uq_lava_subscriptions_lava_id UNIQUE (lava_subscription_id);
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT uq_lava_subscriptions_order_id UNIQUE (order_id);
ALTER TABLE ONLY public.yookassa_payments
    ADD CONSTRAINT yookassa_payments_pkey PRIMARY KEY (id);
CREATE INDEX idx_mulenpay_payment_id ON public.mulenpay_payments USING btree (mulen_payment_id);
CREATE UNIQUE INDEX ix_antilopay_payments_antilopay_payment_id ON public.antilopay_payments USING btree (antilopay_payment_id);
CREATE UNIQUE INDEX ix_antilopay_payments_order_id ON public.antilopay_payments USING btree (order_id);
CREATE INDEX ix_antilopay_payments_user_id ON public.antilopay_payments USING btree (user_id);
CREATE INDEX ix_apple_iap_abuse_events_event_type ON public.apple_iap_abuse_events USING btree (event_type);
CREATE INDEX ix_apple_iap_abuse_events_id ON public.apple_iap_abuse_events USING btree (id);
CREATE INDEX ix_apple_iap_abuse_events_transaction_id ON public.apple_iap_abuse_events USING btree (transaction_id);
CREATE INDEX ix_apple_iap_abuse_events_user_id ON public.apple_iap_abuse_events USING btree (user_id);
CREATE INDEX ix_apple_iap_accounts_id ON public.apple_iap_accounts USING btree (id);
CREATE INDEX ix_apple_notifications_environment ON public.apple_notifications USING btree (environment);
CREATE INDEX ix_apple_notifications_id ON public.apple_notifications USING btree (id);
CREATE INDEX ix_apple_notifications_notification_type ON public.apple_notifications USING btree (notification_type);
CREATE INDEX ix_apple_notifications_notification_uuid ON public.apple_notifications USING btree (notification_uuid);
CREATE INDEX ix_apple_notifications_original_transaction_id ON public.apple_notifications USING btree (original_transaction_id);
CREATE UNIQUE INDEX ix_apple_notifications_payload_hash ON public.apple_notifications USING btree (payload_hash);
CREATE INDEX ix_apple_notifications_status_received_at ON public.apple_notifications USING btree (status, received_at) WHERE ((status)::text = ANY (ARRAY[('received'::character varying)::text, ('failed'::character varying)::text]));
CREATE INDEX ix_apple_notifications_transaction_id ON public.apple_notifications USING btree (transaction_id);
CREATE INDEX ix_apple_transactions_app_account_token ON public.apple_transactions USING btree (app_account_token);
CREATE INDEX ix_apple_transactions_original_transaction_id ON public.apple_transactions USING btree (original_transaction_id);
CREATE INDEX ix_apple_transactions_signed_transaction_hash ON public.apple_transactions USING btree (signed_transaction_hash);
CREATE INDEX ix_apple_transactions_transaction_id ON public.apple_transactions USING btree (transaction_id);
CREATE INDEX ix_apple_transactions_user_id ON public.apple_transactions USING btree (user_id);
CREATE UNIQUE INDEX ix_apple_transactions_web_order_line_item_id ON public.apple_transactions USING btree (web_order_line_item_id);
CREATE UNIQUE INDEX ix_aurapay_payments_aurapay_invoice_id ON public.aurapay_payments USING btree (aurapay_invoice_id);
CREATE UNIQUE INDEX ix_aurapay_payments_order_id ON public.aurapay_payments USING btree (order_id);
CREATE INDEX ix_aurapay_payments_user_id ON public.aurapay_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_cashera_payments_cashera_uuid ON public.cashera_payments USING btree (cashera_uuid);
CREATE UNIQUE INDEX ix_cashera_payments_order_id ON public.cashera_payments USING btree (order_id);
CREATE INDEX ix_cashera_payments_user_id ON public.cashera_payments USING btree (user_id);
CREATE INDEX ix_cashera_subscriptions_subscription_id ON public.cashera_subscriptions USING btree (subscription_id);
CREATE INDEX ix_cashera_subscriptions_user_active ON public.cashera_subscriptions USING btree (user_id, status);
CREATE INDEX ix_cashera_subscriptions_user_id ON public.cashera_subscriptions USING btree (user_id);
CREATE UNIQUE INDEX ix_cispay_payments_cispay_payment_id ON public.cispay_payments USING btree (cispay_payment_id);
CREATE UNIQUE INDEX ix_cispay_payments_order_id ON public.cispay_payments USING btree (order_id);
CREATE INDEX ix_cispay_payments_user_id ON public.cispay_payments USING btree (user_id);
CREATE INDEX ix_cloudpayments_payments_id ON public.cloudpayments_payments USING btree (id);
CREATE UNIQUE INDEX ix_cloudpayments_payments_invoice_id ON public.cloudpayments_payments USING btree (invoice_id);
CREATE INDEX ix_cloudpayments_payments_metadata_purchase_token ON public.cloudpayments_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_cloudpayments_payments_transaction_id_cp ON public.cloudpayments_payments USING btree (transaction_id_cp);
CREATE UNIQUE INDEX ix_donut_payments_donut_transaction_id ON public.donut_payments USING btree (donut_transaction_id);
CREATE UNIQUE INDEX ix_donut_payments_order_id ON public.donut_payments USING btree (order_id);
CREATE INDEX ix_donut_payments_user_id ON public.donut_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_etoplatezhi_payments_etoplatezhi_payment_id ON public.etoplatezhi_payments USING btree (etoplatezhi_payment_id);
CREATE UNIQUE INDEX ix_etoplatezhi_payments_order_id ON public.etoplatezhi_payments USING btree (order_id);
CREATE INDEX ix_etoplatezhi_payments_user_id ON public.etoplatezhi_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_freekassa_payments_freekassa_order_id ON public.freekassa_payments USING btree (freekassa_order_id);
CREATE INDEX ix_freekassa_payments_id ON public.freekassa_payments USING btree (id);
CREATE INDEX ix_freekassa_payments_metadata_purchase_token ON public.freekassa_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_freekassa_payments_order_id ON public.freekassa_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_jupiter_payments_jupiter_transaction_id ON public.jupiter_payments USING btree (jupiter_transaction_id);
CREATE UNIQUE INDEX ix_jupiter_payments_order_id ON public.jupiter_payments USING btree (order_id);
CREATE INDEX ix_jupiter_payments_user_id ON public.jupiter_payments USING btree (user_id);
CREATE INDEX ix_kassa_ai_payments_id ON public.kassa_ai_payments USING btree (id);
CREATE UNIQUE INDEX ix_kassa_ai_payments_kassa_ai_order_id ON public.kassa_ai_payments USING btree (kassa_ai_order_id);
CREATE INDEX ix_kassa_ai_payments_metadata_purchase_token ON public.kassa_ai_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_kassa_ai_payments_order_id ON public.kassa_ai_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_lava_payments_lava_invoice_id ON public.lava_payments USING btree (lava_invoice_id);
CREATE UNIQUE INDEX ix_lava_payments_order_id ON public.lava_payments USING btree (order_id);
CREATE INDEX ix_lava_payments_user_id ON public.lava_payments USING btree (user_id);
CREATE INDEX ix_lava_subscriptions_subscription_id ON public.lava_subscriptions USING btree (subscription_id);
CREATE INDEX ix_lava_subscriptions_user_active ON public.lava_subscriptions USING btree (user_id, status);
CREATE INDEX ix_lava_subscriptions_user_id ON public.lava_subscriptions USING btree (user_id);
CREATE INDEX ix_mulenpay_payments_id ON public.mulenpay_payments USING btree (id);
CREATE INDEX ix_mulenpay_payments_metadata_purchase_token ON public.mulenpay_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE INDEX ix_mulenpay_payments_mulen_payment_id ON public.mulenpay_payments USING btree (mulen_payment_id);
CREATE UNIQUE INDEX ix_mulenpay_payments_uuid ON public.mulenpay_payments USING btree (uuid);
CREATE UNIQUE INDEX ix_overpay_payments_order_id ON public.overpay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_overpay_payments_overpay_payment_id ON public.overpay_payments USING btree (overpay_payment_id);
CREATE INDEX ix_overpay_payments_user_id ON public.overpay_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_pal24_payments_bill_id ON public.pal24_payments USING btree (bill_id);
CREATE INDEX ix_pal24_payments_id ON public.pal24_payments USING btree (id);
CREATE INDEX ix_pal24_payments_metadata_purchase_token ON public.pal24_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE INDEX ix_pal24_payments_order_id ON public.pal24_payments USING btree (order_id);
CREATE INDEX ix_pal24_payments_payment_id ON public.pal24_payments USING btree (payment_id);
CREATE INDEX ix_paritypay_payments_id ON public.paritypay_payments USING btree (id);
CREATE UNIQUE INDEX ix_paritypay_payments_order_id ON public.paritypay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_paritypay_payments_paritypay_payment_id ON public.paritypay_payments USING btree (paritypay_payment_id);
CREATE INDEX ix_paritypay_payments_user_id ON public.paritypay_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_paypear_payments_order_id ON public.paypear_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_paypear_payments_paypear_id ON public.paypear_payments USING btree (paypear_id);
CREATE INDEX ix_paypear_payments_user_id ON public.paypear_payments USING btree (user_id);
CREATE INDEX ix_riopay_payments_metadata_purchase_token ON public.riopay_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_riopay_payments_order_id ON public.riopay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_riopay_payments_riopay_order_id ON public.riopay_payments USING btree (riopay_order_id);
CREATE INDEX ix_riopay_payments_user_id ON public.riopay_payments USING btree (user_id);
CREATE UNIQUE INDEX ix_rollypay_payments_order_id ON public.rollypay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_rollypay_payments_rollypay_payment_id ON public.rollypay_payments USING btree (rollypay_payment_id);
CREATE INDEX ix_rollypay_payments_user_id ON public.rollypay_payments USING btree (user_id);
CREATE INDEX ix_saved_payment_methods_user_active ON public.saved_payment_methods USING btree (user_id, is_active);
CREATE INDEX ix_saved_payment_methods_user_id ON public.saved_payment_methods USING btree (user_id);
CREATE UNIQUE INDEX ix_saved_payment_methods_yookassa_payment_method_id ON public.saved_payment_methods USING btree (yookassa_payment_method_id);
CREATE INDEX ix_severpay_payments_metadata_purchase_token ON public.severpay_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_severpay_payments_order_id ON public.severpay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_severpay_payments_severpay_id ON public.severpay_payments USING btree (severpay_id);
CREATE UNIQUE INDEX ix_severpay_payments_severpay_uid ON public.severpay_payments USING btree (severpay_uid);
CREATE INDEX ix_severpay_payments_user_id ON public.severpay_payments USING btree (user_id);
CREATE INDEX ix_tabpay_payments_id ON public.tabpay_payments USING btree (id);
CREATE UNIQUE INDEX ix_tabpay_payments_order_id ON public.tabpay_payments USING btree (order_id);
CREATE UNIQUE INDEX ix_tabpay_payments_tabpay_payment_id ON public.tabpay_payments USING btree (tabpay_payment_id);
CREATE INDEX ix_tabpay_payments_user_id ON public.tabpay_payments USING btree (user_id);
CREATE INDEX ix_yookassa_payments_id ON public.yookassa_payments USING btree (id);
CREATE INDEX ix_yookassa_payments_metadata_purchase_token ON public.yookassa_payments USING btree (((metadata_json ->> 'purchase_token'::text))) WHERE (is_paid = true);
CREATE UNIQUE INDEX ix_yookassa_payments_yookassa_payment_id ON public.yookassa_payments USING btree (yookassa_payment_id);
CREATE UNIQUE INDEX uq_cashera_subscriptions_alive ON public.cashera_subscriptions USING btree (subscription_id) WHERE ((status)::text = ANY ((ARRAY['PENDING'::character varying, 'ACTIVE'::character varying, 'PAST_DUE'::character varying])::text[]));
CREATE UNIQUE INDEX uq_lava_subscriptions_alive ON public.lava_subscriptions USING btree (subscription_id) WHERE ((status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('ACTIVE'::character varying)::text, ('PAST_DUE'::character varying)::text]));
ALTER TABLE ONLY public.antilopay_payments
    ADD CONSTRAINT antilopay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.antilopay_payments
    ADD CONSTRAINT antilopay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.apple_iap_abuse_events
    ADD CONSTRAINT apple_iap_abuse_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.apple_iap_accounts
    ADD CONSTRAINT apple_iap_accounts_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.apple_transactions
    ADD CONSTRAINT apple_transactions_transaction_id_fk_fkey FOREIGN KEY (transaction_id_fk) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.apple_transactions
    ADD CONSTRAINT apple_transactions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.aurapay_payments
    ADD CONSTRAINT aurapay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.aurapay_payments
    ADD CONSTRAINT aurapay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.cashera_payments
    ADD CONSTRAINT cashera_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.cashera_payments
    ADD CONSTRAINT cashera_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT cashera_subscriptions_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT cashera_subscriptions_tariff_id_fkey FOREIGN KEY (tariff_id) REFERENCES public.tariffs(id);
ALTER TABLE ONLY public.cashera_subscriptions
    ADD CONSTRAINT cashera_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.cispay_payments
    ADD CONSTRAINT cispay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.cispay_payments
    ADD CONSTRAINT cispay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.cloudpayments_payments
    ADD CONSTRAINT cloudpayments_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.cloudpayments_payments
    ADD CONSTRAINT cloudpayments_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.donut_payments
    ADD CONSTRAINT donut_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.donut_payments
    ADD CONSTRAINT donut_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.etoplatezhi_payments
    ADD CONSTRAINT etoplatezhi_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.etoplatezhi_payments
    ADD CONSTRAINT etoplatezhi_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.freekassa_payments
    ADD CONSTRAINT freekassa_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.freekassa_payments
    ADD CONSTRAINT freekassa_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.jupiter_payments
    ADD CONSTRAINT jupiter_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.jupiter_payments
    ADD CONSTRAINT jupiter_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.kassa_ai_payments
    ADD CONSTRAINT kassa_ai_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.kassa_ai_payments
    ADD CONSTRAINT kassa_ai_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.lava_payments
    ADD CONSTRAINT lava_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.lava_payments
    ADD CONSTRAINT lava_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT lava_subscriptions_subscription_id_fkey FOREIGN KEY (subscription_id) REFERENCES public.subscriptions(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT lava_subscriptions_tariff_id_fkey FOREIGN KEY (tariff_id) REFERENCES public.tariffs(id);
ALTER TABLE ONLY public.lava_subscriptions
    ADD CONSTRAINT lava_subscriptions_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mulenpay_payments
    ADD CONSTRAINT mulenpay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.mulenpay_payments
    ADD CONSTRAINT mulenpay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.overpay_payments
    ADD CONSTRAINT overpay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.overpay_payments
    ADD CONSTRAINT overpay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.pal24_payments
    ADD CONSTRAINT pal24_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.pal24_payments
    ADD CONSTRAINT pal24_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.paritypay_payments
    ADD CONSTRAINT paritypay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.paritypay_payments
    ADD CONSTRAINT paritypay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.paypear_payments
    ADD CONSTRAINT paypear_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.paypear_payments
    ADD CONSTRAINT paypear_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.riopay_payments
    ADD CONSTRAINT riopay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.riopay_payments
    ADD CONSTRAINT riopay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.rollypay_payments
    ADD CONSTRAINT rollypay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.rollypay_payments
    ADD CONSTRAINT rollypay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.saved_payment_methods
    ADD CONSTRAINT saved_payment_methods_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);
ALTER TABLE ONLY public.severpay_payments
    ADD CONSTRAINT severpay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.severpay_payments
    ADD CONSTRAINT severpay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.tabpay_payments
    ADD CONSTRAINT tabpay_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.tabpay_payments
    ADD CONSTRAINT tabpay_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.yookassa_payments
    ADD CONSTRAINT yookassa_payments_transaction_id_fkey FOREIGN KEY (transaction_id) REFERENCES public.transactions(id);
ALTER TABLE ONLY public.yookassa_payments
    ADD CONSTRAINT yookassa_payments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;
"""


def _statement_table(statement: str) -> str:
    match = _OWNER_RE.search(statement)
    if match is None:
        raise ValueError(f'No table in statement: {statement[:80]}')
    return match.group(1).removesuffix('_id_seq')


def _statements() -> list[str]:
    return [part.strip() for part in _DDL.split(';') if part.strip()]


def upgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    present = [table for table in TABLES if table in existing]

    non_empty = [table for table in present if bind.execute(sa.text(f'SELECT 1 FROM {table} LIMIT 1')).first()]
    if non_empty:
        logger.warning('Keeping removed payment providers because their tables hold rows: %s', non_empty)
        return
    if present:
        op.execute('DROP TABLE IF EXISTS ' + ', '.join(present))

    op.execute('ALTER TABLE tariffs DROP COLUMN IF EXISTS lava_product_id')

    if 'payment_method_configs' in existing:
        bind.execute(
            sa.text('DELETE FROM payment_method_configs WHERE method_id = ANY(:methods)'),
            {'methods': list(REMOVED_METHODS)},
        )


def downgrade() -> None:
    op.execute('ALTER TABLE tariffs ADD COLUMN IF NOT EXISTS lava_product_id VARCHAR(255)')

    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for statement in _statements():
        if _statement_table(statement) not in existing:
            op.execute(statement)
