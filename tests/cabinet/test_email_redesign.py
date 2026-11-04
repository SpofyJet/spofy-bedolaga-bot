"""Новый вид писем: у каждого письма с действием — кнопка с глубокой ссылкой в кабинет,
стили переживают почтовики без <style>, текстовая версия сохраняет ссылку кнопки."""

import re

import pytest

from app.cabinet.routes.admin_email_templates import AVAILABLE_LANGUAGES, SAMPLE_CONTEXTS, TEMPLATE_TYPES
from app.cabinet.services import email_layout
from app.cabinet.services.email_layout import inline_email_styles, reset_email_layout_cache
from app.cabinet.services.email_service import EmailService
from app.cabinet.services.email_templates import EmailNotificationTemplates
from app.config import settings
from app.services.notification_types import NotificationType


CABINET = 'https://lk.example.com'

# Письмо -> куда должна вести главная кнопка.
EXPECTED_BUTTON = {
    NotificationType.SUBSCRIPTION_EXPIRING: '/subscriptions',
    NotificationType.SUBSCRIPTION_EXPIRED: '/subscriptions',
    NotificationType.SUBSCRIPTION_RENEWED: '/subscriptions',
    NotificationType.SUBSCRIPTION_ACTIVATED: '/connection',
    NotificationType.AUTOPAY_SUCCESS: '/subscriptions',
    NotificationType.AUTOPAY_FAILED: '/subscriptions',
    NotificationType.AUTOPAY_INSUFFICIENT_FUNDS: '/balance/top-up',
    NotificationType.BALANCE_TOPUP: '/subscription/purchase',
    NotificationType.DAILY_DEBIT: '/balance/top-up',
    NotificationType.DAILY_INSUFFICIENT_FUNDS: '/balance/top-up',
    NotificationType.WINBACK_EXPIRED_1D: '/subscriptions',
    NotificationType.WINBACK_DISCOUNT: '/subscription/purchase',
    NotificationType.WINBACK_TRIAL_ENDING: '/subscription/purchase',
}


@pytest.fixture(autouse=True)
def _cabinet(monkeypatch):
    monkeypatch.setattr(settings, 'CABINET_URL', CABINET, raising=False)
    reset_email_layout_cache()
    yield
    reset_email_layout_cache()


def _buttons(body: str) -> list[str]:
    return re.findall(r'<a href="([^"]+)" class="button[^"]*"', body)


@pytest.mark.parametrize('ntype', list(EXPECTED_BUTTON))
@pytest.mark.parametrize('lang', ['ru', 'en'])
def test_actionable_email_has_deep_link_button(ntype, lang):
    sample = SAMPLE_CONTEXTS.get(ntype.value, {})
    template = EmailNotificationTemplates().get_template(ntype, lang, dict(sample))
    buttons = _buttons(template['body_html'])
    assert buttons, f'{ntype.value}/{lang}: нет кнопки'
    assert buttons[0].startswith(CABINET + EXPECTED_BUTTON[ntype]), buttons[0]


@pytest.mark.parametrize('type_key', [t['type'] for t in TEMPLATE_TYPES])
@pytest.mark.parametrize('lang', AVAILABLE_LANGUAGES)
def test_no_placeholder_or_python_artifacts_left(type_key, lang):
    from app.cabinet.routes.admin_email_templates import _get_default_template

    template = _get_default_template(type_key, lang, SAMPLE_CONTEXTS[type_key])
    fragment = email_layout.extract_content_fragment(template['body_html']) or ''
    assert not re.search(r'\{[a-z_]+\}', fragment), f'{type_key}/{lang}: литерал плейсхолдера в письме'
    assert 'None' not in template['subject']
    # Фрагмент без inline-фона: иначе сохранённый из редактора шаблон потерял бы обёртку.
    assert 'background' not in fragment.lower(), f'{type_key}/{lang}'


def test_auth_emails_have_button_and_plain_link():
    sent = {}
    for ntype, ctx, url in (
        (
            NotificationType.EMAIL_VERIFICATION,
            {'verification_url': f'{CABINET}/verify-email?token=abc'},
            '/verify-email',
        ),
        (NotificationType.PASSWORD_RESET, {'reset_url': f'{CABINET}/reset-password?token=abc'}, '/reset-password'),
    ):
        for lang in ('ru', 'en'):
            body = EmailNotificationTemplates().get_template(ntype, lang, {**ctx, 'expire_hours': 24})['body_html']
            buttons = _buttons(body)
            assert buttons and url in buttons[0]
            assert body.count(f'{CABINET}{url}?token=abc') >= 3  # кнопка + запасная ссылка (href и текст)
            sent[(ntype, lang)] = body
    assert 'Подтвердить email' in sent[(NotificationType.EMAIL_VERIFICATION, 'ru')]


def test_email_change_code_puts_code_in_subject_and_big_block():
    template = EmailNotificationTemplates().get_template(
        NotificationType.EMAIL_CHANGE_CODE, 'ru', {'code': '482913', 'expire_minutes': 10}
    )
    assert template['subject'] == 'Код подтверждения: 482913'
    assert '<div class="code">482913</div>' in template['body_html']
    assert '10 мин' in template['body_html']


def test_expiring_subject_uses_russian_plural():
    t = EmailNotificationTemplates()
    subjects = [
        t.get_template(NotificationType.SUBSCRIPTION_EXPIRING, 'ru', {'days_left': n, 'expires_at': '05.12'})['subject']
        for n in (1, 3, 5)
    ]
    assert subjects == [
        'Подписка закончится через 1 день',
        'Подписка закончится через 3 дня',
        'Подписка закончится через 5 дней',
    ]


def test_known_subscription_links_straight_to_its_renew_screen():
    body = EmailNotificationTemplates().get_template(
        NotificationType.SUBSCRIPTION_EXPIRED, 'ru', {'subscription_id': 42}
    )['body_html']
    assert _buttons(body)[0] == f'{CABINET}/subscriptions/42/renew'


def test_legacy_languages_keep_their_texts():
    body = EmailNotificationTemplates().get_template(
        NotificationType.EMAIL_VERIFICATION, 'ua', {'verification_url': 'https://x/v?t=1'}
    )['body_html']
    assert 'Підтвердити email' in body


def test_inliner_styles_default_layout_once_and_skips_foreign_documents():
    body = EmailNotificationTemplates().get_template(NotificationType.SUBSCRIPTION_EXPIRED, 'ru', {})['body_html']
    inlined = inline_email_styles(body)
    button = re.search(r'<a href="[^"]+" class="button"[^>]*>', inlined).group(0)
    assert 'background-color:#2563eb' in button and 'color:#ffffff' in button
    assert 'data-sp-email="inlined"' in inlined
    assert inline_email_styles(inlined) == inlined, 'повторная отправка из очереди не должна дублировать стили'

    foreign = '<!DOCTYPE html><html><body><p class="highlight">x</p></body></html>'
    assert inline_email_styles(foreign) == foreign


def test_inliner_keeps_explicit_styles_last():
    doc = '<html><body data-sp-email="1"><p class="note" style="color:red">x</p></body></html>'
    out = inline_email_styles(doc)
    style = re.search(r'style="([^"]+)"', out).group(1)
    assert style.endswith('color:red')
    assert 'font-size:13px' in style


def test_plain_text_keeps_button_link_and_drops_preheader():
    body = EmailNotificationTemplates()._get_base_template(
        '<h2>Т</h2><p class="cta"><a href="https://x/renew" class="button">Продлить подписку</a></p>',
        'ru',
        preheader='Скрытая строка',
    )
    text = EmailService._html_to_plain_text(body)
    assert 'Продлить подписку: https://x/renew' in text
    assert 'Скрытая строка' not in text
    assert '&zwnj;' not in text and '&#847;' not in text


def test_payment_reminder_uses_shared_layout(monkeypatch):
    import asyncio
    import importlib

    from app.services import payment_reminder_email

    email_service_module = importlib.import_module('app.cabinet.services.email_service')

    captured = {}

    def fake_send(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(type(settings), 'is_notifications_enabled', lambda self: True)
    monkeypatch.setattr(email_service_module.email_service, 'is_configured', lambda: True)
    monkeypatch.setattr(email_service_module.email_service, 'send_email', fake_send)
    sent = asyncio.run(
        payment_reminder_email.send_payment_reminder_email(
            email='a@b.c', language='ru', user_id=0, kind='payment', amount_kopeks=31550
        )
    )
    assert sent
    body = captured['body_html']
    assert 'data-sp-email="1"' in body
    assert _buttons(body) == [f'{CABINET}/balance/top-up?amount=316']
