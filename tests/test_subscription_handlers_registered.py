"""Каждая кнопка покупки должна иметь обработчик: без него нажатие молча висит."""

from aiogram import Dispatcher

from app.handlers.subscription.purchase import register_handlers


REQUIRED = {
    'start_subscription_purchase',
    'handle_subscription_cancel',
    'set_autopay_days',
    'set_autopay_period',
    'handle_manage_country',
    'apply_countries_changes',
    'claim_discount_offer',
    'handle_promo_offer_close',
    'handle_happ_download_request',
    'handle_happ_download_platform_choice',
}


def test_purchase_flow_handlers_are_registered():
    dispatcher = Dispatcher()

    register_handlers(dispatcher)

    registered = {handler.callback.__name__ for handler in dispatcher.callback_query.handlers}
    assert not REQUIRED - registered
