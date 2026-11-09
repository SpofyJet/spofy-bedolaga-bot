"""Balance and payment routes for cabinet."""

import math
import time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot_factory import create_bot
from app.config import settings
from app.database.crud.user import get_user_by_id
from app.database.models import PaymentMethod, Transaction, User
from app.services.payment_method_config_service import get_enabled_methods_for_user
from app.services.payment_service import PaymentService
from app.services.payment_verification_service import (
    SUPPORTED_MANUAL_CHECK_METHODS,
    PendingPayment,
    get_payment_record,
    list_recent_pending_payments,
    method_display_name,
    run_manual_check,
)
from app.utils.currency_converter import currency_converter
from app.utils.miniapp_buttons import strip_leading_emoji, tg_emoji_to_unicode

from ..dependencies import get_cabinet_db, get_current_cabinet_user
from ..schemas.balance import (
    BalanceResponse,
    ManualCheckResponse,
    PaymentMethodResponse,
    PendingPaymentListResponse,
    PendingPaymentResponse,
    StarsInvoiceRequest,
    StarsInvoiceResponse,
    TopUpRequest,
    TopUpResponse,
    TransactionListResponse,
    TransactionResponse,
)


logger = structlog.get_logger(__name__)

router = APIRouter(prefix='/balance', tags=['Cabinet Balance'])


@router.get('', response_model=BalanceResponse)
async def get_balance(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get current user's balance."""
    # Reload user from current session to get fresh data
    # (user object is from different session in get_current_cabinet_user)
    fresh_user = await get_user_by_id(db, user.id)
    if not fresh_user:
        raise HTTPException(status_code=404, detail='User not found')

    return BalanceResponse(
        balance_kopeks=fresh_user.balance_kopeks,
        balance_rubles=fresh_user.balance_kopeks / 100,
    )


@router.get('/transactions', response_model=TransactionListResponse)
async def get_transactions(
    page: int = Query(1, ge=1, description='Page number'),
    per_page: int = Query(20, ge=1, le=100, description='Items per page'),
    type: str | None = Query(None, description='Filter by transaction type'),
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get transaction history."""
    # Base query
    query = select(Transaction).where(Transaction.user_id == user.id)

    # Filter by type
    if type:
        query = query.where(Transaction.type == type)

    # Get total count
    count_query = select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id)
    if type:
        count_query = count_query.where(Transaction.type == type)

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * per_page
    query = query.order_by(desc(Transaction.created_at)).offset(offset).limit(per_page)

    result = await db.execute(query)
    transactions = result.scalars().all()

    items = []
    for t in transactions:
        # Determine sign based on transaction type
        # Credits (positive): DEPOSIT, REFERRAL_REWARD, REFUND, POLL_REWARD
        # Debits (negative): SUBSCRIPTION_PAYMENT, WITHDRAWAL, GIFT_PAYMENT
        is_debit = t.type in ['subscription_payment', 'withdrawal', 'gift_payment']
        amount_kopeks = -abs(t.amount_kopeks) if is_debit else abs(t.amount_kopeks)

        items.append(
            TransactionResponse(
                id=t.id,
                type=t.type,
                amount_kopeks=amount_kopeks,
                amount_rubles=amount_kopeks / 100,
                description=t.description,
                payment_method=t.payment_method,
                is_completed=t.is_completed,
                created_at=t.created_at,
                completed_at=t.completed_at,
            )
        )

    pages = math.ceil(total / per_page) if total > 0 else 1

    return TransactionListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get('/payment-methods', response_model=list[PaymentMethodResponse])
async def get_payment_methods(
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get available payment methods for the current user.

    Uses PaymentMethodConfig from database for:
    - Sort order (sort_order)
    - Enabled/disabled status (is_enabled)
    - Display names (display_name with fallback to env)
    - Min/max amounts (with fallback to env defaults)
    - Sub-options filtering (sub_options)
    - User filters (user_type_filter, first_topup_filter, promo_group_filter)
    """
    # Check if this is user's first topup
    from sqlalchemy import exists

    has_completed_topup = await db.execute(
        select(
            exists().where(
                Transaction.user_id == user.id,
                Transaction.type == 'deposit',
                Transaction.is_completed == True,
            )
        )
    )
    is_first_topup = not has_completed_topup.scalar()

    # Get enabled methods from database config
    enabled_methods = await get_enabled_methods_for_user(db, user=user, is_first_topup=is_first_topup)

    # Build response with additional options formatting
    methods = []
    for method_data in enabled_methods:
        method_id = method_data['id']

        # Format options with descriptions for specific methods
        options = method_data.get('options')
        if options:
            formatted_options = []
            for opt in options:
                opt_id = opt['id']
                opt_name = opt.get('name', opt_id)
                description = ''

                # Add descriptions based on method and option
                if method_id == 'platega':
                    # Platega options already have descriptions from config
                    definitions = settings.get_platega_method_definitions()
                    info = definitions.get(int(opt_id), {}) if opt_id.isdigit() else {}
                    description = info.get('description') or info.get('name') or ''

                formatted_options.append(
                    {
                        'id': opt_id,
                        'name': strip_leading_emoji(tg_emoji_to_unicode(opt_name) or ''),
                        'description': tg_emoji_to_unicode(description) or '',
                    }
                )
            options = formatted_options or None

        # Platega: разворачиваем активные методы в отдельные карточки (как в боте)
        if method_id == 'platega' and settings.PLATEGA_INLINE_METHODS:
            from app.localization.texts import get_texts as _get_texts

            _texts = _get_texts(getattr(user, 'language', None) or settings.DEFAULT_LANGUAGE)
            _PLATEGA_OPTION_DESCRIPTIONS = {
                2: 'Система быстрых платежей (QR)',
                11: 'Банковская карта РФ (RUB)',
                12: 'Visa / Mastercard (EUR)',
                13: 'Криптовалюта',
            }
            for _code in settings.get_platega_active_methods():
                methods.append(
                    PaymentMethodResponse(
                        id=f'platega_m{_code}',
                        name=strip_leading_emoji(
                            tg_emoji_to_unicode(
                                _texts.t(
                                    f'PAYMENT_PLATEGA_M{_code}',
                                    settings.get_platega_method_display_title(_code),
                                )
                            )
                            or ''
                        ),
                        description=tg_emoji_to_unicode(
                            _PLATEGA_OPTION_DESCRIPTIONS.get(_code, method_data.get('description'))
                        ),
                        min_amount_kopeks=method_data['min_amount_kopeks'],
                        max_amount_kopeks=method_data['max_amount_kopeks'],
                        is_available=True,
                        options=None,
                        quick_amounts=method_data.get('quick_amounts') or [],
                        open_url_direct=bool(method_data.get('open_url_direct', False)),
                    )
                )
            continue

        methods.append(
            PaymentMethodResponse(
                id=method_id,
                name=strip_leading_emoji(tg_emoji_to_unicode(method_data['name']) or ''),
                description=tg_emoji_to_unicode(method_data.get('description')),
                min_amount_kopeks=method_data['min_amount_kopeks'],
                max_amount_kopeks=method_data['max_amount_kopeks'],
                is_available=True,
                options=options,
                quick_amounts=method_data.get('quick_amounts') or [],
                open_url_direct=bool(method_data.get('open_url_direct', False)),
            )
        )

    return methods


@router.post('/stars-invoice', response_model=StarsInvoiceResponse)
async def create_stars_invoice(
    request: StarsInvoiceRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """
    Создать Telegram Stars invoice для пополнения баланса.
    Используется в Telegram Mini App для прямой оплаты Stars.
    """
    if not settings.TELEGRAM_STARS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Telegram Stars payments are not enabled',
        )

    # Validate amount
    if request.amount_kopeks < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Minimum amount is 1.00 RUB',
        )

    if request.amount_kopeks > 1000000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Maximum amount is 10,000.00 RUB',
        )

    # Calculate Stars amount and normalize kopeks to match exact star value
    try:
        amount_rubles = request.amount_kopeks / 100
        stars_amount = settings.rubles_to_stars(amount_rubles)

        if stars_amount <= 0:
            stars_amount = 1

        # Normalize kopeks so credited amount = stars * rate (no rounding mismatch)
        normalized_kopeks = round(stars_amount * settings.get_stars_rate() * 100)
    except Exception as e:
        logger.error('Error calculating Stars amount', error=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to calculate Stars amount',
        )

    # Create payload for tracking payment
    payload = f'balance_topup_{user.id}_{normalized_kopeks}_{int(time.time())}'

    # Create invoice through Telegram Bot API
    try:
        from aiogram.exceptions import TelegramAPIError
        from aiogram.types import LabeledPrice

        async with create_bot() as bot:
            invoice_url = await bot.create_invoice_link(
                title='Пополнение баланса VPN',
                description=f'Пополнение баланса на {normalized_kopeks / 100:.2f} ₽ ({stars_amount} ⭐)',
                payload=payload,
                provider_token='',
                currency='XTR',
                prices=[LabeledPrice(label='Пополнение баланса', amount=stars_amount)],
            )

        logger.info(
            'Created Stars invoice for balance top-up: user=, amount= kopeks, stars',
            user_id=user.id,
            amount_kopeks=request.amount_kopeks,
            stars_amount=stars_amount,
        )

        return StarsInvoiceResponse(
            invoice_url=invoice_url,
            stars_amount=stars_amount,
            amount_kopeks=normalized_kopeks,
        )

    except TelegramAPIError as e:
        logger.error('Error creating Stars invoice', error=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to create Stars invoice',
        )


@router.post('/topup', response_model=TopUpResponse)
async def create_topup(
    request: TopUpRequest,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Create payment for balance top-up."""
    if getattr(user, 'restriction_topup', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Balance top-up is restricted for this account',
        )

    # Validate payment method
    methods = await get_payment_methods(user=user, db=db)
    method = next((m for m in methods if m.id == request.payment_method), None)

    if not method or not method.is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid or unavailable payment method',
        )

    # Platega: отдельные карточки методов (platega_m{code}) -> platega + payment_option
    if isinstance(request.payment_method, str) and request.payment_method.startswith('platega_m'):
        request.payment_option = request.payment_method[len('platega_m') :]
        request.payment_method = 'platega'

    # Validate amount
    if request.amount_kopeks < method.min_amount_kopeks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Minimum amount is {method.min_amount_kopeks / 100:.2f} RUB',
        )

    if request.amount_kopeks > method.max_amount_kopeks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Maximum amount is {method.max_amount_kopeks / 100:.2f} RUB',
        )

    # Провайдер может отвечать десятки секунд: соединение на это время не держим.
    await db.commit()

    amount_rubles = request.amount_kopeks / 100
    payment_url = None
    payment_id = None
    qr_payload: str | None = None
    cabinet_return_url = f'{settings.CABINET_URL.rstrip("/")}/balance/top-up/result?method={request.payment_method}'
    cabinet_success_url = f'{cabinet_return_url}&status=success'
    cabinet_failed_url = f'{cabinet_return_url}&status=failed'

    try:
        if request.payment_method == 'cryptobot':
            if not settings.is_cryptobot_enabled():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='CryptoBot payment method is unavailable',
                )

            try:
                rate = await currency_converter.get_usd_to_rub_rate()
            except Exception:
                rate = 0.0
            if not rate or rate <= 0:
                rate = 95.0

            try:
                amount_usd = float(
                    (Decimal(request.amount_kopeks) / Decimal(100) / Decimal(str(rate))).quantize(
                        Decimal('0.01'), rounding=ROUND_HALF_UP
                    )
                )
            except (InvalidOperation, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Unable to convert amount to USD',
                )

            payment_service = PaymentService()
            result = await payment_service.create_cryptobot_payment(
                db=db,
                user_id=user.id,
                amount_usd=amount_usd,
                asset=settings.CRYPTOBOT_DEFAULT_ASSET,
                description=settings.get_balance_payment_description(
                    request.amount_kopeks, telegram_user_id=user.telegram_id, user_db_id=user.id
                ),
                payload=f'cabinet_topup_{user.id}_{request.amount_kopeks}',
            )
            if result:
                payment_url = (
                    result.get('bot_invoice_url')
                    or result.get('mini_app_invoice_url')
                    or result.get('web_app_invoice_url')
                )
                payment_id = result.get('invoice_id') or str(result.get('local_payment_id', 'pending'))
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to create CryptoBot invoice',
                )

        elif request.payment_method == 'xrocket':
            if not settings.is_xrocket_enabled():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='xRocket payment method is unavailable',
                )

            allowed_assets = settings.get_xrocket_assets()
            asset = (request.payment_option or settings.XROCKET_DEFAULT_ASSET).strip().upper()
            if asset == 'TON':
                asset = 'TONCOIN'  # алиас: у xRocket тикер TONCOIN
            if asset not in allowed_assets and allowed_assets:
                asset = allowed_assets[0]  # мягкий откат на первый доступный актив вместо 400
            if asset not in allowed_assets:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f'Unsupported xRocket asset. Allowed: {", ".join(allowed_assets)}',
                )

            payment_service = PaymentService()
            result = await payment_service.create_xrocket_payment(
                db=db,
                user_id=user.id,
                amount_kopeks=request.amount_kopeks,
                asset=asset,
                description=settings.get_balance_payment_description(
                    request.amount_kopeks, telegram_user_id=user.telegram_id, user_db_id=user.id
                ),
                payload=f'cabinet_topup_{user.id}_{request.amount_kopeks}',
            )
            if result and result.get('pay_url'):
                payment_url = result.get('pay_url')
                payment_id = result.get('invoice_id') or str(result.get('local_payment_id', 'pending'))
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        'Failed to create xRocket invoice. The amount may be below the minimum for the selected asset.'
                    ),
                )

        elif request.payment_method == 'telegram_stars':
            # Telegram Stars payments require bot interaction
            bot_username = settings.get_bot_username() or 'bot'
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f'Telegram Stars payments are only available through the bot. Please use @{bot_username}',
            )

        elif request.payment_method == 'platega':
            if not settings.is_platega_enabled():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Platega payment method is unavailable',
                )

            active_methods = settings.get_platega_active_methods()
            if not active_methods:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='No Platega payment methods configured',
                )

            # Use payment_option if provided, otherwise use first active method
            method_option = request.payment_option or str(active_methods[0])
            try:
                method_code = int(str(method_option).strip())
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Invalid Platega payment option',
                )

            if method_code not in active_methods:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Selected Platega method is unavailable',
                )

            payment_service = PaymentService()
            result = await payment_service.create_platega_payment(
                db=db,
                user_id=user.id,
                amount_kopeks=request.amount_kopeks,
                description=settings.get_balance_payment_description(
                    request.amount_kopeks, telegram_user_id=user.telegram_id, user_db_id=user.id
                ),
                language=getattr(user, 'language', None) or settings.DEFAULT_LANGUAGE,
                payment_method_code=method_code,
                return_url=cabinet_success_url,
                failed_url=cabinet_failed_url,
            )

            if result and result.get('redirect_url'):
                payment_url = result.get('redirect_url')
                payment_id = result.get('transaction_id') or str(result.get('local_payment_id', 'pending'))
            else:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail='Platega is temporarily unavailable, please choose another payment method',
                )

        elif request.payment_method == 'heleket':
            if not settings.is_heleket_enabled():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Heleket payment method is unavailable',
                )

            payment_service = PaymentService()
            result = await payment_service.create_heleket_payment(
                db=db,
                user_id=user.id,
                amount_kopeks=request.amount_kopeks,
                description=settings.get_balance_payment_description(
                    request.amount_kopeks, telegram_user_id=user.telegram_id, user_db_id=user.id
                ),
                language=getattr(user, 'language', None) or settings.DEFAULT_LANGUAGE,
                return_url=cabinet_return_url,
                success_url=cabinet_success_url,
            )

            if result and result.get('payment_url'):
                payment_url = result.get('payment_url')
                payment_id = str(result.get('local_payment_id') or result.get('uuid') or 'pending')
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to create Heleket payment',
                )

        elif request.payment_method == 'wata':
            if not settings.is_wata_enabled():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail='Wata payment method is unavailable',
                )

            payment_service = PaymentService()
            result = await payment_service.create_wata_payment(
                db=db,
                user_id=user.id,
                amount_kopeks=request.amount_kopeks,
                description=settings.get_balance_payment_description(
                    request.amount_kopeks, telegram_user_id=user.telegram_id, user_db_id=user.id
                ),
                language=getattr(user, 'language', None) or settings.DEFAULT_LANGUAGE,
                return_url=cabinet_success_url,
                failed_url=cabinet_failed_url,
            )

            if result and result.get('payment_url'):
                payment_url = result.get('payment_url')
                payment_id = str(result.get('local_payment_id') or result.get('payment_link_id') or 'pending')
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail='Failed to create Wata payment',
                )

        else:
            # For other payment methods, redirect to bot
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail='This payment method is only available through the Telegram bot.',
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error('Payment creation error', error=e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Failed to create payment. Please try again later.',
        )

    if not payment_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail='Payment URL not received',
        )

    return TopUpResponse(
        payment_id=payment_id or 'pending',
        payment_url=payment_url,
        amount_kopeks=request.amount_kopeks,
        amount_rubles=amount_rubles,
        status='pending',
        expires_at=None,
        qr_payload=qr_payload,
    )


def _get_status_info(record: PendingPayment) -> tuple[str, str]:
    """Get status emoji and text for a pending payment."""
    status = (record.status or '').lower()

    if record.is_paid:
        return '✅', 'Оплачено'

    if record.method == PaymentMethod.WATA:
        mapping = {
            'opened': ('⏳', 'Ожидает оплаты'),
            'pending': ('⏳', 'Ожидает оплаты'),
            'processing': ('⌛', 'Обрабатывается'),
            'paid': ('✅', 'Оплачено'),
            'closed': ('✅', 'Оплачено'),
            'declined': ('❌', 'Отклонено'),
            'canceled': ('❌', 'Отменено'),
            'expired': ('⌛', 'Истёк'),
        }
        return mapping.get(status, ('❓', 'Неизвестно'))

    if record.method == PaymentMethod.PLATEGA:
        mapping = {
            'pending': ('⏳', 'Ожидает оплаты'),
            'inprogress': ('⌛', 'Обрабатывается'),
            'confirmed': ('✅', 'Оплачено'),
            'failed': ('❌', 'Ошибка'),
            'canceled': ('❌', 'Отменено'),
            'expired': ('⌛', 'Истёк'),
        }
        return mapping.get(status, ('❓', 'Неизвестно'))

    if record.method == PaymentMethod.HELEKET:
        if status in {'pending', 'created', 'waiting', 'check', 'processing'}:
            return '⏳', 'Ожидает оплаты'
        if status in {'paid', 'paid_over'}:
            return '✅', 'Оплачено'
        if status in {'cancel', 'canceled', 'fail', 'failed', 'expired'}:
            return '❌', 'Отменено'
        return '❓', 'Неизвестно'

    if record.method == PaymentMethod.CRYPTOBOT:
        mapping = {
            'active': ('⏳', 'Ожидает оплаты'),
            'paid': ('✅', 'Оплачено'),
            'expired': ('⌛', 'Истёк'),
        }
        return mapping.get(status, ('❓', 'Неизвестно'))

    return '❓', 'Неизвестно'


def _is_checkable(record: PendingPayment) -> bool:
    """Check if payment can be manually checked."""
    if record.method not in SUPPORTED_MANUAL_CHECK_METHODS:
        return False
    if not record.is_recent():
        return False
    status = (record.status or '').lower()
    if record.method == PaymentMethod.WATA:
        return status in {'opened', 'pending', 'processing', 'inprogress', 'in_progress'}
    if record.method == PaymentMethod.PLATEGA:
        return status in {'pending', 'inprogress', 'in_progress'}
    if record.method == PaymentMethod.HELEKET:
        return status not in {'paid', 'paid_over', 'cancel', 'canceled', 'fail', 'failed', 'expired'}
    if record.method == PaymentMethod.CRYPTOBOT:
        return status == 'active'
    return False


def _get_payment_url(record: PendingPayment) -> str | None:
    """Extract payment URL from record."""
    payment = record.payment
    payment_url = getattr(payment, 'payment_url', None)

    if record.method == PaymentMethod.WATA:
        payment_url = getattr(payment, 'url', None) or payment_url
    elif record.method == PaymentMethod.CRYPTOBOT:
        payment_url = (
            getattr(payment, 'bot_invoice_url', None)
            or getattr(payment, 'mini_app_invoice_url', None)
            or getattr(payment, 'web_app_invoice_url', None)
            or payment_url
        )
    elif record.method == PaymentMethod.PLATEGA:
        payment_url = getattr(payment, 'redirect_url', None) or payment_url

    return payment_url


def _record_to_response(record: PendingPayment) -> PendingPaymentResponse:
    """Convert PendingPayment to API response."""
    status_emoji, status_text = _get_status_info(record)
    return PendingPaymentResponse(
        id=record.local_id,
        method=record.method.value,
        method_display=method_display_name(record.method),
        identifier=record.identifier,
        amount_kopeks=record.amount_kopeks,
        amount_rubles=record.amount_kopeks / 100,
        status=record.status or '',
        status_emoji=status_emoji,
        status_text=status_text,
        is_paid=record.is_paid,
        is_checkable=_is_checkable(record),
        created_at=record.created_at,
        expires_at=record.expires_at,
        payment_url=_get_payment_url(record),
        user_id=record.user.id if record.user else None,
        user_telegram_id=record.user.telegram_id if record.user else None,
        user_username=record.user.username if record.user else None,
    )


@router.get('/pending-payments', response_model=PendingPaymentListResponse)
async def get_pending_payments(
    page: int = Query(1, ge=1, description='Page number'),
    per_page: int = Query(10, ge=1, le=50, description='Items per page'),
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get user's pending payments for manual verification."""
    all_pending = await list_recent_pending_payments(db)

    # Filter only current user's payments
    user_payments = [p for p in all_pending if p.user and p.user.id == user.id]

    total = len(user_payments)
    pages = math.ceil(total / per_page) if total > 0 else 1

    # Paginate
    start_idx = (page - 1) * per_page
    page_payments = user_payments[start_idx : start_idx + per_page]

    items = [_record_to_response(p) for p in page_payments]

    return PendingPaymentListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get('/pending-payments/{method}/latest', response_model=PendingPaymentResponse)
async def get_latest_payment_by_method(
    method: str,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get user's most recent payment for a given method (any status, not just pending)."""
    try:
        payment_method = PaymentMethod(method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid payment method: {method}',
        )

    from datetime import UTC, datetime, timedelta

    from sqlalchemy.orm import selectinload

    from app.database.models import CryptoBotPayment, HeleketPayment, PlategaPayment, WataPayment

    model_map: dict[PaymentMethod, type] = {
        PaymentMethod.CRYPTOBOT: CryptoBotPayment,
        PaymentMethod.HELEKET: HeleketPayment,
        PaymentMethod.WATA: WataPayment,
        PaymentMethod.PLATEGA: PlategaPayment,
    }

    model = model_map.get(payment_method)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Unsupported payment method: {method}',
        )

    cutoff = datetime.now(UTC) - timedelta(hours=1)
    stmt = (
        select(model)
        .options(selectinload(model.user))
        .where(model.user_id == user.id, model.created_at >= cutoff)
        .order_by(desc(model.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    payment = result.scalars().first()

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='No recent payments found',
        )

    record = PendingPayment(
        local_id=payment.id,
        method=payment_method,
        identifier=str(getattr(payment, 'correlation_id', None) or payment.id),
        amount_kopeks=payment.amount_kopeks,
        status=payment.status or '',
        is_paid=bool(payment.is_paid),
        created_at=payment.created_at,
        expires_at=getattr(payment, 'expires_at', None),
        user=payment.user,
        payment=payment,
    )

    return _record_to_response(record)


@router.get('/pending-payments/{method}/{payment_id}', response_model=PendingPaymentResponse)
async def get_pending_payment_details(
    method: str,
    payment_id: int,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Get details of a specific pending payment."""
    try:
        payment_method = PaymentMethod(method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid payment method: {method}',
        )

    record = await get_payment_record(db, payment_method, payment_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Payment not found',
        )

    # Check that payment belongs to the current user
    if not record.user or record.user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied',
        )

    return _record_to_response(record)


@router.post('/pending-payments/{method}/{payment_id}/check', response_model=ManualCheckResponse)
async def check_payment_status(
    method: str,
    payment_id: int,
    user: User = Depends(get_current_cabinet_user),
    db: AsyncSession = Depends(get_cabinet_db),
):
    """Manually check and update payment status."""
    try:
        payment_method = PaymentMethod(method)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'Invalid payment method: {method}',
        )

    # Get current record
    record = await get_payment_record(db, payment_method, payment_id)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Payment not found',
        )

    # Check that payment belongs to the current user
    if not record.user or record.user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Access denied',
        )

    # Check if manual check is available
    if not _is_checkable(record):
        return ManualCheckResponse(
            success=False,
            message='Ручная проверка недоступна для этого платежа',
            payment=_record_to_response(record),
            status_changed=False,
        )

    old_status = record.status
    old_is_paid = record.is_paid

    # Run manual check
    bot = create_bot()
    try:
        payment_service = PaymentService(bot=bot)
        updated = await run_manual_check(db, payment_method, payment_id, payment_service)
    finally:
        await bot.session.close()

    if not updated:
        return ManualCheckResponse(
            success=False,
            message='Не удалось проверить статус платежа',
            payment=_record_to_response(record),
            status_changed=False,
        )

    status_changed = updated.status != old_status or updated.is_paid != old_is_paid

    if status_changed:
        _, new_status_text = _get_status_info(updated)
        message = f'Статус обновлён: {new_status_text}'
    else:
        message = 'Статус не изменился'

    return ManualCheckResponse(
        success=True,
        message=message,
        payment=_record_to_response(updated),
        status_changed=status_changed,
        old_status=old_status,
        new_status=updated.status,
    )
