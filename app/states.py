from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    waiting_for_language = State()
    waiting_for_rules_accept = State()
    waiting_for_privacy_policy_accept = State()
    waiting_for_referral_code = State()


class SubscriptionStates(StatesGroup):
    adding_countries = State()
    adding_traffic = State()
    adding_devices = State()
    extending_subscription = State()
    confirming_traffic_reset = State()
    cart_saved_for_topup = State()

    # Состояния для простой подписки

    # Состояния для кастомных дней/трафика при покупке тарифа
    selecting_custom_days = State()
    selecting_custom_traffic = State()
    confirming_custom_purchase = State()

    # Локальное переименование HWID-устройства (alias). hwid и page/sub_id
    # передаются через state data, чтобы вернуться к ровно тому же списку.
    renaming_device = State()


class GiftPurchaseStates(StatesGroup):
    selecting_tariff = State()
    selecting_period = State()
    confirming_purchase = State()
    cart_saved_for_topup = State()


class GiftActivationStates(StatesGroup):
    waiting_for_code = State()


class BalanceStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_platega_method = State()
    waiting_for_stars_payment = State()
    waiting_for_support_request = State()


class PromoCodeStates(StatesGroup):
    waiting_for_code = State()
    waiting_for_referral_code = State()


class AdminStates(StatesGroup):
    waiting_for_user_search = State()
    editing_user_balance = State()
    extending_subscription = State()
    adding_traffic = State()
    granting_subscription = State()
    editing_user_restriction_reason = State()

    creating_promocode = State()
    setting_promocode_value = State()
    setting_promocode_uses = State()
    setting_promocode_expiry = State()
    setting_discount_hours = State()  # Для DISCOUNT: ввод срока действия скидки в часах
    setting_promocode_combo_days = State()  # Для BALANCE_AND_DAYS: ввод дней подписки после суммы

    creating_campaign_name = State()
    creating_campaign_start = State()
    creating_campaign_bonus = State()
    creating_campaign_balance = State()

    waiting_for_broadcast_message = State()
    waiting_for_broadcast_media = State()

    editing_user_referrals = State()
    editing_user_referral_percent = State()

    waiting_for_message_buttons = 'waiting_for_message_buttons'

    editing_promo_offer_active_duration = State()


class TicketStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_message = State()
    waiting_for_reply = State()


class AdminTicketStates(StatesGroup):
    waiting_for_reply = State()
    waiting_for_block_duration = State()


class ReferralWithdrawalStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_payment_details = State()
    confirming = State()
