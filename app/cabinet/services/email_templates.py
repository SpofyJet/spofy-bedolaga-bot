"""
Email notification templates for different notification types.

Supports multiple languages: ru, en, zh, ua, fa
"""

import html
from collections.abc import Callable
from functools import partial
from typing import Any

from app.config import settings
from app.services.notification_types import NotificationType


class EmailNotificationTemplates:
    """HTML email templates for user notifications."""

    # Плейсхолдеры получателя, которые обёртка берёт из контекста письма.
    _LAYOUT_RECIPIENT_VARS = ('username', 'email', 'date')

    def __init__(self):
        self.service_name = settings.SMTP_FROM_NAME or 'VPN Service'
        self.cabinet_url = settings.CABINET_URL
        # Контекст текущего рендера — чтобы обёртка знала получателя
        # ({username}, {email}), не протаскивая его через все 50 билдеров.
        self._render_context: dict[str, Any] | None = None

    # WEBHOOK_* уведомления делят один generic-билдер: значение типа -> ключ
    # копирайта в WEBHOOK_EMAIL_COPY. Ключи — строки, а не enum: NotificationType
    # импортируется лениво (цикл модулей), а редактору этот список нужен на
    # уровне класса, чтобы собирать свои записи из тех же текстов.
    WEBHOOK_EMAIL_KINDS: dict[str, str] = {
        'webhook_sub_expired': 'sub_expired',
        'webhook_sub_disabled': 'sub_disabled',
        'webhook_sub_enabled': 'sub_enabled',
        'webhook_sub_limited': 'sub_limited',
        'webhook_sub_traffic_reset': 'sub_traffic_reset',
        'webhook_sub_deleted': 'sub_deleted',
        'webhook_sub_revoked': 'sub_revoked',
        'webhook_sub_expiring': 'sub_expiring',
        'webhook_sub_first_connected': 'sub_first_connected',
        'webhook_sub_bandwidth_threshold': 'sub_bandwidth_threshold',
        'webhook_user_not_connected': 'user_not_connected',
        'webhook_device_added': 'device_added',
        'webhook_device_deleted': 'device_deleted',
        'webhook_torrent_detected': 'torrent_detected',
    }

    def _template_map(self) -> dict['NotificationType', Callable[[str, dict[str, Any]], dict[str, str]]]:
        """Тип уведомления -> билдер письма. Единственный реестр email-шаблонов.

        Список типов в редакторе админки строится отсюда же (supported_types):
        рукописная копия рядом отставала, и письма уходили со стандартным
        шаблоном, который нельзя было поменять.
        """
        template_map: dict[NotificationType, Callable[[str, dict[str, Any]], dict[str, str]]] = {
            NotificationType.BALANCE_TOPUP: self._balance_topup_template,
            NotificationType.BALANCE_CHANGE: self._balance_change_template,
            NotificationType.SUBSCRIPTION_EXPIRING: self._subscription_expiring_template,
            NotificationType.SUBSCRIPTION_EXPIRED: self._subscription_expired_template,
            NotificationType.SUBSCRIPTION_RENEWED: self._subscription_renewed_template,
            NotificationType.GRACE_ACCESS_GRANTED: self._grace_access_granted_template,
            NotificationType.GRACE_ACCESS_ENDED: self._grace_access_ended_template,
            NotificationType.SUBSCRIPTION_ACTIVATED: self._subscription_activated_template,
            NotificationType.WINBACK_EXPIRED_1D: self._winback_expired_1d_template,
            NotificationType.WINBACK_DISCOUNT: self._winback_discount_template,
            NotificationType.WINBACK_TRIAL_ENDING: self._winback_trial_ending_template,
            NotificationType.AUTOPAY_SUCCESS: self._autopay_success_template,
            NotificationType.AUTOPAY_FAILED: self._autopay_failed_template,
            NotificationType.AUTOPAY_INSUFFICIENT_FUNDS: self._autopay_insufficient_funds_template,
            NotificationType.DAILY_DEBIT: self._daily_debit_template,
            NotificationType.DAILY_INSUFFICIENT_FUNDS: self._daily_insufficient_funds_template,
            NotificationType.BAN_NOTIFICATION: self._ban_template,
            NotificationType.UNBAN_NOTIFICATION: self._unban_template,
            NotificationType.WARNING_NOTIFICATION: self._warning_template,
            NotificationType.REFERRAL_BONUS: self._referral_bonus_template,
            NotificationType.REFERRAL_REGISTERED: self._referral_registered_template,
            NotificationType.REFERRAL_WELCOME: self._referral_welcome_template,
            NotificationType.PARTNER_APPLICATION_APPROVED: self._partner_approved_template,
            NotificationType.PARTNER_APPLICATION_REJECTED: self._partner_rejected_template,
            NotificationType.WITHDRAWAL_APPROVED: self._withdrawal_approved_template,
            NotificationType.WITHDRAWAL_REJECTED: self._withdrawal_rejected_template,
            NotificationType.TRAFFIC_RESET: self._traffic_reset_template,
            NotificationType.PAYMENT_RECEIVED: self._payment_received_template,
            NotificationType.PROMO_OFFER: self._promo_offer_template,
            NotificationType.TICKET_REPLY: self._ticket_reply_template,
            NotificationType.PROMO_GROUP_AUTO_ASSIGNED: self._promo_group_auto_assigned_template,
            NotificationType.EMAIL_VERIFICATION: self._email_verification_template,
            NotificationType.PASSWORD_RESET: self._password_reset_template,
            NotificationType.EMAIL_CHANGE_CODE: self._email_change_code_template,
            NotificationType.GUEST_SUBSCRIPTION_DELIVERED: self._guest_subscription_delivered_template,
            NotificationType.GUEST_ACTIVATION_REQUIRED: self._guest_activation_required_template,
            NotificationType.GUEST_GIFT_RECEIVED: self._guest_gift_received_template,
            NotificationType.GUEST_CABINET_CREDENTIALS: self._guest_cabinet_credentials_template,
            NotificationType.GUEST_GIFT_LINK_BUYER: self._guest_gift_link_buyer_template,
        }
        webhook_map = {
            NotificationType(type_value): partial(self._webhook_event_email, kind)
            for type_value, kind in self.WEBHOOK_EMAIL_KINDS.items()
        }
        return {**template_map, **webhook_map}

    def supported_types(self) -> list['NotificationType']:
        """Типы, у которых есть email-шаблон, — источник истины для списка редактора."""
        return list(self._template_map())

    def get_template(
        self,
        notification_type: 'NotificationType',
        language: str,
        context: dict[str, Any],
    ) -> dict[str, str] | None:
        """
        Get email template for notification type.

        Args:
            notification_type: Type of notification
            language: Language code (ru, en, zh, ua, fa)
            context: Context data for template rendering

        Returns:
            Dict with 'subject', 'body_html', and optionally 'body_text'
        """
        template_func = self._template_map().get(notification_type)
        if not template_func:
            return None

        self._render_context = context
        try:
            return template_func(language, context)
        finally:
            self._render_context = None

    def _wrap_override_template(
        self,
        content: str,
        language: str = 'ru',
        *,
        unsubscribe_url: str = '',
        context: dict[str, Any] | None = None,
    ) -> str:
        """Wrap override template content appropriately based on its structure.

        ``unsubscribe_url`` и ``context`` (данные получателя) нужны только
        обёртке третьего уровня — у полного документа всё уже внутри.

        Three-tier detection:
        1. Full HTML document (<!DOCTYPE or <html>) — return as-is, no wrapping
        2. Styled content (has <style> tag or background CSS) — minimal HTML wrapper
           without forced colors, headers, or footers
        3. Simple HTML fragment — wrap with base template (header, footer, white bg)
           for backward compatibility
        """
        content_stripped = content.strip()
        content_lower = content_stripped.lower()

        # Tier 1: Full HTML document — return as-is
        if content_lower.startswith('<!doctype') or content_lower.startswith('<html'):
            return content_stripped

        # Tier 2: Styled content — minimal wrapper without forced styling
        if '<style' in content_lower or 'background' in content_lower:
            return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0;">
    {content}
</body>
</html>"""

        # Tier 3: Simple HTML fragment — use base template for structure
        self._render_context = context
        try:
            return self._get_base_template(content, language, unsubscribe_url)
        finally:
            self._render_context = None

    def _get_base_template(
        self, content: str, language: str = 'ru', unsubscribe_url: str = '', *, preheader: str = ''
    ) -> str:
        """Wrap content in the email layout — сохранённая в редакторе обёртка, иначе встроенная.

        ``unsubscribe_url`` непустой только у маркетинговых писем — у писем со
        сбросом пароля или чеком отписке взяться неоткуда.
        """
        from .email_layout import render_email_layout, resolve_email_layout

        recipient = {
            key: value
            for key, value in (self._render_context or {}).items()
            if key in self._LAYOUT_RECIPIENT_VARS and value not in (None, '')
        }
        return render_email_layout(
            resolve_email_layout(language),
            language,
            {
                **recipient,
                'content': content,
                'unsubscribe_url': unsubscribe_url,
                'service_name': self.service_name,
                'preheader': preheader,
            },
        )

    def _get_cabinet_button(self, language: str) -> str:
        """Кнопка «Открыть личный кабинет» — для писем без более точного действия."""
        return self._action('cabinet', language)

    def _link_button(self, url: str, language: str, texts: dict[str, str]) -> str:
        """Кнопка с произвольной ссылкой в том же стиле, что кнопка кабинета."""
        return self._button(url, texts.get(language) or texts['en'])

    # ============================================================================
    # Кирпичики писем: заголовок, строки «название — значение», кнопка, примечание
    # ============================================================================
    #
    # Тело письма собирается из классов обёртки (.details, .cta, .button, .note,
    # .code), а не из inline-стилей: перед отправкой inline_email_styles()
    # дублирует их в style="", а редактор получает чистый фрагмент (слово
    # background во фрагменте перевело бы сохранённый шаблон в «свой дизайн»
    # без обёртки).

    # Куда ведёт кнопка письма и как она называется. Пути — реальные экраны кабинета.
    _ACTIONS: dict[str, tuple[str, dict[str, str]]] = {
        'renew': (
            '/subscriptions',
            {
                'ru': 'Продлить подписку',
                'en': 'Renew subscription',
            },
        ),
        'buy': (
            '/subscription/purchase',
            {
                'ru': 'Оформить подписку',
                'en': 'Get a subscription',
            },
        ),
        'topup': (
            '/balance/top-up',
            {
                'ru': 'Пополнить баланс',
                'en': 'Top up balance',
            },
        ),
        'connect': (
            '/connection',
            {'ru': 'Подключить VPN', 'en': 'Connect VPN'},
        ),
        'subscription': (
            '/subscriptions',
            {
                'ru': 'Открыть подписку',
                'en': 'Open subscription',
            },
        ),
        'balance': (
            '/balance',
            {
                'ru': 'Открыть баланс',
                'en': 'Open balance',
            },
        ),
        'cabinet': (
            '',
            {
                'ru': 'Открыть личный кабинет',
                'en': 'Open Dashboard',
            },
        ),
    }

    @staticmethod
    def _ru_days(count: Any) -> str:
        """«1 день», «3 дня», «5 дней» — в теме письма «дн.» выглядит канцелярски."""
        try:
            n = abs(int(count))
        except (TypeError, ValueError):
            return f'{count} дн.'
        if n % 10 == 1 and n % 100 != 11:
            word = 'день'
        elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            word = 'дня'
        else:
            word = 'дней'
        return f'{n} {word}'

    @staticmethod
    def _en_days(count: Any) -> str:
        try:
            n = int(count)
        except (TypeError, ValueError):
            return f'{count} days'
        return f'{n} day' if abs(n) == 1 else f'{n} days'

    def _cabinet_link(self, path: str = '', query: str = '') -> str:
        if not self.cabinet_url:
            return ''
        url = f'{self.cabinet_url.rstrip("/")}{path}'
        return f'{url}?{query}' if query else url

    def _button(self, url: str, text: str, *, secondary: bool = False) -> str:
        """Кнопка письма. Без ссылки — ничего: пустая кнопка хуже никакой."""
        if not url:
            return ''
        css = 'button secondary' if secondary else 'button'
        return (
            f'<p class="cta"><a href="{html.escape(url, quote=True)}" class="{css}" target="_blank">'
            f'{html.escape(text)}</a></p>'
        )

    def _action(self, kind: str, language: str, *, query: str = '', path: str = '', secondary: bool = False) -> str:
        default_path, labels = self._ACTIONS[kind]
        label = labels.get(language) or labels['en']
        return self._button(self._cabinet_link(path or default_path, query), label, secondary=secondary)

    @staticmethod
    def _rows(rows: list[tuple[str, Any]]) -> str:
        """Таблица «название — значение»; пустые значения пропускаются. Значения уже экранированы."""
        cells = ''.join(
            f'<tr><td class="k">{label}</td><td class="v">{value}</td></tr>'
            for label, value in rows
            if value not in (None, '')
        )
        if not cells:
            return ''
        return (
            f'<table role="presentation" class="details" width="100%" cellpadding="0" cellspacing="0">{cells}</table>'
        )

    @staticmethod
    def _letter(title: str, *parts: str) -> str:
        return f'<h2>{title}</h2>' + ''.join(part for part in parts if part)

    def _modern(
        self, subject: str, content: str, language: str, *, preheader: str = '', unsubscribe_url: str = ''
    ) -> dict[str, str]:
        return {
            'subject': subject,
            'body_html': self._get_base_template(content, language, unsubscribe_url, preheader=preheader),
        }

    @staticmethod
    def _modern_lang(language: str) -> str:
        return 'en' if language == 'en' else 'ru'

    def _tariff_value(self, context: dict[str, Any]) -> str:
        return html.escape(str(context.get('tariff_name') or '').strip())

    def _renew_query(self, context: dict[str, Any]) -> tuple[str, str]:
        """Путь продления: известная подписка — сразу её экран продления, иначе список подписок."""
        sub_id = context.get('subscription_id')
        if isinstance(sub_id, int) and sub_id > 0:
            return f'/subscriptions/{sub_id}/renew', ''
        return '', ''

    def _auth_fallback(self, url: str, lang: str) -> str:
        label = 'Кнопка не работает? Откройте ссылку:' if lang == 'ru' else 'Button not working? Open this link:'
        return f'<p class="note">{label}<br><a class="link" href="{url}">{url}</a></p>'

    def render_simple_letter(
        self,
        *,
        language: str,
        title: str,
        body_html: str,
        button_url: str = '',
        button_text: str = '',
        note: str = '',
        unsubscribe_url: str = '',
        preheader: str = '',
    ) -> str:
        """Готовое письмо «заголовок — текст — кнопка — примечание» в общей обёртке.

        Для писем, которые собираются вне реестра типов (напоминания об оплате):
        тот же вид и те же кнопки, что у остальных. ``body_html`` уже экранирован.
        """
        content = self._letter(
            html.escape(title),
            f'<p class="lead">{body_html}</p>',
            self._button(button_url, button_text),
            f'<p class="note">{html.escape(note)}</p>' if note else '',
        )
        return self._get_base_template(content, language, unsubscribe_url, preheader=preheader)

    # ============================================================================
    # Новые тексты (ru/en)
    # ============================================================================

    def _modern_email_verification(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        username = html.escape(str(context.get('username') or ''))
        raw_url = str(context.get('verification_url') or '#')
        url = html.escape(raw_url, quote=True)
        hours = html.escape(str(context.get('expire_hours', 24)))
        if lang == 'ru':
            content = self._letter(
                'Подтвердите email',
                f'<p>Здравствуйте, {username}!</p>' if username else '',
                '<p class="lead">Остался один шаг: нажмите кнопку, и адрес будет подтверждён.</p>',
                self._button(raw_url, 'Подтвердить email'),
                self._auth_fallback(url, lang),
                f'<p class="note">Ссылка действует {hours} ч. Если вы не регистрировались, просто проигнорируйте письмо.</p>',
            )
            return self._modern(
                'Подтвердите email', content, 'ru', preheader=f'Нажмите кнопку в письме — ссылка действует {hours} ч.'
            )
        content = self._letter(
            'Confirm your email',
            f'<p>Hi {username},</p>' if username else '',
            '<p class="lead">One step left: press the button to confirm your address.</p>',
            self._button(raw_url, 'Confirm email'),
            self._auth_fallback(url, lang),
            f'<p class="note">The link is valid for {hours} h. If you didn\'t sign up, just ignore this email.</p>',
        )
        return self._modern(
            'Confirm your email',
            content,
            'en',
            preheader=f'Press the button in this email — the link is valid for {hours} h.',
        )

    def _modern_password_reset(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        username = html.escape(str(context.get('username') or ''))
        raw_url = str(context.get('reset_url') or '#')
        url = html.escape(raw_url, quote=True)
        hours = html.escape(str(context.get('expire_hours', 1)))
        if lang == 'ru':
            content = self._letter(
                'Сброс пароля',
                f'<p>Здравствуйте, {username}!</p>' if username else '',
                '<p class="lead">Мы получили запрос на сброс пароля. Нажмите кнопку и задайте новый.</p>',
                self._button(raw_url, 'Задать новый пароль'),
                self._auth_fallback(url, lang),
                f'<p class="note">Ссылка действует {hours} ч. Не запрашивали сброс? Ничего не делайте — пароль останется прежним.</p>',
            )
            return self._modern(
                'Сброс пароля', content, 'ru', preheader=f'Задайте новый пароль — ссылка действует {hours} ч.'
            )
        content = self._letter(
            'Reset your password',
            f'<p>Hi {username},</p>' if username else '',
            '<p class="lead">We got a request to reset your password. Press the button to set a new one.</p>',
            self._button(raw_url, 'Set a new password'),
            self._auth_fallback(url, lang),
            f'<p class="note">The link is valid for {hours} h. Didn\'t ask for this? Do nothing — your password stays the same.</p>',
        )
        return self._modern(
            'Reset your password', content, 'en', preheader=f'Set a new password — the link is valid for {hours} h.'
        )

    def _modern_email_change_code(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        code = html.escape(str(context.get('code') or ''))
        minutes = html.escape(str(context.get('expire_minutes', 10)))
        code_block = f'<div class="code">{code}</div>'
        if lang == 'ru':
            content = self._letter(
                'Код для смены email',
                '<p class="lead">Введите этот код в кабинете, чтобы подтвердить новый адрес:</p>',
                code_block,
                f'<p class="note">Код действует {minutes} мин. Если вы не меняли email, проигнорируйте письмо — адрес останется прежним.</p>',
            )
            return self._modern(f'Код подтверждения: {code}', content, 'ru', preheader=f'Код действует {minutes} мин.')
        content = self._letter(
            'Your email change code',
            '<p class="lead">Enter this code in your dashboard to confirm the new address:</p>',
            code_block,
            f'<p class="note">The code is valid for {minutes} min. If you didn\'t change your email, ignore this message — nothing changes.</p>',
        )
        return self._modern(f'Your code: {code}', content, 'en', preheader=f'The code is valid for {minutes} min.')

    def _modern_subscription_expiring(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        days_left = context.get('days_left', 0)
        expires_at = html.escape(str(context.get('expires_at') or ''))
        tariff = self._tariff_value(context)
        path, query = self._renew_query(context)
        if lang == 'ru':
            days = self._ru_days(days_left)
            content = self._letter(
                'Подписка скоро закончится',
                f'<p class="lead">Осталось {days}. Продлите заранее, чтобы VPN не отключился.</p>',
                self._rows([('Тариф', tariff), ('Действует до', expires_at)]),
                self._action('renew', 'ru', path=path, query=query),
            )
            return self._modern(
                f'Подписка закончится через {days}',
                content,
                'ru',
                preheader=f'Действует до {expires_at}. Продлите, чтобы не потерять доступ.' if expires_at else '',
            )
        days = self._en_days(days_left)
        content = self._letter(
            'Your subscription ends soon',
            f'<p class="lead">{days} left. Renew now so your VPN keeps working.</p>',
            self._rows([('Plan', tariff), ('Valid until', expires_at)]),
            self._action('renew', 'en', path=path, query=query),
        )
        return self._modern(
            f'Your subscription ends in {days}',
            content,
            'en',
            preheader=f'Valid until {expires_at}. Renew to keep access.' if expires_at else '',
        )

    def _modern_subscription_expired(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        tariff = self._tariff_value(context)
        path, query = self._renew_query(context)
        if lang == 'ru':
            content = self._letter(
                'Подписка закончилась',
                '<p class="lead">VPN отключён. Продлите подписку — доступ вернётся сразу, ссылка и настройки на устройствах останутся прежними.</p>',
                self._rows([('Тариф', tariff)]),
                self._action('renew', 'ru', path=path, query=query),
            )
            return self._modern(
                'Подписка закончилась — VPN отключён',
                content,
                'ru',
                preheader='Продлите подписку — доступ вернётся сразу.',
            )
        content = self._letter(
            'Your subscription has ended',
            '<p class="lead">VPN is off. Renew and access comes back right away — your link and device settings stay the same.</p>',
            self._rows([('Plan', tariff)]),
            self._action('renew', 'en', path=path, query=query),
        )
        return self._modern(
            'Subscription ended — VPN is off', content, 'en', preheader='Renew and access comes back right away.'
        )

    def _modern_subscription_renewed(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        until = html.escape(str(context.get('new_expires_at') or ''))
        tariff = self._tariff_value(context)
        if lang == 'ru':
            content = self._letter(
                'Подписка продлена',
                '<p class="lead">Всё работает, ничего настраивать не нужно.</p>',
                self._rows([('Тариф', tariff), ('Действует до', until)]),
                self._action('subscription', 'ru'),
            )
            return self._modern(f'Подписка продлена до {until}' if until else 'Подписка продлена', content, 'ru')
        content = self._letter(
            'Subscription renewed',
            '<p class="lead">Everything keeps working, nothing to set up.</p>',
            self._rows([('Plan', tariff), ('Valid until', until)]),
            self._action('subscription', 'en'),
        )
        return self._modern(f'Subscription renewed until {until}' if until else 'Subscription renewed', content, 'en')

    def _modern_subscription_activated(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        until = html.escape(str(context.get('expires_at') or ''))
        tariff = self._tariff_value(context)
        if lang == 'ru':
            content = self._letter(
                'Подписка активна',
                '<p class="lead">Осталось подключить устройство — откройте инструкцию, это займёт минуту.</p>',
                self._rows([('Тариф', tariff), ('Действует до', until)]),
                self._action('connect', 'ru'),
            )
            return self._modern(
                'Подписка активна — подключите VPN', content, 'ru', preheader='Подключение займёт минуту.'
            )
        content = self._letter(
            'Your subscription is active',
            '<p class="lead">Now connect a device — the guide takes about a minute.</p>',
            self._rows([('Plan', tariff), ('Valid until', until)]),
            self._action('connect', 'en'),
        )
        return self._modern(
            'Subscription active — connect your VPN', content, 'en', preheader='Connecting takes about a minute.'
        )

    def _modern_autopay_success(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        amount = html.escape(str(context.get('formatted_amount') or f'{context.get("amount_rubles", 0):.2f} ₽'))
        until = html.escape(str(context.get('new_expires_at') or ''))
        if lang == 'ru':
            content = self._letter(
                'Подписка продлена автоматически',
                '<p class="lead">Автопродление сработало, VPN работает без перерыва.</p>',
                self._rows([('Списано с баланса', amount), ('Действует до', until)]),
                self._action('subscription', 'ru'),
            )
            return self._modern(f'Автопродление: списано {amount}', content, 'ru')
        content = self._letter(
            'Renewed automatically',
            '<p class="lead">Auto-renewal went through, your VPN keeps working.</p>',
            self._rows([('Charged from balance', amount), ('Valid until', until)]),
            self._action('subscription', 'en'),
        )
        return self._modern(f'Auto-renewal: {amount} charged', content, 'en')

    def _modern_autopay_failed(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        reason = html.escape(str(context.get('reason') or ''))
        path, query = self._renew_query(context)
        if lang == 'ru':
            content = self._letter(
                'Автопродление не сработало',
                '<p class="lead">Продлите подписку вручную, чтобы VPN не отключился.</p>',
                self._rows([('Причина', reason)]),
                self._action('renew', 'ru', path=path, query=query),
            )
            return self._modern(
                'Не получилось продлить подписку', content, 'ru', preheader='Продлите вручную, чтобы VPN не отключился.'
            )
        content = self._letter(
            "Auto-renewal didn't go through",
            '<p class="lead">Renew manually so your VPN stays on.</p>',
            self._rows([('Reason', reason)]),
            self._action('renew', 'en', path=path, query=query),
        )
        return self._modern(
            "Couldn't renew your subscription", content, 'en', preheader='Renew manually so your VPN stays on.'
        )

    def _topup_query(self, context: dict[str, Any]) -> str:
        missing = context.get('missing_kopeks')
        if isinstance(missing, int) and missing > 0:
            return f'amount={(missing + 99) // 100}'
        return ''

    def _modern_autopay_insufficient_funds(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        required = html.escape(str(context.get('required_amount') or ''))
        balance = html.escape(str(context.get('current_balance') or ''))
        query = self._topup_query(context)
        if lang == 'ru':
            content = self._letter(
                'Не хватает на автопродление',
                '<p class="lead">Пополните баланс — подписка продлится автоматически, ничего больше делать не нужно.</p>',
                self._rows([('Нужно', required), ('На балансе', balance)]),
                self._action('topup', 'ru', query=query),
            )
            return self._modern(
                'Пополните баланс для автопродления',
                content,
                'ru',
                preheader='Пополните баланс — подписка продлится сама.',
            )
        content = self._letter(
            'Not enough for auto-renewal',
            '<p class="lead">Top up your balance and the subscription renews by itself.</p>',
            self._rows([('Required', required), ('Balance', balance)]),
            self._action('topup', 'en', query=query),
        )
        return self._modern(
            'Top up to keep auto-renewal', content, 'en', preheader='Top up and the subscription renews by itself.'
        )

    def _modern_balance_topup(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        amount = html.escape(str(context.get('formatted_amount') or f'{context.get("amount_rubles", 0):.2f} ₽'))
        balance = html.escape(str(context.get('formatted_balance') or f'{context.get("new_balance_rubles", 0):.2f} ₽'))
        if lang == 'ru':
            content = self._letter(
                f'Зачислено <span class="amount">+{amount}</span>',
                self._rows([('Баланс', balance)]),
                '<p>Деньги на балансе — оформите или продлите подписку в пару нажатий.</p>',
                self._action('buy', 'ru'),
            )
            return self._modern(f'Зачислено {amount}', content, 'ru', preheader=f'Баланс: {balance}')
        content = self._letter(
            f'Credited <span class="amount">+{amount}</span>',
            self._rows([('Balance', balance)]),
            '<p>The money is on your balance — get or renew a subscription in a couple of taps.</p>',
            self._action('buy', 'en'),
        )
        return self._modern(f'{amount} credited', content, 'en', preheader=f'Balance: {balance}')

    def _modern_payment_received(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        amount = html.escape(str(context.get('formatted_amount') or f'{context.get("amount_rubles", 0):.2f} ₽'))
        method = html.escape(str(context.get('payment_method') or ''))
        if lang == 'ru':
            content = self._letter(
                'Оплата получена',
                self._rows([('Сумма', amount), ('Способ', method)]),
                self._action('cabinet', 'ru'),
            )
            return self._modern(f'Оплата получена: {amount}', content, 'ru')
        content = self._letter(
            'Payment received',
            self._rows([('Amount', amount), ('Method', method)]),
            self._action('cabinet', 'en'),
        )
        return self._modern(f'Payment received: {amount}', content, 'en')

    def _modern_daily_debit(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        amount = html.escape(str(context.get('formatted_amount') or f'{context.get("amount_rubles", 0):.2f} ₽'))
        balance = html.escape(str(context.get('formatted_balance') or f'{context.get("new_balance_rubles", 0):.2f} ₽'))
        if lang == 'ru':
            content = self._letter(
                'Списание за сутки',
                self._rows([('Списано', amount), ('Остаток', balance)]),
                '<p class="note">Пополните баланс заранее, чтобы подписка не встала на паузу.</p>',
                self._action('topup', 'ru', secondary=True),
            )
            return self._modern(f'Списано {amount} за сутки', content, 'ru', preheader=f'Остаток: {balance}')
        content = self._letter(
            'Daily charge',
            self._rows([('Charged', amount), ('Remaining', balance)]),
            '<p class="note">Top up in advance so your subscription is not paused.</p>',
            self._action('topup', 'en', secondary=True),
        )
        return self._modern(f'{amount} charged for the day', content, 'en', preheader=f'Remaining: {balance}')

    def _modern_daily_insufficient_funds(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        if lang == 'ru':
            content = self._letter(
                'Не хватает на следующий день',
                '<p class="lead">На балансе недостаточно средств, поэтому подписка будет приостановлена. Пополните баланс — VPN снова заработает.</p>',
                self._action('topup', 'ru'),
            )
            return self._modern(
                'Пополните баланс — подписка встанет на паузу',
                content,
                'ru',
                preheader='Пополните баланс, чтобы VPN продолжил работать.',
            )
        content = self._letter(
            'Not enough for the next day',
            '<p class="lead">Your balance is too low, so the subscription will be paused. Top up and the VPN works again.</p>',
            self._action('topup', 'en'),
        )
        return self._modern(
            'Top up — your subscription will be paused', content, 'en', preheader='Top up to keep your VPN running.'
        )

    def _modern_winback_expired_1d(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        end_date = html.escape(str(context.get('end_date') or ''))
        unsubscribe_url = context.get('unsubscribe_url', '')
        if lang == 'ru':
            content = self._letter(
                'VPN отключён со вчерашнего дня',
                f'<p class="lead">Подписка закончилась{f" {end_date}" if end_date else ""}. Продлите — доступ вернётся сразу, настраивать ничего не нужно.</p>',
                self._action('renew', 'ru'),
            )
            return self._modern(
                'Подписка закончилась — вернуть доступ',
                content,
                'ru',
                preheader='Продлите — VPN заработает сразу.',
                unsubscribe_url=unsubscribe_url,
            )
        content = self._letter(
            'Your VPN has been off since yesterday',
            f'<p class="lead">Your subscription ended{f" on {end_date}" if end_date else ""}. Renew and access comes back right away — nothing to set up.</p>',
            self._action('renew', 'en'),
        )
        return self._modern(
            'Subscription ended — get access back',
            content,
            'en',
            preheader='Renew and your VPN works right away.',
            unsubscribe_url=unsubscribe_url,
        )

    def _modern_winback_discount(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        percent = html.escape(str(context.get('percent', '')))
        expires_at = html.escape(str(context.get('expires_at') or ''))
        unsubscribe_url = context.get('unsubscribe_url', '')
        if lang == 'ru':
            content = self._letter(
                f'Скидка {percent}% на продление',
                '<p class="lead">Скидка уже закреплена за вами и применится к любому тарифу при оплате.</p>',
                self._rows([('Скидка', f'{percent}%'), ('Действует до', expires_at)]),
                self._button(self._cabinet_link('/subscription/purchase'), f'Продлить со скидкой {percent}%'),
            )
            return self._modern(
                f'Скидка {percent}% на продление',
                content,
                'ru',
                preheader=f'Действует до {expires_at}' if expires_at else '',
                unsubscribe_url=unsubscribe_url,
            )
        content = self._letter(
            f'{percent}% off your renewal',
            '<p class="lead">The discount is already on your account and applies to any plan at checkout.</p>',
            self._rows([('Discount', f'{percent}%'), ('Valid until', expires_at)]),
            self._button(self._cabinet_link('/subscription/purchase'), f'Renew with {percent}% off'),
        )
        return self._modern(
            f'{percent}% off your renewal',
            content,
            'en',
            preheader=f'Valid until {expires_at}' if expires_at else '',
            unsubscribe_url=unsubscribe_url,
        )

    def _modern_winback_trial_ending(self, lang: str, context: dict[str, Any]) -> dict[str, str]:
        unsubscribe_url = context.get('unsubscribe_url', '')
        if lang == 'ru':
            content = self._letter(
                'Пробный период скоро закончится',
                '<p class="lead">Оформите подписку, чтобы VPN не отключился. Ссылка и устройства останутся прежними.</p>',
                self._action('buy', 'ru'),
            )
            return self._modern(
                'Пробный период скоро закончится',
                content,
                'ru',
                preheader='Оформите подписку — VPN продолжит работать.',
                unsubscribe_url=unsubscribe_url,
            )
        content = self._letter(
            'Your trial ends soon',
            '<p class="lead">Get a subscription so your VPN keeps working. Your link and devices stay the same.</p>',
            self._action('buy', 'en'),
        )
        return self._modern(
            'Your trial ends soon',
            content,
            'en',
            preheader='Subscribe and your VPN keeps working.',
            unsubscribe_url=unsubscribe_url,
        )

    def _guest_gift_link_buyer_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Email покупателю подарка: ссылка на активацию, чтобы переслать получателю."""
        claim_url = str(context.get('claim_url', '') or '')
        claim_url_html = html.escape(claim_url, quote=True)
        tariff_name = html.escape(str(context.get('tariff_name', '') or ''))
        period_days = context.get('period_days')
        subjects = {
            'ru': 'Ссылка на ваш подарок',
            'en': 'Your gift link',
        }
        details = {
            'ru': f'<p>Подарок: <strong>{tariff_name}</strong>{f" на {period_days} дн." if period_days else ""}</p>'
            if tariff_name
            else '',
            'en': f'<p>Gift: <strong>{tariff_name}</strong>{f" for {period_days} days" if period_days else ""}</p>'
            if tariff_name
            else '',
        }
        button = {
            'ru': 'Открыть ссылку на подарок',
            'en': 'Open gift link',
        }
        link = f'<p><a href="{claim_url_html}">{claim_url_html}</a></p>'
        bodies = {
            'ru': f'<h2>🎁 Спасибо за покупку подарка!</h2><div class="highlight">{details["ru"]}<p>Перешлите эту ссылку тому, кому предназначен подарок, — он активирует его сам:</p>{link}</div>{self._link_button(claim_url, language, button)}',
            'en': f'<h2>🎁 Thanks for your gift purchase!</h2><div class="highlight">{details["en"]}<p>Forward this link to the person the gift is for — they activate it themselves:</p>{link}</div>{self._link_button(claim_url, language, button)}',
        }
        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Balance Templates
    # ============================================================================

    def _balance_topup_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_balance_topup(lang, context)

    def _balance_change_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for balance change notification."""
        amount = context.get('formatted_amount', f'{context.get("amount_rubles", 0):.2f} ₽')
        balance = context.get('formatted_balance', f'{context.get("new_balance_rubles", 0):.2f} ₽')

        subjects = {
            'ru': 'Изменение баланса',
            'en': 'Balance Changed',
        }

        bodies = {
            'ru': f"""
                <h2>Изменение баланса</h2>
                <div class="highlight">
                    <p>Сумма: <strong>{amount}</strong></p>
                    <p>Текущий баланс: <strong>{balance}</strong></p>
                </div>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Balance Changed</h2>
                <div class="highlight">
                    <p>Amount: <strong>{amount}</strong></p>
                    <p>Current balance: <strong>{balance}</strong></p>
                </div>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Subscription Templates
    # ============================================================================

    def _subscription_expiring_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_subscription_expiring(lang, context)

    def _subscription_expired_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_subscription_expired(lang, context)

    def _subscription_renewed_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_subscription_renewed(lang, context)

    WEBHOOK_EMAIL_COPY = {
        'sub_expired': {
            'ru': (
                'Подписка закончилась',
                '<p>Ваша VPN-подписка истекла — доступ отключён.</p><p>Продлите подписку, чтобы вернуться в сервис.</p>',
            ),
            'en': (
                'Subscription expired',
                '<p>Your VPN subscription has expired and access is off.</p><p>Renew it to get back online.</p>',
            ),
        },
        'sub_disabled': {
            'ru': (
                'Подписка приостановлена',
                '<p>Ваша подписка временно отключена.</p><p>Проверьте личный кабинет или напишите в поддержку.</p>',
            ),
            'en': (
                'Subscription suspended',
                '<p>Your subscription has been temporarily disabled.</p><p>Check your dashboard or contact support.</p>',
            ),
        },
        'sub_enabled': {
            'ru': ('Подписка снова активна', '<p>Доступ к VPN восстановлен — можно пользоваться.</p>'),
            'en': ('Subscription re-activated', '<p>Your VPN access has been restored.</p>'),
        },
        'sub_limited': {
            'ru': (
                'Достигнут лимит трафика',
                '<p>Трафик по подписке исчерпан.</p><p>Докупите трафик или дождитесь сброса, чтобы продолжить.</p>',
            ),
            'en': (
                'Traffic limit reached',
                '<p>You have used up your subscription traffic.</p><p>Top up traffic or wait for the reset to continue.</p>',
            ),
        },
        'sub_traffic_reset': {
            'ru': ('Трафик обновлён', '<p>Счётчик трафика сброшен — лимит снова доступен.</p>'),
            'en': ('Traffic reset', '<p>Your traffic counter has been reset — the limit is available again.</p>'),
        },
        'sub_deleted': {
            'ru': (
                'Подписка удалена',
                '<p>Ваша подписка была удалена.</p><p>Если это ошибка — напишите в поддержку.</p>',
            ),
            'en': (
                'Subscription deleted',
                '<p>Your subscription has been deleted.</p><p>If this is a mistake, contact support.</p>',
            ),
        },
        'sub_revoked': {
            'ru': (
                'Ссылка-подписка обновлена',
                '<p>Ваша ссылка-подписка была перевыпущена.</p><p>Импортируйте новую ссылку из личного кабинета.</p>',
            ),
            'en': (
                'Subscription link reissued',
                '<p>Your subscription link has been reissued.</p><p>Import the new link from your dashboard.</p>',
            ),
        },
        'sub_expiring': {
            'ru': (
                'Подписка скоро закончится',
                '<p>Срок действия вашей VPN-подписки подходит к концу.</p><p>Продлите её заранее, чтобы не остаться без доступа.</p>',
            ),
            'en': (
                'Subscription expiring soon',
                '<p>Your VPN subscription is about to expire.</p><p>Renew it in advance to avoid losing access.</p>',
            ),
        },
        'sub_first_connected': {
            'ru': ('Подключение установлено', '<p>Вы успешно подключились к VPN. Приятного пользования!</p>'),
            'en': ('You are connected', '<p>You have successfully connected to the VPN. Enjoy!</p>'),
        },
        'sub_bandwidth_threshold': {
            'ru': (
                'Трафик на исходе',
                '<p>Вы израсходовали большую часть трафика.</p><p>Докупите трафик, чтобы не остаться без доступа.</p>',
            ),
            'en': (
                'Traffic running low',
                '<p>You have used most of your traffic.</p><p>Top up to avoid losing access.</p>',
            ),
        },
        'user_not_connected': {
            'ru': (
                'Нужна помощь с подключением VPN?',
                '<p>Ваша подписка <strong>активна</strong>, но приложение пока не настроено — поэтому VPN не работает.</p><p>Это занимает 5 минут: установите приложение и импортируйте ссылку-подписку. Если что-то не выходит — напишите в поддержку, поможем.</p>',
            ),
            'en': (
                'Need help connecting your VPN?',
                '<p>Your subscription is <strong>active</strong>, but the app is not set up yet — so the VPN is not working.</p><p>It takes 5 minutes: install the app and import your subscription link. If anything goes wrong, contact support.</p>',
            ),
        },
        'device_added': {
            'ru': (
                'Новое устройство подключено',
                '<p>К вашей подписке добавлено устройство{device}.</p><p>Если это были не вы — напишите в поддержку.</p>',
            ),
            'en': (
                'New device connected',
                '<p>A device{device} was added to your subscription.</p><p>If this was not you, contact support.</p>',
            ),
        },
        'device_deleted': {
            'ru': ('Устройство отключено', '<p>Устройство{device} отвязано от вашей подписки.</p>'),
            'en': ('Device removed', '<p>A device{device} was removed from your subscription.</p>'),
        },
        'torrent_detected': {
            'ru': (
                'Обнаружен торрент-трафик',
                '<p>Зафиксирована torrent-активность.</p><p>На VPN она заблокирована — используйте обычные приложения.</p>',
            ),
            'en': (
                'Torrent traffic detected',
                '<p>Torrent activity was detected.</p><p>It is blocked on the VPN — please use regular apps.</p>',
            ),
        },
    }

    def _webhook_event_email(self, kind: str, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Generic email for Remnawave webhook notifications (email-only users).

        Each WEBHOOK_* notification type routes through notification_delivery_service,
        which sends email to email-only users — but these types had no email template,
        so email was silently skipped. This covers all of them.
        """
        lang = language if language in ('ru', 'en') else 'ru'
        copy = self.WEBHOOK_EMAIL_COPY.get(kind, self.WEBHOOK_EMAIL_COPY['user_not_connected'])
        subject, body = copy.get(lang, copy['ru'])

        device = str(context.get('device') or context.get('device_name') or '').strip()
        device_suffix = f' — {html.escape(device)}' if device and device != '—' else ''
        body = body.replace('{device}', device_suffix)

        content = f'<h2>{subject}</h2>{body}{self._webhook_button(kind, language)}'
        return {
            'subject': subject,
            'body_html': self._get_base_template(content, language),
        }

    # Событие панели -> что человеку сделать дальше. Остальные — просто в кабинет.
    _WEBHOOK_ACTIONS = {
        'sub_expired': 'renew',
        'sub_expiring': 'renew',
        'sub_disabled': 'subscription',
        'sub_enabled': 'connect',
        'sub_limited': 'subscription',
        'sub_bandwidth_threshold': 'subscription',
        'sub_traffic_reset': 'connect',
        'sub_revoked': 'connect',
        'sub_deleted': 'buy',
        'user_not_connected': 'connect',
        'sub_first_connected': 'subscription',
        'device_added': 'subscription',
        'device_deleted': 'subscription',
    }

    def _webhook_button(self, kind: str, language: str) -> str:
        return self._action(self._WEBHOOK_ACTIONS.get(kind, 'cabinet'), language)

    # Grace-доступ: подписка кончилась, но на время оставлен доступ к тому, что
    # оператор назвал в GRACE_ACCESS_ALLOWED_SERVICES ({allowed}); {reason} —
    # expired|limited, остальное — числа и даты. Всё экранируется: фразу и имя
    # тарифа пишет оператор.
    GRACE_EMAIL_COPY = {
        'granted': {
            'ru': (
                'Подписка закончилась, но связь оставили',
                '<p>Ваша подписка{tariff} {why}. На <strong>{hours} ч.</strong> доступно только: <strong>{allowed}</strong>. Трафика на это время — {traffic_gb} ГБ, чтобы вы успели продлить подписку.</p><p>Остальное не работает до продления. Доступ действует до <strong>{until}</strong>.</p>',
                {'expired': 'закончилась', 'limited': 'исчерпала трафик'},
            ),
            'en': (
                'Subscription ended, but you are not cut off',
                '<p>Your subscription{tariff} {why}. For <strong>{hours} h</strong> only this stays available: <strong>{allowed}</strong>. You have {traffic_gb} GB of traffic for it, so you can renew.</p><p>Everything else stays off until you renew. Access lasts until <strong>{until}</strong>.</p>',
                {'expired': 'has ended', 'limited': 'has used up its traffic'},
            ),
        },
        'ended': {
            'ru': (
                'Временный доступ закончился',
                '<p>Подписка{tariff} так и не продлена, временный доступ закрыт. Больше не работает и то, что оставалось: <strong>{allowed}</strong>.</p><p>Продлите подписку, чтобы вернуть VPN.</p>',
                {},
            ),
            'en': (
                'Temporary access has ended',
                '<p>Subscription{tariff} was not renewed, temporary access is closed. What was still available is now off too: <strong>{allowed}</strong>.</p><p>Renew to get your VPN back.</p>',
                {},
            ),
        },
    }

    def _grace_access_email(self, event: str, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = language if language in ('ru', 'en') else 'ru'
        subject, body, why_by_reason = self.GRACE_EMAIL_COPY[event][lang]
        tariff_name = str(context.get('tariff_name') or '').strip()
        reason = str(context.get('reason') or 'expired').strip().lower()
        values = {
            'tariff': f' «{html.escape(tariff_name)}»' if tariff_name else '',
            'why': why_by_reason.get(reason, why_by_reason.get('expired', '')),
            'allowed': html.escape(str(context.get('allowed') or 'Telegram')),
            'hours': html.escape(str(context.get('hours') or '')),
            'traffic_gb': html.escape(str(context.get('traffic_gb') or '')),
            'until': html.escape(str(context.get('until') or '')),
        }
        for key, value in values.items():
            body = body.replace('{' + key + '}', value)
        content = f'<h2>{subject}</h2>{body}{self._action("renew", language)}'
        return {'subject': subject, 'body_html': self._get_base_template(content, language)}

    def _grace_access_granted_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        return self._grace_access_email('granted', language, context)

    def _grace_access_ended_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        return self._grace_access_email('ended', language, context)

    def _winback_expired_1d_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_winback_expired_1d(lang, context)

    def _winback_discount_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_winback_discount(lang, context)

    def _winback_trial_ending_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_winback_trial_ending(lang, context)

    def _subscription_activated_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_subscription_activated(lang, context)

    # ============================================================================
    # Autopay Templates
    # ============================================================================

    def _autopay_success_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_autopay_success(lang, context)

    def _autopay_failed_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_autopay_failed(lang, context)

    def _autopay_insufficient_funds_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_autopay_insufficient_funds(lang, context)

    # ============================================================================
    # Daily Subscription Templates
    # ============================================================================

    def _daily_debit_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_daily_debit(lang, context)

    def _daily_insufficient_funds_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_daily_insufficient_funds(lang, context)

    def _traffic_reset_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for traffic reset notification."""
        subjects = {
            'ru': 'Трафик обновлён',
            'en': 'Traffic Reset',
        }

        bodies = {
            'ru': f"""
                <h2>Трафик обновлён</h2>
                <div class="highlight success">
                    <p>Ваш трафик был сброшен. Вы можете продолжить использование VPN.</p>
                </div>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Traffic Reset</h2>
                <div class="highlight success">
                    <p>Your traffic has been reset. You can continue using the VPN.</p>
                </div>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Account Status Templates
    # ============================================================================

    def _ban_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for ban notification."""
        reason = html.escape(context.get('reason', ''))

        subjects = {
            'ru': 'Аккаунт заблокирован',
            'en': 'Account Suspended',
        }

        bodies = {
            'ru': f"""
                <h2>Аккаунт заблокирован</h2>
                <div class="highlight danger">
                    <p>Ваш аккаунт был заблокирован.</p>
                    {f'<p>Причина: {reason}</p>' if reason else ''}
                </div>
                <p>Если вы считаете, что это ошибка, обратитесь в поддержку.</p>
            """,
            'en': f"""
                <h2>Account Suspended</h2>
                <div class="highlight danger">
                    <p>Your account has been suspended.</p>
                    {f'<p>Reason: {reason}</p>' if reason else ''}
                </div>
                <p>If you believe this is an error, please contact support.</p>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _unban_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for unban notification."""
        subjects = {
            'ru': 'Аккаунт разблокирован',
            'en': 'Account Reactivated',
        }

        bodies = {
            'ru': f"""
                <h2>Аккаунт разблокирован</h2>
                <div class="highlight success">
                    <p>Ваш аккаунт был разблокирован.</p>
                    <p>Вы снова можете пользоваться сервисом.</p>
                </div>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Account Reactivated</h2>
                <div class="highlight success">
                    <p>Your account has been reactivated.</p>
                    <p>You can use the service again.</p>
                </div>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _warning_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for warning notification."""
        message = html.escape(context.get('message', ''))

        subjects = {
            'ru': 'Предупреждение',
            'en': 'Warning',
        }

        bodies = {
            'ru': f"""
                <h2>Предупреждение</h2>
                <div class="highlight warning">
                    {f'<p>{message}</p>' if message else '<p>Вы получили предупреждение от администрации.</p>'}
                </div>
            """,
            'en': f"""
                <h2>Warning</h2>
                <div class="highlight warning">
                    {f'<p>{message}</p>' if message else '<p>You have received a warning from the administration.</p>'}
                </div>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Referral Templates
    # ============================================================================

    def _referral_bonus_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for referral bonus notification.

        Награда может быть выдана днями подписки, а не деньгами. В копейках такая
        награда честно нулевая, поэтому текст строится по ``formatted_reward`` —
        единственному полю, верному и для денег, и для дней, и для их сочетания.
        Без него письмо о выданных семи днях уходит как «Реферальный бонус: +0.00 ₽».
        """
        bonus = context.get('formatted_reward') or context.get(
            'formatted_bonus', f'{context.get("bonus_rubles", 0):.2f} ₽'
        )
        referral_name = html.escape(context.get('referral_name', ''))
        raw_level = context.get('level', 1)
        try:
            show_level = int(raw_level or 1) > 1
        except (TypeError, ValueError):
            # Редактор шаблонов рендерит их с токенами вида '{level}'. Уровень там
            # неизвестен, но блок обязан попасть в payload — иначе админ его просто
            # не увидит и не сможет отредактировать.
            show_level = True
        level_label = html.escape(str(raw_level))
        level_note_ru = f'<p>Уровень вашей сети: {level_label}</p>' if show_level else ''
        level_note_en = f'<p>Network level: {level_label}</p>' if show_level else ''

        subjects = {
            'ru': f'Реферальный бонус: +{bonus}',
            'en': f'Referral bonus: +{bonus}',
        }

        bodies = {
            'ru': f"""
                <h2>Реферальный бонус!</h2>
                <div class="highlight success">
                    <p>Вы получили реферальный бонус: <span class="amount">+{bonus}</span></p>
                    {f'<p>Благодаря пользователю: {referral_name}</p>' if referral_name else ''}
                    {level_note_ru}
                </div>
                <p>Продолжайте приглашать друзей и зарабатывайте больше!</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Referral Bonus!</h2>
                <div class="highlight success">
                    <p>You received a referral bonus: <span class="amount">+{bonus}</span></p>
                    {f'<p>Thanks to: {referral_name}</p>' if referral_name else ''}
                    {level_note_en}
                </div>
                <p>Keep inviting friends and earn more!</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _promo_offer_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for personal promo offer notification.

        ``message_html`` — уже отрендеренный текст предложения (Telegram-HTML:
        b/i/code — валидный HTML-фрагмент, переносы строк заменены на <br>).
        Пишется админом или собирается дефолтным билдером — доверенный контент,
        не экранируем.
        """
        message_html = context.get('message_html', '')
        valid_hours = int(context.get('valid_hours', 0) or 0)
        discount_percent = int(context.get('discount_percent', 0) or 0)

        if discount_percent > 0:
            subjects = {
                'ru': f'🎁 Персональное предложение: скидка {discount_percent}%',
                'en': f'🎁 Personal offer: {discount_percent}% off',
            }
        else:
            subjects = {
                'ru': '🎁 Персональное предложение',
                'en': '🎁 Personal offer',
            }

        valid_lines = {
            'ru': f'<p>⏰ Предложение действует <b>{valid_hours} ч.</b></p>' if valid_hours else '',
            'en': f'<p>⏰ The offer is valid for <b>{valid_hours} h.</b></p>' if valid_hours else '',
        }

        bodies = {
            'ru': f"""
                <h2>Персональное предложение</h2>
                <div class="highlight">
                    <p>{message_html}</p>
                </div>
                {valid_lines['ru']}
                <p>Активировать предложение можно в личном кабинете.</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Personal Offer</h2>
                <div class="highlight">
                    <p>{message_html}</p>
                </div>
                {valid_lines['en']}
                <p>You can activate the offer in your account.</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(
                bodies.get(language, bodies['ru']), language, context.get('unsubscribe_url', '')
            ),
        }

    def _referral_registered_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for new referral registered notification."""
        referral_name = html.escape(context.get('referral_name', ''))

        subjects = {
            'ru': 'Новый реферал зарегистрирован',
            'en': 'New Referral Registered',
        }

        bodies = {
            'ru': f"""
                <h2>Новый реферал!</h2>
                <div class="highlight success">
                    <p>По вашей ссылке зарегистрировался новый пользователь{f': <strong>{referral_name}</strong>' if referral_name else ''}.</p>
                </div>
                <p>Вы будете получать бонусы с его пополнений!</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>New Referral!</h2>
                <div class="highlight success">
                    <p>A new user registered using your link{f': <strong>{referral_name}</strong>' if referral_name else ''}.</p>
                </div>
                <p>You will receive bonuses from their top-ups!</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _referral_welcome_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for the newcomer who registered by a referral link.

        Приглашённому обещают не выплату, а условие («7 дн. подписки», «100 ₽ при
        первом пополнении от 500 ₽») — оно приходит готовой фразой в
        ``bonus_promise``; пустая фраза — блок с бонусом не показывается.
        """
        referrer_name = html.escape(context.get('referrer_name', '') or '')
        bonus_promise = html.escape(context.get('bonus_promise', '') or '')
        by_whom_ru = f' пользователя <strong>{referrer_name}</strong>' if referrer_name else ''
        by_whom_en = f' of <strong>{referrer_name}</strong>' if referrer_name else ''
        promise_ru = f'<p>Ваш бонус: <span class="amount">{bonus_promise}</span></p>' if bonus_promise else ''
        promise_en = f'<p>Your bonus: <span class="amount">{bonus_promise}</span></p>' if bonus_promise else ''

        subjects = {
            'ru': 'Добро пожаловать по приглашению',
            'en': 'Welcome by invitation',
        }

        bodies = {
            'ru': f"""
                <h2>Добро пожаловать!</h2>
                <div class="highlight success">
                    <p>Вы зарегистрировались по реферальной ссылке{by_whom_ru}.</p>
                    {promise_ru}
                </div>
                <p>Рады видеть вас среди наших пользователей!</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Welcome!</h2>
                <div class="highlight success">
                    <p>You signed up using the referral link{by_whom_en}.</p>
                    {promise_en}
                </div>
                <p>Glad to have you with us!</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Partner Templates
    # ============================================================================

    def _partner_approved_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for partner application approved notification."""
        commission = context.get('commission_percent', 0)
        comment = html.escape(context.get('comment', ''))

        subjects = {
            'ru': 'Заявка на партнёрство одобрена',
            'en': 'Partner Application Approved',
        }

        bodies = {
            'ru': f"""
                <h2>Заявка на партнёрство одобрена!</h2>
                <div class="highlight success">
                    <p>Ваша заявка на партнёрство была одобрена.</p>
                    <p>Ваша комиссия: <strong>{commission}%</strong></p>
                    {f'<p>Комментарий: {comment}</p>' if comment else ''}
                </div>
                <p>Теперь вы можете приглашать пользователей и получать вознаграждение!</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Partner Application Approved!</h2>
                <div class="highlight success">
                    <p>Your partner application has been approved.</p>
                    <p>Your commission rate: <strong>{commission}%</strong></p>
                    {f'<p>Comment: {comment}</p>' if comment else ''}
                </div>
                <p>You can now invite users and earn rewards!</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _partner_rejected_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for partner application rejected notification."""
        comment = html.escape(context.get('comment', ''))

        subjects = {
            'ru': 'Заявка на партнёрство отклонена',
            'en': 'Partner Application Rejected',
        }

        bodies = {
            'ru': f"""
                <h2>Заявка на партнёрство отклонена</h2>
                <div class="highlight danger">
                    <p>К сожалению, ваша заявка на партнёрство была отклонена.</p>
                    {f'<p>Причина: {comment}</p>' if comment else ''}
                </div>
                <p>Вы можете подать новую заявку позже.</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Partner Application Rejected</h2>
                <div class="highlight danger">
                    <p>Unfortunately, your partner application has been rejected.</p>
                    {f'<p>Reason: {comment}</p>' if comment else ''}
                </div>
                <p>You can submit a new application later.</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Withdrawal Templates
    # ============================================================================

    def _withdrawal_approved_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for withdrawal approved notification."""
        amount = context.get('formatted_amount', f'{context.get("amount_rubles", 0):.2f} ₽')
        comment = html.escape(context.get('comment', ''))

        subjects = {
            'ru': f'Запрос на вывод {amount} одобрен',
            'en': f'Withdrawal request for {amount} approved',
        }

        bodies = {
            'ru': f"""
                <h2>Запрос на вывод одобрен!</h2>
                <div class="highlight success">
                    <p>Ваш запрос на вывод средств одобрен.</p>
                    <p>Сумма: <span class="amount">{amount}</span></p>
                    {f'<p>Комментарий: {comment}</p>' if comment else ''}
                </div>
                <p>Средства будут переведены в ближайшее время.</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Withdrawal Request Approved!</h2>
                <div class="highlight success">
                    <p>Your withdrawal request has been approved.</p>
                    <p>Amount: <span class="amount">{amount}</span></p>
                    {f'<p>Comment: {comment}</p>' if comment else ''}
                </div>
                <p>Funds will be transferred shortly.</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _withdrawal_rejected_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for withdrawal rejected notification."""
        amount = context.get('formatted_amount', f'{context.get("amount_rubles", 0):.2f} ₽')
        comment = html.escape(context.get('comment', ''))

        subjects = {
            'ru': f'Запрос на вывод {amount} отклонён',
            'en': f'Withdrawal request for {amount} rejected',
        }

        bodies = {
            'ru': f"""
                <h2>Запрос на вывод отклонён</h2>
                <div class="highlight danger">
                    <p>Ваш запрос на вывод средств был отклонён.</p>
                    <p>Сумма: <strong>{amount}</strong></p>
                    {f'<p>Причина: {comment}</p>' if comment else ''}
                </div>
                <p>Средства возвращены на ваш баланс.</p>
                {self._get_cabinet_button(language)}
            """,
            'en': f"""
                <h2>Withdrawal Request Rejected</h2>
                <div class="highlight danger">
                    <p>Your withdrawal request has been rejected.</p>
                    <p>Amount: <strong>{amount}</strong></p>
                    {f'<p>Reason: {comment}</p>' if comment else ''}
                </div>
                <p>Funds have been returned to your balance.</p>
                {self._get_cabinet_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Payment Templates
    # ============================================================================

    def _payment_received_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_payment_received(lang, context)

    # ============================================================================
    # Support Ticket Templates
    # ============================================================================

    def _get_support_button(self, language: str) -> str:
        """Get support section link button HTML."""
        if not self.cabinet_url:
            return ''

        texts = {
            'ru': 'Открыть обращение',
            'en': 'Open request',
        }
        return self._button(self._cabinet_link('/support'), texts.get(language) or texts['en'])

    def _promo_group_auto_assigned_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Промогруппа назначена автоматически за траты — какие скидки теперь действуют."""
        group_name = html.escape(str(context.get('group_name') or ''))
        total_spent = html.escape(str(context.get('total_spent') or ''))
        period_discounts = html.escape(str(context.get('period_discounts') or ''))

        def _percent(key: str) -> int:
            try:
                return max(0, int(context.get(key) or 0))
            except (TypeError, ValueError):
                return 0

        labels = {
            'ru': ('Серверы', 'Трафик', 'Доп. устройства', 'За длительный период'),
            'en': ('Servers', 'Traffic', 'Extra devices', 'Long-term periods'),
        }
        servers, traffic, devices, periods = labels.get(language, labels['ru'])
        items = [
            f'<li>{label}: <strong>{percent}%</strong></li>'
            for label, percent in (
                (servers, _percent('server_discount')),
                (traffic, _percent('traffic_discount')),
                (devices, _percent('device_discount')),
            )
            if percent
        ]
        if period_discounts:
            items.append(f'<li>{periods}: {period_discounts}</li>')
        discounts_html = f'<ul>{"".join(items)}</ul>' if items else ''

        subjects = {
            'ru': f'Новая промогруппа: {group_name}',
            'en': f'New promo group: {group_name}',
        }
        intros = {
            'ru': (
                f'Вы потратили у нас {total_spent} — спасибо! Теперь для вас постоянно действуют скидки:'
                if items
                else f'Вы потратили у нас {total_spent} — спасибо! Вас перевели в новую промогруппу.'
            ),
            'en': (
                f'You have spent {total_spent} with us — thank you! These discounts now apply to you permanently:'
                if items
                else f'You have spent {total_spent} with us — thank you! You have been moved to a new promo group.'
            ),
        }
        subject = subjects.get(language, subjects['ru'])
        intro = intros.get(language, intros['ru'])
        content = (
            f'<h2>{subject}</h2><div class="highlight"><p>{intro}</p>{discounts_html}</div>'
            f'{self._get_cabinet_button(language)}'
        )
        return {'subject': subject, 'body_html': self._get_base_template(content, language)}

    def _ticket_reply_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for a support reply in a ticket."""
        ticket_id = context.get('ticket_id', '')
        # Экранируем ПОСЛЕ обрезки превью на стороне вызывающего кода: ответ
        # поддержки вполне может содержать угловые скобки («откройте <config>»).
        preview = html.escape(str(context.get('reply_preview', '') or '')).replace('\n', '<br>')
        has_photo = bool(context.get('has_photo'))

        subjects = {
            'ru': f'Ответ по тикету #{ticket_id}',
            'en': f'Reply to ticket #{ticket_id}',
        }

        photo_notes = {
            'ru': '<p>К ответу приложено изображение — оно доступно в кабинете.</p>',
            'en': '<p>The reply includes an image — it is available in your dashboard.</p>',
        }
        photo_note = photo_notes.get(language, photo_notes['ru']) if has_photo else ''

        bodies = {
            'ru': f"""
                <h2>Ответ поддержки по тикету #{ticket_id}</h2>
                <div class="highlight">
                    {f'<p>{preview}</p>' if preview else '<p>Поддержка ответила на ваше обращение.</p>'}
                </div>
                {photo_note}
                <p>Ответить можно в личном кабинете.</p>
                {self._get_support_button(language)}
            """,
            'en': f"""
                <h2>Support replied to ticket #{ticket_id}</h2>
                <div class="highlight">
                    {f'<p>{preview}</p>' if preview else '<p>Support has replied to your request.</p>'}
                </div>
                {photo_note}
                <p>You can reply from your dashboard.</p>
                {self._get_support_button(language)}
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    # ============================================================================
    # Auth Email Templates
    # ============================================================================

    def _email_verification_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_email_verification(lang, context)

    def _password_reset_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_password_reset(lang, context)

    def _email_change_code_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        lang = self._modern_lang(language)
        return self._modern_email_change_code(lang, context)

    # ============================================================================
    # Guest Purchase Templates
    # ============================================================================

    def _guest_subscription_delivered_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for guest subscription delivered notification."""
        tariff_name = html.escape(context.get('tariff_name', ''))
        period_days = context.get('period_days', 0)
        cabinet_url = html.escape(context.get('cabinet_url', ''))
        cabinet_email = html.escape(context.get('cabinet_email', ''))
        cabinet_password = context.get('cabinet_password', '')

        subjects = {
            'ru': 'Ваша VPN подписка готова',
            'en': 'Your VPN subscription is ready',
        }

        creds_block_ru = (
            f"""
                <div class="highlight">
                    <p><strong>Данные для входа в личный кабинет:</strong></p>
                    <p><strong>Email:</strong> <code>{cabinet_email}</code></p>
                    <p><strong>Пароль:</strong> <code>{cabinet_password}</code></p>
                </div>
        """
            if cabinet_password
            else ''
        )

        creds_block_en = (
            f"""
                <div class="highlight">
                    <p><strong>Your cabinet login credentials:</strong></p>
                    <p><strong>Email:</strong> <code>{cabinet_email}</code></p>
                    <p><strong>Password:</strong> <code>{cabinet_password}</code></p>
                </div>
        """
            if cabinet_password
            else ''
        )

        bodies = {
            'ru': f"""
                <h2>Ваша VPN подписка готова!</h2>
                <div class="highlight success">
                    <p>Тариф: <strong>{tariff_name}</strong></p>
                    <p>Период: <strong>{period_days} дней</strong></p>
                </div>
                {creds_block_ru}
                <p>Подписка активирована в вашем личном кабинете.</p>
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Перейти в личный кабинет</a></p>
            """,
            'en': f"""
                <h2>Your VPN subscription is ready!</h2>
                <div class="highlight success">
                    <p>Plan: <strong>{tariff_name}</strong></p>
                    <p>Period: <strong>{period_days} days</strong></p>
                </div>
                {creds_block_en}
                <p>Your subscription has been activated in your cabinet.</p>
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Go to Cabinet</a></p>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _guest_activation_required_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for guest purchase pending activation (user already has a subscription)."""
        tariff_name = html.escape(context.get('tariff_name', ''))
        period_days = context.get('period_days', 0)
        success_page_url = html.escape(context.get('success_page_url', ''))
        gift_message = context.get('gift_message')
        is_gift = context.get('is_gift', False)

        gift_block_ru = ''
        gift_block_en = ''
        if is_gift and gift_message:
            escaped_msg = html.escape(gift_message)
            gift_block_ru = f'<div class="highlight"><p><em>Сообщение: {escaped_msg}</em></p></div>'
            gift_block_en = f'<div class="highlight"><p><em>Message: {escaped_msg}</em></p></div>'

        subjects = {
            'ru': 'Требуется активация подписки',
            'en': 'Subscription activation required',
        }

        bodies = {
            'ru': f"""
                <h2>Требуется активация подписки</h2>
                {gift_block_ru}
                <div class="highlight">
                    <p>Тариф: <strong>{tariff_name}</strong></p>
                    <p>Период: <strong>{period_days} дней</strong></p>
                </div>
                <p class="warning">У вас уже есть активная подписка. Активация новой заменит текущую.</p>
                <p style="text-align: center;"><a href="{success_page_url}" class="button">Активировать подписку</a></p>
            """,
            'en': f"""
                <h2>Subscription activation required</h2>
                {gift_block_en}
                <div class="highlight">
                    <p>Plan: <strong>{tariff_name}</strong></p>
                    <p>Period: <strong>{period_days} days</strong></p>
                </div>
                <p class="warning">You already have an active subscription. Activating will replace your current one.</p>
                <p style="text-align: center;"><a href="{success_page_url}" class="button">Activate subscription</a></p>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _guest_gift_received_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for gift subscription received notification."""
        tariff_name = html.escape(context.get('tariff_name', ''))
        period_days = context.get('period_days', 0)
        gift_message = context.get('gift_message')
        cabinet_password = context.get('cabinet_password')
        cabinet_email = html.escape(context.get('cabinet_email', ''))
        cabinet_url = html.escape(context.get('cabinet_url', ''))

        # Credentials block for gift recipients who got a new cabinet account
        cred_block = {'ru': '', 'en': ''}
        if cabinet_password and cabinet_email:
            escaped_pw = html.escape(cabinet_password)
            cred_block = {
                'ru': f"""
                    <div class="highlight">
                        <p><strong>Данные для входа в личный кабинет:</strong></p>
                        <p>Email: <code>{cabinet_email}</code></p>
                        <p>Пароль: <code>{escaped_pw}</code></p>
                    </div>
                    <p style="text-align: center;"><a href="{cabinet_url}" class="button">Перейти в личный кабинет</a></p>
                """,
                'en': f"""
                    <div class="highlight">
                        <p><strong>Your cabinet login credentials:</strong></p>
                        <p>Email: <code>{cabinet_email}</code></p>
                        <p>Password: <code>{escaped_pw}</code></p>
                    </div>
                    <p style="text-align: center;"><a href="{cabinet_url}" class="button">Go to Cabinet</a></p>
                """,
            }

        gift_block_ru = ''
        gift_block_en = ''
        if gift_message:
            escaped_msg = html.escape(gift_message)
            gift_block_ru = f'<div class="highlight"><p><em>Сообщение: {escaped_msg}</em></p></div>'
            gift_block_en = f'<div class="highlight"><p><em>Message: {escaped_msg}</em></p></div>'

        subjects = {
            'ru': 'Вам подарили VPN подписку!',
            'en': "You've been gifted a VPN subscription!",
        }

        bodies = {
            'ru': f"""
                <h2>Вам подарили VPN подписку!</h2>
                {gift_block_ru}
                <div class="highlight success">
                    <p>Тариф: <strong>{tariff_name}</strong></p>
                    <p>Период: <strong>{period_days} дней</strong></p>
                </div>
                <p>Подписка активирована в личном кабинете.</p>
                {cred_block['ru']}
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Перейти в личный кабинет</a></p>
            """,
            'en': f"""
                <h2>You've been gifted a VPN subscription!</h2>
                {gift_block_en}
                <div class="highlight success">
                    <p>Plan: <strong>{tariff_name}</strong></p>
                    <p>Period: <strong>{period_days} days</strong></p>
                </div>
                <p>Your subscription has been activated in the cabinet.</p>
                {cred_block['en']}
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Go to Cabinet</a></p>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }

    def _guest_cabinet_credentials_template(self, language: str, context: dict[str, Any]) -> dict[str, str]:
        """Template for cabinet login credentials email (sent separately from subscription)."""
        cabinet_email = html.escape(context.get('cabinet_email', ''))
        cabinet_password = html.escape(context.get('cabinet_password', ''))
        cabinet_url = html.escape(context.get('cabinet_url', ''))
        tariff_name = html.escape(context.get('tariff_name', ''))
        period_days = context.get('period_days', 0)

        subjects = {
            'ru': 'Данные для входа в личный кабинет',
            'en': 'Your cabinet login credentials',
        }

        bodies = {
            'ru': f"""
                <h2>Данные для входа в личный кабинет</h2>
                <div class="highlight success">
                    <p>Тариф: <strong>{tariff_name}</strong></p>
                    <p>Период: <strong>{period_days} дней</strong></p>
                </div>
                <div class="highlight">
                    <p><strong>Email:</strong> <code>{cabinet_email}</code></p>
                    <p><strong>Пароль:</strong> <code>{cabinet_password}</code></p>
                </div>
                <p>Сохраните эти данные для входа. Вы можете изменить пароль в настройках кабинета.</p>
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Перейти в личный кабинет</a></p>
            """,
            'en': f"""
                <h2>Your cabinet login credentials</h2>
                <div class="highlight success">
                    <p>Plan: <strong>{tariff_name}</strong></p>
                    <p>Period: <strong>{period_days} days</strong></p>
                </div>
                <div class="highlight">
                    <p><strong>Email:</strong> <code>{cabinet_email}</code></p>
                    <p><strong>Password:</strong> <code>{cabinet_password}</code></p>
                </div>
                <p>Save these credentials. You can change your password in cabinet settings.</p>
                <p style="text-align: center;"><a href="{cabinet_url}" class="button">Go to Cabinet</a></p>
            """,
        }

        return {
            'subject': subjects.get(language, subjects['ru']),
            'body_html': self._get_base_template(bodies.get(language, bodies['ru']), language),
        }


# Singleton instance
email_notification_templates = EmailNotificationTemplates()
