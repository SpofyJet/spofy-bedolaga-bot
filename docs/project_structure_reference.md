# База по структуре проекта

> Документ собирается автоматически: `make docs-structure`.
> Правки руками затрутся — меняйте генератор `scripts/generate_structure_reference.py`.

Перечислены файлы под контролем версий. Для Python-модулей указаны классы
(с числом методов) и функции верхнего уровня; имена, начинающиеся с
подчёркивания, опущены как внутренние.

## Общая структура корня

- `.dockerignore` — файл
- `.env.example` — файл
- `.github/`
- `.gitignore` — файл
- `.python-version` — файл
- `.release-please-manifest.json` — файл
- `CHANGELOG.md` — файл
- `CONTRIBUTING.md` — файл
- `Dockerfile` — файл
- `LICENSE` — файл
- `Makefile` — файл
- `README.md` — файл
- `SECURITY.md` — файл
- `alembic.ini` — файл
- `app/`
- `assets/`
- `banners/`
- `docker/`
- `docker-compose.local.yml` — файл
- `docker-compose.yml` — файл
- `docs/`
- `locales/`
- `main.py` — Python-модуль
  Классы: `GracefulExit` (2 методов)
  Функции: `main`
- `migrations/`
- `pyproject.toml` — файл
- `release-please-config.json` — файл
- `scripts/`
- `tests/`
- `uv.lock` — файл
- `vpn_logo.png` — файл

## .github

- `.github/ISSUE_TEMPLATE/`
- `.github/assets/`
- `.github/codeql/`
- `.github/dependabot.yml` — файл
- `.github/workflows/`

### .github/ISSUE_TEMPLATE

- `.github/ISSUE_TEMPLATE/bug-bedolage.md` — файл
- `.github/ISSUE_TEMPLATE/feat-bedolage.md` — файл

### .github/assets

- `.github/assets/bot-preview.png` — файл
- `.github/assets/cabinet-admin.png` — файл
- `.github/assets/cabinet-preview.png` — файл
- `.github/assets/logo.png` — файл
- `.github/assets/platega-logo.jpg` — файл
- `.github/assets/wata-logo.jpg` — файл

### .github/codeql

- `.github/codeql/codeql-config.yml` — файл

### .github/workflows

- `.github/workflows/ci.yml` — файл
- `.github/workflows/codeql.yml` — файл
- `.github/workflows/docker-hub.yml` — файл
- `.github/workflows/docker-registry.yml` — файл
- `.github/workflows/lint.yml` — файл
- `.github/workflows/pg-upgrade.yml` — файл
- `.github/workflows/release-please.yml` — файл
- `.github/workflows/release-pr-guard.yml` — файл
- `.github/workflows/release.yml` — файл
- `.github/workflows/security-audit.yml` — файл
- `.github/workflows/tests.yml` — файл

## app

- `app/bot.py` — Python-модуль
  Классы: нет
  Функции: `setup_bot`
- `app/bot_factory.py` — Python-модуль
  Классы: нет
  Функции: `create_bot` — Create a Bot instance with SOCKS5 proxy and/or custom Telegram API server.
- `app/cabinet/`
- `app/config.py` — Python-модуль
  Классы: `Settings` (182 методов)
  Функции: `transliterate_cyrillic` — Заменяет кириллические буквы латинскими, сохраняя регистр («Шмель» → «Shmel»)., `set_period_prices_from_db` — Устанавливает периоды/цены из БД., `refresh_period_prices` — Rebuild cached period price mapping., `refresh_classic_period_prices` — Rebuild CLASSIC_PERIOD_PRICES from current settings., `get_traffic_prices`, `refresh_traffic_prices`
- `app/database/`
- `app/external/`
- `app/handlers/`
- `app/keyboards/`
- `app/localization/`
- `app/logging_config.py` — Python-модуль
  Классы: нет
  Функции: `redact_secrets` — Скрывает значения секретных заголовков и токены в произвольной строке (лог, текст исключения)., `setup_logging` — Configure structlog and return formatters + notifier.
- `app/logging_handler.py` — Python-модуль
  Классы: `TelegramNotifierProcessor` (8 методов)
  Функции: нет
- `app/logging_safety.py` — Python-модуль
  Классы: нет
  Функции: `redact_text`, `safe_exception_summary`, `safe_value` — Copy containers so nested exceptions cannot fall back to credential-bearing repr., `safe_event`, `safe_traceback` — Keep frames, causes and exception groups, without HTTP request metadata., `sanitize_log_event`, `render_safe_exception`
- `app/middlewares/`
- `app/referral_levels.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/`
- `app/states.py` — Python-модуль
  Классы: `RegistrationStates`, `SubscriptionStates`, `GiftPurchaseStates`, `GiftActivationStates`, `BalanceStates`, `PromoCodeStates`, `AdminStates`, `TicketStates`, `AdminTicketStates`, `ReferralWithdrawalStates`
  Функции: нет
- `app/tools/`
- `app/utils/`
- `app/webserver/`

### app/cabinet

- `app/cabinet/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/auth/`
- `app/cabinet/dependencies.py` — Python-модуль
  Классы: нет
  Функции: `get_cabinet_db` — Get database session for cabinet operations., `get_current_cabinet_user` — Get current authenticated cabinet user from JWT token., `get_optional_cabinet_user` — Optionally get current authenticated cabinet user., `require_permission` — FastAPI dependency factory for RBAC permission checks.
- `app/cabinet/ip_utils.py` — Python-модуль
  Классы: нет
  Функции: `get_client_ip` — Extract real client IP, trusting proxy headers only from known proxies.
- `app/cabinet/routes/`
- `app/cabinet/schemas/`
- `app/cabinet/services/`
- `app/cabinet/utils/`
- `app/cabinet/ws_manager.py` — Python-модуль
  Классы: `CabinetConnectionManager` (5 методов)
  Функции: нет

#### app/cabinet/auth

- `app/cabinet/auth/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/auth/email_auth_gate.py` — Python-модуль
  Классы: нет
  Функции: `is_email_auth_enabled` — Строка в system_settings важнее значения из окружения., `require_email_auth_enabled` — Первый шаг любого email/password-роута: до rate-limit и до таблицы users.
- `app/cabinet/auth/email_verification.py` — Python-модуль
  Классы: нет
  Функции: `generate_email_change_code` — Generate a 6-digit verification code for email change., `get_email_change_expires_at` — Get the expiration datetime for an email change code., `generate_verification_token` — Generate a secure random verification token., `generate_password_reset_token` — Generate a secure random password reset token., `get_verification_expires_at` — Get the expiration datetime for a verification token., `get_password_reset_expires_at` — Get the expiration datetime for a password reset token., `is_token_expired` — Check if a token has expired.
- `app/cabinet/auth/jwt_handler.py` — Python-модуль
  Классы: нет
  Функции: `create_access_token` — Create a short-lived access token., `create_refresh_token` — Create a long-lived refresh token., `decode_token` — Decode and validate a JWT token., `get_token_payload` — Decode token and verify its type., `create_auto_login_token` — Short-lived JWT for auto-login from guest purchase success page., `get_refresh_token_expires_at` — Get the expiration datetime for a new refresh token.
- `app/cabinet/auth/merge_service.py` — Python-модуль
  Классы: нет
  Функции: `store_email_merge_otp` — Store a pending email-merge code for the initiator (overwrites any prior)., `get_email_merge_otp` — Read the pending email-merge code without consuming it., `clear_email_merge_otp` — Drop the pending email-merge code., `create_merge_token` — Generate a merge token and store its payload in Redis., `get_merge_token_data` — Read merge token payload *without* consuming it., `consume_merge_token` — Atomically read and delete a merge token (GETDEL)., `restore_merge_token` — Re-store a consumed merge token so the user can retry after a DB failure.
- `app/cabinet/auth/oauth_providers.py` — Python-модуль
  Классы: `OAuthProviderConfig`, `OAuthTokenResponse`, `GoogleUserInfoResponse`, `YandexUserInfoResponse`, `DiscordUserInfoResponse`, `VKIDUserData`, `VKIDUserInfoResponse`, `OAuthUserInfo`, `OAuthProvider` (5 методов), `GoogleProvider` (3 методов), `YandexProvider` (3 методов), `DiscordProvider` (3 методов), `VKProvider` (5 методов)
  Функции: `generate_oauth_state` — Generate a CSRF state token for OAuth flow., `peek_oauth_state` — Read a CSRF state token's data without consuming it (preview before confirmation)., `validate_oauth_state` — Validate and consume a CSRF state token from Redis., `resolve_oauth_redirect_uri` — Pick the OAuth redirect_uri for the request's origin., `get_provider` — Get an OAuth provider instance if enabled.
- `app/cabinet/auth/password_utils.py` — Python-модуль
  Классы: нет
  Функции: `hash_password` — Hash a password using bcrypt., `verify_password` — Verify a password against its hash.
- `app/cabinet/auth/registration_access.py` — Python-модуль
  Классы: нет
  Функции: `evaluate_public_registration`, `raise_for_registration_decision`, `is_env_admin_recovery` — True when a non-ACTIVE account must be restored because env names it as admin.
- `app/cabinet/auth/registration_throttle.py` — Python-модуль
  Классы: нет
  Функции: `enforce_email_registration_throttle`, `enforce_verification_resend_throttle` — Дроссель кнопки «Отправить письмо ещё раз» на экране «Проверьте почту».
- `app/cabinet/auth/telegram_auth.py` — Python-модуль
  Классы: нет
  Функции: `validate_telegram_login_widget` — Validate Telegram Login Widget data., `validate_telegram_init_data` — Validate Telegram WebApp initData., `validate_telegram_oidc_token` — Validate a Telegram OIDC id_token using JWKS.

#### app/cabinet/routes

- `app/cabinet/routes/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/routes/account_linking.py` — Python-модуль
  Классы: `OAuthStateData`, `LinkedProvider`, `LinkedProvidersResponse`, `LinkInitResponse`, `LinkCallbackRequest`, `LinkCallbackResponse`, `UnlinkResponse`, `LinkTelegramRequest` (1 методов), `MergePreviewSubscription`, `MergePreviewUser`, `MergePreviewResponse`, `MergeRequest`, `MergeResponse`, `ServerCompleteRequest`, `ServerCompleteResponse`, `ServerCompletePreviewResponse`
  Функции: `get_linked_providers` — Return all auth methods with their link status for the current user., `link_provider_init` — Start OAuth flow for linking a new provider to the current account., `link_provider_callback` — Handle OAuth callback for linking a provider to the current account., `unlink_provider` — Unlink an OAuth provider from the current account., `link_telegram` — Link Telegram account via WebApp initData, OIDC id_token, or Login Widget., `link_server_complete_preview` — Показать, к какому аккаунту будет привязан вход, — до подтверждения (state не гасится)., `link_server_complete` — Complete OAuth account linking without JWT., `get_merge_preview_endpoint` — Preview the result of merging two accounts before confirming., `execute_merge_endpoint` — Execute account merge. Consumes the merge token (one-time use).
- `app/cabinet/routes/activity.py` — Python-модуль
  Классы: `ActivityEvent`, `ActivityEventsRequest`
  Функции: `report_activity_events` — Принять пачку событий (fire-and-forget, ответ не ждёт записи).
- `app/cabinet/routes/admin_apps.py` — Python-модуль
  Классы: `RemnaWaveConfigStatus`, `UpdateRemnaWaveUuidRequest`
  Функции: `get_remnawave_config_status` — Get RemnaWave config integration status., `set_remnawave_config_uuid` — Set RemnaWave subscription config UUID., `list_remnawave_subscription_configs` — List available subscription page configs from RemnaWave panel.
- `app/cabinet/routes/admin_broadcasts.py` — Python-модуль
  Классы: нет
  Функции: `get_filters` — Get all available filters with user counts., `get_tariffs` — Get tariffs for broadcast filtering., `get_buttons` — Get available buttons for broadcasts., `preview_audience` — Count and page through the recipients selected at this moment., `search_audience_users` — Find a person by any part of Telegram ID, username, or email., `list_broadcasts` — Get list of broadcasts with pagination., `get_email_filters` — Get all available email filters with user counts., `render_email_broadcast` — Письмо рассылки так, как его получит адресат., `create_combined_broadcast` — Create and start a combined broadcast (telegram/email/both)., `get_broadcast` — Get broadcast details., `stop_broadcast` — Stop a running broadcast (telegram or email).
- `app/cabinet/routes/admin_button_styles.py` — Python-модуль
  Классы: `ButtonSectionConfig`, `ButtonStylesResponse`, `ButtonSectionUpdate`, `ButtonStylesUpdate`
  Функции: `get_button_styles` — Return current per-section button styles. Admin only., `update_button_styles` — Partially update per-section button styles. Admin only., `reset_button_styles` — Reset all button styles to defaults. Admin only.
- `app/cabinet/routes/admin_campaigns.py` — Python-модуль
  Классы: нет
  Функции: `get_overview` — Get campaigns overview statistics., `get_available_servers` — Get list of available server squads for campaign subscription bonus., `get_available_tariffs` — Get list of available tariffs for campaign tariff bonus., `get_available_partners` — Get list of approved partners for campaign partner selector., `list_campaigns` — Get list of all campaigns., `get_campaign` — Get detailed campaign info., `get_campaign_chart_data` — Get chart data for admin campaign analytics., `get_campaign_stats` — Get detailed campaign statistics., `get_campaign_registrations` — Get list of users registered through campaign., `create_new_campaign` — Create a new advertising campaign., `update_existing_campaign` — Update an existing campaign., `delete_existing_campaign` — Delete a campaign., `toggle_campaign` — Toggle campaign active status.
- `app/cabinet/routes/admin_channels.py` — Python-модуль
  Классы: нет
  Функции: `list_channels`, `create_channel`, `update_channel_endpoint`, `toggle_channel_endpoint`, `delete_channel_endpoint`
- `app/cabinet/routes/admin_email_queue.py` — Python-модуль
  Классы: нет
  Функции: `get_email_queue` — Сводка по очереди писем и последние письма в ней., `clear_email_queue` — Убрать письма из очереди. По умолчанию — целиком, вместе с историей.
- `app/cabinet/routes/admin_email_templates.py` — Python-модуль
  Классы: `EmailTemplateUpdate`, `EmailTemplateEnabledRequest`, `EmailTemplatePreviewRequest`, `EmailTemplateSendTestRequest`
  Функции: `list_template_types` — List all available email template types with override status., `get_templates_for_type` — Get all language templates for a specific notification type., `update_template` — Save a custom email template override., `set_template_enabled` — Выключатель писем по типу: отключённое письмо не отправляется никому., `reset_template` — Delete custom template override, reverting to default., `preview_template` — Preview a rendered email template with sample data., `send_test_email` — Send a test email to the admin's email address.
- `app/cabinet/routes/admin_legal_pages.py` — Python-модуль
  Классы: `LegalDocumentItem`, `LegalDocumentResponse`, `LegalDocumentItemUpdate`, `LegalDocumentUpdateRequest`, `RulesItem`, `RulesResponse`, `RulesItemUpdate`, `RulesUpdateRequest`, `FaqSettingItem`, `FaqPageItem`, `FaqResponse`, `FaqUpdateRequest`, `FaqPageCreateRequest`, `FaqPageUpdateRequest`
  Функции: `get_privacy_policy_admin`, `update_privacy_policy_admin`, `get_public_offer_admin`, `update_public_offer_admin`, `get_rules_admin`, `update_rules_admin`, `get_faq_admin`, `update_faq_admin`, `create_faq_page_admin`, `update_faq_page_admin`, `delete_faq_page_admin`
- `app/cabinet/routes/admin_menu_layout.py` — Python-модуль
  Классы: `ButtonConfig`, `RowConfig`, `MenuConfigResponse`, `MenuConfigUpdateRequest`
  Функции: `get_menu_layout` — Return merged menu layout config (rows + button styles). Admin only., `update_menu_layout` — Save full menu layout config. Splits into layout + button styles. Admin only., `reset_menu_layout` — Reset menu layout AND button styles to defaults. Admin only.
- `app/cabinet/routes/admin_partners.py` — Python-модуль
  Классы: `PartnerSettingsResponse`, `PartnerSettingsUpdateRequest`
  Функции: `get_partner_settings` — Get partner system settings., `update_partner_settings` — Update partner system settings — в system_settings, с применением сразу., `list_applications` — List partner applications., `approve_application` — Approve a partner application., `reject_application` — Reject a partner application., `get_partner_stats` — Get overall partner statistics., `list_partners` — List approved partners., `list_referral_levels` — Список уровней реферальных наград и текущая схема., `upsert_referral_level` — Создать или обновить правило уровня., `remove_referral_level` — Удалить правило уровня., `update_referral_depth` — Сколько звеньев цепочки получают награду., `import_legacy_referral_settings` — Перенести действующие настройки ``REFERRAL_*`` в уровень 1., `update_referral_levels_mode` — Что означает номер уровня: глубина цепочки или ранг партнёра., `update_referral_scheme` — Переключить схему наград., `get_partner_detail` — Get detailed partner info., `update_commission` — Update partner commission percent., `revoke_partner` — Revoke partner status., `assign_campaign` — Assign a campaign to a partner., `unassign_campaign` — Unassign a campaign from a partner.
- `app/cabinet/routes/admin_payment_methods.py` — Python-модуль
  Классы: `SubOptionInfo`, `PaymentMethodConfigResponse`, `PaymentMethodConfigUpdateRequest` (2 методов), `SortOrderRequest`, `PromoGroupSimple`
  Функции: `list_payment_methods` — List all payment method configurations., `list_promo_groups` — List all promo groups for filter selector., `get_payment_method` — Get a single payment method configuration., `update_payment_methods_order` — Batch update sort order for payment methods., `update_payment_method` — Update a payment method configuration.
- `app/cabinet/routes/admin_payments.py` — Python-модуль
  Классы: `PendingPaymentResponse`, `PendingPaymentListResponse`, `ManualCheckResponse`, `PaymentsStatsResponse`, `SearchStatsResponse`
  Функции: `get_all_pending_payments` — Get all pending payments for admin verification., `get_payments_stats` — Get statistics about pending payments., `search_payments_endpoint` — Search payments across all providers with filters., `search_payments_stats_endpoint` — Get aggregated statistics for payment search results., `get_pending_payment_details` — Get details of a specific pending payment., `check_payment_status` — Manually check and update payment status.
- `app/cabinet/routes/admin_pinned_messages.py` — Python-модуль
  Классы: нет
  Функции: `list_pinned_messages` — Get list of pinned messages with pagination., `get_active_message` — Get current active pinned message., `get_pinned_message` — Get pinned message by ID., `create_pinned_message` — Create a new pinned message., `update_pinned_message` — Update a pinned message content, media, or settings., `deactivate_active_message` — Deactivate the current active pinned message without unpinning from users., `unpin_active_message` — Unpin messages from all users and deactivate the active pinned message., `activate_pinned_message` — Activate a pinned message., `broadcast_message` — Broadcast a pinned message to all active users., `delete_pinned_message` — Delete a pinned message. Active messages must be deactivated first.
- `app/cabinet/routes/admin_promo_offers.py` — Python-модуль
  Классы: `PromoOfferUserInfo`, `PromoOfferTemplateResponse`, `PromoOfferTemplateListResponse`, `PromoOfferTemplateUpdateRequest`, `PromoOfferBroadcastRequest` (1 методов), `PromoOfferBroadcastResponse`, `PromoOfferSegment`, `PromoOfferSegmentListResponse`, `PromoOfferLogOfferInfo`, `PromoOfferLogResponse`, `PromoOfferLogListResponse`
  Функции: `list_segments` — Число пользователей в каждом сегменте — чтобы админ видел охват до отправки., `list_templates` — Get list of promo offer templates., `update_template` — Update a promo offer template., `broadcast_offer` — Broadcast promo offer to users with optional Telegram notification., `get_logs` — Get promo offer logs.
- `app/cabinet/routes/admin_promocodes.py` — Python-модуль
  Классы: `PromoCodeResponse`, `PromoCodeListResponse`, `PromoCodeRecentUse`, `PromoCodeDetailResponse`, `PromoCodeCreateRequest`, `PromoCodeUpdateRequest`, `PromoGroupResponse`, `PromoGroupListResponse`, `PromoGroupCreateRequest`, `PromoGroupUpdateRequest`, `PromoGroupRecalculationLast`, `PromoGroupRecalculationStatus`, `DeactivateDiscountResponse`
  Функции: `list_promocodes` — Get list of all promocodes., `get_promocode` — Get promocode details with usage statistics., `create_promocode_endpoint` — Create a new promocode., `update_promocode_endpoint` — Update an existing promocode., `delete_promocode_endpoint` — Delete a promocode., `admin_deactivate_discount_promocode` — Admin: deactivate a user's active discount (promo code or promo offer)., `list_promo_groups` — Get list of all promo groups., `start_promo_group_recalculation` — Пересчитать промогруппы всех людей по их тратам (в фоне)., `get_promo_group_recalculation_status` — Идёт ли пересчёт и чем кончился последний., `get_promo_group` — Get promo group details., `create_promo_group_endpoint` — Create a new promo group., `update_promo_group_endpoint` — Update a promo group., `delete_promo_group_endpoint` — Delete a promo group.
- `app/cabinet/routes/admin_referral_network.py` — Python-модуль
  Классы: `NetworkUserNode`, `TopReferrer`, `NetworkCampaignNode`, `NetworkEdge`, `NetworkGraphResponse`, `NetworkUserDetail`, `NetworkCampaignDetail`, `NetworkSearchResult`, `CampaignOption`, `PartnerOption`, `ScopeOptionsResponse`
  Функции: `get_referral_network` — Return full referral network graph data for visualization., `get_scope_options` — Return lightweight lists of campaigns and partners for the scope selector., `get_scoped_referral_network` — Return scoped referral network graph for selected campaigns, partners, and/or users., `get_network_user_detail` — Return detailed info about a specific user in the referral network., `get_network_campaign_detail` — Return detailed info about a specific advertising campaign., `search_referral_network` — Search users and campaigns in the referral network by telegram_id, username, email, or campaign name.
- `app/cabinet/routes/admin_remnawave.py` — Python-модуль
  Классы: `RestartAllNodesPayload`
  Функции: `get_remnawave_status` — Get RemnaWave configuration and connection status., `get_system_statistics` — Get full system statistics from RemnaWave., `get_recap` — Panel recap: lifetime/this-month traffic, version, uptime, distinct countries., `get_devices_stats` — HWID device statistics: breakdown by platform and app + totals., `get_top_consumers_route` — Top traffic-consuming users aggregated across nodes for the last N days., `get_health_route` — Panel process runtime health: RAM, event-loop p99 lag, uptime., `get_subscription_requests_route` — Subscription-link request stats by client app., `list_nodes` — Get list of all nodes., `get_nodes_realtime` — Get realtime node usage data., `get_node_details` — Get detailed information about a specific node., `perform_node_action` — Perform an action on a node (enable/disable/restart)., `restart_all_nodes` — Restart all nodes., `start_node_geocheck` — Queue a GeoCheck on the node and return its job id., `get_node_geocheck` — Poll a GeoCheck job: the node may take up to a minute to answer., `list_squads` — Get list of all squads with local database info., `get_auto_sync_status` — Get auto sync status., `toggle_auto_sync` — Toggle auto sync on/off., `run_auto_sync_now` — Run auto sync immediately., `sync_from_panel` — Sync users from RemnaWave panel to bot., `sync_to_panel` — Sync users from bot to RemnaWave panel., `sync_full` — Полная синхронизация: из панели в бота и серверы — как в боте и по расписанию. Панель — истина, в неё не пишем., `sync_servers` — Sync servers/squads from RemnaWave., `validate_subscriptions` — Validate and fix subscriptions., `cleanup_subscriptions` — Cleanup orphaned subscriptions., `sync_subscription_statuses` — Sync subscription statuses., `get_sync_recommendations` — Get sync recommendations.
- `app/cabinet/routes/admin_sales_stats.py` — Python-модуль
  Классы: `SalesSummary`, `ProviderBreakdownItem`, `DailyTrialItem`, `TrialsStatsResponse`, `SalesByTariffItem`, `SalesByPeriodItem`, `DailySalesItem`, `DailyTariffSalesItem`, `SalesStatsResponse`, `DailyRenewalItem`, `RenewalPeriodStats`, `RenewalChange`, `RenewalsStatsResponse`, `AddonByPackageItem`, `DailyAddonItem`, `DailyDeviceItem`, `AddonsStatsResponse`, `DepositByMethodItem`, `DailyDepositItem`, `DailyDepositByMethodItem`, `DepositsStatsResponse`, `GatewaySuccessItem`, `PaymentHealthResponse`
  Функции: `get_sales_summary` — Get summary statistics for sales dashboard cards., `get_trials_stats` — Get trial registration statistics with provider breakdown., `get_sales_stats` — Get subscription sales statistics., `get_renewals_stats` — Get renewal statistics with period comparison., `get_addons_stats` — Get add-on purchase statistics., `get_deposits_stats` — Get deposit statistics with payment method breakdown., `get_payment_health` — Payment reliability: per-gateway success-rate + failed-purchase rollbacks.
- `app/cabinet/routes/admin_servers.py` — Python-модуль
  Классы: нет
  Функции: `list_servers` — Get list of all servers., `get_server` — Get detailed server info., `update_existing_server` — Update an existing server., `toggle_server` — Toggle server availability., `toggle_server_trial` — Toggle server trial eligibility., `sync_servers` — Sync servers with RemnaWave.
- `app/cabinet/routes/admin_settings.py` — Python-модуль
  Классы: `SettingCategoryRef`, `SettingChoice`, `SettingHint`, `SettingDefinition`, `SettingUpdateRequest`
  Функции: `list_settings` — Get list of all settings or settings for a specific category., `update_setting` — Update a setting value., `reset_setting` — Reset a setting to its default value.
- `app/cabinet/routes/admin_stats.py` — Python-модуль
  Классы: `NodeStatus`, `NodesOverview`, `RevenueData`, `SubscriptionStats`, `FinancialStats`, `ServerStats`, `TariffStatItem`, `TariffStats`, `DashboardStats`, `SystemInfoResponse`, `TopReferrerItem`, `TopReferrersResponse`, `TopCampaignItem`, `TopCampaignsResponse`, `RecentPaymentItem`, `RecentPaymentsResponse`
  Функции: `get_dashboard_stats` — Get complete dashboard statistics for admin panel., `get_system_info` — Get system information for admin dashboard., `restart_node` — Restart a node., `toggle_node` — Enable or disable a node., `get_top_referrers` — Get top referrers with earnings breakdown by period., `get_top_campaigns` — Get top advertising campaigns with statistics., `get_recent_payments` — Get recent payments with user info.
- `app/cabinet/routes/admin_system_errors.py` — Python-модуль
  Классы: `SystemErrorListItem`, `SystemErrorDetail`, `SystemErrorListResponse`, `SystemErrorSummary`
  Функции: `system_errors_summary` — Сводка для бейджа в шапке и верхнего блока страницы., `list_system_errors` — Список ошибок с фильтрами по уровню, статусу доставки и периоду., `get_system_error` — Полная запись с трейсбеком и контекстом., `retry_system_error_delivery` — Повторно отправить сохранённую ошибку в админ-чат.
- `app/cabinet/routes/admin_tariffs.py` — Python-модуль
  Классы: нет
  Функции: `list_tariffs` — Get list of all tariffs., `get_available_servers` — Get list of all servers for tariff selection., `get_available_external_squads` — Fetch external squads from RemnaWave panel., `update_tariff_order` — Update the display order of tariffs., `get_tariff` — Get detailed tariff info., `create_new_tariff` — Create a new tariff., `update_existing_tariff` — Update an existing tariff., `delete_existing_tariff` — Delete a tariff., `toggle_tariff` — Toggle tariff active status., `toggle_trial_tariff` — Toggle tariff trial availability.
- `app/cabinet/routes/admin_tickets.py` — Python-модуль
  Классы: `AdminTicketUserInfo`, `AdminTicketResponse`, `AdminTicketDetailResponse`, `AdminTicketListResponse`, `AdminReplyRequest` (1 методов), `AdminStatusUpdateRequest`, `AdminStatsResponse`, `TicketSettingsResponse`, `TicketSettingsUpdateRequest`
  Функции: `get_ticket_stats` — Get ticket statistics., `get_ticket_settings` — Get ticket system settings., `update_ticket_settings` — Update ticket system settings — всё в system_settings: SLA формой, режим и уведомления через сервис., `get_all_tickets` — Get all tickets for admin., `get_ticket_detail` — Get ticket with all messages for admin., `reply_to_ticket` — Reply to a ticket as admin., `update_ticket_status` — Update ticket status.
- `app/cabinet/routes/admin_traffic.py` — Python-модуль
  Классы: нет
  Функции: `get_traffic_usage` — Get paginated per-user traffic usage by node., `get_traffic_enrichment` — Return enrichment data: device counts, spending, dates, last node., `export_traffic_csv` — Generate CSV with traffic usage and send to admin's Telegram DM.
- `app/cabinet/routes/admin_users.py` — Python-модуль
  Классы: нет
  Функции: `list_users` — Get paginated list of users with filtering and sorting., `get_users_stats` — Get overall users statistics., `get_user_by_remnawave_identifier` — Resolve an exact Remnawave identifier through its owning subscription only., `get_user_detail` — Get detailed user information by ID., `get_user_by_telegram` — Get user by Telegram ID., `get_user_panel_info` — Get user panel info from Remnawave (config links, traffic, connection data)., `get_subscription_request_history` — Get subscription request history from RemnaWave panel., `get_user_node_usage` — Get user per-node traffic usage (always 30 days with daily breakdown)., `update_user_balance` — Update user balance., `update_user_subscription` — Update user subscription., `delete_user_subscription` — Удалить конкретную подписку пользователя из его карточки., `get_user_available_tariffs` — Get list of tariffs available for a specific user., `block_user` — Block a user — sets DB status AND disables panel user in RemnaWave., `unblock_user` — Unblock a user — sets DB status AND re-enables panel user in RemnaWave., `send_user_message` — Send a direct Telegram message to the user via the bot., `update_user_restrictions` — Update user restrictions (topup, subscription)., `update_user_promo_group` — Update user promo group., `update_user_referral_commission` — Update user's individual referral commission percentage., `assign_user_referrer` — Manually assign a referrer to a user (e.g. cabinet-registered users without telegram_id)., `remove_user_referrer` — Remove who referred this user (set referred_by_id to None)., `remove_user_referral` — Remove a specific referral from a user (unbind referral_user from this referrer)., `get_user_devices` — Get user devices from Remnawave panel., `delete_user_device` — Delete a single device for user., `rename_user_device` — Set/clear a local alias for a user's HWID device (admin override)., `reset_user_devices` — Reset all devices for user., `full_delete_user` — Full user deletion - removes from bot database AND Remnawave panel., `reset_user_trial` — Reset user trial - allows user to activate trial again., `disable_user` — Disable user - deactivates subscription and blocks access., `get_user_referrals` — Get list of users referred by this user., `get_user_transactions` — Get user transactions., `get_user_activity` — Таймлайн активности пользователя в боте и кабинете., `get_user_sync_status` — Get sync status between bot and panel for a user., `sync_user_from_panel` — Sync user data FROM panel TO bot., `sync_user_to_panel` — Отправить данные пользователя из бота в панель., `get_user_gifts` — Get all gift subscriptions sent and received by user.
- `app/cabinet/routes/admin_wheel.py` — Python-модуль
  Классы: нет
  Функции: `get_admin_wheel_config` — Получить полную конфигурацию колеса., `update_admin_wheel_config` — Обновить конфигурацию колеса., `get_prizes` — Получить список призов., `create_prize` — Создать новый приз., `update_prize` — Обновить приз., `delete_prize_endpoint` — Удалить приз., `reorder_prizes` — Переупорядочить призы., `get_statistics` — Получить статистику колеса., `get_all_spins_endpoint` — Получить все спины с фильтрами.
- `app/cabinet/routes/admin_withdrawals.py` — Python-модуль
  Классы: нет
  Функции: `list_withdrawals` — List all withdrawal requests., `get_withdrawal_detail` — Get detailed withdrawal request with risk analysis., `approve_withdrawal` — Approve a withdrawal request., `reject_withdrawal` — Reject a withdrawal request., `complete_withdrawal` — Mark a withdrawal as completed (money transferred).
- `app/cabinet/routes/auth.py` — Python-модуль
  Классы: нет
  Функции: `auth_telegram` — Authenticate using Telegram WebApp initData., `auth_telegram_widget` — Authenticate using Telegram Login Widget data., `auth_telegram_oidc` — Authenticate using Telegram OIDC id_token (popup flow)., `register_email` — Register/link email to existing Telegram account., `verify_email_merge` — Confirm an email account merge with the code mailed to the existing account., `register_email_standalone` — Register new account with email and password., `verify_email` — Verify email with token and return auth tokens., `resend_verification` — Resend verification email., `resend_verification_public` — Повторно отправить письмо подтверждения с экрана «Проверьте почту»., `login_email` — Login with email and password., `refresh_token` — Refresh access token using refresh token., `logout` — Logout and revoke refresh token., `auto_login` — Auto-login using a short-lived JWT from guest purchase success page., `forgot_password` — Request password reset., `reset_password` — Reset password with token., `get_current_user` — Get current authenticated user info., `get_my_avatar` — Фото профиля Telegram для шапки кабинета., `get_my_permissions` — Get current user's RBAC permissions, roles, and level., `check_is_admin` — Check if current user is an admin (legacy config or RBAC)., `request_email_change` — Request email change., `verify_email_change` — Verify email change with code., `request_deep_link_token` — Generate a one-time deep link auth token., `poll_deep_link_token` — Poll for deep link auth completion.
- `app/cabinet/routes/balance.py` — Python-модуль
  Классы: нет
  Функции: `get_balance` — Get current user's balance., `get_transactions` — Get transaction history., `get_payment_methods` — Get available payment methods for the current user., `create_stars_invoice` — Создать Telegram Stars invoice для пополнения баланса., `create_topup` — Create payment for balance top-up., `get_pending_payments` — Get user's pending payments for manual verification., `get_latest_payment_by_method` — Get user's most recent payment for a given method (any status, not just pending)., `get_pending_payment_details` — Get details of a specific pending payment., `check_payment_status` — Manually check and update payment status.
- `app/cabinet/routes/branding.py` — Python-модуль
  Классы: `BrandingResponse`, `BrandingNameUpdate`, `ThemeColorsResponse`, `ThemeColorsUpdate`, `EnabledThemesResponse`, `EnabledThemesUpdate`, `AnimationEnabledResponse`, `AnimationEnabledUpdate`, `AnimationConfigResponse`, `AnimationConfigUpdate` (1 методов), `FullscreenEnabledResponse`, `FullscreenEnabledUpdate`, `EmailAuthEnabledResponse`, `EmailAuthEnabledUpdate`, `TelegramWidgetConfigResponse`, `LiteModeEnabledResponse`, `LiteModeEnabledUpdate`, `GiftEnabledResponse`, `GiftEnabledUpdate`, `OfflineConvGoal`, `AnalyticsCountersResponse`, `AnalyticsCountersUpdate`, `BotStartVideoResponse`, `YandexCidRequest`, `FooterEnabledResponse`, `FooterEnabledUpdate`
  Функции: `ensure_branding_dir` — Ensure branding directory exists., `get_setting_value` — Read a setting through the short in-process cache., `set_setting_value` — Set a setting value in database., `get_logo_path` — Get the path to the custom logo file (any supported format)., `has_custom_logo` — Check if a custom logo exists., `get_branding` — Get current branding settings., `get_logo` — Get the custom logo image., `get_favicon` — Иконка для <link rel="icon"> кабинета: логотип из админки или монограмма., `get_web_manifest` — Web app manifest кабинета: имя, цвета темы и иконки из брендинга., `get_app_icon` — Иконка приложения для манифеста: непрозрачный квадрат ``size``×``size``., `get_maskable_app_icon` — Maskable-иконка для Android: содержимое в безопасной зоне, края под маску системы., `get_bot_logo` — Get the BOT's menu logo (settings.LOGO_FILE, e.g. vpn_logo.png)., `get_bot_start_video` — Текущее видео стартового меню бота (Telegram file_id)., `upload_bot_start_video` — Загружает видео, которое бот прикрепляет к стартовому меню., `delete_bot_start_video` — Убирает видео — меню возвращается к фото-логотипу/тексту., `update_branding_name` — Update the project name. Admin only. Empty name allowed (logo only mode)., `upload_logo` — Upload a custom logo. Admin only., `delete_logo` — Delete custom logo and revert to letter. Admin only., `validate_hex_color` — Validate hex color format., `get_theme_colors` — Get current theme colors., `update_theme_colors` — Update theme colors. Admin only. Partial update supported., `reset_theme_colors` — Reset theme colors to defaults. Admin only., `get_enabled_themes` — Get which themes are enabled., `update_enabled_themes` — Update which themes are enabled. Admin only. At least one theme must be enabled., `get_animation_enabled` — Get animation enabled setting., `update_animation_enabled` — Update animation enabled setting. Admin only., `get_animation_config` — Get full animation config. Public endpoint., `update_animation_config` — Update animation config (partial update). Admin only., `get_fullscreen_enabled` — Get fullscreen enabled setting., `update_fullscreen_enabled` — Update fullscreen enabled setting. Admin only., `get_email_auth_enabled` — Get email auth enabled setting., `update_email_auth_enabled` — Update email auth enabled setting. Admin only., `get_telegram_widget_config` — Get Telegram Login Widget configuration., `get_analytics_counters` — Get analytics counter settings., `update_analytics_counters` — Update analytics counter settings. Admin only. Partial update supported., `store_yandex_cid` — Store Yandex Metrika ClientID for the authenticated cabinet user., `get_lite_mode_enabled` — Get lite mode enabled setting., `update_lite_mode_enabled` — Update lite mode enabled setting. Admin only., `get_gift_enabled` — Get gift feature enabled setting. Public endpoint., `update_gift_enabled` — Update gift feature enabled setting. Admin only., `get_footer_enabled` — Get legal footer enabled setting. Public endpoint - no authentication required., `update_footer_enabled` — Update legal footer enabled setting. Admin only.
- `app/cabinet/routes/gift.py` — Python-модуль
  Классы: нет
  Функции: `get_gift_config` — Get gift subscription configuration: tariffs, payment methods, balance., `create_gift_purchase` — Create a gift subscription purchase from the cabinet., `get_pending_gifts` — Get pending gift purchases that the current user can activate., `get_gift_purchase_status` — Get the status of a cabinet gift purchase., `get_sent_gifts` — Get all gifts the current user has sent., `get_received_gifts` — Get all gifts the current user has received., `activate_gift_by_code` — Activate a gift subscription by its code (token).
- `app/cabinet/routes/info.py` — Python-модуль
  Классы: `FaqPageResponse`, `RulesResponse`, `PrivacyPolicyResponse`, `PublicOfferResponse`, `SupportConfigResponse`, `InfoVisibilityResponse`, `LegalConsentConfigResponse`
  Функции: `get_faq_pages` — Get list of FAQ pages., `get_rules` — Get service rules - uses same function as bot., `get_privacy_policy` — Get privacy policy., `get_public_offer` — Get public offer., `get_available_languages` — Get list of available languages., `get_support_config` — Get support/tickets configuration for cabinet., `get_legal_consent_config` — Нужны ли новому пользователю галочки «ознакомлен» и с чем именно., `get_info_visibility`
- `app/cabinet/routes/landing.py` — Python-модуль
  Классы: `PurchaseStatusResponse`, `GiftClaimRequest` (1 методов), `GiftClaimResponse`
  Функции: `get_purchase_status` — Get the status of a guest purchase by token., `activate_purchase` — Activate a pending guest purchase, replacing the user's current subscription., `get_gift_claim` — Public gift claim page data (tariff, period, message, claim links)., `claim_gift` — Web (email) arm of the channel-agnostic gift claim.
- `app/cabinet/routes/media.py` — Python-модуль
  Классы: `MediaUploadResponse`
  Функции: `make_media_token` — Signed, expiring token authorizing download of `file_id` (any opaque subject string)., `upload_media` — Upload media file for use in ticket messages., `download_media` — Download media file by file_id.
- `app/cabinet/routes/notifications.py` — Python-модуль
  Классы: `NotificationSettingsResponse`, `NotificationSettingsUpdate`
  Функции: `get_notification_settings` — Get user's notification settings., `update_notification_settings` — Update user's notification settings., `send_test_notification` — Send a test notification to the user., `get_notification_history` — Get user's notification history.
- `app/cabinet/routes/oauth.py` — Python-модуль
  Классы: `OAuthProviderInfo`, `OAuthProvidersResponse`, `OAuthAuthorizeResponse`, `OAuthCallbackRequest`
  Функции: `get_oauth_providers` — Get list of enabled OAuth providers., `get_oauth_authorize_url` — Get authorization URL for an OAuth provider., `oauth_callback` — Handle OAuth callback: exchange code, find/create user, return JWT.
- `app/cabinet/routes/partner_application.py` — Python-модуль
  Классы: нет
  Функции: `get_partner_status` — Get partner status and latest application for current user., `get_campaign_stats` — Get detailed stats for a single campaign belonging to the current partner., `apply_for_partner` — Submit partner application.
- `app/cabinet/routes/promo.py` — Python-модуль
  Классы: `PromoOfferInfo`, `ActiveDiscountInfo`, `ClaimOfferRequest`, `ClaimOfferResponse`, `PromoGroupDiscounts`, `LoyaltyTierInfo`, `LoyaltyTiersResponse`
  Функции: `get_promo_offers` — Get list of available promo offers for the user., `get_active_discount` — Get user's currently active discount., `get_loyalty_tiers` — Get all loyalty tiers (promo groups with auto-assign thresholds) and user's progress., `claim_promo_offer` — Claim a promo offer., `clear_active_discount` — Clear user's active discount.
- `app/cabinet/routes/promocode.py` — Python-модуль
  Классы: `PromocodeActivateRequest`, `PromocodeActivateResponse`, `PromocodeDeactivateResponse`
  Функции: `activate_promocode` — Activate a promo code for the current user., `deactivate_discount_promocode` — Deactivate the currently active discount promo code for the current user.
- `app/cabinet/routes/referral.py` — Python-модуль
  Классы: нет
  Функции: `get_referral_info` — Get referral program info for current user., `get_referral_list` — Get list of invited users., `get_referral_earnings` — Get referral earnings history., `update_reward_choice` — Сохранить, что получать и куда класть дни., `get_referral_terms` — Get referral program terms.
- `app/cabinet/routes/settings_form.py` — Python-модуль
  Классы: нет
  Функции: `save_settings_form` — Записать значения по ключам Settings; ``set_value`` сам применяет их в памяти., `env_locked_fields` — Имена полей формы, чьи ключи закреплены в .env (порядок — как в форме)., `form_updates` — Переданные (не None) поля формы → ключи Settings.
- `app/cabinet/routes/spofy_subpage.py` — Python-модуль
  Классы: `CheckoutRequest`
  Функции: `require_subpage_key`, `resolve_owner` — Subscription (and its user) behind a Remnawave short UUID., `snapshot` — What the page compares before/after payment to show «готово»., `tariff_offers` — Tariffs a trial (or tariff-less) user can buy; plain period tariffs only (v1)., `save_renewal_cart` — Mirror of POST /subscription/renew on insufficient funds — without ever charging., `save_tariff_cart` — Mirror of POST /subscription/purchase-tariff on insufficient funds (plain period tariffs)., `device_offer` — Device add-on with an exact quote per count., `get_offer`, `safe_return_url` — The page's return address, or None when it must not be handed to a payment provider., `checkout`, `payment_status`
- `app/cabinet/routes/subscription.py` — Python-модуль
  Классы: нет
  Функции: `get_subscription`
- `app/cabinet/routes/subscription_modules/`
- `app/cabinet/routes/support_ws.py` — Python-модуль
  Классы: `WsUserContext` (2 методов), `UploadTransfer` (1 методов), `DownloadTransfer` (1 методов), `SupportWsSession` (2 методов), `SupportWsManager` (4 методов)
  Функции: `support_mobile_websocket_endpoint` — Mobile-only support ticket command WebSocket., `register_support_ticket_event_bridge` — Attach the support-socket bridge to the global event emitter (idempotent).
- `app/cabinet/routes/ticket_notifications.py` — Python-модуль
  Классы: `TicketNotificationResponse`, `TicketNotificationListResponse`, `UnreadCountResponse`
  Функции: `get_user_notifications` — Get ticket notifications for current user., `get_user_unread_count` — Get unread notifications count for current user., `mark_notification_as_read` — Mark a notification as read., `mark_all_notifications_as_read` — Mark all notifications as read for current user., `mark_ticket_notifications_as_read` — Mark all notifications for a specific ticket as read., `get_admin_notifications` — Get ticket notifications for admins., `get_admin_unread_count` — Get unread notifications count for admins., `mark_admin_notification_as_read` — Mark an admin notification as read., `mark_all_admin_notifications_as_read` — Mark all admin notifications as read., `mark_admin_ticket_notifications_as_read` — Mark all admin notifications for a specific ticket as read.
- `app/cabinet/routes/tickets.py` — Python-модуль
  Классы: нет
  Функции: `new_ticket_message` — Сообщение тикета из запроса кабинета (пользователь или админ)., `ticket_message_to_response` — Convert TicketMessage to response (общий для кабинета пользователя и админки)., `get_tickets` — Get user's support tickets., `create_ticket` — Create a new support ticket., `get_ticket` — Get ticket with all messages., `close_ticket` — Close the user's own ticket (the bot has the same button). Closing twice is not an error., `add_ticket_message` — Add message to existing ticket.
- `app/cabinet/routes/unsubscribe.py` — Python-модуль
  Классы: нет
  Функции: `unsubscribe_page` — Ничего не меняет — только отдаёт самоотправляющуюся форму., `unsubscribe_one_click` — Единственное место, где отписка применяется.
- `app/cabinet/routes/websocket.py` — Python-модуль
  Классы: нет
  Функции: `verify_cabinet_ws_token` — Проверить JWT токен для WebSocket., `cabinet_websocket_endpoint` — WebSocket endpoint для real-time уведомлений кабинета., `notify_user_ticket_reply` — Уведомить пользователя об ответе в тикете., `notify_admins_new_ticket` — Уведомить админов о новом тикете., `notify_admins_ticket_reply` — Уведомить админов об ответе пользователя., `notify_user_balance_topup` — Уведомить пользователя о пополнении баланса., `notify_user_subscription_activated` — Уведомить пользователя об активации подписки., `notify_user_subscription_renewed` — Уведомить пользователя о продлении подписки., `notify_user_devices_purchased` — Уведомить пользователя о покупке устройств., `notify_user_traffic_purchased` — Уведомить пользователя о покупке трафика.
- `app/cabinet/routes/wheel.py` — Python-модуль
  Классы: `StarsInvoiceResponse`
  Функции: `get_wheel_config` — Получить конфигурацию колеса удачи., `check_spin_availability` — Проверить доступность спина., `spin_wheel` — Крутить колесо удачи., `get_spin_history` — Получить историю спинов пользователя., `create_stars_invoice` — Создать Telegram Stars invoice для оплаты спина колеса.
- `app/cabinet/routes/withdrawal.py` — Python-модуль
  Классы: нет
  Функции: `get_withdrawal_balance` — Get withdrawal balance stats for current user., `create_withdrawal` — Create a withdrawal request., `get_withdrawal_history` — Get user's withdrawal request history., `cancel_withdrawal` — Cancel a pending withdrawal request.

##### app/cabinet/routes/subscription_modules

- `app/cabinet/routes/subscription_modules/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/routes/subscription_modules/autopay.py` — Python-модуль
  Классы: нет
  Функции: `update_autopay` — Update autopay settings.
- `app/cabinet/routes/subscription_modules/daily.py` — Python-модуль
  Классы: нет
  Функции: `toggle_subscription_pause` — Toggle pause/resume for daily subscription.
- `app/cabinet/routes/subscription_modules/devices.py` — Python-модуль
  Классы: `DeviceRenameRequest`
  Функции: `purchase_devices` — Purchase additional device slots for subscription., `save_devices_cart` — Save cart for device purchase (for insufficient balance flow)., `get_device_price` — Get price for additional devices., `get_devices` — Get list of connected devices., `rename_device` — Set/clear a local alias for the user's HWID device., `delete_device` — Delete a specific device by HWID., `delete_all_devices` — Delete all connected devices., `get_device_reduction_info` — Get info about device limit reduction availability., `reduce_devices` — Reduce device limit (no refund).
- `app/cabinet/routes/subscription_modules/helpers.py` — Python-модуль
  Классы: нет
  Функции: `resolve_subscription` — Подписка пользователя: одна на человека., `ensure_subscription_has_tariff` — Докупки старой подписке не продаются — сперва переход на тариф.
- `app/cabinet/routes/subscription_modules/multi_tariff.py` — Python-модуль
  Классы: `SubscriptionListItem`, `SubscriptionsListResponse`
  Функции: `list_subscriptions` — Подписки пользователя; ``multi_tariff_enabled`` всегда False — поле читает кабинет., `delete_subscription` — Delete an expired/disabled subscription. Active subscriptions cannot be deleted.
- `app/cabinet/routes/subscription_modules/purchase.py` — Python-модуль
  Классы: нет
  Функции: `get_purchase_options` — Get all subscription purchase options (periods, servers, traffic, devices)., `purchase_tariff` — Purchase a tariff (for tariffs mode)., `get_trial_info` — Get trial subscription info and availability., `activate_trial` — Activate trial subscription.
- `app/cabinet/routes/subscription_modules/renewal.py` — Python-модуль
  Классы: нет
  Функции: `get_renewal_options` — Get available subscription renewal options with prices., `renew_subscription` — Renew subscription (pay from balance).
- `app/cabinet/routes/subscription_modules/revoke.py` — Python-модуль
  Классы: нет
  Функции: `revoke_subscription` — Revoke and reissue subscription (generate new connection link).
- `app/cabinet/routes/subscription_modules/servers.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/routes/subscription_modules/status.py` — Python-модуль
  Классы: нет
  Функции: `get_subscription` — Get current user's subscription details (served by GET /subscription in ../subscription.py)., `get_connection_link` — Get subscription connection link and instructions., `get_app_config` — Get app configuration for connection with deep links.
- `app/cabinet/routes/subscription_modules/tariff_switch.py` — Python-модуль
  Классы: нет
  Функции: `preview_tariff_switch` — Preview tariff switch - shows cost calculation., `switch_tariff` — Switch to a different tariff without changing end date.
- `app/cabinet/routes/subscription_modules/traffic.py` — Python-модуль
  Классы: нет
  Функции: `get_traffic_packages` — Get available traffic packages., `purchase_traffic` — Purchase additional traffic., `save_traffic_cart` — Save cart for traffic purchase (for insufficient balance flow)., `refresh_traffic` — Refresh traffic usage from RemnaWave panel.

#### app/cabinet/schemas

- `app/cabinet/schemas/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/schemas/auth.py` — Python-модуль
  Классы: `TelegramAuthRequest`, `TelegramWidgetAuthRequest`, `TelegramOIDCAuthRequest`, `EmailRegisterRequest`, `EmailVerifyRequest`, `EmailLoginRequest`, `RefreshTokenRequest`, `VerificationResendRequest`, `PasswordForgotRequest`, `PasswordResetRequest`, `AutoLoginRequest`, `TokenResponse`, `UserResponse`, `UserAvatarResponse`, `EmailRegisterStandaloneRequest`, `CampaignBonusInfo`, `AuthResponse`, `RegisterResponse`, `EmailChangeRequest`, `EmailChangeVerifyRequest`, `EmailMergeVerifyRequest`, `EmailChangeResponse`, `DeepLinkTokenResponse`, `DeepLinkPollRequest`
  Функции: нет
- `app/cabinet/schemas/balance.py` — Python-модуль
  Классы: `BalanceResponse`, `TransactionResponse`, `TransactionListResponse`, `PaymentMethodResponse`, `TopUpRequest`, `TopUpResponse`, `StarsInvoiceRequest`, `StarsInvoiceResponse`, `PendingPaymentResponse`, `PendingPaymentListResponse`, `ManualCheckResponse`
  Функции: нет
- `app/cabinet/schemas/broadcasts.py` — Python-модуль
  Классы: `BroadcastFilter`, `TariffFilter`, `BroadcastFiltersResponse`, `BroadcastAudienceCondition`, `BroadcastAudience` (1 методов), `TariffForBroadcast`, `BroadcastTariffsResponse`, `BroadcastButton`, `BroadcastButtonsResponse`, `CustomBroadcastButton` (1 методов), `BroadcastMediaRequest`, `BroadcastResponse`, `BroadcastListResponse`, `BroadcastAudiencePreviewRequest`, `BroadcastAudiencePreviewUser`, `BroadcastAudiencePreviewResponse`, `BroadcastAudienceUserSearchResponse`, `EmailFilterItem`, `EmailFiltersResponse`, `CombinedBroadcastCreateRequest`, `EmailRenderRequest`, `EmailRenderResponse`
  Функции: нет
- `app/cabinet/schemas/campaigns.py` — Python-модуль
  Классы: `TariffInfo`, `CampaignListItem`, `CampaignListResponse`, `CampaignDetailResponse`, `CampaignCreateRequest`, `CampaignUpdateRequest`, `CampaignToggleResponse`, `CampaignStatisticsResponse`, `CampaignRegistrationItem`, `CampaignRegistrationsResponse`, `CampaignsOverviewResponse`, `AvailablePartnerItem`, `ServerSquadInfo`, `AdminDailyStatItem`, `AdminPeriodStats`, `AdminPeriodChange`, `AdminPeriodComparison`, `AdminTopRegistrationItem`, `AdminCampaignChartDataResponse`
  Функции: нет
- `app/cabinet/schemas/channel.py` — Python-модуль
  Классы: `ChannelResponse`, `ChannelListResponse`, `ChannelCreateRequest` (2 методов), `ChannelUpdateRequest` (2 методов)
  Функции: нет
- `app/cabinet/schemas/gift.py` — Python-модуль
  Классы: `GiftConfigSubOption`, `GiftConfigTariffPeriod`, `GiftConfigTariff`, `GiftConfigPaymentMethod`, `GiftConfigResponse`, `GiftPurchaseRequest` (1 методов), `GiftPurchaseResponse`, `GiftPurchaseStatusResponse`, `PendingGiftResponse`, `SentGiftResponse`, `ReceivedGiftResponse`, `ActivateGiftRequest`, `ActivateGiftResponse`
  Функции: нет
- `app/cabinet/schemas/media.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/schemas/partners.py` — Python-модуль
  Классы: `PartnerApplicationRequest`, `PartnerApplicationInfo`, `PartnerCampaignInfo`, `PartnerStatusResponse`, `DailyStatItem`, `PeriodStats`, `PeriodChange`, `PeriodComparison`, `CampaignReferralItem`, `PartnerCampaignDetailedStats`, `AdminPartnerApplicationItem`, `AdminPartnerApplicationsResponse`, `AdminApproveRequest`, `AdminRejectRequest`, `AdminPartnerItem`, `AdminPartnerListResponse`, `CampaignSummary`, `AdminPartnerDetailResponse`, `AdminUpdateCommissionRequest`
  Функции: нет
- `app/cabinet/schemas/pinned_messages.py` — Python-модуль
  Классы: `PinnedMessageMedia`, `PinnedMessageCreateRequest`, `PinnedMessageUpdateRequest`, `PinnedMessageResponse`, `PinnedMessageBroadcastResponse`, `PinnedMessageUnpinResponse`, `PinnedMessageListResponse`
  Функции: нет
- `app/cabinet/schemas/referral.py` — Python-модуль
  Классы: `ReferralInfoResponse`, `ReferralItemResponse`, `ReferralListResponse`, `ReferralEarningResponse`, `ReferralEarningsListResponse`, `ReferralDaysTargetOption`, `ReferralRewardChoiceRequest`, `ReferralProgramLevel`, `ReferralTermsResponse`, `ReferralRewardLevelResponse`, `ReferralRewardTariffOption`, `ReferralRewardLevelsResponse`, `ReferralRewardLevelUpdateRequest`, `ReferralSchemeUpdateRequest`, `ReferralDepthUpdateRequest`, `ReferralLevelsModeUpdateRequest`
  Функции: нет
- `app/cabinet/schemas/remnawave.py` — Python-модуль
  Классы: `ConnectionStatus`, `RemnaWaveStatusResponse`, `SystemSummary`, `ServerInfo`, `Bandwidth`, `TrafficPeriod`, `TrafficPeriods`, `SystemStatsResponse`, `NodeInfo`, `NodesListResponse`, `NodesOverview`, `NodeActionRequest`, `NodeActionResponse`, `GeocheckRequest` (4 методов), `GeocheckStartResponse`, `GeocheckImage`, `GeocheckResult`, `GeocheckJobResponse`, `SquadWithLocalInfo`, `SquadsListResponse`, `AutoSyncStatus`, `AutoSyncToggleRequest`, `AutoSyncRunResponse`, `SyncMode`, `SyncResponse`, `RecapTotal`, `RecapThisMonth`, `RecapResponse`, `PlatformCount`, `AppCount`, `DeviceTopUser`, `DevicesStatsResponse`, `TopConsumer`, `TopConsumersResponse`, `HealthResponse`, `SubscriptionRequestStatsResponse`
  Функции: нет
- `app/cabinet/schemas/servers.py` — Python-модуль
  Классы: `PromoGroupInfo`, `ServerListItem`, `ServerListResponse`, `ServerDetailResponse`, `ServerUpdateRequest`, `ServerToggleResponse`, `ServerTrialToggleResponse`, `ServerSyncResponse`
  Функции: нет
- `app/cabinet/schemas/subscription.py` — Python-модуль
  Классы: `ServerInfo`, `TrafficPurchaseInfo`, `SubscriptionData`, `SubscriptionStatusResponse`, `RenewalOptionResponse`, `RenewalRequest`, `TrafficPackageResponse`, `TrafficPurchaseRequest`, `DevicePurchaseRequest`, `AutopayUpdateRequest`, `TrialActivateRequest`, `TrialInfoResponse`, `TariffPurchaseRequest`
  Функции: нет
- `app/cabinet/schemas/tariffs.py` — Python-модуль
  Классы: `PeriodPrice` (1 методов), `ServerTrafficLimit`, `ServerInfo`, `PromoGroupInfo`, `TariffListItem`, `TariffListResponse`, `TariffDetailResponse`, `ExternalSquadInfoResponse`, `TariffCreateRequest` (1 методов), `TariffUpdateRequest` (1 методов), `TariffSortOrderRequest`, `TariffToggleResponse`, `TariffTrialResponse`
  Функции: нет
- `app/cabinet/schemas/tickets.py` — Python-модуль
  Классы: `TicketMediaItem` (1 методов), `TicketMessageResponse`, `TicketResponse`, `TicketDetailResponse`, `TicketListResponse`, `TicketCreateRequest` (1 методов), `TicketMessageCreateRequest` (1 методов)
  Функции: нет
- `app/cabinet/schemas/traffic.py` — Python-модуль
  Классы: `TrafficNodeInfo`, `SubscriptionTrafficInfo`, `UserTrafficItem`, `TrafficUsageResponse`, `SubscriptionEnrichmentInfo`, `UserTrafficEnrichment`, `TrafficEnrichmentResponse`, `ExportCsvRequest`, `ExportCsvResponse`
  Функции: нет
- `app/cabinet/schemas/users.py` — Python-модуль
  Классы: `UserStatusEnum`, `SortByEnum`, `SortOrderEnum`, `TrafficPurchaseItem`, `UserSubscriptionInfo`, `UserPromoGroupInfo`, `SubscriptionListItem`, `UserListItem`, `UsersListResponse`, `UserByRemnawaveResponse`, `UserTransactionItem`, `UserReferralInfo`, `UserDetailResponse`, `UserPanelInfoResponse`, `UserNodeUsageItem`, `UserNodeUsageResponse`, `UpdateBalanceRequest`, `UpdateBalanceResponse`, `UpdateSubscriptionRequest`, `UpdateSubscriptionResponse`, `UpdateUserStatusResponse`, `SendUserMessageRequest`, `SendUserMessageResponse`, `UpdateRestrictionsRequest`, `UpdateRestrictionsResponse`, `UpdatePromoGroupRequest`, `UpdatePromoGroupResponse`, `UpdateReferralCommissionRequest`, `UpdateReferralCommissionResponse`, `AssignReferrerRequest`, `AssignReferrerResponse`, `RemoveReferrerResponse`, `RemoveReferralResponse`, `DeviceInfo`, `UserDevicesResponse`, `DeleteDeviceResponse`, `RenameDeviceRequest`, `RenameDeviceResponse`, `ResetDevicesResponse`, `UsersStatsResponse`, `PeriodPriceInfo`, `UserAvailableTariffItem`, `UserAvailableTariffsResponse`, `PanelUserInfo`, `SyncFromPanelRequest`, `SyncFromPanelResponse`, `SyncToPanelRequest`, `SyncToPanelResponse`, `PanelSyncStatusResponse`, `FullDeleteUserRequest`, `FullDeleteUserResponse`, `ResetTrialRequest`, `ResetTrialResponse`, `DisableUserRequest`, `DisableUserResponse`, `AdminUserGiftItem`, `AdminUserGiftsResponse`
  Функции: нет
- `app/cabinet/schemas/wheel.py` — Python-модуль
  Классы: `WheelPaymentType`, `WheelPrizeType`, `WheelPrizeDisplay`, `WheelConfigResponse`, `SpinAvailabilityResponse`, `SpinRequest`, `SpinResultResponse`, `SpinHistoryItem`, `SpinHistoryResponse`, `WheelPrizeAdminResponse`, `AdminWheelConfigResponse`, `UpdateWheelConfigRequest`, `CreatePrizeRequest`, `UpdatePrizeRequest`, `ReorderPrizesRequest`, `AdminSpinItem`, `AdminSpinsResponse`, `WheelStatisticsResponse`
  Функции: нет
- `app/cabinet/schemas/withdrawals.py` — Python-модуль
  Классы: `WithdrawalBalanceResponse`, `WithdrawalCreateRequest`, `WithdrawalItemResponse`, `WithdrawalListResponse`, `WithdrawalCreateResponse`, `AdminWithdrawalItem`, `AdminWithdrawalListResponse`, `AdminWithdrawalDetailResponse`, `AdminApproveWithdrawalRequest`, `AdminRejectWithdrawalRequest`
  Функции: нет

#### app/cabinet/services

- `app/cabinet/services/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/services/email_layout.py` — Python-модуль
  Классы: нет
  Функции: `inline_email_styles` — Дублирует стили классов встроенной обёртки в style="" — только у её писем и один раз., `layout_is_valid` — Обёртка без {content} проглотила бы тело каждого письма., `unsubscribe_block` — Ссылка отписки — только у маркетинговых писем, у остальных пусто., `build_layout_context` — Реальные значения плейсхолдеров обёртки для языка., `render_email_layout` — Подставляет плейсхолдеры обёртки. Недостающие берутся из build_layout_context., `extract_content_fragment` — Тело письма из готового HTML по маркерам, None если маркеров нет., `reset_email_layout_cache`, `set_cached_email_layouts` — Заменяет кэш; обёртки без {content} отбрасываются с предупреждением., `get_cached_email_layout` — Обёртка для языка; нет своей — русская; нет и её — None (встроенная)., `resolve_email_layout`, `is_layout_cache_stale`, `refresh_email_layout_cache` — Подтягивает сохранённые обёртки, если кэш устарел (или force после сохранения).
- `app/cabinet/services/email_service.py` — Python-модуль
  Классы: `EmailService` (24 методов)
  Функции: нет
- `app/cabinet/services/email_template_overrides.py` — Python-модуль
  Классы: нет
  Функции: `apply_legacy_aliases` — Возвращает копию контекста со старыми именами плейсхолдеров, если есть новые., `build_common_context` — Values for the type-independent placeholders., `substitute_context_vars` — Replace {var} placeholders in template text with context values., `get_template_override` — Get custom email template from the database., `get_all_overrides` — Get all custom template overrides from the database., `get_overrides_for_type` — Get all language overrides for a specific notification type., `save_template_override` — Save or update a custom email template in the database., `get_rendered_override` — Get a custom template override rendered with the base email template., `delete_template_override` — Delete a custom template override (revert to default).
- `app/cabinet/services/email_templates.py` — Python-модуль
  Классы: `EmailNotificationTemplates` (72 методов)
  Функции: нет
- `app/cabinet/services/email_type_switch.py` — Python-модуль
  Классы: нет
  Функции: `can_disable_email_type`, `is_email_type_enabled` — False — письмо этого типа отключено админом; отправитель молча пропускает его., `set_email_type_enabled` — Включает/выключает тип письма; возвращает новый набор отключённых.
- `app/cabinet/services/email_unsubscribe.py` — Python-модуль
  Классы: нет
  Функции: `build_token` — Собирает токен отписки для конкретного адреса., `parse_token` — Достаёт (user_id, category) БЕЗ проверки подписи., `verify_token` — Проверяет подпись токена против текущего адреса пользователя., `build_unsubscribe_url` — Публичная ссылка отписки. Пустая строка = отписки в этом письме не будет., `build_unsubscribe_mailto` — mailto-вариант для клиентов без HTTP one-click. Пусто, если не настроен., `apply_unsubscribe` — Выключает маркетинговые рассылки по токену.

#### app/cabinet/utils

- `app/cabinet/utils/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/cabinet/utils/app_icon.py` — Python-модуль
  Классы: нет
  Функции: `is_hex_color`, `readable_text_on` — Белый или тёмный текст на заливке — тот же выбор, что readableTextOnHex в кабинете., `logo_edge_color` — Цвет, которым логотип залит до краёв; ``None`` — единого цвета у краёв нет., `logo_app_icon` — PNG ``size``×``size``: логотип вписан целиком по центру на непрозрачном фоне., `monogram_app_icon` — PNG ``size``×``size``: первая буква на сплошной заливке ``background``., `render_app_icon` — Иконка приложения: из логотипа, если он растровый и читается, иначе монограмма.
- `app/cabinet/utils/brand_monogram.py` — Python-модуль
  Классы: нет
  Функции: `monogram_letter` — Первая буква строки заглавной; при пустой строке — ``fallback``., `monogram_svg`, `bold_font`, `monogram_png` — PNG-монограмма в геометрии SVG. Рисуется один раз на букву.
- `app/cabinet/utils/device_ownership.py` — Python-модуль
  Классы: нет
  Функции: `verify_hwid_belongs_to_user` — Best-effort check that `hwid` is on one of the user's RemnaWave panels.
- `app/cabinet/utils/favicon_tile.py` — Python-модуль
  Классы: нет
  Функции: `is_raster_logo`, `rounded_logo_tile` — PNG ``size``×``size``: логотип вписан по принципу object-fit: cover, углы прозрачные., `cached_rounded_logo_tile` — Плитка по файлу логотипа; перерисовывается только когда файл заменили.
- `app/cabinet/utils/fonts/`
- `app/cabinet/utils/links.py` — Python-модуль
  Классы: нет
  Функции: `get_campaign_deep_link` — Generate a Telegram deep link for a campaign., `get_campaign_web_link` — Generate a web app link for a campaign.

##### app/cabinet/utils/fonts

- `app/cabinet/utils/fonts/OFL.txt` — файл
- `app/cabinet/utils/fonts/manrope-variable.ttf` — файл

### app/database

- `app/database/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/database/auth_methods.py` — Python-модуль
  Классы: нет
  Функции: `compute_auth_methods` — Вычисляет список методов авторизации пользователя.
- `app/database/constants.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/database/crud/`
- `app/database/database.py` — Python-модуль
  Классы: нет
  Функции: `get_db` — Стандартная dependency для FastAPI, `sync_postgres_sequences` — Ensure PostgreSQL sequences match the current max values after restores.
- `app/database/errors.py` — Python-модуль
  Классы: нет
  Функции: `is_missing_greenlet` — Ленивая подгрузка вне greenlet: обращение к незагруженному атрибуту в async-коде.
- `app/database/local_date.py` — Python-модуль
  Классы: нет
  Функции: `local_date_expr` — SQL-выражение «дата ``column`` в зоне ``tz``» (по умолчанию settings.TIMEZONE)., `as_date` — Значение ``local_date_expr`` из строки результата как ``date``.
- `app/database/migrations.py` — Python-модуль
  Классы: нет
  Функции: `run_alembic_upgrade` — Run ``alembic upgrade head``, handling fresh and legacy databases.
- `app/database/models.py` — Python-модуль
  Классы: `AwareDateTime` (2 методов), `UserStatus`, `SubscriptionStatus`, `TransactionType`, `PromoCodeType`, `PaymentMethod`, `MainMenuButtonActionType`, `MainMenuButtonVisibility`, `WheelPrizeType`, `WheelSpinPaymentType`, `CryptoBotPayment` (5 методов), `XRocketPayment` (5 методов), `Pay2328Payment` (5 методов), `WataPayment` (2 методов), `PlategaPayment` (2 методов), `PlategaSubscription` (1 методов), `PromoGroup` (3 методов), `UserPromoGroup` (1 методов), `Tariff` (16 методов), `PartnerStatus`, `User` (9 методов), `Subscription` (13 методов), `GraceAccessSessionModel`, `TrafficPurchase` (1 методов), `Transaction` (1 методов), `PaidTrafficResetIntent`, `SubscriptionConversion` (1 методов), `PromoCode` (2 методов), `PromoCodeUse`, `CouponStatus`, `CouponBatch` (2 методов), `Coupon` (1 методов), `ReferralRewardType`, `ReferralRewardTrigger`, `ReferralRewardMode`, `ReferralRewardLevel` (1 методов), `ReferralEarning` (1 методов), `WithdrawalRequestStatus`, `WithdrawalRequest` (1 методов), `PartnerApplication`, `Squad` (1 методов), `ServiceRule`, `PrivacyPolicy`, `PublicOffer`, `LegalConsent`, `RecurrentPayments`, `FaqSetting`, `FaqPage`, `SystemSetting`, `EmailTemplate`, `MonitoringLog`, `SentNotification`, `SubscriptionEvent`, `DiscountOffer`, `PromoOfferTemplate`, `SubscriptionTemporaryAccess`, `PromoOfferLog`, `BroadcastHistory`, `ServerSquad` (3 методов), `SubscriptionServer`, `SupportAuditLog`, `UserMessage` (1 методов), `WelcomeText`, `PinnedMessage`, `AdvertisingCampaign` (4 методов), `AdvertisingCampaignRegistration` (1 методов), `TicketStatus`, `Ticket` (6 методов), `TicketMessage` (2 методов), `WebApiToken` (1 методов), `MainMenuButton` (1 методов), `MenuLayoutHistory` (1 методов), `ButtonClickLog` (1 методов), `Webhook` (1 методов), `WebhookDelivery` (1 методов), `CabinetRefreshToken` (4 методов), `WheelConfig` (1 методов), `WheelPrize` (1 методов), `WheelSpin` (1 методов), `TicketNotification` (1 методов), `PaymentMethodConfig` (1 методов), `RequiredChannel` (1 методов), `UserChannelSubscription` (1 методов), `AdminRole` (1 методов), `UserRole` (1 методов), `AccessPolicy` (1 методов), `AdminAuditLog` (1 методов), `GuestPurchaseStatus`, `GuestPurchase` (1 методов), `NewsArticle` (1 методов), `NewsCategory` (1 методов), `NewsTag` (1 методов), `YandexClientIdMap`, `InfoPage`, `UserDeviceAlias`, `SystemErrorEvent`, `EmailQueueItem`, `ReachabilityBatch`, `ReachabilityJob`, `ReachabilityLeg`, `ReachabilityTargetPref`, `DpiCheckerAction`, `UserReminder`, `UserReminderState`, `MassSendJob`, `DecisionLog`
  Функции: нет

#### app/database/crud

- `app/database/crud/campaign.py` — Python-модуль
  Классы: нет
  Функции: `create_campaign`, `get_campaign_by_id`, `get_campaign_by_start_parameter`, `get_campaigns_list` — Кампании, новые первыми., `get_campaigns_count`, `update_campaign`, `delete_campaign`, `get_campaign_registration_by_user`, `record_campaign_registration` — Создаёт или возвращает запись регистрации в рекламной кампании., `get_campaign_statistics`, `get_campaigns_statistics` — ``get_campaign_statistics`` для пачки кампаний за 6 запросов вместо 9 на каждую., `get_campaigns_overview`
- `app/database/crud/cryptobot.py` — Python-модуль
  Классы: нет
  Функции: `create_cryptobot_payment`, `get_cryptobot_payment_by_invoice_id`, `get_cryptobot_payment_by_id`, `get_cryptobot_payment_by_invoice_id_for_update`, `update_cryptobot_payment_status`, `link_cryptobot_payment_to_transaction`
- `app/database/crud/discount_offer.py` — Python-модуль
  Классы: нет
  Функции: `upsert_discount_offer` — Create or refresh a discount offer for a user., `get_offer_by_id`, `mark_offer_claimed`, `deactivate_expired_offers`, `get_latest_claimed_offer_for_user`
- `app/database/crud/faq.py` — Python-модуль
  Классы: нет
  Функции: `get_faq_setting`, `set_faq_enabled`, `get_faq_pages`, `get_faq_page_by_id`, `create_faq_page`, `update_faq_page`, `delete_faq_page`
- `app/database/crud/landing.py` — Python-модуль
  Классы: нет
  Функции: `generate_purchase_token` — Generate a cryptographically secure purchase token., `create_guest_purchase` — Create a new guest purchase with an auto-generated token., `get_purchase_by_token` — Get a guest purchase by its token., `update_purchase_status` — Update the status of a guest purchase and optional extra fields.
- `app/database/crud/notification.py` — Python-модуль
  Классы: нет
  Функции: `notification_sent`, `list_sent_notification_keys` — Все отметки «уже отправлено» одного типа для пачки подписок одним запросом., `record_notification`, `clear_notifications`, `clear_notification_by_type`
- `app/database/crud/pay2328.py` — Python-модуль
  Классы: нет
  Функции: `create_pay2328_payment`, `get_pay2328_payment_by_uuid`, `get_pay2328_payment_by_order_id`, `get_pay2328_payment_by_id`, `get_pay2328_payment_by_id_for_update`, `update_pay2328_payment`, `link_pay2328_payment_to_transaction`
- `app/database/crud/payment_gateway_stats.py` — Python-модуль
  Классы: нет
  Функции: `get_gateway_success_rates` — Per-gateway {method, total, paid, success_rate} for gateways with activity.
- `app/database/crud/platega.py` — Python-модуль
  Классы: нет
  Функции: `create_platega_payment`, `get_platega_payment_by_id`, `get_platega_payment_by_id_for_update`, `get_platega_payment_by_transaction_id`, `get_platega_payment_by_correlation_id`, `update_platega_payment`, `link_platega_payment_to_transaction`
- `app/database/crud/privacy_policy.py` — Python-модуль
  Классы: нет
  Функции: `get_privacy_policy`, `upsert_privacy_policy`
- `app/database/crud/promo_group.py` — Python-модуль
  Классы: нет
  Функции: `get_promo_groups_with_counts`, `get_auto_assign_promo_groups`, `has_auto_assign_promo_groups`, `get_promo_group_by_id`, `count_promo_groups`, `get_default_promo_group`, `create_promo_group`, `update_promo_group`, `delete_promo_group`, `count_promo_group_members`
- `app/database/crud/promo_offer_log.py` — Python-модуль
  Классы: нет
  Функции: `log_promo_offer_action` — Persist a promo offer log entry., `list_promo_offer_logs`
- `app/database/crud/promo_offer_template.py` — Python-модуль
  Классы: нет
  Функции: `ensure_default_templates`, `list_promo_offer_templates`, `get_promo_offer_template_by_id`, `update_promo_offer_template`
- `app/database/crud/promocode.py` — Python-модуль
  Классы: нет
  Функции: `get_promocode_by_code`, `get_promocode_by_id` — Получает промокод по ID с eager loading всех связанных данных., `check_promocode_validity` — Проверяет существование и валидность промокода без активации., `create_promocode`, `check_user_promocode_usage`, `create_promocode_use`, `get_promocode_use_by_user_and_code`, `count_user_recent_activations` — Подсчитывает количество активаций промокодов пользователем за последние N часов., `get_promocodes_list`, `get_promocodes_count`, `update_promocode`, `delete_promocode`, `get_active_discount_promocode_for_user` — Находит активный промокод на скидку, который сейчас действует у пользователя., `get_promocode_statistics`
- `app/database/crud/public_offer.py` — Python-модуль
  Классы: нет
  Функции: `get_public_offer`, `upsert_public_offer`
- `app/database/crud/rbac.py` — Python-модуль
  Классы: `UserRoleCRUD` (2 методов), `AuditLogCRUD` (1 методов)
  Функции: нет
- `app/database/crud/referral.py` — Python-модуль
  Классы: нет
  Функции: `not_referee_directed` — Предикат «строка описывает МОЕГО реферала»., `get_user_campaign_id` — Получить campaign_id первой регистрации пользователя., `create_referral_earning` — Строка реферального ledger'а., `get_commission_payment_count` — Подсчитать количество комиссионных начислений реферера за платежи конкретного реферала., `get_referral_statistics`, `get_user_referral_stats_light` — Облегчённая статистика для главного меню: один запрос к Postgres.
- `app/database/crud/referral_reward_level.py` — Python-модуль
  Классы: нет
  Функции: `normalize_reward_preference` — Предпочтение награды или ``None`` — «как настроено правилом»., `normalize_mode` — Режим наград с приведением к известному значению., `normalize_trigger`, `get_all_reward_levels`, `get_reward_level`, `upsert_reward_level` — Создать или обновить правило уровня., `delete_reward_level`
- `app/database/crud/required_channel.py` — Python-модуль
  Классы: нет
  Функции: `validate_channel_id` — Validate and normalize channel_id. Auto-prefixes -100 for bare digits., `get_active_channels` — Get all active required channels (sorted by sort_order)., `get_all_channels` — Get all required channels (including inactive)., `get_channel_by_id`, `add_channel`, `update_channel` — Update channel fields. Only fields in _UPDATABLE_FIELDS are accepted., `delete_channel`, `toggle_channel`, `upsert_user_channel_sub` — Upsert user subscription status (PostgreSQL ON CONFLICT)., `get_user_channel_subs` — Get all channel subscriptions for a user.
- `app/database/crud/rules.py` — Python-модуль
  Классы: нет
  Функции: `get_rules_by_language`, `create_or_update_rules`, `clear_all_rules`, `get_current_rules_content`
- `app/database/crud/server_squad.py` — Python-модуль
  Классы: нет
  Функции: `create_server_squad`, `get_server_squad_by_uuid`, `get_server_squad_by_id`, `get_all_server_squads`, `get_available_server_squads`, `get_effective_tariff_squad_uuids` — Resolve tariff squads, treating an empty list as "all available squads"., `update_server_squad_promo_groups`, `update_server_squad`, `sync_with_remnawave`, `get_trial_eligible_server_squads`, `choose_random_trial_server_squad`, `get_random_trial_squad_uuid`, `get_server_statistics`, `count_active_users_for_squad` — Возвращает количество активных подписок, подключенных к указанному скваду., `add_user_to_servers`, `remove_user_from_servers`, `update_server_user_counts` — Increment and decrement server user counters in a single sorted pass., `get_server_ids_by_uuids`, `get_server_squads_by_uuids` — Получает список ServerSquad объектов по их UUID с загрузкой allowed_promo_groups., `ensure_servers_synced` — Проверяет и синхронизирует серверы при запуске.
- `app/database/crud/subscription.py` — Python-модуль
  Классы: нет
  Функции: `generate_unique_short_id` — Generate a unique remnawave_short_id (6 hex chars) with collision check., `is_recently_updated_by_webhook` — Return True if subscription was updated by webhook within guard window., `device_addons_carry_over` — Переносятся ли докупленные места со старого тарифа на новый., `calc_device_limit_on_tariff_switch` — device_limit после смены тарифа самим пользователем., `calc_device_limit_on_admin_tariff_change` — device_limit после смены тарифа админом (одному или массово)., `is_active_paid_subscription` — Return True if subscription is active, paid (non-trial), and not expired., `get_subscription_by_user_id` — Get primary subscription for user., `get_subscription_by_user_id_in_session` — То же, что ``get_subscription_by_user_id``, но человек и тариф — из сессии, без selectinload., `apply_trial_conversion_defaults` — Настройки, которые подписка получает, перестав быть триалом., `create_trial_subscription` — Создает триальную подписку., `create_paid_subscription`, `replace_subscription` — Перезаписывает параметры существующей подписки пользователя., `reconcile_tariff_traffic_limit` — Вернуть тарифную подписку к условиям тарифа: база тарифа + активные докупки., `reconcile_subscription_traffic_limit` — Приводит снапшот traffic_limit_gb к инварианту «база тарифа + активные докупки»., `resync_traffic_limit_for_tariff_subscriptions` — Ресинк снапшотов traffic_limit_gb всех подписок тарифа после его правки., `should_carry_trial_remaining_days` — Переносить ли остаток триальных дней на платную подписку при переходе., `carried_seconds_by_value` — Остаток срока при переходе на тариф дороже — по стоимости, а не день в день., `extend_subscription` — Продлевает подписку на указанное количество дней., `add_subscription_traffic`, `decrement_subscription_server_counts` — Decrease server counters linked to the provided subscription., `update_subscription_autopay`, `deactivate_subscription`, `reset_subscription` — Полностью обнулить подписку «как будто пользователь её не оформлял», НЕ удаляя, `reactivate_subscription` — Реактивация подписки (например, после повторной подписки на канал или докупки трафика)., `get_expiring_subscriptions`, `get_expired_subscriptions`, `get_subscriptions_statistics`, `wipe_trial_subscriptions` — Снимает доступ и удаляет переданные триал-подписки — единый код для ботовой, `update_subscription_usage`, `get_all_subscriptions`, `get_subscriptions_batch` — Получает подписки пачками для синхронизации. Загружает связанных пользователей и тарифы., `add_subscription_servers`, `get_subscription_server_ids`, `expire_subscription`, `expire_subscription_if_still_due` — Погасить подписку, только если в базе она всё ещё ACTIVE с прошедшей датой., `check_and_update_subscription_status`, `create_subscription_no_commit` — Создает подписку без немедленного коммита для пакетной обработки, `create_subscription`, `get_daily_subscriptions_for_charge` — Получает все суточные подписки, которые нужно обработать для списания., `get_disabled_daily_subscriptions_for_resume` — Получает список DISABLED суточных подписок, которые можно возобновить., `get_expired_daily_subscriptions_for_recovery` — Получает EXPIRED суточные подписки, которые были ошибочно экспайрены, `get_limited_daily_subscriptions_for_recovery` — Суточные подписки, застрявшие в LIMITED (панель зарезала их по лимиту трафика)., `pause_daily_subscription` — Приостанавливает суточную подписку (списание не будет происходить)., `resume_daily_subscription` — Возобновляет суточную подписку (списание продолжится)., `update_daily_charge_time` — Обновляет время последнего суточного списания и продлевает подписку на 1 день., `suspend_daily_subscription_insufficient_balance` — Приостанавливает подписку из-за недостатка баланса., `toggle_daily_subscription_pause` — Переключает состояние паузы суточной подписки., `get_active_subscriptions_by_user_id` — Get all active/trial/limited subscriptions for a user., `get_subscription_by_id_for_user` — Get subscription by ID with ownership check (IDOR protection)., `get_subscription_by_id` — Get subscription by ID (admin use only, no ownership check)., `get_subscription_by_user_and_tariff` — Get a subscription for a specific user+tariff combination., `deactivate_user_trial_subscriptions` — Deactivate all trial subscriptions for a user., `get_all_subscriptions_by_user_id` — Get all subscriptions for a user (any status).
- `app/database/crud/subscription_conversion.py` — Python-модуль
  Классы: нет
  Функции: `create_subscription_conversion`, `get_conversion_by_user_id`, `get_conversion_statistics`
- `app/database/crud/subscription_event.py` — Python-модуль
  Классы: нет
  Функции: `create_subscription_event`
- `app/database/crud/subscription_segments.py` — Python-модуль
  Классы: нет
  Функции: `segment_condition` — SQL-условие «подписка относится к сегменту» (по строке ``subscriptions``)., `subscription_segment` — Python-зеркало ``segment_condition`` для одной подписки (строка списка, чип).
- `app/database/crud/system_errors.py` — Python-модуль
  Классы: нет
  Функции: `list_error_events` — Постранично отдать события с фильтрами. Возвращает (записи, всего)., `get_error_event`, `get_error_summary` — Сводка для бейджа и шапки страницы., `mark_delivery_result` — Записать исход ручной повторной доставки.
- `app/database/crud/system_setting.py` — Python-модуль
  Классы: нет
  Функции: `upsert_system_setting`, `get_setting_value` — Get a setting value from database., `delete_system_setting`
- `app/database/crud/tariff.py` — Python-модуль
  Классы: нет
  Функции: `get_all_tariffs` — Получает все тарифы с опциональной фильтрацией по активности., `get_tariff_by_id` — Получает тариф по ID., `get_trial_tariff` — Получает тариф, доступный для триала (is_trial_available=True)., `get_tariffs_for_user` — Получает тарифы, доступные для пользователя с учетом его промогруппы., `create_tariff` — Создает новый тариф., `update_tariff` — Обновляет существующий тариф., `delete_tariff` — Удаляет тариф., `get_tariff_subscriptions_count` — Подсчитывает количество подписок на тарифе., `set_tariff_promo_groups` — Устанавливает промогруппы для тарифа., `reorder_tariffs` — Изменяет порядок отображения тарифов., `sync_default_tariff_from_config` — Синхронизирует дефолтный тариф из конфига (.env) в БД., `load_period_prices_from_db` — Загружает периоды/цены из тарифа в PERIOD_PRICES., `ensure_tariffs_synced` — Проверяет и синхронизирует тарифы при запуске.
- `app/database/crud/ticket.py` — Python-модуль
  Классы: `TicketCRUD` (14 методов), `TicketMessageCRUD` (3 методов)
  Функции: нет
- `app/database/crud/ticket_notification.py` — Python-модуль
  Классы: `TicketNotificationCRUD` (13 методов)
  Функции: нет
- `app/database/crud/transaction.py` — Python-модуль
  Классы: нет
  Функции: `traffic_addon_clause` — SQL-условие: описание транзакции похоже на докупку трафика., `device_addon_clause` — SQL-условие: описание транзакции похоже на покупку доп. устройств., `addon_description_clause` — SQL-условие: транзакция — любой доп (трафик или устройства), не продажа/продление., `create_transaction`, `emit_transaction_side_effects` — Fire side-effects that were deferred when create_transaction(commit=False) was used., `get_transaction_by_id`, `get_transaction_by_external_id`, `get_user_transactions`, `get_user_history_page` — Страница истории операций без дублей и общее число страниц-элементов., `get_user_transactions_count`, `get_user_total_spent_kopeks` — Sum of personal spending for promo group auto-assignment., `get_last_subscription_payment_at` — Когда человек последний раз платил за подписку (завершённая оплата подписки)., `get_transactions_statistics`, `get_revenue_by_period` — Доход по календарным дням settings.TIMEZONE за последние ``days`` дней, включая сегодня.
- `app/database/crud/user.py` — Python-модуль
  Классы: нет
  Функции: `generate_referral_code`, `get_user_by_id`, `get_user_by_telegram_id`, `find_phantom_user_by_username` — Find a phantom user created by guest purchase (no telegram_id, auth_type=telegram)., `get_user_by_referral_code`, `get_user_by_remnawave_id` — Найти бот-пользователя по числовому id пользователя панели., `create_unique_referral_code`, `create_user_no_commit` — Создает пользователя без немедленного коммита для пакетной обработки, `emit_user_created_event` — Emit the best-effort post-commit user.created event for a persisted user., `create_user`, `update_user`, `lock_user_for_update` — Lock user row with SELECT FOR UPDATE to prevent concurrent balance modifications., `lock_user_for_update_if_exists` — Как lock_user_for_update, но None, если строку пользователя уже удалили., `add_user_balance`, `lock_user_for_pricing` — Lock user row with FOR NO KEY UPDATE and return refreshed instance., `subtract_user_balance`, `cleanup_expired_promo_offer_discounts`, `get_users_list` — Страница списка пользователей админки., `get_users_count`, `get_users_spending_stats` — Получает статистику трат для списка пользователей., `get_referrals`, `get_users_for_promo_segment`, `get_inactive_users`, `delete_user`, `get_users_statistics`, `create_user_by_email` — Создать пользователя через email регистрацию (без Telegram)., `get_user_by_email` — Get user by email address (case-insensitive)., `get_user_by_email_alias` — Найти пользователя, чей адрес ведёт в тот же ящик, что и ``email``., `is_email_taken` — Check if email is already taken by another user., `set_email_change_pending` — Set pending email change for user., `verify_and_apply_email_change` — Verify email change code and apply the change., `clear_email_change_pending` — Clear pending email change data., `get_user_by_oauth_provider` — Find a user by OAuth provider ID., `set_user_oauth_provider_id` — Link an OAuth provider ID to an existing user., `provider_attested_email` — Email, который держится только на этом провайдере: получен от него (backfill при, `clear_user_oauth_provider_id` — Unlink an OAuth provider from an existing user (set column to None)., `create_user_by_oauth` — Create a new user via OAuth provider.
- `app/database/crud/user_device_alias.py` — Python-модуль
  Классы: нет
  Функции: `normalize_alias` — Strip + collapse whitespace + cap length. Returns '' for empty/None input., `get_aliases_for_user` — Return all device aliases for a user as a {hwid: alias} dict., `get_alias` — Return a single alias or None when not set., `set_alias` — Insert or update an alias., `upsert_alias` — Deprecated convenience wrapper: empty `alias` deletes the row., `delete_alias` — Remove the alias for a (user, hwid) pair., `attach_aliases_to_devices` — Mutate-and-return: enrich each device dict with a `local_name` field.
- `app/database/crud/user_message.py` — Python-модуль
  Классы: нет
  Функции: `get_active_user_messages`, `get_random_active_message`
- `app/database/crud/user_promo_group.py` — Python-модуль
  Классы: нет
  Функции: `sync_user_primary_promo_group` — Публичная обертка для синхронизации primary промогруппы пользователя., `add_user_to_promo_group` — Добавляет пользователю промогруппу., `remove_user_from_promo_group` — Удаляет промогруппу у пользователя., `get_user_promo_groups` — Получает все промогруппы пользователя, отсортированные по приоритету., `has_user_promo_group` — Проверяет наличие промогруппы у пользователя.
- `app/database/crud/wata.py` — Python-модуль
  Классы: нет
  Функции: `create_wata_payment`, `get_wata_payment_by_id`, `get_wata_payment_by_id_for_update`, `get_wata_payment_by_link_id`, `get_wata_payment_by_order_id`, `update_wata_payment_status`, `link_wata_payment_to_transaction`
- `app/database/crud/webhook.py` — Python-модуль
  Классы: нет
  Функции: `get_active_webhooks_for_event` — Получить все активные webhooks для конкретного события., `delete_webhook` — Удалить webhook., `record_webhook_delivery` — Записать попытку доставки webhook., `update_webhook_stats` — Обновить статистику webhook.
- `app/database/crud/welcome_text.py` — Python-модуль
  Классы: нет
  Функции: `get_active_welcome_text`, `replace_placeholders`, `get_welcome_text_for_user`
- `app/database/crud/wheel.py` — Python-модуль
  Классы: нет
  Функции: `get_wheel_config` — Получить текущую конфигурацию колеса (всегда id=1)., `get_or_create_wheel_config` — Получить или создать конфигурацию колеса., `update_wheel_config` — Обновить конфигурацию колеса., `get_wheel_prizes` — Получить список призов колеса., `get_wheel_prize_by_id` — Получить приз по ID., `create_wheel_prize` — Создать новый приз на колесе., `update_wheel_prize` — Обновить приз колеса., `delete_wheel_prize` — Удалить приз колеса., `reorder_wheel_prizes` — Переупорядочить призы колеса., `create_wheel_spin` — Создать запись о спине колеса., `get_wheel_spin_by_charge_id` — Найти спин по Telegram charge id (идемпотентность Stars-платежа)., `get_user_spins_today` — Получить количество спинов пользователя за сегодня., `get_topup_deposits_split` — Реальные пополнения (до since, с since). Без since акция не началась — (0, 0)., `get_free_spin_counters` — (выиграно спинов призом «Ещё спин», потрачено бесплатных спинов)., `grant_free_spins` — Выдать пользователю бесплатные спины (тест, подарок). Коммит — на вызывающем., `get_user_spin_history` — Получить историю спинов пользователя., `get_all_spins` — Получить все спины с фильтрами (для админки)., `get_wheel_statistics` — Получить статистику колеса удачи.
- `app/database/crud/xrocket.py` — Python-модуль
  Классы: нет
  Функции: `create_xrocket_payment`, `get_xrocket_payment_by_invoice_id`, `get_xrocket_payment_by_id`, `get_xrocket_payment_by_invoice_id_for_update`, `update_xrocket_payment_status`, `link_xrocket_payment_to_transaction`
- `app/database/crud/yandex_client_id.py` — Python-модуль
  Классы: нет
  Функции: `upsert_cid` — Insert or update Yandex ClientID for a user (race-safe via ON CONFLICT)., `get_cid` — Get Yandex ClientID mapping for a user., `mark_registration_sent` — Mark registration event as sent for a user., `mark_trial_sent` — Mark trial event as sent for a user., `upsert_subid` — Save subid for a user. Updates existing record or creates with placeholder CID., `get_subid` — Get subid for a user.

### app/external

- `app/external/cryptobot.py` — Python-модуль
  Классы: `CryptoBotService` (9 методов)
  Функции: нет
- `app/external/pay2328.py` — Python-модуль
  Классы: `Pay2328Service` (8 методов)
  Функции: нет
- `app/external/remnawave_api.py` — Python-модуль
  Классы: `UserStatus`, `TrafficLimitStrategy`, `UserTraffic`, `RemnaWaveUser` (4 методов), `RemnaWaveInbound`, `RemnaWaveInternalSquad`, `RemnaWaveAccessibleNode`, `RemnaWaveNode` (2 методов), `SubscriptionInfo`, `SubscriptionPageConfig`, `RemnaWaveExternalSquad`, `RemnaWaveTransientError`, `RemnaWaveAPI` (84 методов)
  Функции: `is_expire_in_past_error` — Панель отвергла ``expireAt`` как прошедшую дату., `is_user_not_found_error` — Панель сообщила, что такого пользователя НЕТ (удалён / протух идентификатор)., `is_stale_external_squad_error` — Панель отвергла запись из-за ``externalSquadUuid`` (или не смогла её отличить)., `parse_bytes`, `test_api_connection`
- `app/external/remnawave_errors.py` — Python-модуль
  Классы: `RemnaWaveAPIError` (1 методов), `RemnaWaveInvalidUserIdError`
  Функции: `coerce_panel_user_id` — Привести локально хранимый идентификатор к числовому id панели.
- `app/external/telegram_stars.py` — Python-модуль
  Классы: `TelegramStarsService` (6 методов)
  Функции: нет
- `app/external/wata_webhook.py` — Python-модуль
  Классы: `WataPublicKeyProvider` (3 методов), `WataWebhookHandler` (4 методов)
  Функции: нет
- `app/external/xrocket.py` — Python-модуль
  Классы: `XRocketService` (12 методов)
  Функции: нет

### app/handlers

- `app/handlers/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/handlers/admin/`
- `app/handlers/balance/`
- `app/handlers/channel_member.py` — Python-модуль
  Классы: нет
  Функции: `on_user_joined_channel` — User subscribed to a channel -- update cache and reactivate VPN if applicable., `on_user_left_channel` — User unsubscribed from a channel -- update cache and deactivate VPN if applicable., `register_handlers` — Register channel member event handlers on the dispatcher/router.
- `app/handlers/common.py` — Python-модуль
  Классы: нет
  Функции: `handle_webhook_notification_close` — Удаляет webhook-уведомление при нажатии кнопки Закрыть., `handle_noop`, `handle_current_page`, `handle_cancel`, `handle_unknown_message` — Человек написал боту текстом или прислал фото вне сценария., `handle_unknown_to_support` — Одним нажатием превращает сообщение в обращение (или дописывает в открытое)., `show_rules`, `register_handlers`
- `app/handlers/gift_activation.py` — Python-модуль
  Классы: нет
  Функции: `handle_gift_activate` — Handle gift_activate:{purchase_id} callback from Telegram notification., `register_handlers`
- `app/handlers/menu.py` — Python-модуль
  Классы: нет
  Функции: `build_main_menu_keyboard` — Клавиатура главного меню: show_main_menu, handle_back_to_menu и живое меню (live_menu_service)., `show_main_menu`, `handle_profile_unavailable`, `show_service_rules`, `show_info_menu`, `show_legal_menu` — n3c: единый вход «Правила и документы» — подменю включённых документов., `show_promo_groups_info`, `show_faq_pages`, `show_faq_page`, `show_privacy_policy`, `show_public_offer`, `show_language_menu`, `process_language_change`, `handle_back_to_menu`, `is_new_user_with_free_trial` — Ни одной подписки и бесплатный пробный ещё доступен — тот же гейт, что у кнопки пробного в меню., `get_main_menu_text`, `handle_activate_button` — Умная кнопка активации — система сама решает что делать:, `register_handlers`
- `app/handlers/promo_deeplink.py` — Python-модуль
  Классы: нет
  Функции: `is_promo_deeplink`, `promo_code_from`, `claim_promo_link` — Обработать ссылку. ``True`` — параметр был промокодом и дальше его не разбирать.
- `app/handlers/promocode.py` — Python-модуль
  Классы: нет
  Функции: `show_promocode_menu`, `wheel_spin_keyboard` — Кнопка мини-приложения на колесо после кода на спин; иначе None., `activate_promocode_for_registration` — Активирует промокод для пользователя., `promocode_error_text` — Текст для кода ошибки активации/проверки промокода (ручной ввод и ссылка promo_)., `process_promocode`, `register_handlers`
- `app/handlers/referral.py` — Python-модуль
  Классы: нет
  Функции: `show_referral_info`, `cmd_referral` — /referral из меню команд — тот же экран, что у кнопки «Пригласить друзей»., `show_referral_qr`, `show_detailed_referral_list`, `show_referral_analytics`, `create_invite_message`, `show_withdrawal_info` — Показывает информацию о выводе реферального баланса., `start_withdrawal_request` — Начинает процесс оформления заявки на вывод., `parse_withdrawal_amount_kopeks` — Сумма в рублях из текста → копейки; None, если это не конечное число разумного размера., `process_withdrawal_amount` — Обрабатывает ввод суммы для вывода., `process_withdrawal_amount_callback` — Обрабатывает выбор суммы для вывода через кнопку., `process_payment_details` — Обрабатывает ввод реквизитов и показывает подтверждение., `confirm_withdrawal_request` — Подтверждает и создаёт заявку на вывод., `cancel_withdrawal_request` — Отменяет процесс создания заявки на вывод., `register_handlers`
- `app/handlers/referral_settings.py` — Python-модуль
  Классы: нет
  Функции: `show_reward_settings`, `set_reward_preference` — Сохранить, что получать. Неразрешённая настройка не сохраняется вовсе., `set_days_target` — Сохранить подписку для дней., `register_handlers`
- `app/handlers/stars_payments.py` — Python-модуль
  Классы: нет
  Функции: `handle_pre_checkout_query`, `handle_successful_payment`, `register_stars_handlers`
- `app/handlers/start.py` — Python-модуль
  Классы: нет
  Функции: `answer_menu_with_media` — Отвечает меню с медиа-шапкой на входящее сообщение (например, /start)., `send_menu_with_media` — Отправляет меню с медиа-шапкой: видео → фото-логотип → обычный текст., `handle_potential_referral_code`, `cmd_start`, `process_language_selection`, `process_rules_accept` — Обрабатывает принятие или отклонение правил пользователем., `process_privacy_policy_accept`, `process_referral_code_input`, `process_referral_code_skip`, `complete_registration_from_callback`, `complete_registration`, `get_referral_code_keyboard`, `get_main_menu_text`, `required_sub_channel_check`, `process_webauth_confirm` — Handle web auth confirmation or denial., `register_handlers`
- `app/handlers/subscription/`
- `app/handlers/subscription_deeplinks.py` — Python-модуль
  Классы: нет
  Функции: `subscription_deeplink_action` — ``renew`` и ``renew_<источник>`` → ``'renew'``, ``traffic`` → ``'traffic'``, остальное → None., `subscription_deeplink_source` — ``renew_ch1212`` → ``ch1212``; без метки — пустая строка., `open_subscription_deeplink` — Ответить на диплинк. False — ответить нечем (``traffic`` без подписки): пусть отработает обычный /start.
- `app/handlers/support.py` — Python-модуль
  Классы: нет
  Функции: `show_support_info`, `register_handlers`, `payment_support_command` — /paysupport — required of bots that sell for Telegram Stars (Bot Developer Terms 6.2.1)., `register_command_handlers`
- `app/handlers/tickets.py` — Python-модуль
  Классы: `TicketStates`
  Функции: `show_ticket_priority_selection`, `handle_ticket_message_input`, `show_my_tickets`, `show_my_tickets_closed`, `view_ticket` — Показать детали тикета с пагинацией, `send_ticket_attachments`, `user_delete_message`, `reply_to_ticket` — Начать ответ на тикет, `handle_ticket_reply`, `close_ticket` — Закрыть тикет, `cancel_ticket_creation` — Отменить создание тикета, `cancel_ticket_reply` — Отменить ответ на тикет, `close_ticket_notification` — Закрыть уведомление о тикете, `build_ticket_card_keyboard` — Клавиатура карточки тикета по роли получателя ('admin' / 'moderator' / 'group')., `build_ticket_card_text` — Карточка обращения для админ-чата., `notify_admins_about_new_ticket` — Уведомить админов о новом тикете, `notify_admins_about_ticket_reply` — Уведомить админов об ответе пользователя на тикет, `register_handlers` — Регистрация обработчиков тикетов
- `app/handlers/ultima_deeplink.py` — Python-модуль
  Классы: нет
  Функции: `is_ultima_deeplink`, `link_source` — ``ultima_ch1`` → ``ch1``; просто ``ultima`` → пустая строка., `open_ultima_offer` — Выдать (или показать действующее) предложение ULTIMA. False — предложения нет, пусть идёт обычный /start.

#### app/handlers/admin

- `app/handlers/admin/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/handlers/admin/blocked_users.py` — Python-модуль
  Классы: `BlockedUsersText`, `BlockedUsersCallback`, `BlockedUsersStates`
  Функции: `get_blocked_users_menu_keyboard` — Клавиатура главного меню модуля., `get_blocked_list_keyboard` — Клавиатура списка заблокированных пользователей., `get_confirm_keyboard` — Клавиатура подтверждения действия., `show_blocked_users_menu` — Показывает главное меню модуля заблокированных пользователей., `start_scan` — Запускает сканирование пользователей., `show_blocked_list` — Показывает список заблокированных пользователей., `handle_blocked_list_pagination` — Обрабатывает пагинацию списка заблокированных., `show_action_confirm` — Показывает подтверждение действия., `handle_action_delete_db` — Обрабатывает выбор удаления из БД., `handle_action_delete_remnawave` — Обрабатывает выбор удаления из Remnawave., `handle_action_delete_both` — Обрабатывает выбор полного удаления., `handle_action_mark` — Обрабатывает выбор пометки как заблокированных., `handle_confirm_action` — Выполняет подтвержденное действие., `handle_cancel` — Отменяет текущее действие и возвращает в меню., `register_handlers` — Регистрирует хендлеры модуля заблокированных пользователей.
- `app/handlers/admin/campaigns.py` — Python-модуль
  Классы: нет
  Функции: `show_campaigns_menu`, `show_campaigns_overall_stats`, `show_campaigns_list`, `show_campaign_detail`, `show_campaign_stats`, `start_campaign_creation`, `process_campaign_name`, `process_campaign_start_parameter`, `select_campaign_bonus_type`, `process_campaign_balance_value`, `register_handlers`
- `app/handlers/admin/main.py` — Python-модуль
  Классы: нет
  Функции: `show_admin_panel`, `show_users_submenu`, `show_promo_submenu`, `show_communications_submenu`, `show_support_submenu`, `show_moderator_panel`, `show_system_submenu`, `register_handlers`
- `app/handlers/admin/maintenance.py` — Python-модуль
  Классы: `MaintenanceStates`
  Функции: `show_maintenance_panel`, `toggle_maintenance_mode`, `process_maintenance_reason`, `toggle_monitoring`, `force_api_check`, `check_panel_status`, `send_manual_notification`, `handle_manual_notification`, `process_notification_message`, `register_handlers`
- `app/handlers/admin/messages.py` — Python-модуль
  Классы: нет
  Функции: `safe_edit_or_send_text` — Безопасно редактирует сообщение или удаляет и отправляет новое., `create_broadcast_keyboard`, `show_messages_menu`, `show_broadcast_targets`, `show_custom_broadcast`, `select_custom_criteria`, `select_broadcast_target`, `process_broadcast_message`, `handle_media_selection`, `process_broadcast_media`, `show_media_preview`, `handle_media_confirmation`, `handle_change_media`, `show_button_selector_callback`, `toggle_button_selection`, `confirm_button_selection`, `confirm_broadcast`, `get_target_users_count` — Быстрый подсчёт пользователей через SQL COUNT вместо загрузки всех в память., `get_target_users`, `get_custom_users_count`, `get_custom_users`, `get_users_statistics`, `get_target_name`, `get_target_display_name`, `register_handlers`
- `app/handlers/admin/promo_offers.py` — Python-модуль
  Классы: нет
  Функции: `show_promo_offers_menu`, `show_promo_offer_details`, `show_promo_offer_logs`, `prompt_edit_active_duration`, `show_send_segments`, `send_offer_to_segment`, `process_edit_active_duration_hours`, `register_handlers`
- `app/handlers/admin/promocodes.py` — Python-модуль
  Классы: нет
  Функции: `show_promocodes_menu`, `show_promocodes_list`, `show_promocodes_list_page` — Обработчик пагинации списка промокодов., `show_promocode_management`, `show_promocode_edit_menu`, `start_edit_promocode_date`, `start_edit_promocode_amount`, `start_edit_promocode_days`, `start_edit_promocode_uses`, `start_promocode_creation`, `select_promocode_type`, `process_promocode_code`, `process_promocode_value`, `process_promocode_combo_days` — Шаг 2 комбинированного промокода (BALANCE_AND_DAYS): ввод дней подписки., `handle_edit_value`, `process_promocode_uses`, `handle_edit_uses`, `process_promocode_expiry`, `process_discount_hours` — Обработчик ввода срока действия скидки в часах для DISCOUNT промокода., `handle_edit_expiry`, `confirm_delete_promocode`, `delete_promocode_confirmed`, `register_handlers`
- `app/handlers/admin/referrals.py` — Python-модуль
  Классы: нет
  Функции: `show_referral_statistics`, `show_pending_withdrawal_requests` — Показывает список ожидающих заявок на вывод., `view_withdrawal_request` — Показывает детали заявки на вывод., `approve_withdrawal_request` — Одобряет заявку на вывод., `reject_withdrawal_request` — Отклоняет заявку на вывод., `complete_withdrawal_request` — Отмечает заявку как выполненную (деньги переведены)., `register_handlers`
- `app/handlers/admin/support_decisions.py` — Python-модуль
  Классы: нет
  Функции: `parse_decision`, `is_support_decision`, `handle_support_decision`
- `app/handlers/admin/system_logs.py` — Python-модуль
  Классы: нет
  Функции: `show_system_logs`, `refresh_system_logs`, `download_system_logs`, `register_handlers`
- `app/handlers/admin/ticket_group_reply.py` — Python-модуль
  Классы: нет
  Функции: `extract_ticket_id`, `is_admin_group_ticket_reply` — Ответ админа/модератора на карточку обращения в админ-чате., `handle_admin_group_ticket_reply`, `is_admin_group_tickets_command`, `handle_admin_group_tickets_command`
- `app/handlers/admin/tickets.py` — Python-модуль
  Классы: нет
  Функции: `show_admin_tickets` — Показать все тикеты для админов, `view_admin_ticket` — Показать детали тикета для админа с пагинацией, `reply_to_admin_ticket` — Начать ответ на тикет от админа, `handle_admin_ticket_reply`, `close_all_open_admin_tickets` — Закрыть все открытые тикеты., `close_admin_ticket` — Закрыть тикет админом, `cancel_admin_ticket_reply` — Отменить ответ админа на тикет, `block_user_in_ticket`, `handle_admin_block_duration_input`, `unblock_user_in_ticket`, `block_user_permanently`, `notify_user_about_ticket_reply` — Уведомить пользователя о новом ответе в тикете, `delete_sent_message` — Кнопка «🗑 Удалить» на служебных сообщениях поддержки (админ или модератор)., `register_handlers` — Регистрация админских обработчиков тикетов
- `app/handlers/admin/users.py` — Python-модуль
  Классы: нет
  Функции: `show_users_menu`, `show_users_list`, `handle_users_list_pagination_fixed`, `start_user_search`, `show_user_subscription`, `admin_select_user_subscription` — «К подписке» из экранов с явным ``_s{id}``: подписка у пользователя одна., `show_user_transactions`, `confirm_user_delete`, `delete_user_account`, `process_user_search`, `show_user_management`, `show_user_referrals`, `start_balance_edit`, `process_balance_edit`, `confirm_user_block`, `block_user`, `show_user_restrictions` — Показать меню управления ограничениями пользователя., `toggle_user_restriction_topup` — Переключить ограничение на пополнение баланса., `toggle_user_restriction_subscription` — Переключить ограничение на продление/покупку подписки., `ask_restriction_reason` — Запросить ввод причины ограничения., `save_restriction_reason` — Сохранить причину ограничения., `clear_user_restrictions` — Снять все ограничения с пользователя., `confirm_user_unblock`, `unblock_user`, `extend_user_subscription`, `process_subscription_extension_days`, `process_subscription_extension_text`, `add_subscription_traffic`, `process_traffic_addition_button`, `process_traffic_addition_text`, `deactivate_user_subscription`, `confirm_subscription_deactivation`, `reset_user_subscription` — Подтверждение полного обнуления подписки (с сохранением пользователя и тикетов)., `confirm_subscription_reset`, `activate_user_subscription`, `grant_paid_subscription`, `process_subscription_grant_days`, `process_subscription_grant_text`, `show_server_selection`, `toggle_user_server`, `refresh_server_selection_screen`, `change_subscription_type`, `admin_buy_subscription`, `admin_buy_subscription_confirm`, `admin_buy_subscription_execute`, `change_subscription_type_confirm`, `show_admin_tariff_change` — Показывает список доступных тарифов для смены., `select_admin_tariff_change` — Подтверждение выбора тарифа., `confirm_admin_tariff_change` — Применяет смену тарифа., `register_handlers`

#### app/handlers/balance

- `app/handlers/balance/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/handlers/balance/cryptobot.py` — Python-модуль
  Классы: нет
  Функции: `start_cryptobot_payment`, `process_cryptobot_payment_amount`, `check_cryptobot_payment_status`
- `app/handlers/balance/main.py` — Python-модуль
  Классы: нет
  Функции: `route_payment_by_method` — Роутер платежей по методу оплаты., `show_balance_menu`, `show_balance_history`, `handle_balance_history_pagination`, `show_payment_methods`, `show_payment_methods_other_amount` — «Другая сумма»: способы оплаты без предзаполненной суммы корзины —, `handle_payment_methods_unavailable`, `request_support_topup`, `process_topup_amount`, `handle_topup_amount_callback`, `register_balance_handlers`
- `app/handlers/balance/pay2328.py` — Python-модуль
  Классы: нет
  Функции: `start_pay2328_payment`, `process_pay2328_payment_amount`, `check_pay2328_payment_status`
- `app/handlers/balance/platega.py` — Python-модуль
  Классы: нет
  Функции: `platega_status_answer` — Ответ на «Проверить статус» словами, а не словом провайдера., `start_platega_payment`, `handle_platega_method_selection`, `start_platega_direct_method` — Handle direct Platega method selection from the main payment screen (inline mode)., `process_platega_payment_amount`, `check_platega_payment_status`
- `app/handlers/balance/stars.py` — Python-модуль
  Классы: нет
  Функции: `start_stars_payment`, `process_stars_payment_amount`
- `app/handlers/balance/wata.py` — Python-модуль
  Классы: нет
  Функции: `start_wata_payment`, `process_wata_payment_amount`, `check_wata_payment_status`
- `app/handlers/balance/xrocket.py` — Python-модуль
  Классы: нет
  Функции: `start_xrocket_payment`, `process_xrocket_payment_amount`, `select_xrocket_asset` — Пользователь выбрал актив: xrocket_asset_{ASSET}_{kopeks}., `check_xrocket_payment_status`

#### app/handlers/subscription

- `app/handlers/subscription/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/handlers/subscription/addon_cart.py` — Python-модуль
  Классы: нет
  Функции: `resume_addon_cart_from_button` — Довести докупку до конца по явному нажатию; при нехватке — снова к пополнению.
- `app/handlers/subscription/autopay.py` — Python-модуль
  Классы: нет
  Функции: `handle_autopay_menu`, `toggle_autopay`, `show_autopay_days`, `set_autopay_days`, `show_autopay_period` — Period picker UI for autopay., `set_autopay_period` — Handle period selection (autopay_period_<N> or autopay_period_default)., `handle_sbp_recurring_unavailable` — Кнопки СБП-автопродления в старых сообщениях и рассылках: функции больше нет., `handle_subscription_cancel`
- `app/handlers/subscription/common.py` — Python-модуль
  Классы: нет
  Функции: `resolve_subscription_from_context` — Подписка пользователя для обработчиков бота: одна на человека., `update_traffic_prices`, `get_localized_value`, `render_guide_blocks` — Render block-format guide steps to HTML text., `build_redirect_link`, `get_device_name`, `load_app_config_async` — Load app config from Remnawave API (if configured), with TTL cache., `invalidate_app_config_cache` — Clear the cached app config so next call re-fetches from Remnawave., `get_apps_for_platform_async` — Get apps for a device type from Remnawave config., `normalize_app` — Normalize Remnawave app dict to a unified format with blocks., `get_platforms_list` — Extract available platforms from config for keyboard generation., `resolve_button_url` — Resolve template variables in button URLs (port of cabinet's _resolve_button_url)., `create_deep_link`, `get_traffic_switch_keyboard`, `get_confirm_switch_traffic_keyboard`
- `app/handlers/subscription/countries.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/handlers/subscription/devices.py` — Python-модуль
  Классы: нет
  Функции: `get_servers_display_names`, `get_current_devices_count`, `handle_change_devices`, `confirm_change_devices`, `execute_change_devices`, `handle_device_management`, `show_devices_page`, `handle_devices_page`, `start_device_rename` — Callback `device_rename_<idx>_<page>` — prompts user for the new alias., `process_device_rename` — Text input from the user with the new alias (or `-`/`/clear` to delete)., `cancel_device_rename` — Callback `device_rename_cancel` — «Отмена» в промпте переименования., `handle_single_device_reset`, `handle_all_devices_reset_from_management`, `confirm_add_devices`, `handle_reset_devices`, `confirm_reset_devices`, `handle_device_guide`, `handle_app_selection`, `handle_specific_app_guide`, `show_device_connection_help`
- `app/handlers/subscription/gift.py` — Python-модуль
  Классы: нет
  Функции: `handle_gift_catalog` — Entry point for native gift catalog and history hub., `handle_gift_tariff_select` — Handle tariff selection in gift flow and render periods., `handle_gift_period_select` — Handle period selection in gift flow and render confirmation summary., `handle_gift_back_tariffs` — Navigate back to tariff catalog., `handle_gift_back_periods` — Navigate back to period selection for current tariff., `handle_gift_cancel` — Cancel gift checkout, clean up saved gift cart, and return to origin subscription view., `handle_gift_confirm` — Confirmation handler: validates selection, preflights channels, purchases from balance, and renders result., `handle_return_to_gift_cart` — Resume gift cart after balance top-up (Task 6)., `handle_gift_enter_code` — Prompt user to manually enter gift code or link., `handle_gift_activation_cancel` — Cancel manual code entry and return to gift catalog view., `handle_gift_code_input` — Handle manual gift code or link input in GiftActivationStates.waiting_for_code., `handle_gift_my` — Entry handler for 'My gifts' history list (Page 1)., `handle_gift_my_page` — Handle pagination page change in gift history., `handle_gift_my_open` — Open detail card for a specific gift owned by the sender (IDOR protected)., `handle_gift_my_qr` — Показать QR со ссылкой на активацию подарка., `handle_gift_my_text` — Готовое сообщение получателю, скопировать одним нажатием., `handle_gift_my_back` — Return from gift detail card to history list., `register_gift_handlers` — Register all gift purchase, navigation, and code activation handlers.
- `app/handlers/subscription/happ.py` — Python-модуль
  Классы: нет
  Функции: `handle_happ_download_request`, `handle_happ_download_platform_choice`, `handle_happ_download_close`, `handle_happ_download_back`
- `app/handlers/subscription/links.py` — Python-модуль
  Классы: нет
  Функции: `handle_connect_subscription`, `handle_open_subscription_link`
- `app/handlers/subscription/promo.py` — Python-модуль
  Классы: нет
  Функции: `claim_discount_offer`, `handle_promo_offer_close`
- `app/handlers/subscription/purchase.py` — Python-модуль
  Классы: нет
  Функции: `show_subscription_info`, `show_trial_offer`, `activate_trial`, `start_subscription_purchase`, `return_to_saved_cart`, `handle_extend_subscription`, `confirm_extend_subscription`, `handle_subscription_settings`, `clear_saved_cart`, `handle_toggle_daily_subscription_pause` — Переключает паузу суточной подписки., `register_handlers`
- `app/handlers/subscription/revoke.py` — Python-модуль
  Классы: нет
  Функции: `start_subscription_revoke` — Show revoke confirmation for classic single-subscription mode., `confirm_subscription_revoke` — Execute revoke of the user's subscription.
- `app/handlers/subscription/tariff_purchase.py` — Python-модуль
  Классы: `SavedTariffCart` (3 методов), `SavedTariffCartRejection`
  Функции: `tariff_traffic_text` — Трафик тарифа на экранах покупки: у тарифа с обходами — «∞ + 50 ГБ обходов», а не «50 ГБ»., `format_tariffs_list_text` — Форматирует текст со списком тарифов для отображения., `get_tariffs_keyboard` — Создает компактную клавиатуру выбора тарифов (только названия)., `get_tariff_periods_keyboard` — Создает клавиатуру выбора периода для тарифа с учетом скидок по периодам., `get_tariff_periods_keyboard_with_traffic` — Клавиатура выбора периода для тарифа с кастомным трафиком (переход к настройке трафика)., `get_tariff_confirm_keyboard` — Создает клавиатуру подтверждения покупки тарифа., `get_tariff_insufficient_balance_keyboard` — Создает клавиатуру при недостаточном балансе., `get_tariff_extend_insufficient_balance_keyboard` — Клавиатура «Недостаточно средств» при продлении тарифа., `format_tariff_info_for_user` — Форматирует информацию о тарифе для пользователя., `get_daily_tariff_confirm_keyboard` — Создает клавиатуру подтверждения покупки суточного тарифа., `get_daily_tariff_insufficient_balance_keyboard` — Создает клавиатуру при недостаточном балансе для суточного тарифа., `get_custom_tariff_keyboard` — Создает клавиатуру для настройки кастомных дней и трафика., `format_custom_tariff_preview` — Форматирует предпросмотр покупки с кастомными параметрами., `show_tariffs_list` — Показывает список тарифов для покупки., `select_tariff` — Обрабатывает выбор тарифа., `handle_custom_days_change` — Обрабатывает изменение количества дней., `handle_custom_traffic_change` — Обрабатывает изменение количества трафика., `handle_custom_confirm` — Подтверждает покупку тарифа с кастомными параметрами., `select_tariff_period_with_traffic` — Обрабатывает выбор периода для тарифа с кастомным трафиком - показывает экран настройки трафика., `trim_tariff_devices` — «Только N устройств»: возвращает подписку к числу устройств из тарифа и пересчитывает покупку., `select_tariff_period` — Обрабатывает выбор периода для тарифа., `confirm_tariff_purchase` — Подтверждает покупку тарифа и создает подписку., `confirm_daily_tariff_purchase` — Подтверждает покупку суточного тарифа., `get_tariff_extend_keyboard` — Создает клавиатуру выбора периода для продления по тарифу с учетом скидок по периодам., `get_tariff_extend_confirm_keyboard` — Создает клавиатуру подтверждения продления по тарифу., `show_tariff_extend` — Показывает экран продления по текущему тарифу., `select_tariff_extend_period` — Обрабатывает выбор периода для продления., `confirm_tariff_extend` — Подтверждает продление по тарифу., `format_tariff_switch_list_text` — Форматирует текст со списком тарифов для переключения., `get_tariff_switch_keyboard` — Создает компактную клавиатуру выбора тарифа для переключения., `get_tariff_switch_periods_keyboard` — Создает клавиатуру выбора периода для переключения тарифа с учетом скидок по периодам., `get_tariff_switch_confirm_keyboard` — Создает клавиатуру подтверждения переключения тарифа., `get_tariff_switch_insufficient_balance_keyboard` — Создает клавиатуру при недостаточном балансе для переключения., `show_tariff_switch_list` — Показывает список тарифов для переключения., `select_tariff_switch` — Обрабатывает выбор тарифа для переключения., `select_tariff_switch_period` — Обрабатывает выбор периода для переключения тарифа., `confirm_tariff_switch` — Подтверждает переключение тарифа., `confirm_daily_tariff_switch` — Подтверждает смену на суточный тариф., `format_instant_switch_list_text` — Форматирует текст со списком тарифов для мгновенного переключения., `get_instant_switch_keyboard` — Создает клавиатуру для мгновенного переключения тарифа., `get_instant_switch_confirm_keyboard` — Создает клавиатуру подтверждения мгновенного переключения., `get_instant_switch_insufficient_balance_keyboard` — Создает клавиатуру при недостаточном балансе для мгновенного переключения., `show_instant_switch_list` — Показывает список тарифов для мгновенного переключения., `preview_instant_switch` — Показывает превью мгновенного переключения тарифа., `confirm_instant_switch` — Подтверждает мгновенное переключение тарифа., `load_saved_tariff_cart` — Проверяет сохранённую корзину тарифа и пересчитывает её цену. Ничего не списывает и не сохраняет., `return_to_saved_tariff_cart` — Восстанавливает сохраненную корзину тарифа после пополнения баланса., `one_tap_confirm_callback` — callback_data существующей кнопки «Подтвердить» для этой корзины; None — нужен экран оформления., `confirm_saved_cart_after_topup` — «Подтвердить» прямо в сообщении о пополнении: одно нажатие вместо двух., `register_tariff_purchase_handlers` — Регистрирует обработчики покупки по тарифам.
- `app/handlers/subscription/traffic.py` — Python-модуль
  Классы: нет
  Функции: `handle_add_traffic`, `handle_reset_traffic`, `confirm_reset_traffic`, `add_traffic`, `handle_no_traffic_packages`, `handle_switch_traffic`, `confirm_switch_traffic`, `execute_switch_traffic`

### app/keyboards

- `app/keyboards/admin.py` — Python-модуль
  Классы: нет
  Функции: `get_admin_main_keyboard`, `get_admin_users_submenu_keyboard`, `get_admin_promo_submenu_keyboard`, `get_admin_communications_submenu_keyboard`, `get_admin_support_submenu_keyboard`, `get_admin_system_submenu_keyboard`, `get_admin_users_keyboard`, `get_admin_promocodes_keyboard`, `get_admin_campaigns_keyboard`, `get_campaign_management_keyboard`, `get_campaign_bonus_type_keyboard`, `get_admin_messages_keyboard`, `get_user_management_keyboard`, `get_user_restrictions_keyboard` — Клавиатура управления ограничениями пользователя., `get_confirmation_keyboard`, `get_promocode_type_keyboard`, `get_broadcast_target_keyboard`, `get_custom_criteria_keyboard`, `get_admin_pagination_keyboard`, `get_maintenance_keyboard`, `get_broadcast_button_config`, `get_broadcast_button_labels`, `get_broadcast_media_keyboard`, `get_media_confirm_keyboard`, `get_updated_message_buttons_selector_keyboard_with_media`
- `app/keyboards/button_icons.py` — Python-модуль
  Классы: нет
  Функции: `apply_button_icons` — Ставит icon_custom_emoji_id кнопкам с известным эмодзи и чистит текст.
- `app/keyboards/group_callbacks.py` — Python-модуль
  Классы: нет
  Функции: `is_group_safe_callback` — Можно ли обрабатывать это нажатие вне лички., `strip_group_unsafe_buttons` — Оставляет для группы только URL-кнопки и разрешённые callback'и.
- `app/keyboards/inline.py` — Python-модуль
  Классы: нет
  Функции: `get_main_menu_keyboard_async` — Асинхронная версия get_main_menu_keyboard с поддержкой конструктора меню., `get_rules_keyboard`, `get_privacy_policy_keyboard`, `get_channel_sub_keyboard` — Subscription keyboard for required channels., `get_post_registration_keyboard`, `get_language_selection_keyboard`, `build_connect_button` — «🔗 Подключиться» для только что оплаченной (активной) подписки — по CONNECT_BUTTON_MODE., `get_main_menu_keyboard`, `get_info_menu_keyboard`, `get_happ_download_button_row`, `get_happ_cryptolink_keyboard`, `get_happ_download_platform_keyboard`, `get_happ_download_link_keyboard`, `get_back_keyboard`, `get_support_menu_button` — Кнопка «Поддержка» (та же, что в «Инфо»); None, если раздел поддержки выключен., `payment_error_navigation_rows` — «Назад» и «Поддержка» под сообщением о сбое оплаты — чтобы экран не был тупиком., `get_payment_error_keyboard`, `get_insufficient_balance_keyboard`, `get_subscription_keyboard`, `get_insufficient_balance_keyboard_with_cart`, `get_balance_keyboard`, `get_payment_methods_keyboard`, `get_referral_keyboard`, `get_support_keyboard`, `get_stars_credited_to_balance_keyboard` — «Мой баланс» + «Поддержка» — после того как оплату Stars не удалось применить, `get_pagination_keyboard`, `get_confirmation_keyboard`, `get_autopay_keyboard`, `get_autopay_days_keyboard`, `get_autopay_period_keyboard` — Period picker for autopay. `current_period=None` means "use default"., `get_add_traffic_keyboard`, `get_add_traffic_keyboard_from_tariff` — Клавиатура для докупки трафика из настроек тарифа., `get_change_devices_keyboard`, `get_confirm_change_devices_keyboard`, `get_reset_traffic_confirm_keyboard`, `get_device_selection_keyboard`, `get_connection_guide_keyboard`, `get_app_selection_keyboard`, `get_specific_app_keyboard`, `get_devices_management_keyboard`, `get_updated_subscription_settings_keyboard`, `get_device_management_help_keyboard`, `get_ticket_cancel_keyboard`, `get_my_tickets_keyboard`, `get_ticket_view_keyboard`, `get_ticket_reply_cancel_keyboard`, `get_admin_tickets_keyboard`, `get_admin_ticket_view_keyboard`, `get_ticket_notification_keyboard` — Клавиатура для уведомления о тикете (личный или групповой админ-чат)., `get_admin_ticket_reply_cancel_keyboard`
- `app/keyboards/topup_amounts.py` — Python-модуль
  Классы: нет
  Функции: `resolve_config_method_id`, `format_quick_amount`, `get_topup_amount_keyboard`
- `app/keyboards/withdrawal.py` — Python-модуль
  Классы: нет
  Функции: `get_withdrawal_request_keyboard` — Клавиатура заявки по её статусу и роли получателя; ``None`` — кнопок нет.

### app/localization

- `app/localization/default_locales/`
- `app/localization/loader.py` — Python-модуль
  Классы: нет
  Функции: `ensure_locale_templates`, `load_locale`, `clear_locale_cache`
- `app/localization/locales/`
- `app/localization/texts.py` — Python-модуль
  Классы: `Texts` (9 методов)
  Функции: `get_texts`, `get_rules_from_db`, `get_privacy_policy`, `get_default_rules` — Правила из локали — когда в базе их нет или они пустые., `get_rules`, `refresh_rules_cache`

#### app/localization/default_locales

- `app/localization/default_locales/en.yml` — файл
- `app/localization/default_locales/ru.yml` — файл

#### app/localization/locales

- `app/localization/locales/en.json` — файл
- `app/localization/locales/ru.json` — файл

### app/middlewares

- `app/middlewares/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/middlewares/auth.py` — Python-модуль
  Классы: `AuthMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/banner_variant.py` — Python-модуль
  Классы: `BannerVariantMiddleware` (1 методов)
  Функции: `is_text_only_screen`, `banner_variant_for` — Имя файла баннера (без .png) для человека; ``None`` — нужен общий баннер., `show_banner_state` — Сменить баннер для оставшейся части обновления — после того, как состояние человека изменилось.
- `app/middlewares/blacklist.py` — Python-модуль
  Классы: `BlacklistMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/button_icons_middleware.py` — Python-модуль
  Классы: `ButtonIconsMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/button_stats.py` — Python-модуль
  Классы: `ButtonStatsMiddleware` (8 методов)
  Функции: нет
- `app/middlewares/channel_checker.py` — Python-модуль
  Классы: `ChannelCheckerMiddleware` (8 методов)
  Функции: `save_pending_payload_to_redis` — Save pending_start_payload to Redis via the shared cache singleton., `get_pending_payload_from_redis` — Get pending_start_payload from Redis via the shared cache singleton., `delete_pending_payload_from_redis` — Delete pending_start_payload from Redis via the shared cache singleton.
- `app/middlewares/chat_type_filter.py` — Python-модуль
  Классы: `ChatTypeFilterMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/context_binding.py` — Python-модуль
  Классы: `ContextVarsMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/display_name_restriction.py` — Python-модуль
  Классы: `DisplayNameRestrictionMiddleware` (5 методов)
  Функции: нет
- `app/middlewares/global_error.py` — Python-модуль
  Классы: `GlobalErrorMiddleware` (10 методов)
  Функции: `send_error_to_admin_chat` — Отправляет уведомление об ошибке в админский чат с троттлингом.
- `app/middlewares/logging.py` — Python-модуль
  Классы: `LoggingMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/maintenance.py` — Python-модуль
  Классы: `MaintenanceMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/stale_callback_answer.py` — Python-модуль
  Классы: `StaleCallbackAnswerMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/subscription_checker.py` — Python-модуль
  Классы: `SubscriptionStatusMiddleware` (1 методов)
  Функции: нет
- `app/middlewares/throttling.py` — Python-модуль
  Классы: `ThrottlingMiddleware` (3 методов)
  Функции: нет
- `app/middlewares/tidy_text_request.py` — Python-модуль
  Классы: `TidyTextRequestMiddleware` (4 методов)
  Функции: нет

### app/services

- `app/services/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/account_merge_service.py` — Python-модуль
  Классы: нет
  Функции: `get_merge_preview` — Возвращает превью данных обоих аккаунтов для подтверждения мержа., `flush_remnawave_deletions` — Удаляет (или деактивирует как fallback) пользователей RemnaWave., `execute_merge` — Выполняет атомарный мерж двух аккаунтов. Caller отвечает за commit/rollback.
- `app/services/activation_funnel_service.py` — Python-модуль
  Классы: `ActivationFunnelService` (15 методов)
  Функции: нет
- `app/services/admin_notification_service.py` — Python-модуль
  Классы: `NotificationCategory`, `AdminNotificationService` (49 методов)
  Функции: нет
- `app/services/autopay_guard.py` — Python-модуль
  Классы: `AutopayLock`
  Функции: `lock_autopay_target_checked` — Hold User then Subscription until caller commits the whole renewal., `lock_autopay_target` — Обёртка для вызывающих, которым причина пропуска не нужна.
- `app/services/autopay_period.py` — Python-модуль
  Классы: нет
  Функции: `resolve_autopay_period_candidate` — Return ``candidate`` only if it is a valid renewal period for ``tariff``.
- `app/services/backup_service.py` — Python-модуль
  Классы: `BackupSettings`, `BackupService` (52 методов)
  Функции: нет
- `app/services/blacklist_service.py` — Python-модуль
  Классы: `BlacklistService` (9 методов)
  Функции: нет
- `app/services/blocked_users_service.py` — Python-модуль
  Классы: `BlockCheckStatus`, `BlockedUserAction`, `BlockCheckResult`, `BlockedUsersScanResult` (1 методов), `CleanupResult`, `BlockedUsersService` (8 методов)
  Функции: нет
- `app/services/broadcast_audience.py` — Python-модуль
  Классы: нет
  Функции: `validate_audience` — Reject forged field/value combinations and unknown tariff or promo group IDs., `audience_predicate` — Combine rows strictly from top to bottom, including mixed AND/OR rows., `audience_user_query` — One user row per recipient, independent of subscription count., `select_audience_users` — Return the same ordered, unique people for preview and delivery., `preview_audience_users` — Count exactly while keeping only one page of users in memory.
- `app/services/broadcast_email_mirror.py` — Python-модуль
  Классы: `MirrorJob` (1 методов), `DailyCounter` (4 методов), `BroadcastEmailMirror` (20 методов)
  Функции: `telegram_html_to_email_html` — HTML сообщения Telegram → фрагмент HTML письма., `subject_from_telegram_text` — Тема письма: первая непустая строка без тегов, не длиннее 90 символов., `build_email_body` — Тело письма: текст и кнопки-ссылки., `pick_mirror_user_ids` — Из тех же адресатов, что у Telegram-рассылки, — те, кому она не дойдёт:, `fetch_mirror_user_ids` — Адресаты копии для рассылки по target/audience (без загрузки адресов в память)., `should_mirror` — Персональные отправки (промопредложения) и продолжение после перезапуска не копируются.
- `app/services/broadcast_service.py` — Python-модуль
  Классы: `BroadcastMediaConfig`, `BroadcastConfig`, `EmailBroadcastConfig`, `BroadcastService` (19 методов), `EmailBroadcastService` (15 методов)
  Функции: `parse_email_scoped_target` — Email-таргет с идентификатором: ``promo_group_{id}`` или ``user_{id}``.
- `app/services/bypass_downgrade.py` — Python-модуль
  Классы: нет
  Функции: `mode`, `is_configured`, `is_enforcing` — Режим true и оба сквада заданы: подписки реально переводятся., `is_observing`, `quota_exhausted`, `is_suspension_effective` — Отдавать ли панели «обходы отключены» для этой подписки прямо сейчас., `panel_squads_for` — Сквады, которые уходят в панель: сквады тарифа или ``[Bypass-Off]``., `panel_traffic_limit_bytes_for` — Лимит для панели: в Bypass-Off — безлимит (обычные ноды считают ×0)., `ineligibility_reason` — Почему подписку НЕЛЬЗЯ перевести в Bypass-Off; ``None`` — можно., `has_bypass_quota` — Лимит подписки — это квота на обходы: в сквадах обходы, у тарифа есть лимит., `tariff_has_bypass_quota` — Лимит тарифа — квота на обходы (как has_bypass_quota у подписки, но по сквадам тарифа)., `is_suspended_snapshot` — Сквады из панели — это форма «обходы отключены», а не смена тарифа.
- `app/services/bypass_downgrade_service.py` — Python-модуль
  Классы: `BypassDowngradeService` (15 методов)
  Функции: нет
- `app/services/campaign_service.py` — Python-модуль
  Классы: `CampaignBonusResult`, `AdvertisingCampaignService` (8 методов)
  Функции: нет
- `app/services/channel_subscription_service.py` — Python-модуль
  Классы: `ChannelSubscriptionService` (15 методов)
  Функции: нет
- `app/services/checkout_squad_validation.py` — Python-модуль
  Классы: `CheckoutSquadsUnavailableError` (1 методов)
  Функции: `validate_checkout_squads` — Do not charge when every explicitly selected squad has been deleted., `validate_trial_checkout_squads` — Check a configured trial tariff before legacy paths debit its activation.
- `app/services/connected_accounts.py` — Python-модуль
  Классы: `ConnectedAccounts` (1 методов)
  Функции: нет
- `app/services/daily_subscription_service.py` — Python-модуль
  Классы: `DailySubscriptionService` (22 методов)
  Функции: нет
- `app/services/decision_log.py` — Python-модуль
  Классы: нет
  Функции: `record_decision` — Записать решение. Никогда не бросает: журнал не должен ломать то, что он журналирует.
- `app/services/disposable_email_service.py` — Python-модуль
  Классы: `DisposableEmailService` (7 методов)
  Функции: `parse_extra_domains` — Список оператора из настройки: любые разделители, регистр и ведущие '@'/'.' не важны., `domain_and_parents` — 'deep.sub.mail.tm' → 'deep.sub.mail.tm', 'sub.mail.tm', 'mail.tm' (голый TLD не считается).
- `app/services/email_retry_service.py` — Python-модуль
  Классы: `EmailRetryService` (13 методов)
  Функции: нет
- `app/services/event_emitter.py` — Python-модуль
  Классы: `EventEmitter` (6 методов)
  Функции: нет
- `app/services/faq_service.py` — Python-модуль
  Классы: `FaqService` (5 методов)
  Функции: нет
- `app/services/gift_claim_service.py` — Python-модуль
  Классы: `GiftClaimError`, `GiftClaimNotFoundError`, `GiftClaimSelfActivationError`, `GiftClaimAlreadyOwnedError`, `GiftClaimNotActivatableError`
  Функции: `claim_gift_for_user` — Claim and activate a gift subscription for an authenticated user., `claim_bound_gift_for_user` — Activate an already bound gift subscription by purchase ID (directed callback).
- `app/services/gift_history_service.py` — Python-модуль
  Классы: `GiftHistoryItem` (3 методов)
  Функции: `format_safe_recipient` — Format a privacy-safe recipient representation for display., `list_sender_gifts` — Query paginated gift history purchased by the given buyer., `get_sender_gift` — Retrieve a single gift purchase owned by the buyer by its ID., `has_sender_gifts` — Check whether the buyer has any eligible gift history (lightweight check).
- `app/services/gift_notification_service.py` — Python-модуль
  Классы: нет
  Функции: `resolve_gift_claim_channel` — Resolve and validate available claim channels (bot username and/or cabinet URL)., `build_gift_result_presentation` — Build localized text and inline keyboard for gift purchase result., `build_gift_history_detail_presentation` — Build localized HTML text and inline keyboard for sender gift detail view., `send_gift_result_message` — Send localized gift result presentation directly to user's Telegram chat.
- `app/services/gift_purchase_service.py` — Python-модуль
  Классы: `GiftQuote` (2 методов), `GiftTariffOffer`, `GiftRecipient`, `GiftPurchaseResult`, `GiftError`, `GiftFeatureDisabledError`, `GiftTariffUnavailableError`, `GiftPeriodUnavailableError`, `GiftPurchaseRestrictedError`, `GiftInsufficientBalanceError` (1 методов), `GiftPriceChangedError` (1 методов), `GiftIdempotencyConflictError`
  Функции: `is_gift_enabled` — Check if the gift feature is enabled via system settings., `list_gift_offers` — List eligible tariffs and their personalized quotes for gift purchase., `quote_gift_purchase` — Calculate personalized quote for a specific tariff and period., `purchase_gift_from_balance` — Atomically purchase a gift subscription from user balance with database idempotency.
- `app/services/guest_purchase_service.py` — Python-модуль
  Классы: `GuestPurchaseError` (1 методов), `GiftLifetimeHolderError` (1 методов)
  Функции: `get_claimable_gift` — Resolve one still-activatable gift by full token or deep-link prefix., `create_purchase` — Create a guest purchase record., `fulfill_purchase` — Fulfill a paid guest purchase by creating/extending the user account and subscription., `find_guest_purchase_user` — Find a guest-purchase user without mutating the account or session state., `evaluate_guest_purchase_registration` — Evaluate invite-only policy before a landing flow may mutate ``User``., `send_guest_notification` — Send notification for guest purchase delivery or activation requirement., `notify_gift_claim_available` — Best-effort: tell people a paid gift is waiting, with the CLAIM link., `activate_purchase` — Activate a PENDING_ACTIVATION purchase by replacing or creating a subscription., `retry_stuck_paid_purchases` — Retry fulfillment for purchases stuck in PAID status., `retry_stuck_pending_activation` — Retry activation for purchases stuck in PENDING_ACTIVATION status., `recover_stuck_pending_purchases` — Recover purchases stuck in PENDING by checking provider payment status.
- `app/services/landing_payment_records.py` — Python-модуль
  Классы: нет
  Функции: `get_landing_payment`, `fetch_landing_payments`, `exclude_landing_duplicates` — Match by purchase token/provider, never by amount, user or numeric row id.
- `app/services/legal_consent_service.py` — Python-модуль
  Классы: `LegalConsentRequirement`
  Функции: `get_requirement` — Требование согласия для НОВОГО пользователя кабинета., `missing_documents` — Какие из обязательных документов пользователь не отметил., `record_consent` — Записать факт согласия. Сбой записи не должен ронять регистрацию.
- `app/services/live_menu_service.py` — Python-модуль
  Классы: нет
  Функции: `live_menu_loop`, `refresh_live_menus` — Один проход. True — бот/панель/Telegram заняты или была ошибка: следующий проход реже.
- `app/services/log_rotation_service.py` — Python-модуль
  Классы: `LogRotationStatus`, `LogRotationService` (15 методов)
  Функции: нет
- `app/services/main_menu_button_service.py` — Python-модуль
  Классы: `MainMenuButtonService` (4 методов)
  Функции: нет
- `app/services/maintenance_service.py` — Python-модуль
  Классы: `MaintenanceStatus`, `MaintenanceService` (18 методов)
  Функции: нет
- `app/services/mass_send_service.py` — Python-модуль
  Классы: `MassSendService` (9 методов)
  Функции: нет
- `app/services/menu_layout/`
- `app/services/menu_layout_service.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/monitoring_service.py` — Python-модуль
  Классы: `AutopayFailState` (2 методов), `MonitoringService` (52 методов)
  Функции: `decide_autopay_fail_notification` — Decide whether/what to send on a failed-autopay tick., `apply_autopay_fail_notification` — Mutate state to record that a notification with `reason` was just sent., `traffic_warning_cache_key` — «Предупредили о трафике» — на подписку и текущий лимит (докупка или новый период дают новый ключ)., `telegram_blocked_cache_key`, `autopay_fail_notice_key`
- `app/services/notification_delivery_service.py` — Python-модуль
  Классы: `NotificationDeliveryService` (21 методов)
  Функции: нет
- `app/services/notification_settings_service.py` — Python-модуль
  Классы: `NotificationSettingsService` (12 методов)
  Функции: нет
- `app/services/notification_types.py` — Python-модуль
  Классы: `NotificationType`
  Функции: нет
- `app/services/paid_traffic_reset_service.py` — Python-модуль
  Классы: нет
  Функции: `stage_daily_reset` — Part of the financial transaction; caller commits charge and intent together., `deliver_daily_reset` — Canonical panel sync must have succeeded first. Never charges the user., `process_pending_daily_resets` — Recover committed requests after queue loss/restart, with bounded due scans.
- `app/services/panel_online.py` — Python-модуль
  Классы: `PanelOnlineSnapshot` (2 методов)
  Функции: `fetch_online_snapshot` — Обойти список панели по убыванию ``onlineAt``, пока отметка свежее окна., `get_online_snapshot` — Отметки подключений; ``None`` — панель не настроена или не ответила (это «не знаем», не «никого»).
- `app/services/panel_sync/`
- `app/services/partner_application_service.py` — Python-модуль
  Классы: `PartnerApplicationService` (6 методов)
  Функции: нет
- `app/services/partner_stats_service.py` — Python-модуль
  Классы: `PartnerStatsService` (5 методов)
  Функции: нет
- `app/services/payment/`
- `app/services/payment_decline_notice.py` — Python-модуль
  Классы: нет
  Функции: `decide_platega_decline_notice` — Писать ли человеку об отказе. Вызывать под блокировкой строки платежа, до смены статуса., `decline_notice_message`, `send_platega_decline_notice` — Отправить сообщение об отказе. Решение ``'sent'`` к этому моменту уже записано и закоммичено.
- `app/services/payment_method_config_service.py` — Python-модуль
  Классы: нет
  Функции: `refresh_display_name_overrides` — Reload names and saved order for synchronous Telegram keyboards., `get_display_name_override` — Sync read of a cabinet-set display name for a method, or None if not set., `get_display_sort_order`, `normalize_quick_amounts`, `get_effective_quick_amounts`, `ensure_payment_method_configs` — Initialize payment method configs if they don't exist yet., `get_all_configs` — Get all payment method configs ordered by sort_order., `get_config_by_method_id` — Get a single config by method_id., `update_config` — Update a payment method config., `update_sort_order` — Batch update sort order for all methods., `get_all_promo_groups` — Get all promo groups for the filter selector., `get_enabled_methods_for_user` — Get payment methods available for a specific user.
- `app/services/payment_problem_alert.py` — Python-модуль
  Классы: нет
  Функции: `build_payment_problem_text`, `alert_payment_not_applied` — Лог уровня error + сообщение в админ-чат (топик ошибок)., `note_invoice_created` — Счёт создан: провайдер работает, накопленные сбои больше не считаются., `alert_invoice_failed` — Провайдер не создал счёт на реальную попытку оплаты.
- `app/services/payment_reminder_email.py` — Python-модуль
  Классы: нет
  Функции: `render_reminder` — ``(subject, html)`` письма: ``kind`` это ``payment`` или ``cart``., `send_payment_reminder_email` — Шлёт письмо-напоминание. True — письмо реально отправлено.
- `app/services/payment_reversal_alert.py` — Python-модуль
  Классы: нет
  Функции: `alert_paid_payment_reversed`
- `app/services/payment_search_service.py` — Python-модуль
  Классы: `StatusFilter`, `PeriodPreset`, `SearchParams` (2 методов), `SearchStats`
  Функции: `search_payments` — Search payments across all (or filtered) providers., `search_payments_stats` — Compute aggregated statistics for the given search filters.
- `app/services/payment_service.py` — Python-модуль
  Классы: `PaymentService` (2 методов)
  Функции: `create_transaction`, `get_transaction_by_external_id`, `add_user_balance`, `get_user_by_id`, `get_user_by_telegram_id`, `create_wata_payment`, `get_wata_payment_by_link_id`, `get_wata_payment_by_id`, `get_wata_payment_by_local_id`, `get_wata_payment_by_order_id`, `update_wata_payment_status`, `link_wata_payment_to_transaction`, `create_platega_payment`, `get_platega_payment_by_id`, `get_platega_payment_by_id_for_update`, `get_platega_payment_by_transaction_id`, `get_platega_payment_by_correlation_id`, `update_platega_payment`, `link_platega_payment_to_transaction`, `create_cryptobot_payment`, `get_cryptobot_payment_by_invoice_id`, `update_cryptobot_payment_status`, `link_cryptobot_payment_to_transaction`, `create_xrocket_payment`, `get_xrocket_payment_by_invoice_id`, `update_xrocket_payment_status`, `link_xrocket_payment_to_transaction`, `create_pay2328_payment`, `get_pay2328_payment_by_uuid`, `get_pay2328_payment_by_id`, `update_pay2328_payment`, `link_pay2328_payment_to_transaction`
- `app/services/payment_verification_service.py` — Python-модуль
  Классы: `PendingPayment` (1 методов), `AutoPaymentVerificationService` (9 методов)
  Функции: `method_display_name`, `get_enabled_auto_methods`, `list_recent_pending_payments` — Return pending payments (top-ups) from supported providers within the age window., `get_payment_record` — Load single payment record and normalize it to :class:`PendingPayment`., `run_manual_check` — Trigger provider specific status refresh and return the updated record.
- `app/services/permission_service.py` — Python-модуль
  Классы: `PermissionService` (3 методов)
  Функции: `get_all_permissions` — Return flat list of all permissions: ``['users:read', 'users:edit', ...]``., `permission_matches` — Check if *user_perm* grants access for *required_perm*.
- `app/services/phantom_service.py` — Python-модуль
  Классы: нет
  Функции: `claim_phantom` — Claim a phantom user by backfilling Telegram profile data., `merge_phantom_into_user` — Merge phantom user into active user using the full account merge service., `sync_remnawave_after_phantom_merge` — Sync Remnawave panel after a phantom merge that transferred a subscription.
- `app/services/pinned_message_service.py` — Python-модуль
  Классы: нет
  Функции: `get_active_pinned_message`, `set_active_pinned_message`, `deactivate_active_pinned_message`, `deliver_pinned_message_to_user`, `broadcast_pinned_message` — Рассылает закреплённое сообщение всем активным пользователям., `unpin_active_pinned_message` — Открепляет активное сообщение у всех пользователей.
- `app/services/platega_service.py` — Python-модуль
  Классы: `PlategaService` (10 методов)
  Функции: нет
- `app/services/pricing_engine.py` — Python-модуль
  Классы: `TariffSwitchPricingUnavailableError`, `TariffBreakdown`, `ClassicBreakdown`, `RenewalPricing` (1 методов), `TariffSwitchResult` (2 методов), `PricingEngine` (21 методов)
  Функции: нет
- `app/services/privacy_policy_service.py` — Python-модуль
  Классы: `PrivacyPolicyService` (5 методов)
  Функции: нет
- `app/services/promo_group_assignment.py` — Python-модуль
  Классы: нет
  Функции: `maybe_assign_promo_group_by_total_spent` — Выдаёт человеку промогруппу по сумме трат.
- `app/services/promo_group_notifications.py` — Python-модуль
  Классы: `PromoGroupDiscounts` (1 методов)
  Функции: `collect_promo_group_discounts`, `format_discounts_for_telegram`, `format_period_discounts_plain` — «30 дней — 10%, 90 дней — 15%» для письма; пусто, если скидок по периодам нет., `notify_user_about_auto_assignment` — Сообщить человеку о новой промогруппе. Никогда не бросает.
- `app/services/promo_group_recalculation.py` — Python-модуль
  Классы: `RecalculationResult` (1 методов), `PromoGroupRecalculation` (8 методов)
  Функции: `recalculate_promo_groups` — Прогоняет правило автоназначения по всем платившим. Уведомлений на каждого — нет., `build_summary_text` — Одна сводка админам за весь проход., `notify_admins_about_recalculation` — Сводка уходит только когда есть что сказать: изменения или сбой.
- `app/services/promo_offer_email.py` — Python-модуль
  Классы: нет
  Функции: `send_promo_offer_email` — Шлёт одно промопредложение на почту. True — письмо реально отправлено.
- `app/services/promo_offer_service.py` — Python-модуль
  Классы: `PromoOfferService` (3 методов)
  Функции: нет
- `app/services/promocode_service.py` — Python-модуль
  Классы: `PromoCodeService` (12 методов)
  Функции: нет
- `app/services/public_offer_service.py` — Python-модуль
  Классы: `PublicOfferService` (5 методов)
  Функции: нет
- `app/services/rbac_bootstrap_service.py` — Python-модуль
  Классы: `AdminEnvCheck` (2 методов)
  Функции: `normalize_admin_email` — Канонизация email для сравнения с ADMIN_EMAILS: NFKC + lower + strip., `is_user_admin_by_env` — Проверяет, является ли юзер админом по ENV-конфигу (ADMIN_IDS/ADMIN_EMAILS)., `is_protected_from_blocking` — An account named in ADMIN_IDS/ADMIN_EMAILS must never end up BLOCKED., `bootstrap_superadmins` — Ensure every user from ADMIN_IDS / ADMIN_EMAILS has the Superadmin role., `ensure_superadmin_role_on_login` — Idempotent Superadmin assign for ADMIN_IDS / ADMIN_EMAILS users at login time.
- `app/services/referral_reward_service.py` — Python-модуль
  Классы: `RewardEvent`, `LevelConfig` (3 методов), `RewardComponent` (1 методов), `ReferralRewardLevelService` (4 методов), `DaysGrant`, `GrantOutcome` (1 методов), `LevelView`, `TierProgress`
  Функции: `resolve_referrer_chain` — Цепочка пригласивших снизу вверх: [(1, прямой), (2, его пригласивший), ...]., `count_level_payments` — Сколько раз этот уровень уже платил за эту пару., `count_referrals` — Сколько рефералов у пользователя., `is_level_unlocked` — Открыт ли уровень для этого партнёра., `select_tier_config` — Ранг партнёра: единственный уровень, который к нему применяется., `resolve_reward_preference` — Что получатель предпочитает, когда правило платит и деньгами, и днями., `build_reward_components` — Что и кому причитается. Ничего не начисляет., `grant_reward_days` — Выдать дни подписки. Возвращает исход, а не бросает., `award_referral_rewards` — Посчитать и выдать награды всей цепочке. Возвращает фактически выданное., `build_level_views` — Ступени программы, уровень смотрящего и его личная ставка., `describe_reward_choice_sides` — Что человек получит, выбрав деньги, и что — выбрав дни., `describe_active_levels` — Человекочитаемое описание активных ступеней., `describe_referee_bonus` — Что получит сам приглашённый. ``None`` — ничего не настроено., `resolve_tier_progress` — Ранг партнёра и ближайшая недостигнутая ступень. ``None`` вне режима рангов., `format_tier_progress` — Прогресс по рангам двумя строками: где сейчас и сколько до следующего., `format_reward_total` — Выплаченное одной строкой: деньги, дни или и то и другое., `legacy_percent_for_import` — Процент для переносимого уровня и то, о чём нужно предупредить.
- `app/services/referral_service.py` — Python-модуль
  Классы: нет
  Функции: `save_pending_referral` — Save pending referral to Redis for a not-yet-registered user., `get_pending_referral` — Get pending referral from Redis., `clear_pending_referral` — Clear pending referral after successful registration., `get_paid_referrals_count`, `get_referral_reward_payment_count`, `calculate_referral_commission_percent`, `attach_referrer_if_missing` — Eagerly attach a referrer to ``user`` when one isn't already set., `save_pending_campaign` — Сохранить атрибуцию кампании в Redis для ещё не зарегистрированного пользователя., `get_pending_campaign` — Get pending campaign from Redis., `clear_pending_campaign` — Clear pending campaign after successful application., `send_referral_notification` — Отправляет реферальное уведомление в Telegram или по email., `process_referral_registration`, `process_referral_topup`
- `app/services/referral_withdrawal_service.py` — Python-модуль
  Классы: `ReferralWithdrawalService` (19 методов)
  Функции: нет
- `app/services/registration_access_service.py` — Python-модуль
  Классы: `RegistrationChannel`, `RegistrationAccessReason`, `RegistrationInviteKind`, `VerifiedRegistrationIdentity`, `RegistrationInviteEvidence`, `RegistrationInviteValidator` (1 методов), `RegistrationAccessContext`, `RegistrationAccessDecision`, `RegistrationAccessService` (3 методов)
  Функции: нет
- `app/services/registration_invite_service.py` — Python-модуль
  Классы: `RegistrationInviteConflict`, `RegistrationInviteService` (2 методов)
  Функции: нет
- `app/services/remnawave_identity_backfill.py` — Python-модуль
  Классы: `UnresolvedRow`, `AppliedRow`, `BackfillReport` (3 методов)
  Функции: `backfill_remnawave_ids` — Populate ``remnawave_id`` on subscriptions, users and grace sessions.
- `app/services/remnawave_resync_service.py` — Python-модуль
  Классы: нет
  Функции: `resync_user_subscriptions_with_panel` — Resync all active subscriptions for a user with the RemnaWave panel.
- `app/services/remnawave_retry_queue.py` — Python-модуль
  Классы: `RetryItem`, `RemnaWaveRetryQueue` (10 методов)
  Функции: нет
- `app/services/remnawave_service.py` — Python-модуль
  Классы: `RemnaWaveConfigurationError`, `RemnaWaveService` (46 методов)
  Функции: нет
- `app/services/remnawave_sync_service.py` — Python-модуль
  Классы: `RemnaWaveAutoSyncStatus`, `FullSyncAlreadyRunning` (1 методов), `RemnaWaveAutoSyncService` (12 методов)
  Функции: `is_full_sync_running`, `perform_full_sync` — Полная синхронизация — одна для бота, кабинета и расписания., `sync_servers_from_panel` — Сквады панели → серверы бота; кеш стран сбрасывается.
- `app/services/remnawave_webhook_service.py` — Python-модуль
  Классы: `RemnaWaveWebhookService` (48 методов)
  Функции: нет
- `app/services/reporting_service.py` — Python-модуль
  Классы: `ReportingServiceError`, `ReportPeriod`, `ReportPeriodRange`, `ReportingService` (22 методов)
  Функции: нет
- `app/services/s2s_postback_service.py` — Python-модуль
  Классы: нет
  Функции: `send_postback` — Send S2S postback for an event.
- `app/services/settings_store.py` — Python-модуль
  Классы: нет
  Функции: `store_setting` — Сохранить настройку в базу и применить к процессу; ошибка — в лог, ответ False., `read_legacy_json` — Содержимое старого файла настроек; None — файла нет или он не читается (остаётся человеку)., `import_legacy_values` — Перенести значения из старого файла в базу и переименовать файл.
- `app/services/spofy_subpage_context.py` — Python-модуль
  Классы: нет
  Функции: `subpage_purchase_context`, `mark_subpage_text`, `subpage_return_url`, `subpage_return_context`, `purchase_source_context`, `cart_purchase_source` — Источник корзины: кабинет пишет source='cabinet', корзины бота поля не имеют., `current_purchase_source`, `mark_title` — Дописать пометку к первой строке — заголовку уведомления (в rich-виде это h6)., `user_has_pending_subpage_purchase` — Есть корзина страницы подписки и свежая метка пополнения под неё —
- `app/services/spofy_subpage_service.py` — Python-модуль
  Классы: `CheckoutSerializer` (5 методов)
  Функции: `checkout_fingerprint` — Idempotency key of one checkout attempt: same subscription + same cart + same method., `is_subpage_cart`, `tag_current_cart_as_subpage` — Re-tag the cart the cabinet helpers just saved (devices / traffic carry source='cabinet')., `has_resumable_cart` — Есть ли корзина, которую меню может предложить продолжить., `bind_cart_to_payment` — Remember what the page asked the customer to pay for this cart., `is_funded_by_payment` — True only if the credited amount is this cart's own payment and covers its price., `complete_subpage_carts_after_topup` — Complete only subscription-page carts funded by the payment that just arrived.
- `app/services/start_media_service.py` — Python-модуль
  Классы: нет
  Функции: `get_start_video_file_id` — file_id видео для стартового меню либо None., `set_start_video_file_id` — Сохраняет (или очищает) file_id видео стартового меню., `reset_start_video_cache` — Сбрасывает кеш (для тестов и ручной инвалидации).
- `app/services/startup_notification_service.py` — Python-модуль
  Классы: `StartupNotificationService` (7 методов), `ShutdownReason` (1 методов)
  Функции: `render_startup_message` — Классический вид (HTML): разделы деревом, внимание — отдельным блоком., `render_startup_rich` — Rich-вид (Bot API 10.1): те же разделы таблицами., `send_bot_startup_notification` — Удобная функция для отправки стартового уведомления., `format_uptime` — «3 д 4 ч 12 мин»; нули в начале опускаются, меньше минуты — словами., `render_shutdown_message` — Классический HTML: причина, аптайм, что делать дальше., `send_shutdown_notification` — Сообщить в админ-чат, что бот останавливается и почему., `send_crash_notification` — Отправляет уведомление о падении бота с лог-файлом.
- `app/services/subscription_auto_purchase_service.py` — Python-модуль
  Классы: `AutoPurchaseContext`, `AutoExtendContext`
  Функции: `renewal_cart_period_days` — Срок из корзины, если корзина — продление того же тарифа по прайсу; иначе None., `try_auto_extend_expired_after_topup` — Renew an opted-in expired subscription; release billing locks on abort., `try_resume_disabled_daily_after_topup` — Resume a DISABLED daily subscription immediately after balance top-up., `resume_addon_cart` — Докупка трафика/устройств из сохранённой корзины по явному нажатию., `auto_purchase_saved_cart_after_topup` — Attempts to automatically purchase subscriptions from saved carts.
- `app/services/subscription_dedup_service.py` — Python-модуль
  Классы: нет
  Функции: `dedupe_expired_tariff_subscriptions` — Background-safe entrypoint: never raises, returns the count removed.
- `app/services/subscription_deletion_service.py` — Python-модуль
  Классы: нет
  Функции: `delete_subscription_record` — Удалить подписку целиком.
- `app/services/subscription_purchase_service.py` — Python-модуль
  Классы: `PurchaseTrafficOption` (1 методов), `PurchaseTrafficConfig` (1 методов), `PurchaseServerOption` (1 методов), `PurchaseServersConfig` (1 методов), `PurchaseDevicesConfig` (1 методов), `PurchasePeriodConfig` (1 методов), `PurchaseSelection`, `PurchasePricingResult`, `PurchaseOptionsContext`, `PurchaseValidationError` (1 методов), `PurchaseBalanceError` (1 методов), `MiniAppSubscriptionPurchaseService` (7 методов), `SubscriptionPurchaseService`
  Функции: нет
- `app/services/subscription_renewal_service.py` — Python-модуль
  Классы: `SubscriptionRenewalError`, `SubscriptionRenewalChargeError`, `SubscriptionRenewalPricing` (2 методов), `SubscriptionRenewalResult`, `RenewalPaymentDescriptor`, `SubscriptionRenewalService` (1 методов)
  Функции: `build_renewal_period_id`, `decode_payment_payload`, `parse_payment_metadata`, `with_admin_notification_service`
- `app/services/subscription_service.py` — Python-модуль
  Классы: `SubscriptionReissueResult`, `SubscriptionService` (32 методов)
  Функции: `reload_after_panel_failure` — Перечитать объекты, которые откат сессии пометил протухшими., `reset_subscription_with_panel` — Обнулить подписку «как будто не оформляли» и снять доступ в панели RemnaWave,
- `app/services/support_settings_service.py` — Python-модуль
  Классы: `SupportSettingsService` (17 методов)
  Функции: нет
- `app/services/system_error_log_service.py` — Python-модуль
  Классы: `SystemErrorLogService` (13 методов)
  Функции: нет
- `app/services/system_settings_service.py` — Python-модуль
  Классы: `SettingDefinition` (1 методов), `ChoiceOption`, `ReadOnlySettingError`, `BotConfigurationService` (38 методов)
  Функции: нет
- `app/services/tariff_squad_sync.py` — Python-модуль
  Классы: нет
  Функции: `sync_tariff_squads_in_background` — Прогнать сквады тарифа по всем его живым подпискам со своей сессией БД.
- `app/services/tariff_switch_policy.py` — Python-модуль
  Классы: нет
  Функции: `remaining_days_for_switch` — Сколько дней остатка оплачивать при переключении тарифа., `should_reset_used_traffic` — Обнулять ли счётчик трафика при переключении тарифа.
- `app/services/topup_checkout_offer.py` — Python-модуль
  Классы: `TopupCheckoutOffer` (1 методов)
  Функции: `parse_confirm_callback` — (ключ корзины, цена, баланс) из кнопки подтверждения; None — данные не наши или битые., `is_one_tap_cart` — Корзина покупки или продления тарифа, которую оформляет сам человек кнопкой в боте., `resolve_topup_checkout_offer` — Предложение подтвердить сохранённую корзину сразу — или None, если нужен экран оформления., `checkout_offer_line` — Одна строка под «Зачислено»: что будет оформлено кнопкой, на какой срок и за сколько., `checkout_offer_button` — Та же кнопка «Подтвердить», что на экране оформления, с тем же текстом., `apply_topup_checkout_offer` — Сообщение о пополнении с кнопкой подтверждения вместо «Продолжить оформление»., `consume_recent_offer` — Было ли человеку только что отправлено сообщение с кнопкой подтверждения (одноразово).
- `app/services/traffic_cycle.py` — Python-модуль
  Классы: нет
  Функции: `begin_traffic_cycle` — Новая покупка: отсчёт начинается заново., `keep_traffic_cycle` — Запомнить день сброса перед тем, как изменится ``start_date``., `latest_cycle_date` — Последний день сброса не позже ``today``. ``None`` — первого месяца ещё не прошло., `is_cycle_due`, `next_cycle_date` — Первый день сброса строго после ``today``., `next_reset_at` — Начало (в UTC) местного дня, когда счётчик обнулится в следующий раз.
- `app/services/traffic_cycle_service.py` — Python-модуль
  Классы: `TrafficCycleService` (9 методов)
  Функции: `next_traffic_reset_at` — Когда этот проход обнулит трафик подписки в следующий раз; ``None`` — сброса не будет.
- `app/services/traffic_monitoring_service.py` — Python-модуль
  Классы: `TrafficViolation`, `TrafficMonitoringServiceV2` (35 методов), `TrafficMonitoringSchedulerV2` (7 методов), `TrafficMonitoringService` (1 методов), `TrafficMonitoringScheduler` (7 методов)
  Функции: нет
- `app/services/traffic_reset_policy.py` — Python-модуль
  Классы: нет
  Функции: `should_reset_traffic_on_daily_charge` — Обнулять ли израсходованный трафик после успешного суточного списания., `should_reset_traffic_on_tariff_purchase` — Обнулять ли израсходованный трафик при покупке тарифа из кабинета., `lift_panel_traffic_limit` — Снять с аккаунта в панели статус «трафик исчерпан» после оплаты новых суток.
- `app/services/trial_abuse_service.py` — Python-модуль
  Классы: `TrialAbuseService` (38 методов)
  Функции: нет
- `app/services/trial_activation_service.py` — Python-модуль
  Классы: `TrialActivationReversionResult`
  Функции: `rollback_trial_subscription_activation` — Удаляет только что созданную триальную подписку; False — если база не дала это сделать., `revert_trial_activation` — Откатывает триал, если панель не смогла его выдать.
- `app/services/trial_quest_service.py` — Python-модуль
  Классы: нет
  Функции: `on_first_connected` — Друг впервые подключился. Возвращает True, если награда выдана и сообщение отправлено.
- `app/services/user_action_log_service.py` — Python-модуль
  Классы: нет
  Функции: `current_request_path`, `normalize_cabinet_path` — Сворачивает числовые сегменты пути в {id} для группировки однотипных действий., `normalize_screen_path` — Путь экрана без секретов: числа → {id}, токены → {token}, хвостовой слэш срезан., `mark_user_seen` — Подвинуть ``last_activity``, если она старше интервала. Возвращает, изменилось ли., `should_log_cabinet_action`, `schedule_cabinet_action_log` — Fire-and-forget запись действия юзера в кабинете — не задерживает запрос., `schedule_screen_view_log` — Fire-and-forget запись открытия экрана; повтор в окне дедупликации — не пишется., `schedule_click_log` — Fire-and-forget запись нажатия: подпись кнопки + экран, где нажали., `remember_task` — Держать фоновую задачу сильной ссылкой до завершения., `drain_pending_actions` — Дождаться фоновых записей (нужно тестам и корректному завершению).
- `app/services/user_activity_service.py` — Python-модуль
  Классы: `UserActivityItem`, `UserActivityResponse`, `UnknownActivityTypes` (1 методов)
  Функции: `activity_sources` — Источники таймлайна активности: type -> (select, count_select, mapper)., `collect_user_activity` — Собрать страницу таймлайна.
- `app/services/user_avatar_service.py` — Python-модуль
  Классы: нет
  Функции: `pick_avatar_file_id` — Самый маленький размер, который ещё не мылится в шапке; иначе самый крупный., `get_avatar_file_id` — file_id текущего фото профиля или None. Никогда не бросает: аватар — не повод ронять кабинет.
- `app/services/user_cart_service.py` — Python-модуль
  Классы: `UserCartService` (21 методов)
  Функции: нет
- `app/services/user_revival_service.py` — Python-модуль
  Классы: `NotDeletedError`
  Функции: `revive_deleted_user` — Flip ``user.status`` from DELETED back to ACTIVE.
- `app/services/user_service.py` — Python-модуль
  Классы: `DeleteUserResult`, `UserService` (10 методов)
  Функции: нет
- `app/services/version_service.py` — Python-модуль
  Классы: `VersionInfo` (6 методов), `VersionService` (8 методов)
  Функции: нет
- `app/services/wata_service.py` — Python-модуль
  Классы: `WataAPIError`, `WataService` (14 методов)
  Функции: нет
- `app/services/web_auth_service.py` — Python-модуль
  Классы: нет
  Функции: `create_web_auth_token` — Generate a web auth token and store it in Redis (pending state)., `get_web_auth_request_context` — Who requested this sign-in (IP, browser, time) — read-only, the token stays pending., `link_web_auth_token` — Link a web auth token to a Telegram user (called by bot on /start)., `poll_web_auth_token` — Poll for web auth token status (non-destructive)., `consume_web_auth_token` — Atomically get and delete a web auth token.
- `app/services/webhook_service.py` — Python-модуль
  Классы: `DeliveryResult`, `WebhookService` (7 методов)
  Функции: нет
- `app/services/wheel_admin_notifier.py` — Python-модуль
  Классы: нет
  Функции: `build_spin_admin_message`, `notify_admin_about_spin` — Поставить уведомление в фон. Вызывать после коммита спина.
- `app/services/wheel_service.py` — Python-модуль
  Классы: `FreeSpinState` (1 методов), `SpinResult`, `EligibleSubscription`, `SpinAvailability`, `FortuneWheelService` (20 методов)
  Функции: `prize_rarity` — Подпись редкости для витрины призов: часто / редко / джекпот., `prize_days_end` — Новый конец срока для дней-приза: истёкшей подписке — от сейчас, а не от прошедшей даты.
- `app/services/wheel_topup_notifier.py` — Python-модуль
  Классы: нет
  Функции: `wheel_cabinet_url`, `spins_earned` — Сколько новых спинов дало это пополнение (порог мог быть перейдён несколько раз)., `build_spin_earned_message`, `on_payment_completed`, `register_wheel_topup_notifier` — Подключает слушатель к глобальному event_emitter (повторный вызов только обновляет бота).
- `app/services/withdrawal_notifications.py` — Python-модуль
  Классы: нет
  Функции: `build_withdrawal_status_message` — Текст и клавиатура уведомления о новом статусе заявки на языке пользователя., `notify_user_about_withdrawal_status` — Шлёт уведомление в Telegram; у пользователя без telegram_id — ничего не делает.
- `app/services/yandex_offline_conv_service.py` — Python-модуль
  Классы: нет
  Функции: `spawn_bg` — Spawn a background Yandex conversion task with proper reference tracking., `fire_trial_bg` — Fire trial event in background with its own DB session., `fire_purchase_bg` — Fire purchase event in background with its own DB session., `store_cid` — Store Yandex ClientID (and optional yclid) for a user. Returns True if stored., `store_cid_and_fire_purchase` — Persist a freshly-provided CID, then fire a purchase event in background., `store_cid_only` — Persist a freshly-provided CID WITHOUT firing a purchase event., `store_cid_and_fire_trial` — Same as `store_cid_and_fire_purchase` but for trial activation (#558449)., `on_registration` — Fire registration event (once per user)., `on_trial` — Fire trial-add event (once per user)., `on_purchase` — Fire ecommerce purchase event (every payment).

#### app/services/menu_layout

- `app/services/menu_layout/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/menu_layout/constants.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/menu_layout/context.py` — Python-модуль
  Классы: `MenuContext`
  Функции: нет
- `app/services/menu_layout/history_service.py` — Python-модуль
  Классы: `MenuLayoutHistoryService` (5 методов)
  Функции: нет
- `app/services/menu_layout/service.py` — Python-модуль
  Классы: `MenuLayoutService` (28 методов)
  Функции: нет
- `app/services/menu_layout/stats_service.py` — Python-модуль
  Классы: `MenuLayoutStatsService` (13 методов)
  Функции: нет

#### app/services/panel_sync

- `app/services/panel_sync/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/panel_sync/adopt.py` — Python-модуль
  Классы: нет
  Функции: `create_payload_as_patch` — Превратить payload создания в безопасный payload обновления., `adopt_or_create_panel_user` — Опознать существующего панельного пользователя по shortUuid, иначе создать.
- `app/services/panel_sync/db_session.py` — Python-модуль
  Классы: нет
  Функции: `release_transaction` — Закрыть транзакцию, которую сессия принесла от вызывающего., `rollback_quietly` — Откатить сессию после сбоя; неудача самого отката — только в debug-лог.
- `app/services/panel_sync/expiry.py` — Python-модуль
  Классы: нет
  Функции: `panel_expire_at` — Что положить в ``expireAt`` панели. ``None`` — не отправлять поле вовсе., `stale_panel_expire_at` — Чем погасить дату подписки в панели. ``None`` — не трогать., `panel_date_is_closing` — Дата в панели уже прошла или это наше собственное гашение на несколько минут вперёд.
- `app/services/panel_sync/expiry_intent.py` — Python-модуль
  Классы: нет
  Функции: `acknowledge_pending_expiry`
- `app/services/panel_sync/fields.py` — Python-модуль
  Классы: нет
  Функции: `narrow_push_fields` — Поля для ``push_subscription(only_fields=...)`` по флагам админа.
- `app/services/panel_sync/identity.py` — Python-модуль
  Классы: `PanelOwner`, `PanelAccountOwnedByAnotherUser` (1 методов), `PanelIdentity` (3 методов)
  Функции: `find_foreign_panel_owner` — Чей это аккаунт панели, если не этой подписки; ``None`` — наш или ничей., `resolve_panel_identity` — Найти в панели аккаунт этой подписки., `panel_id_is_free_for` — Не держит ли этот панельный id уже ДРУГАЯ строка подписок., `user_panel_id_is_free_for` — Не записан ли этот панельный id уже ДРУГОМУ человеку (``users.remnawave_id`` уникальна)., `link_subscription_panel_identity` — Проставить строке id панельного аккаунта, который только что обновили., `should_create_panel_account` — Перед синхронизацией после покупки/перевода: заводить аккаунт панели или обновлять свой.
- `app/services/panel_sync/lease.py` — Python-модуль
  Классы: `SubscriptionLease` (1 методов)
  Функции: `subscription_update_lease` — Держать блокировку подписки и отдать её свежее состояние; коммит — на выходе.
- `app/services/panel_sync/liveness.py` — Python-модуль
  Классы: нет
  Функции: `is_subscription_live` — Включать ли пользователя в панели ради этой подписки., `is_subscription_expired` — Истекла ли подписка по дате — состояние, которое панель выводит сама.
- `app/services/panel_sync/payload.py` — Python-модуль
  Классы: `PanelPayload` (3 методов)
  Функции: `resolve_panel_status` — Статус аккаунта в панели, каким его видит бот., `build_panel_payload` — Собрать поля запроса из пользователя, подписки и её тарифа.
- `app/services/panel_sync/projection.py` — Python-модуль
  Классы: `ProjectionPolicy`, `PanelSnapshot`
  Функции: `read_panel_user` — Разобрать ответ панели — словарь или объект клиента — в снимок., `panel_date_behind_paid_renewal` — Не принимать более короткий срок, пока локальное продление не подтверждено., `project_onto_subscription` — Перенести состояние панели в подписку. Возвращает имена изменённых полей., `panel_status_for_new_subscription` — Статус подписки, которую бот заводит по уже существующему аккаунту панели.
- `app/services/panel_sync/runner.py` — Python-модуль
  Классы: `SyncStats` (1 методов)
  Функции: `push_all_subscriptions` — Отправить в панель все подписки бота.
- `app/services/panel_sync/tags.py` — Python-модуль
  Классы: нет
  Функции: `resolve_panel_user_tag` — Тег для панельного аккаунта подписки.
- `app/services/panel_sync/traffic_strategy.py` — Python-модуль
  Классы: нет
  Функции: `get_traffic_reset_strategy` — Стратегия сброса трафика: настройка тарифа, иначе общая из конфига.
- `app/services/panel_sync/writer.py` — Python-модуль
  Классы: `DeviceLimitReconciliationError`, `PanelWriteResult`
  Функции: `write_panel_user_with_squad_recovery` — Recover a rejected write only when a fresh catalog proves stale squads., `push_subscription` — Отправить состояние подписки в панель., `patch_panel_account` — Обновить карточку аккаунта в панели, не трогая состояние подписки., `patch_panel_squads` — Переназначить аккаунту сквады тарифа.

#### app/services/payment

- `app/services/payment/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/services/payment/common.py` — Python-модуль
  Классы: `PaymentCommonMixin` (3 методов)
  Функции: `notify_email_user_topup` — «Пополнение успешно» для юзеров без Telegram (#2952)., `send_cart_notification_after_topup` — Run post-topup side-effects: resume daily / auto-purchase saved cart / auto-extend., `try_fulfill_guest_purchase` — Attempt to fulfill a guest purchase detected in payment metadata., `build_topup_success_message` — Текст и клавиатура сообщения «Зачислено» — одни для всех платёжных систем., `topup_success_text` — «Зачислено N · Баланс M» — одно сообщение о пополнении для всех платёжных систем.
- `app/services/payment/cryptobot.py` — Python-модуль
  Классы: `CryptoBotPaymentMixin` (6 методов)
  Функции: нет
- `app/services/payment/pay2328.py` — Python-модуль
  Классы: `Pay2328PaymentMixin` (4 методов)
  Функции: нет
- `app/services/payment/payer_identity.py` — Python-модуль
  Классы: `PayerIdentity` (1 методов), `PayerRecord`
  Функции: `synthetic_payer_email` — Стабильный адрес-идентификатор: тот же плательщик → тот же адрес., `platega_email_for` — Email-идентификатор плательщика для Platega. Всегда валиден, никогда не пуст., `payer_from_user` — Плательщик-пользователь., `guest_payer_id` — Идентификатор гостя: сам токен покупки наружу не отдаём — по нему забирают подписку., `payer_from_guest` — Гость лендинга: аккаунта нет, есть контакт, который он оставил (почта или Telegram)., `resolve_user_payer` — Плательщик по id пользователя. Точечный select — это горячий путь оплаты., `resolve_guest_payer` — Плательщик-гость по токену покупки лендинга.
- `app/services/payment/platega.py` — Python-модуль
  Классы: `PlategaPaymentMixin` (5 методов)
  Функции: нет
- `app/services/payment/stars.py` — Python-модуль
  Классы: `TelegramStarsMixin` (5 методов)
  Функции: `stars_to_kopeks` — Рубли за звёзды по текущему курсу — так же, как считается пополнение Stars., `credit_unapplied_stars_payment` — Оплата Stars прошла, а применить её по назначению нельзя — зачисляем на баланс.
- `app/services/payment/wata.py` — Python-модуль
  Классы: `WataPaymentMixin` (4 методов)
  Функции: нет
- `app/services/payment/xrocket.py` — Python-модуль
  Классы: `XRocketPaymentMixin` (7 методов)
  Функции: нет

### app/tools

- `app/tools/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет

### app/utils

- `app/utils/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/utils/background.py` — Python-модуль
  Классы: нет
  Функции: `spawn_background_task` — Как ``asyncio.create_task``, но цикл событий не потеряет задачу при сборке мусора.
- `app/utils/bot_commands.py` — Python-модуль
  Классы: нет
  Функции: `configure_bot_commands`
- `app/utils/bot_identity.py` — Python-модуль
  Классы: нет
  Функции: `sync_bot_username` — Sync settings.BOT_USERNAME from the live bot (token-authoritative).
- `app/utils/button_styles_cache.py` — Python-модуль
  Классы: нет
  Функции: `get_cached_button_styles` — Return the current merged config (DB overrides + defaults)., `load_button_styles_cache` — Load button styles from DB and refresh the module cache.
- `app/utils/cache.py` — Python-модуль
  Классы: `CacheService` (16 методов), `RateLimitCache` (4 методов), `TokenReplayCache` (1 методов), `ChannelSubCache` (7 методов)
  Функции: `cache_key`
- `app/utils/chat_menu_button.py` — Python-модуль
  Классы: нет
  Функции: `configure_chat_menu_button` — Выставляет кнопку меню на открытие веб-кабинета. Возвращает True, если выставлена.
- `app/utils/chat_scope.py` — Python-модуль
  Классы: нет
  Функции: `callback_from_group` — Сообщение с кнопкой лежит не в личке (группа, супергруппа, канал).
- `app/utils/check_reg_process.py` — Python-модуль
  Классы: нет
  Функции: `is_registration_process`
- `app/utils/currency_converter.py` — Python-модуль
  Классы: `CurrencyConverter` (8 методов)
  Функции: нет
- `app/utils/decorators.py` — Python-модуль
  Классы: нет
  Функции: `admin_required`, `auth_required` — Простая проверка на наличие пользователя в апдейте. Middleware уже подтягивает db_user,, `error_handler`, `rate_limit`
- `app/utils/display_mode.py` — Python-модуль
  Классы: нет
  Функции: `normalize_display_mode`, `is_visible_in_bot`, `is_visible_in_web`
- `app/utils/email_alias.py` — Python-модуль
  Классы: нет
  Функции: `canonical_email` — Вид адреса для сравнения: тот же ящик — та же строка., `sibling_domains` — Домены, письма с которых попадают в тот же ящик, включая сам домен., `alias_match_clause` — SQLAlchemy-условие: колонка хранит адрес того же ящика, что и ``email``.
- `app/utils/formatters.py` — Python-модуль
  Классы: нет
  Функции: `format_datetime` — Момент в часовом поясе оператора (settings.TIMEZONE); без зоны — считается UTC., `format_time_ago`, `format_days_declension`, `format_username_link` — Telegram-логин явной ссылкой., `format_human_date` — «12 марта» без года. language — код локали бота (ru/en)., `format_human_datetime` — «12 марта, 14:30» — человеческая дата + время суток.
- `app/utils/formatting.py` — Python-модуль
  Классы: нет
  Функции: `safe_html_name` — HTML-escape a display name for Telegram HTML messages., `user_html_link` — Build an HTML-safe clickable user link for Telegram messages., `format_traffic` — Форматирует трафик., `format_price_kopeks` — Форматирует цену из копеек в рубли., `format_period` — Форматирует период. Бессрочный (ULTIMA, 2222 дня) — «Навсегда».
- `app/utils/fsm_memory.py` — Python-модуль
  Классы: `LimitedMemoryStorage` (7 методов)
  Функции: `peak_rss_mb` — Пик RSS с момента старта процесса (не убывает)., `current_rss_mb` — Текущий RSS процесса в мегабайтах., `log_memory` — Одна строка в лог с RSS; предупреждение при превышении порога.
- `app/utils/fsm_selection.py` — Python-модуль
  Классы: нет
  Функции: `mutate_fsm_if_current` — Compare state AND data before atomically updating or clearing both.
- `app/utils/gift_links.py` — Python-модуль
  Классы: `GiftLinkError`, `InvalidGiftTokenError`, `InvalidBotUsernameError`, `MissingBotUsernameError`, `InvalidCabinetUrlError`, `MissingCabinetUrlError`, `InvalidClaimLinkError`, `InvalidShareTextError`, `GiftClaimArtifacts`
  Функции: `build_gift_public_code` — Build the canonical public gift code (``GIFT_<59_chars>``)., `parse_gift_claim_input` — Parse and normalize gift claim credentials from various user inputs., `build_gift_claim_artifacts` — Build immutable gift claim artifacts with public code and available channel URLs., `build_bot_gift_claim_link` — Build a canonical Telegram deep-link for claiming a gift subscription., `build_cabinet_gift_claim_link` — Build a canonical web cabinet claim link containing the full bearer token., `build_telegram_gift_share_url` — Build a native Telegram share URL (``https://t.me/share/url``) with prefilled text.
- `app/utils/gift_result.py` — Python-модуль
  Классы: нет
  Функции: `gift_valid_until_line` — Строка «Подписка действует до …» по фактической дате окончания., `subscription_end_fields` — ``end_date`` и ``is_lifetime`` подписки после активации — для ответов кабинета.
- `app/utils/incy_crypt1.py` — Python-модуль
  Классы: нет
  Функции: `encrypt_incy_link` — Шифрует ссылку подписки в ``incy://crypt1/...``., `wrap_incy_deep_link` — Подменяет ``incy://import|add/<url>`` на ``incy://crypt1/<зашифрованное>``.
- `app/utils/legacy_subscription.py` — Python-модуль
  Классы: нет
  Функции: `is_legacy_subscription` — Платная подписка без тарифа при включённом режиме тарифов.
- `app/utils/lifetime.py` — Python-модуль
  Классы: нет
  Функции: `lifetime_label` — «Навсегда» на языке пользователя (с заглавной: годится и для кнопки, и после «Период:»)., `is_lifetime_period`, `is_lifetime_end` — Дата окончания бессрочной подписки., `normalize_end_date` — Дата дальше LIFETIME_MIN_DAYS от текущего момента приводится к LIFETIME_END., `apply_lifetime_period` — Для бессрочного периода превращает «{period_days} дн.» в «Навсегда», а «на {period_days} дн.» в «навсегда»., `for_period_ru` — «на 30 дней» для описаний платежей и операций, для бессрочного периода «навсегда».
- `app/utils/log_handlers.py` — Python-модуль
  Классы: `LevelFilterHandler` (5 методов), `PaymentLogFilter` (1 методов), `ExcludePaymentFilter` (1 методов)
  Функции: нет
- `app/utils/logo_fingerprint.py` — Python-модуль
  Классы: нет
  Функции: `logo_fingerprint` — Отпечаток файла логотипа: меняется при каждой загрузке нового файла., `logo_version` — Короткая версия для ``?v=`` в адресе; ``None`` — файла нет.
- `app/utils/long_messages.py` — Python-модуль
  Классы: нет
  Функции: `answer_long_text` — message.answer с разбивкой; клавиатура — на последнем куске., `edit_long_text` — message.edit_text с разбивкой., `send_long_text` — bot.send_message с разбивкой; клавиатура — на последнем куске.
- `app/utils/markdown_to_telegram.py` — Python-модуль
  Классы: нет
  Функции: `github_markdown_to_telegram_html` — Convert GitHub-flavored Markdown to Telegram HTML., `truncate_for_blockquote` — Truncate description HTML to fit within Telegram message limit inside a blockquote.
- `app/utils/menu_layout_cache.py` — Python-модуль
  Классы: нет
  Функции: `get_cached_menu_layout` — Return the current layout config (DB overrides + defaults)., `load_menu_layout_cache` — Load menu layout from DB and refresh the module cache.
- `app/utils/message_patch.py` — Python-модуль
  Классы: нет
  Функции: `caption_exceeds_telegram_limit` — Check if text exceeds Telegram's caption limit (1024 parsed chars)., `set_banner_text_only`, `reset_banner_text_only`, `banner_text_only`, `set_banner_variant`, `reset_banner_variant`, `get_logo_media` — Возвращает кешированный file_id или FSInputFile для логотипа., `is_qr_message`, `append_privacy_hint`, `prepare_privacy_safe_kwargs`, `is_privacy_restricted_error`, `is_topic_required_error` — Проверяет, является ли ошибка связанной с топиками/форумами., `patch_message_methods`
- `app/utils/miniapp_buttons.py` — Python-модуль
  Классы: нет
  Функции: `strip_leading_emoji` — Удалить ведущий юникод-emoji + следующий пробел. Безопасно для текста без emoji., `tg_emoji_to_unicode` — Развернуть <tg-emoji emoji-id='...'>X</tg-emoji> в обычный юникод-эмодзи X., `build_main_menu_button` — Always-callback button for "Main Menu" / "Главное меню" navigation., `build_cabinet_url` — Join ``MINIAPP_CUSTOM_URL`` with an optional *path* segment., `build_miniapp_or_callback_button` — Create a button that opens the cabinet miniapp or falls back to a callback., `build_subscription_extend_button` — Кнопка «Продлить подписку» для уведомлений — единая точка на весь бот., `build_miniapp_startapp_url` — Собрать t.me Mini App deep link, открывающий кабинет в ЛЮБОМ типе чата., `build_admin_ticket_cabinet_button` — Кнопка «открыть тикет в админ-кабинете» для уведомления о тикете.
- `app/utils/notification_keyboards.py` — Python-модуль
  Классы: нет
  Функции: `subscription_button`, `buy_button`, `topup_button`, `buy_traffic_button`, `referral_button`, `support_button`, `keyboard` — Одна кнопка в ряд; пропущенные (``None``) не показываются., `admin_url`, `admin_user_card_keyboard` — Кнопка на карточку пользователя под уведомлением в админ-чате., `admin_startup_keyboard` — Разделы админки, которые открывают чаще всего.
- `app/utils/notification_prefs.py` — Python-модуль
  Классы: нет
  Функции: `get_user_notification_pref` — Get a single notification preference for user., `is_subscription_expiry_enabled` — Check if subscription expiry notifications are enabled for user., `get_subscription_expiry_days` — Get the number of days before expiry to notify., `is_traffic_warning_enabled` — Check if traffic warning notifications are enabled for user., `get_traffic_warning_percent` — Get the traffic usage percentage threshold for warning., `is_balance_low_enabled` — Check if low balance notifications are enabled for user., `get_balance_low_threshold` — Get the low balance threshold in kopeks., `is_news_enabled` — Check if news notifications are enabled for user., `is_promo_offers_enabled` — Check if promo offer notifications are enabled for user., `filter_users_by_broadcast_category` — Отсеивает отписавшихся от рассылки этой категории.
- `app/utils/pagination.py` — Python-модуль
  Классы: `PaginationResult` (1 методов)
  Функции: `paginate_list`, `build_page_nav_row` — Ряд листания «⬅️ N/M ➡️».
- `app/utils/panel_tag.py` — Python-модуль
  Классы: нет
  Функции: `normalize_panel_tag` — Привести тег к виду панели; пустое значение — «тега нет».
- `app/utils/payment_fallback.py` — Python-модуль
  Классы: нет
  Функции: `fallback_methods_keyboard` — Кнопки способов на ту же сумму без упавшего провайдера; ``None``, если других способов нет., `fallback_text`, `answer_creation_failed` — Ответ на сбой создания платежа: другие способы на ту же сумму или прежний текст ошибки.
- `app/utils/payment_logger.py` — Python-модуль
  Классы: нет
  Функции: `configure_payment_logger` — Configure the payment logger with the given handler.
- `app/utils/payment_utils.py` — Python-модуль
  Классы: нет
  Функции: `get_available_payment_methods` — Возвращает список доступных способов оплаты с их настройками, `get_payment_methods_text` — Генерирует текст с описанием доступных способов оплаты
- `app/utils/photo_message.py` — Python-модуль
  Классы: нет
  Функции: `safe_edit_or_resend` — Безопасно отредактировать текст сообщения или отправить новое при ошибке., `edit_or_answer_photo`
- `app/utils/pricing_utils.py` — Python-модуль
  Классы: нет
  Функции: `calculate_months_from_days`, `calculate_period_device_cost` — Cost in kopeks for a periodic tariff's devices; one priced month is 30 days., `calculate_price_per_month` — Месячная ставка для периода длиной period_days дней (месяц = 30 дней)., `calculate_prorated_price` — Calculate prorated price based on remaining days., `count_chargeable_devices` — Сколько докупаемых устройств платные: места в пределах тарифа бесплатны., `calculate_device_addon_price` — Цена докупки устройств — та же, что показывает кабинет., `apply_percentage_discount` — Apply percentage discount using PricingEngine's floor division., `format_period_description`, `validate_pricing_calculation`
- `app/utils/promo_offer.py` — Python-модуль
  Классы: нет
  Функции: `offer_discount_source` — Значение для ``User.promo_offer_discount_source`` при активации предложения., `split_discount_source` — ``(tariff_id или None, notification_type)`` из источника скидки., `get_user_active_promo_discount_percent`, `build_promo_offer_timer_line`, `build_promo_offer_hint`, `build_test_access_hint`
- `app/utils/promo_rate_limiter.py` — Python-модуль
  Классы: `PromoRateLimiter` (7 методов)
  Функции: `validate_promo_format` — Проверяет формат промокода: 3-50 символов, только буквы/цифры/дефис/подчёркивание.
- `app/utils/proxy.py` — Python-модуль
  Классы: нет
  Функции: `mask_proxy_url` — Mask credentials in a proxy URL for safe logging.
- `app/utils/public_url.py` — Python-модуль
  Классы: нет
  Функции: `public_url` — ``url`` (обычно из ``request.url_for``) со схемой и хостом, которые видит клиент за прокси.
- `app/utils/quiet_hours.py` — Python-модуль
  Классы: нет
  Функции: `is_quiet_time`
- `app/utils/redis_client.py` — Python-модуль
  Классы: нет
  Функции: `create_redis` — Клиент с пулом соединений к ``url`` (по умолчанию ``settings.REDIS_URL``).
- `app/utils/rich_admin.py` — Python-модуль
  Классы: нет
  Функции: `is_rich_admin_enabled`, `rich_footer_now` — Футер с меткой и временем: tg-time рендерится в таймзоне админа., `rich_kv_table` — Таблица «показатель → значение» (bordered/striped). Значения — сырой HTML., `rich_traceback_details` — Сворачиваемый traceback: <details> + <pre><code class="language-python">., `classic_admin_html_to_rich` — Конвертирует классическое HTML-уведомление в rich-разметку., `try_send_rich_admin_message` — Отправляет rich-сообщение в админ-чат. False — слать классический вариант.
- `app/utils/rich_buttons.py` — Python-модуль
  Классы: нет
  Функции: `render_keyboard_as_rich_html` — Клавиатура целиком в виде рядов ``<tg-button-row>``.
- `app/utils/rich_media.py` — Python-модуль
  Классы: нет
  Функции: `prepare_rich_message` — Replace HTTP image sources with matching tg://photo references and media.
- `app/utils/rich_menu.py` — Python-модуль
  Классы: нет
  Функции: `is_rich_menu_enabled`, `live_menu_fingerprint` — Только то, что видно в меню. HTML сравнивать нельзя: случайное сообщение админа и таймеры., `remember_live_menu` — Запоминает последнее rich-меню чата для фоновой перерисовки. Никогда не бросает., `forget_live_menu_on_callback` — Нажали кнопку на живом меню — дальше подменю, фон это сообщение не трогает., `build_main_menu_rich_html` — Собирает rich-HTML главного меню (контент, без клавиатуры)., `try_send_rich_main_menu` — Отправляет главное меню rich-сообщением. False — показать классическое меню., `try_answer_rich_main_menu` — Rich-аналог message.answer(menu_text) для /start и завершения регистрации., `try_edit_rich_main_menu` — Rich-аналог edit_or_answer_photo для callback-навигации. False — рисовать классику.
- `app/utils/rich_notify.py` — Python-модуль
  Классы: нет
  Функции: `build_notification_rich_html` — Текст уведомления → rich-разметка в стиле главного меню., `try_send_rich_notification` — Шлёт уведомление rich-сообщением. ``False`` — отправить классическое.
- `app/utils/startup_timeline.py` — Python-модуль
  Классы: `StepRecord`, `StageHandle` (6 методов), `StartupTimeline` (7 методов)
  Функции: нет
- `app/utils/subscription_time.py` — Python-модуль
  Классы: нет
  Функции: `time_left` — Остаток до ``end_date``; у истёкшей подписки — ноль, не отрицательное., `local_days_until` — Через сколько календарных дней наступит дата окончания: 0 — сегодня, 1 — завтра., `days_left_rounded_up` — Начатые сутки остатка: 20 ч → 1, 1 д 23 ч → 2; у истёкшего — 0., `ends_within_days` — Окончание не дальше чем через ``days`` суток (уже истёкшая — тоже да)., `format_time_left` — «1 дн. 23 ч.», «5 ч.», «42 мин.» или «истёк» — без отбрасывания неполных суток., `format_expiry_warning` — Предупреждение под сроком: «истекает сегодня/завтра» по календарю, «через минуты» в последний час.
- `app/utils/subscription_utils.py` — Python-модуль
  Классы: нет
  Функции: `resolve_tariff_cart_traffic` — Resolve explicit custom traffic; reject ambiguous legacy or stale selections., `get_display_subscription_link`, `get_happ_cryptolink_redirect_link`, `convert_subscription_link_to_happ_scheme`, `device_limit_needs_heal` — Return True if a stored ``device_limit`` is structurally invalid., `coerce_panel_device_limit` — Normalize ``hwidDeviceLimit`` from a RemnaWave panel response., `resolve_tariff_renewal_device_limit` — Продление сохраняет докупки лимитного тарифа; ноль у тарифа — безлимит., `resolve_tariff_purchase_device_limit` — Price and provision the same device limit when a paid classic row gets its first tariff., `resolve_min_device_limit` — Нижняя граница, до которой пользователь может уменьшить лимит устройств., `resolve_hwid_device_limit` — Return a positive effective device limit, or None for no finite limit., `active_wheel_bonus_devices` — Сколько бонусных устройств из колеса действует сейчас (0, если нет или срок вышел)., `resolve_hwid_device_limit_for_payload` — Return the device limit that should be sent to RemnaWave APIs.
- `app/utils/support_access.py` — Python-модуль
  Классы: нет
  Функции: `is_payment_support_handler`
- `app/utils/telegram_delivery.py` — Python-модуль
  Классы: нет
  Функции: `is_user_unreachable` — Сообщение некуда доставить: 403 от Telegram или 400 с маркером недоступности., `describe_unreachable` — Причина по-русски для отчёта админам; для незнакомого отказа — общая формулировка.
- `app/utils/telegram_errors.py` — Python-модуль
  Классы: нет
  Функции: `is_stale_callback_query_error` — Telegram уже не ждёт ответ на это нажатие: пользователь давно увидел результат.
- `app/utils/telegram_html.py` — Python-модуль
  Классы: нет
  Функции: `html_to_telegram`, `stored_html_to_telegram_pages` — Сохранённый HTML страницы → куски, которые Telegram согласится разобрать., `trim_broken_markup` — Обрезает незакрытый тег или неполную HTML-сущность в конце куска., `split_telegram_text`
- `app/utils/text_search.py` — Python-модуль
  Классы: нет
  Функции: `case_variants` — Регистровые варианты термина, по которым имеет смысл искать., `contains_patterns` — LIKE-шаблоны «содержит term» для всех регистровых вариантов., `contains_conditions` — ILIKE-условия «колонка содержит term» — по каждой колонке и каждому варианту.
- `app/utils/text_tidy.py` — Python-модуль
  Классы: нет
  Функции: `tidy_text` — Схлопывает 2+ пустые строки в одну и убирает хвостовые пробелы. ``None`` и пустое возвращает как есть., `strip_tg_emoji` — <tg-emoji …>🎁</tg-emoji> → 🎁 for text that leaves the bot as plain text (copied, forwarded, shared)., `plain_alert_text` — Текст для всплывающего окна после нажатия кнопки: HTML там не разбирается., `brand_bypass_sign` — «Голый» 🏴‍☠️ в HTML-тексте → тот же щит Spofy, что в локали и на кнопках. Только для parse_mode=HTML.
- `app/utils/ticket_media.py` — Python-модуль
  Классы: нет
  Функции: `get_ticket_media`, `ticket_media_chunks`, `send_ticket_media` — Отправить вложения тикета пачками (одно — отдельным сообщением)., `delete_ticket_media_notice` — Кнопка «🗑 Удалить» под отправленными вложениями: убрать последнее вложение и само уведомление.
- `app/utils/ticket_text.py` — Python-модуль
  Классы: нет
  Функции: `preview_text` — Короткое превью сообщения для уведомлений (полный текст — в карточке тикета)., `split_long_block` — Режет блок по границам строк/слов, не разрывая HTML-теги и сущности., `build_ticket_pages` — Собирает страницы «шапка + сообщения», не теряя ни одного символа.
- `app/utils/timezone.py` — Python-модуль
  Классы: нет
  Функции: `get_local_timezone` — Return the configured local timezone., `local_date` — Календарная дата момента ``moment`` (по умолчанию — сейчас) в зоне ``tz``., `local_day_start` — Полночь локального дня, к которому относится ``moment``, как момент в UTC., `local_day_bounds` — Полуинтервал ``[начало, конец)`` локального дня в UTC: ``created_at >= start`` и ``< end``., `local_month_start` — Полночь первого числа локального месяца, к которому относится ``moment``, как момент в UTC., `next_local_wall_clock` — Ближайший момент (в UTC), когда часы в зоне ``tz`` покажут одно из ``times``., `panel_datetime_to_utc` — Normalize a RemnaWave panel datetime to aware UTC., `to_local_datetime` — Convert a datetime value to the configured local timezone., `format_local_datetime` — Format a datetime value in the configured local timezone., `format_email_datetime` — Format a datetime for email-template substitution.
- `app/utils/topup_retry.py` — Python-модуль
  Классы: нет
  Функции: `format_topup_amount_retry`
- `app/utils/user_utils.py` — Python-модуль
  Классы: нет
  Функции: `format_referrer_info` — Return formatted referrer info for admin notifications., `generate_unique_referral_code`, `get_effective_referral_commission_percent` — Возвращает индивидуальный процент комиссии пользователя или дефолтное значение., `mark_user_as_had_paid_subscription`, `get_user_referral_summary`, `get_detailed_referral_list`, `get_referral_analytics`
- `app/utils/validators.py` — Python-модуль
  Классы: нет
  Функции: `validate_email`, `sanitize_html` — Безопасно санитизирует HTML-текст, заменяя HTML-сущности на соответствующие теги,, `sanitize_telegram_name` — Санитизация Telegram-имени для безопасной вставки в HTML и хранения., `validate_html_tags`, `validate_html_structure`
- `app/utils/websocket_errors.py` — Python-модуль
  Классы: нет
  Функции: `is_client_gone` — Ушёл ли клиент — или это настоящая ошибка, которую надо показать.

### app/webserver

- `app/webserver/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `app/webserver/docs.py` — Python-модуль
  Классы: нет
  Функции: `add_redoc_endpoint` — Attach a ReDoc endpoint if docs are enabled.
- `app/webserver/payments.py` — Python-модуль
  Классы: нет
  Функции: `create_payment_router` — Роутер вебхуков платёжных провайдеров.
- `app/webserver/remnawave_webhook.py` — Python-модуль
  Классы: нет
  Функции: `create_remnawave_webhook_router` — Build the FastAPI router for RemnaWave webhooks.
- `app/webserver/server.py` — Python-модуль
  Классы: `WebAPIServer` (3 методов)
  Функции: нет
- `app/webserver/telegram.py` — Python-модуль
  Классы: `TelegramWebhookProcessorError`, `TelegramWebhookProcessorNotRunningError`, `TelegramWebhookOverloadedError`, `TelegramWebhookProcessor` (8 методов)
  Функции: `create_telegram_router`
- `app/webserver/unified_app.py` — Python-модуль
  Классы: нет
  Функции: `create_unified_app`

## assets

- `assets/bedolaga_app3.svg` — файл
- `assets/logo2.svg` — файл

## banners

- `banners/expired.png` — файл
- `banners/expired_en.png` — файл
- `banners/new.png` — файл
- `banners/new_en.png` — файл
- `banners/paid.png` — файл
- `banners/paid_en.png` — файл
- `banners/trial.png` — файл
- `banners/trial_en.png` — файл

## docker

- `docker/postgres/`

### docker/postgres

- `docker/postgres/pg-upgrade-guard.sh` — файл
- `docker/postgres/pgdg-apt.asc` — файл

## docs

- `docs/abuse-api.md` — файл
- `docs/apple-iap-consumable-topups.md` — файл
- `docs/apple-iap-ios-requirements.md` — файл
- `docs/autopay-concurrency.md` — файл
- `docs/broadcast_audiences.md` — файл
- `docs/handoffs/`
- `docs/hwid-limit-reconciliation.md` — файл
- `docs/menu_stats_api_usage.md` — файл
- `docs/miniapp-setup.md` — файл
- `docs/mobile-support-websocket-v1.md` — файл
- `docs/paid-traffic-resets.md` — файл
- `docs/panel-expiry-recovery.md` — файл
- `docs/payments-payer-data.md` — файл
- `docs/persistent_cart_system.md` — файл
- `docs/postgresql-18-upgrade.md` — файл
- `docs/project_structure_reference.md` — файл
- `docs/referral_program_setting.md` — файл
- `docs/traffic-package-expiry.md` — файл
- `docs/web-admin-integration-guide.md` — файл
- `docs/web-admin-integration.md` — файл
- `docs/websocket-and-webhooks.md` — файл

### docs/handoffs

- `docs/handoffs/handoff-2026-08-31-1659.md` — файл
- `docs/handoffs/handoff-2026-08-31-1944.md` — файл

## locales

- `locales/en.json` — файл
- `locales/ru.json` — файл

## migrations

- `migrations/alembic/`

### migrations/alembic

- `migrations/alembic/env.py` — Python-модуль
  Классы: нет
  Функции: `run_migrations_offline`, `do_run_migrations`, `run_async_migrations`, `run_migrations_online`
- `migrations/alembic/script.py.mako` — файл
- `migrations/alembic/versions/`

#### migrations/alembic/versions

- `migrations/alembic/versions/0001_initial_schema.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0002_add_campaign_id_to_referral_earnings.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0003_add_partner_system.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0004_add_email_templates.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0005_repair_missing_columns.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0006_add_broadcast_email_columns.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0007_fix_naive_timestamps.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0008_add_required_channels.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0009_add_channel_id_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0010_add_channel_leave_settings.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0011_add_rbac_tables.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0012_add_missing_subscription_columns.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0013_add_desired_commission_percent.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0014_fix_referral_transaction_types.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0015_add_promocode_uses_unique_constraint.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0016_add_ondelete_cascade_to_user_fks.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0017_add_unique_constraint_transaction_external_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0018_add_landing_pages_and_guest_purchases.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0019_yookassa_payment_user_id_nullable.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0020_add_guest_purchases_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0021_landing_localized_texts.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0022_payment_tables_user_id_nullable.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0023_users_promo_group_id_nullable.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0024_guest_purchase_cabinet_password.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0025_guest_purchase_auto_login_token.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0026_tariff_external_squad_uuid.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0027_landing_discount.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0028_landing_discount_constraints.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0029_guest_purchases_composite_stats_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0030_add_background_config_to_landing_pages.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0031_drop_legacy_prize_days_column.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0032_guest_purchase_source_and_buyer.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0033_guest_purchase_gift_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0034_guest_purchase_recipient_warning.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0035_guest_purchase_token_pattern_ops_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0036_add_riopay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0037_add_saved_payment_methods.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0038_add_show_in_gift_to_tariffs.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0039_riopay_user_id_nullable.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0040_add_severpay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0041_add_performance_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0042_add_retry_count_and_payment_recovery_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0043_add_rbac_and_email_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0044_fix_null_payment_method_manual_topups.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0045_add_receipt_uuid_to_guest_purchases.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0046_add_news_articles.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0047_add_cascade_to_subscription_servers.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0048_add_lower_username_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0049_add_news_categories_and_tags.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0050_multi_subscription_foundation.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0051_add_subscription_remnawave_short_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0052_add_promocode_tariff_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0053_include_limited_in_unique_active_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0054_add_broadcast_category.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0055_add_pending_campaign_slug.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0056_create_cabinet_refresh_tokens.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0057_alter_notification_settings_to_jsonb.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0058_create_paypear_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0059_create_rollypay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0060_create_aurapay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0061_add_ticket_media_items.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0062_add_landing_analytics_and_sticky.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0063_add_yandex_client_id_map.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0064_create_overpay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0065_create_info_pages.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0066_add_page_type_to_info_pages.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0067_add_replaces_tab_to_info_pages.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0068_add_apple_transactions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0069_create_etoplatezhi_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0070_create_antilopay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0071_add_last_revoke_at_to_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0072_create_jupiter_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0073_create_donut_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0074_create_lava_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0075_rebuild_apple_iap_ledgers.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0076_unique_apple_web_order_line_item_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0077_ensure_uq_campaign_user.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0078_add_revocation_source_to_user_roles.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0079_add_email_verification_source.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0080_add_traffic_purchases_sub_expires_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0081_drop_redundant_traffic_purchases_subscription_id_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0082_add_open_url_direct_to_payment_method_config.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0083_add_user_device_aliases.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0084_drop_stale_stars_rate_default.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0085_referral_pending_unique.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0086_users_referred_by_paid_index.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0087_add_autopay_period_days_to_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0088_dedupe_tariff_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0089_wheel_spins_telegram_charge_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0090_add_quick_amounts_to_payment_method_configs.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0091_add_info_pages_display_mode.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0092_backfill_vk_yandex_email_verified.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0093_yclid.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0094_payment_method_description.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0095_add_coupons.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0096_add_recurrent_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0097_add_grace_access.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0098_create_cispay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0099_add_platega_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0100_platega_sub_unique_alive.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0101_add_lava_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0102_coupon_max_per_user.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0103_add_legal_consents.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0104_remnawave_numeric_id.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0105_promocode_traffic_gb.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0106_guest_purchase_campaign.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0107_guest_purchase_idempotency.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0108_referral_reward_levels.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0109_referral_level_thresholds.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0110_referral_user_reward_choice.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0111_create_system_error_events.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0112_create_email_queue.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0113_create_tabpay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0114_create_paritypay_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0115_create_reachability_tables.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0116_reachability_batches.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0117_tariff_highlight_period.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0118_tariff_is_highlighted.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0119_tariff_panel_tag_and_trial_days.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0120_subscription_grace_tail_expire_at.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0121_subscription_grace_session_open.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0122_subscription_grace_overlay_expire_at.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0123_user_trial_reset_at.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0124_subscription_panel_identity_backfill.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0125_user_panel_identity_backfill.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0126_withdrawal_request_last_reminder_at.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0127_user_reminders.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0128_dpichecker_actions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0129_broadcast_audience.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0130_create_cashera_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0131_add_cashera_subscriptions.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0132_xrocket_payments.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0133_tariff_lifetime_pricing.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0134_subscription_bypass_suspended.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0135_mass_send_and_decision_log.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0136_pending_panel_expiry.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0137_paid_traffic_reset_intents.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0138_wheel_topup_spins.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0139_wheel_threshold_palette.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0140_platega_sub_fk_set_null.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0141_foreign_key_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0142_hot_path_indexes.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0143_remove_unused_payment_providers.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0144_remove_nalogo_receipt_columns.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0145_replace_heleket_with_2328.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0146_remove_contests_and_polls.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0147_remove_landing_pages.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`
- `migrations/alembic/versions/0148_traffic_cycle.py` — Python-модуль
  Классы: нет
  Функции: `upgrade`, `downgrade`

## scripts

- `scripts/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `scripts/backfill_remnawave_ids.py` — Python-модуль
  Классы: нет
  Функции: `main`
- `scripts/check_release_pr_override.mjs` — файл
- `scripts/generate_structure_reference.py` — Python-модуль
  Классы: нет
  Функции: `tracked_paths` — Файлы проекта: отслеживаемые плюс новые, которые git не игнорирует., `describe_module` — Строки «Классы:» и «Функции:» для модуля., `render_entries`, `render`, `build`, `main`
- `scripts/pg-upgrade.sh` — файл
- `scripts/spofy_ultima_lifetime.py` — Python-модуль
  Классы: нет
  Функции: `main`

## tests

- `tests/cabinet/`
- `tests/ci/`
- `tests/conftest.py` — Python-модуль
  Классы: `TelegramApiBlockedInTests`
  Функции: `fixed_datetime` — Возвращает фиксированную отметку времени для воспроизводимых проверок., `registered_paths` — Карта `путь -> {HTTP-методы}` кабинетного роутера, как их реально, `pytest_pyfunc_call` — Позволяет запускать async def тесты без дополнительных плагинов.
- `tests/contracts/`
- `tests/crud/`
- `tests/database/`
- `tests/external/`
- `tests/fixtures/`
- `tests/handlers/`
- `tests/integration/`
- `tests/live/`
- `tests/middlewares/`
- `tests/migrations/`
- `tests/services/`
- `tests/test_back_buttons_have_handlers.py` — Python-модуль
  Классы: нет
  Функции: `test_no_button_points_to_missing_subscription_callback`, `test_menu_subscription_handler_is_registered`
- `tests/test_backup_pg_client.py` — Python-модуль
  Классы: нет
  Функции: `test_image_ships_pg_client_of_the_server_major`, `test_dump_skips_monitoring_rows_only_without_logs`, `test_restore_is_one_transaction_that_stops_on_error`, `test_restore_reports_psql_failure`
- `tests/test_banner_text_only_screens.py` — Python-модуль
  Классы: нет
  Функции: `test_device_referral_and_payment_screens_have_no_banner`, `test_main_subscription_and_other_screens_keep_the_banner`, `test_amount_and_withdrawal_input_states_have_no_banner`, `test_navigation_from_amount_input_state_keeps_the_banner`, `test_answer_without_banner_sends_plain_text`, `test_editing_a_banner_message_into_a_text_screen_replaces_it`, `test_middleware_sets_the_flag_only_for_the_handler`
- `tests/test_banner_variants.py` — Python-модуль
  Классы: нет
  Функции: `test_variant_for_each_state`, `test_paid_wins_over_trial_and_language_suffix`, `test_unknown_user_or_broken_relation_means_generic_banner`, `banners`, `test_variant_file_is_used_and_cached_by_file_id`, `test_variants_do_not_share_file_ids`, `test_missing_or_broken_variant_falls_back_to_generic_banner`, `test_replacing_the_file_drops_the_cached_file_id`, `test_shipped_banners_are_valid_and_fit_telegram_limits`
- `tests/test_button_icon_pictures.py` — Python-модуль
  Классы: нет
  Функции: `test_one_icon_is_not_shared_by_unrelated_symbols`, `test_colour_statuses_stay_emoji`, `test_most_pressed_buttons_have_icons`, `test_payment_method_buttons_have_icons`, `test_payment_methods_of_one_kind_share_an_icon_and_kinds_differ`, `test_bypass_tariff_button_carries_the_bypass_sign`, `test_check_status_is_not_a_chart`, `test_single_emoji_buttons_are_left_alone`, `test_all_icon_ids_look_like_custom_emoji_ids`
- `tests/test_button_icons_are_uniform.py` — Python-модуль
  Классы: нет
  Функции: `test_locale_has_no_stray_icons`, `test_code_defaults_have_no_stray_icons`
- `tests/test_button_styles.py` — Python-модуль
  Классы: нет
  Функции: `test_subscription_screen_main_actions`, `test_balance_keyboard_topup_success`, `test_devices_management_styles`, `test_referral_secondary_buttons_plain`, `test_one_accent_keeps_only_the_preferred_button`, `test_one_accent_falls_back_to_the_top_button`, `test_subscription_screen_has_one_green_button`
- `tests/test_bypass_sign_in_texts.py` — Python-модуль
  Классы: нет
  Функции: `test_sign_is_the_same_as_on_buttons`, `test_bare_flag_becomes_shield_and_wrapped_one_is_left_alone`, `test_text_caption_media_and_rich_message_get_the_shield`, `test_non_html_messages_and_alerts_are_left_alone`
- `tests/test_classic_trial_remaining_days.py` — Python-модуль
  Классы: `FrozenDateTime` (1 методов), `PurchasePersisted`
  Функции: `test_classic_purchase_persists_expiry_balance_and_conversion`
- `tests/test_compose_postgres_service.py` — Python-модуль
  Классы: нет
  Функции: `test_postgres_18_with_new_volume_at_the_18_mount_point`, `test_guard_is_the_entrypoint_and_sees_the_old_volume_read_only`, `test_compose_files_agree_on_the_postgres_service`, `test_initdb_args_and_healthcheck_preserved`, `guard_env` — Окружение как в контейнере: PGDATA нового кластера, старый том, подставной entrypoint., `test_guard_starts_a_fresh_install`, `test_guard_refuses_empty_18_while_15_data_exists`, `test_guard_starts_after_migration_even_if_old_volume_remains`
- `tests/test_config_languages.py` — Python-модуль
  Классы: нет
  Функции: `test_available_languages_default_is_russian_and_english`, `test_available_languages_normalizes_and_deduplicates`
- `tests/test_copy_effect_stars.py` — Python-модуль
  Классы: нет
  Функции: `test_referral_screen_has_no_copy_button`, `test_stars_invoice_is_a_one_time_charge`, `test_subscription_screen_has_no_copy_link_button`
- `tests/test_declared_dependencies.py` — Python-модуль
  Классы: нет
  Функции: `test_every_imported_package_is_declared` — Прямой импорт — прямая зависимость., `test_dependency_names_are_unique` — Один пакет не должен быть объявлен дважды с разными ограничениями., `test_previously_transitive_imports_stay_declared` — Именно эти пять держались на транзитивности — закрепляем результат.
- `tests/test_device_limit_display.py` — Python-модуль
  Классы: нет
  Функции: `test_absent_limit_renders_as_infinity`, `test_real_limit_renders_as_number`, `test_traffic_and_device_limits_agree_on_unlimited` — Трафик уже показывал безлимит бесконечностью — устройства не должны отставать., `test_zero_used_devices_is_not_confused_with_zero_limit` — Форматтер — только для ЛИМИТА: счётчик использованных нулём и остаётся.
- `tests/test_device_limit_resolution.py` — Python-модуль
  Классы: `DummySubscription` (1 методов), `StubSettings` (4 методов)
  Функции: `test_resolve_hwid_device_limit_disabled_mode`, `test_resolve_hwid_device_limit_enabled_mode`, `test_resolve_hwid_device_limit_enabled_ignores_non_positive`, `test_resolve_hwid_device_limit_for_payload_returns_subscription_limit`, `test_resolve_hwid_device_limit_for_payload_explicitly_removes_limit`, `test_resolve_hwid_device_limit_for_payload_prefers_forced_limit`, `test_resolve_hwid_device_limit_for_payload_handles_zero`, `test_coerce_panel_device_limit_preserves_zero_and_rejects_invalid`, `test_coerce_panel_device_limit_honors_default`, `test_device_limit_needs_heal_preserves_zero`, `test_zero_device_limit_is_not_a_warning` — Ноль = «без ограничения» (HWID выключен) — штатное состояние, не повод для warning.
- `tests/test_entrypoint_imports.py` — Python-модуль
  Классы: нет
  Функции: `test_main_imports_only_existing_app_modules`
- `tests/test_env_isolation.py` — Python-модуль
  Классы: нет
  Функции: `test_settings_do_not_leak_from_dotenv_or_process_env`, `test_real_bot_cannot_reach_telegram`, `test_renewal_admin_notification_is_swallowed_not_sent` — Даже с включёнными уведомлениями и «боевым» токеном сообщение не уходит., `test_guest_purchase_admin_notification_is_swallowed_not_sent`
- `tests/test_expired_sub_tariff_button.py` — Python-модуль
  Классы: нет
  Функции: `test_expired_sub_offers_buy_not_switch`, `test_disabled_sub_offers_buy_not_switch`, `test_active_sub_keeps_change_tariff`, `test_limited_sub_keeps_change_tariff` — 'limited' = traffic exhausted but time remaining (end_date>now) — switch still valid.
- `tests/test_free_tariff_instant_switch.py` — Python-модуль
  Классы: нет
  Функции: `test_keyboard_free_tariff_routes_to_period_switch`, `test_keyboard_free_tariff_keeps_instant_when_reset_disabled` — TARIFF_SWITCH_RESET_FREE_DAYS=false — админ явно разрешил перенос бесплатных, `test_keyboard_paid_tariff_keeps_instant_switch`, `test_instant_list_redirects_free_source`, `test_instant_preview_redirects_free_source` — Устаревшая кнопка instant_sw_preview в старом сообщении не должна, `test_instant_confirm_refuses_free_source_and_never_charges` — Ядро фикса: подтверждение instant-switch с бесплатного тарифа не должно, `test_instant_list_keeps_prorated_flow_for_paid_source` — Платный источник: prorated instant-switch работает как раньше.
- `tests/test_holes_20261109.py` — Python-модуль
  Классы: нет
  Функции: `test_carry_to_pricier_tariff_is_by_value`, `test_carry_to_cheaper_or_equal_tariff_is_day_for_day`, `test_carry_with_broken_rate_is_day_for_day`, `test_buying_pricier_tariff_does_not_carry_days_one_to_one`, `test_buying_cheaper_tariff_keeps_days`, `test_renewing_same_tariff_keeps_days`, `test_bot_refuses_package_switch_on_tariff_and_trial`, `test_gift_carry_keeps_value_downwards`, `test_gift_carry_upwards_and_equal_match_purchase`, `test_gift_carry_never_turns_into_forever`, `test_gift_carry_with_broken_rates_is_day_for_day`, `test_gift_of_cheaper_tariff_keeps_the_value_of_the_rest`, `test_gift_of_pricier_tariff_is_not_day_for_day`, `test_gift_of_the_same_tariff_just_adds_days`, `test_gift_over_a_trial_is_not_recalculated`, `test_gift_carry_failure_falls_back_to_day_for_day`
- `tests/test_lazy_package_exports.py` — Python-модуль
  Классы: нет
  Функции: `test_package_declares_exports`, `test_every_exported_name_resolves`, `test_unknown_name_still_raises` — __getattr__ не должен выдавать что попало вместо AttributeError.
- `tests/test_legacy_subscription_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_legacy_subscription_offers_only_move_to_tariff`, `test_expired_legacy_subscription_still_moves_to_tariff` — Истёкшая старая подписка тоже переводится на тариф той же строкой, а не покупкой с нуля., `test_subscription_with_tariff_keeps_renew_and_autopay`, `test_legacy_subscription_has_no_traffic_topup_even_if_classic_topup_is_on` — Классические настройки докупки трафика к старой подписке не применяются., `test_legacy_subscription_settings_offer_no_classic_addons` — В «Настройках» старой подписки нет трафика и устройств по классическим ценам., `test_classic_subscription_settings_keep_classic_addons` — В классическом режиме подписка без тарифа — обычная, её настройки не трогаем.
- `tests/test_locale_integrity.py` — Python-модуль
  Классы: нет
  Функции: `locales`, `test_all_locales_have_identical_keys`, `test_placeholders_consistent_across_locales` — Every {placeholder} must be identical across languages — the code calls, `test_t_calls_without_default_exist_in_ru` — texts.t('KEY') with NO fallback raises KeyError if the key is absent from ru., `test_t_calls_with_static_default_exist_in_ru` — texts.t('KEY', 'статический дефолт') с ключом вне ru.json отдаёт русский, `test_invite_only_keys_exist_in_every_locale`
- `tests/test_locale_path_safety.py` — Python-модуль
  Классы: нет
  Функции: `test_locale_cannot_read_external_file`, `test_custom_locale_names_remain_supported`, `test_invalid_language_uses_default_locale`, `test_locale_symlink_cannot_escape_to_directory_with_same_prefix`
- `tests/test_log_messages_have_no_empty_placeholders.py` — Python-модуль
  Классы: нет
  Функции: `test_scanner_sees_the_codebase` — Страховка от «тест зеленеет, потому что ничего не нашёл»., `test_no_message_carries_an_empty_placeholder`, `test_scanner_catches_known_shapes` — Образцы из issue #3276 — проверка, что сторож ловит именно их.
- `tests/test_logo_file_id_cache_invalidation.py` — Python-модуль
  Классы: нет
  Функции: `logo`, `test_cached_file_id_is_reused_while_the_file_is_the_same`, `test_replaced_logo_file_drops_the_cached_file_id`
- `tests/test_logo_path_validation.py` — Python-модуль
  Классы: нет
  Функции: `test_valid_file_passes_validation`, `test_directory_fails_validation` — The exact failure mode from #586617 — bind-mount created a dir., `test_missing_path_fails_validation` — File doesn't exist at all — sending would raise FileNotFoundError., `test_validator_logs_actionable_message_for_directory` — The warning must mention the path so the operator can fix it without
- `tests/test_logo_resize.py` — Python-модуль
  Классы: нет
  Функции: `test_small_logo_used_as_is`, `test_oversized_logo_is_resized_under_cap` — A 2000×2000 PNG (~well over _LOGO_MAX_DIMENSION) gets resized., `test_oversized_non_square_logo_keeps_aspect` — 1980×1267 (the literal `vpn_logo.png` shipped in the repo) keeps ratio., `test_cached_resized_copy_is_reused` — Subsequent calls on the same source must hit the cached resized file., `test_missing_pil_falls_back_to_original` — If Pillow chokes on the file for any reason we return the source path —, `test_size_thresholds_are_sane` — Guard against accidental edits that would render the resize a noop., `test_get_logo_media_uses_resized_copy` — End-to-end: get_logo_media() returns FSInputFile pointing at the resized copy.
- `tests/test_main_menu_simplified.py` — Python-модуль
  Классы: нет
  Функции: `test_new_user_has_no_empty_balance_but_has_promocode_and_info`, `test_balance_stays_for_people_with_money_or_paid_history`, `test_active_subscriber_gets_info_alone_and_no_promocode`, `test_active_trial_keeps_connect_and_a_separate_purchase`, `test_inactive_subscription_with_link_keeps_connect_and_purchase`, `test_expired_trial_with_link_does_not_duplicate_purchase`, `test_inactive_subscription_without_link_has_no_dead_connect`, `test_support_is_not_in_main_menu_even_when_enabled`, `test_free_trial_is_activated_in_one_tap`, `test_saved_cart_is_the_first_cta`
- `tests/test_menu_screens_simplified.py` — Python-модуль
  Классы: нет
  Функции: `test_info_menu_holds_support_and_language`, `test_info_menu_keeps_support_in_cabinet_mode`, `test_paid_subscription_screen_has_devices_and_their_count`, `test_devices_count_hidden_when_tariff_cannot_sell_devices`, `test_old_settings_back_button_lands_on_the_subscription_screen` — «Назад» из устройств и перевыпуска ведёт на subscription_settings: на тарифах это экран подписки., `test_support_screen_starts_with_direct_chat`, `test_referral_screen_is_one_button_per_row_and_readable`, `test_main_menu_pairs_fit_a_phone`, `test_trial_user_without_money_can_still_reach_promocode`, `test_paying_subscriber_always_sees_balance_even_at_zero`, `test_devices_screen_offers_link_reissue`
- `tests/test_menu_subscription_status.py` — Python-модуль
  Классы: `DummyTexts` (1 методов)
  Функции: `test_get_subscription_status_marks_trial_as_trial`, `complaint_clock`, `test_almost_two_days_left_is_not_tomorrow`, `test_two_hours_past_local_midnight_is_tomorrow`, `test_later_today_is_today`
- `tests/test_menu_ux_redesign.py` — Python-модуль
  Классы: нет
  Функции: `test_active_sub_single_traffic_button`, `test_expired_sub_single_traffic_button`, `test_secondary_actions_one_per_row`
- `tests/test_no_undefined_names.py` — Python-модуль
  Классы: нет
  Функции: `test_no_new_undefined_names`, `test_baseline_does_not_rot` — Исправленное имя обязано выпадать из базы, иначе она копит ложь.
- `tests/test_payment_hardening.py` — Python-модуль
  Классы: нет
  Функции: `test_header_dump_of_an_exception_is_masked`, `test_platega_and_bearer_headers_and_bot_tokens_are_masked`, `test_plain_text_is_left_alone`, `test_event_dict_masks_strings_and_exceptions_but_keeps_exc_info`, `test_wata_status_is_cached_briefly_unless_final`, `test_wata_cache_expires`
- `tests/test_paysupport_command.py` — Python-модуль
  Классы: нет
  Функции: `test_bypass_only_for_the_flagged_private_handler`, `test_active_user_gets_ticket_buttons_and_contact`, `test_unknown_or_blocked_payer_still_gets_a_contact`, `test_no_contact_and_no_tickets_falls_back_to_support_text`, `test_registered_first_with_the_flag`
- `tests/test_pg_upgrade_log_pipe.py` — Python-модуль
  Классы: нет
  Функции: `test_pg_readiness_large_log`
- `tests/test_pg_upgrade_prompt.py` — Python-модуль
  Классы: нет
  Функции: `sandbox`, `test_y_with_crlf_enter_is_accepted`, `test_russian_da_is_accepted`, `test_no_cancels_without_touching_anything`, `test_without_terminal_requires_yes`
- `tests/test_pricing_engine.py` — Python-модуль
  Классы: `TestApplyDiscount` (6 методов), `TestStackedDiscounts` (5 методов), `TestPeriodDaysValidation` (3 методов), `TestCalculateServersPrice` (8 методов), `TestCalculateTrafficPrice` (5 методов), `TestCalculateRenewalPriceTariffMode` (7 методов), `TestCalculateRenewalPriceClassicMode` (10 методов), `TestServerPromoGroupFiltering` (2 методов), `TestFromPayloadRoundTrip` (1 методов), `TestFromPayloadLegacyRoundTrip` (1 методов), `TestOriginalPriceIdentity` (3 методов)
  Функции: `test_renewal_pricing_is_frozen`
- `tests/test_promo_group_base_discounts.py` — Python-модуль
  Классы: нет
  Функции: `base_discount_settings`, `test_base_promo_discount_applies_to_all_categories`, `test_specific_category_discount_overrides_base`
- `tests/test_readme_payment_providers.py` — Python-модуль
  Классы: нет
  Функции: `test_every_gateway_is_listed_in_readme`, `test_claimed_provider_count_matches_reality` — Число провайдеров в тексте не должно отставать от кода., `test_table_has_no_rows_for_unknown_providers` — Каждая строка таблицы указывает на существующий шлюз.
- `tests/test_redis_client_contract.py` — Python-модуль
  Классы: нет
  Функции: `redis_client_module`, `test_every_injected_kwarg_is_accepted_by_async_connection` — Каждый добавленный аргумент обязан приниматься асинхронным соединением., `test_connection_is_actually_creatable` — Соединение создаётся (не подключается) — ровно там падал TypeError., `test_connect_is_retried` — У подключения есть повторы: разовая заминка на старте не должна быть ошибкой., `test_transient_connect_failure_is_retried` — Первая попытка упала по таймауту — вторая доводит подключение до конца., `test_pool_is_blocking_and_sized_from_settings`, `test_busy_pool_waits_for_a_free_connection_instead_of_failing`
- `tests/test_remnawave_connection_type.py` — Python-модуль
  Классы: нет
  Функции: `test_detect_connection_type`
- `tests/test_rich_menu_pins.py` — Python-модуль
  Классы: нет
  Функции: `test_show_main_menu_tries_rich_before_classic`, `test_back_to_menu_tries_rich_before_classic`, `test_start_menu_sites_guarded_by_rich_helpers`, `test_single_subscription_block_reuses_menu_status_builder`, `test_trial_deeplink_wired_in_start` — Диплинк /start trial: ветка сташит pending_trial, drain — сразу после подарочного
- `tests/test_rubles_to_kopeks.py` — Python-модуль
  Классы: нет
  Функции: `test_rubles_to_kopeks_has_no_float_error`, `test_rubles_to_kopeks_rejects_non_finite_amounts`
- `tests/test_settings_have_consumers.py` — Python-модуль
  Классы: нет
  Функции: `test_removed_fields_are_not_in_settings`, `test_removed_keys_are_not_in_env_example`, `test_old_env_file_with_removed_keys_still_loads` — На проде эти ключи ещё лежат в .env: лишние переменные не должны ронять запуск.
- `tests/test_settings_references.py` — Python-модуль
  Классы: нет
  Функции: `test_every_setting_used_in_code_exists`, `test_every_payment_method_used_in_code_exists`
- `tests/test_sla_defaults_match_env_example.py` — Python-модуль
  Классы: нет
  Функции: `test_code_default_matches_env_example`, `test_sla_is_off_by_default` — Явно: без .env напоминания молчат., `test_withdrawal_reminders_are_off_by_default`
- `tests/test_start_menu_text_consistency.py` — Python-модуль
  Классы: нет
  Функции: `test_start_main_menu_text_delegates_to_menu_builder`, `test_start_no_longer_has_duplicate_status_formatter` — The duplicate formatter that caused the /start-vs-menu divergence is gone.
- `tests/test_structure_reference_is_current.py` — Python-модуль
  Классы: нет
  Функции: `test_document_matches_the_code`, `test_only_tracked_files_are_listed` — Документ не должен зависеть от мусора в рабочей копии., `test_generator_is_deterministic` — Два запуска подряд дают один и тот же текст., `test_payment_mixins_are_documented` — Ровно та дыра, из-за которой всё это затевалось., `test_order_does_not_depend_on_platform_case_folding` — WindowsPath сравнивается без учёта регистра, PosixPath — байтово., `test_local_instructions_do_not_change_checkout_structure` — Local instructions stay local; new source files and committed instructions remain visible.
- `tests/test_subscription_cart_integration.py` — Python-модуль
  Классы: нет
  Функции: `mock_callback_query`, `mock_user`, `mock_db`, `mock_state`, `test_clear_saved_cart` — Тест очистки сохраненной корзины, `test_handle_subscription_cancel_clears_saved_cart` — Отмена покупки должна очищать сохраненную корзину, `test_handle_subscription_cancel_clears_only_current_subscription_cart` — Отмена покупки в мультитарифном сценарии чистит только корзину текущей подписки
- `tests/test_subscription_handlers_registered.py` — Python-модуль
  Классы: нет
  Функции: `test_purchase_flow_handlers_are_registered`
- `tests/test_support_contact_telegram.py` — Python-модуль
  Классы: нет
  Функции: `test_telegram_contacts_detected`, `test_external_contacts_not_telegram`, `test_empty_contact_is_not_telegram`
- `tests/test_sync_bot_username.py` — Python-модуль
  Классы: нет
  Функции: `test_sync_overrides_stale_username`, `test_sync_keeps_config_on_get_me_failure`, `test_sync_noop_when_already_correct`
- `tests/test_tariff_devices_price_note.py` — Python-модуль
  Классы: нет
  Функции: `test_period_keyboard_keeps_the_base_prices`, `test_breakdown_note_mentions_extra_devices_only_when_paid`, `test_period_note_shows_device_count_only_when_above_included`, `test_period_keyboard_shows_the_honest_price_with_extra_devices`, `test_period_keyboard_keeps_base_prices_without_extra_devices`, `test_confirm_and_insufficient_keyboards_offer_the_trim_button`, `test_trim_only_sets_the_flag_and_reopens_the_period_screen` — «Только N устр.» до оплаты НИЧЕГО не урезает: лишние устройства отключает
- `tests/test_tariff_highlight_period.py` — Python-модуль
  Классы: нет
  Функции: `test_highlighted_period_is_marked_in_every_keyboard`, `test_nothing_is_marked_without_a_highlight`, `test_stale_highlight_marks_nothing` — Период удалили, а число осталось: отмечать нечего, но и падать нельзя., `test_prices_stay_visible_next_to_the_badge` — Отметка добавляется к строке, а не вместо неё: цена обязана остаться., `test_resolve_keeps_only_existing_periods`, `test_highlight_survives_price_edit_only_if_the_period_survives` — Правка цен не должна оставлять метку на периоде, которого больше нет., `test_highlight_cannot_point_at_a_missing_period`, `test_highlighted_tariff_is_marked_in_the_list`, `test_tariff_list_survives_objects_without_the_flag` — Старые вызовы передают тарифы без нового поля — список не должен падать., `test_tariff_highlight_is_stored_and_cleared`
- `tests/test_tariff_insufficient_balance_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_prefilled_payment_even_when_autopurchase_disabled`, `test_inlines_prefilled_payment_when_autopurchase_enabled`, `test_classic_topup_when_missing_zero`, `test_no_sbp_purchase_button`, `test_falls_back_to_topup_without_direct_payment_methods`, `test_extend_inlines_prefilled_payment_when_autopurchase_enabled`, `test_extend_prefilled_payment_even_when_autopurchase_disabled`, `test_extend_prefilled_amount_is_missing_not_full_price` — Частичная нехватка: доплата = missing (260), не цена (630) и не баланс (370)., `test_extend_back_stays_generic_without_multi_tariff`, `test_extend_falls_back_to_topup_without_direct_payment_methods` — Фильтр строк оплаты — единственное, что делает зеркалирование безопасным.
- `tests/test_tariff_promo_group_eligibility.py` — Python-модуль
  Классы: нет
  Функции: `test_tariff_promo_group_authorization`, `test_stale_telegram_button_denied_before_checkout`
- `tests/test_text_tidy.py` — Python-модуль
  Классы: нет
  Функции: `test_runs_of_blank_lines_collapse_to_one`, `test_edges_and_trailing_spaces_are_cleaned`, `test_the_devices_screen_from_the_complaint_is_fixed`, `test_text_caption_and_media_caption_are_tidied`, `test_messages_with_entities_are_left_alone` — Кастомные эмодзи задаются смещениями: правка текста их бы сдвинула., `test_no_locale_template_has_more_than_one_blank_line_in_a_row`
- `tests/test_texts_owner_rules.py` — Python-модуль
  Классы: нет
  Функции: `test_outdated_message_text_speaks_of_request_not_panel`, `test_device_cap_text_has_no_word_limit`, `test_texts_of_removed_payment_providers_are_gone`
- `tests/test_ticket_notification_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_admin_gets_full_set_including_user_manage`, `test_moderator_omits_user_manage_but_keeps_actions`, `test_user_manage_uses_db_id_not_telegram_id`, `test_user_manage_hidden_when_no_db_id_even_for_admin`, `test_url_buttons_present_for_username_and_telegram_id`, `test_username_with_at_prefix_is_stripped`, `test_no_username_hides_dm_keeps_profile`, `test_email_user_without_telegram_id_has_no_url_buttons_but_keeps_callbacks`, `test_non_numeric_telegram_id_dropped_from_profile_url`, `test_blocked_user_shows_unblock_not_block_controls`, `test_closed_ticket_hides_reply_and_close`, `test_notification_keyboard_never_has_back_button`, `test_group_keyboard_omits_fsm_buttons_keeps_reliable`, `test_group_keyboard_omits_user_manage`, `test_group_keyboard_blocked_shows_unblock`, `test_group_keyboard_closed_ticket_leaves_only_block_forever`, `service_factory` — Build an AdminNotificationService with patched permission helpers., `test_role_admin`, `test_role_moderator`, `test_role_admin_takes_precedence_over_moderator`, `test_role_outsider_private_chat_is_none`, `test_role_group_or_channel_is_group`, `test_role_zero_chat_id_is_none`, `test_role_none_chat_id_is_none`, `test_role_string_username_chat_is_none`, `test_role_numeric_string_chat_id_is_resolved`, `cabinet_settings` — Configure settings for the cabinet deep-link button., `test_cabinet_button_none_when_not_cabinet_mode`, `test_cabinet_button_private_is_webapp_to_admin_ticket_path`, `test_cabinet_button_private_none_without_custom_url`, `test_cabinet_button_group_is_startapp_deeplink`, `test_cabinet_button_group_none_without_short_name`, `test_cabinet_button_group_none_without_bot_username`, `test_keyboard_places_cabinet_button_on_top`
- `tests/test_topup_amounts_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_format_quick_amount`, `test_keyboard_builds_amount_buttons_within_limits`, `test_keyboard_chunks_amounts_two_per_row`, `test_keyboard_falls_back_to_back_only_on_db_error`, `test_resolve_maps_callback_methods_to_config_ids`, `test_resolve_keeps_direct_config_ids`, `test_keyboard_min_amount_override_raises_lower_bound`
- `tests/test_trial_disabled_menu_gating.py` — Python-модуль
  Классы: нет
  Функции: `test_keyboard_hides_trial_when_duration_zero`, `test_keyboard_hides_trial_when_disabled_for_all`, `test_menu_layout_hides_trial_when_disabled`, `test_show_trial_offer_blocks_when_duration_zero`, `test_activate_trial_blocks_when_duration_zero`
- `tests/test_unlimited_tariff_devices.py` — Python-модуль
  Классы: нет
  Функции: `test_tariff_renewal_device_limit`, `test_unlimited_tariff_does_not_charge_device_addons`, `test_admin_tariff_change_preserves_unlimited`
- `tests/test_user_cart_service.py` — Python-модуль
  Классы: `MockRedis` (6 методов)
  Функции: `mock_redis`, `user_cart_service`, `test_save_user_cart` — Тест сохранения корзины пользователя, `test_get_user_cart` — Тест получения корзины пользователя, `test_get_user_cart_not_found` — Тест получения несуществующей корзины пользователя, `test_delete_user_cart` — Тест удаления корзины пользователя, `test_delete_user_cart_not_found` — Тест удаления несуществующей корзины пользователя, `test_has_user_cart` — Тест проверки наличия корзины пользователя, `test_has_user_cart_not_found` — Тест проверки отсутствия корзины пользователя, `test_save_cart_with_return_to_cart_sets_intent` — return_to_cart=True ставит метку намерения пополнить ради корзины., `test_save_cart_without_return_to_cart_no_intent` — Обычное сохранение корзины (без return_to_cart) метку НЕ ставит., `test_has_topup_intent_is_non_destructive` — Проверка наличия метки не гасит её — частичное пополнение может до-сработать., `test_clear_topup_intent` — clear_topup_intent гасит метку (вызывается после успешной авто-покупки)., `test_delete_user_cart_clears_intent` — Очистка корзины снимает и метку намерения, чтобы она не «висела»., `test_has_topup_intent_false_when_redis_down` — Redis недоступен → намерение считается отсутствующим (не списываем молча)., `test_tariff_checkout_identity_survives_repricing_but_not_new_checkout`
- `tests/test_wheel_fixes.py` — Python-модуль
  Классы: нет
  Функции: `test_spin_rechecks_daily_limit_under_lock` — Even if check_availability passed, spin() must re-count under the lock and, `test_spin_under_limit_proceeds_to_payment` — Sanity: when the re-check is below the limit, spin() proceeds to payment., `test_stars_wheel_spin_idempotent_on_redelivery` — A successful_payment redelivered with the same charge id must NOT grant a
- `tests/test_wheel_menu_button.py` — Python-модуль
  Классы: нет
  Функции: `test_main_menu_has_no_wheel_button`, `test_wheel_off_no_button`, `test_no_spins_plain_button_for_everyone`, `test_spin_shows_green_counter_after_topup_and_before_main_menu`, `test_no_cabinet_url_no_button`, `test_spins_word`, `test_spins_word_in_english`, `test_spins_for_menu_counts_only_when_topup_spins_enabled`, `test_spins_for_menu_never_breaks_the_menu`
- `tests/test_withdrawal_request_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_group_gets_only_actions_and_all_of_them_pass_the_chat_filter`, `test_pending_offers_approve_and_reject_and_approved_offers_complete`, `test_admin_in_private_gets_profile_by_db_id_not_telegram_id`, `test_navigation_only_where_asked`, `test_moderator_and_outsider_get_nothing` — Одобрение — только для админа (@admin_required); модератору кнопки бы отвечали «нет доступа»., `admin_chat`, `test_cabinet_withdrawal_notification_carries_the_same_buttons`, `test_notification_without_request_id_stays_plain`
- `tests/utils/`
- `tests/webserver/`

### tests/cabinet

- `tests/cabinet/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/cabinet/test_admin_create_update_schema_parity.py` — Python-модуль
  Классы: нет
  Функции: `test_schema_pairs_are_discovered` — Пустой список сделал бы сторож ниже бессмысленно зелёным., `test_shared_fields_share_constraints`, `test_create_tariff_accepts_zero_as_no_highlight`, `test_create_tariff_keeps_marked_period`, `test_create_tariff_rejects_negative_highlight`, `test_pinned_message_can_be_media_only`, `test_update_tariff_zero_clears_highlight`, `test_update_tariff_moves_highlight_to_another_period`, `test_update_tariff_without_the_field_keeps_highlight`
- `tests/cabinet/test_admin_delete_user_subscription.py` — Python-модуль
  Классы: нет
  Функции: `test_route_registered` — Метод и путь закреплены: иначе маршрут можно переименовать с зелёным CI., `test_force_defaults_to_off` — Без явного force активную платную подписку снести нельзя., `test_deletes_expired_trial` — Базовый случай из отчёта: отработавший триал убирается из карточки., `test_foreign_subscription_not_found` — Подписка чужого пользователя не удаляется по одному лишь sub_id., `test_active_paid_needs_force` — Оплаченный активный доступ не сносится одним промахом.
- `tests/cabinet/test_admin_email_queue.py` — Python-модуль
  Классы: нет
  Функции: `test_summary_counts_each_status`, `test_items_are_newest_first_and_carry_no_letter_body` — Тело письма — это код или ссылка входа: наружу его не отдаём., `test_clear_removes_the_queue_and_reports_the_count`, `test_clear_pending_only_leaves_history` — «Отменить ожидающие» не должно стирать историю доставленных и потерянных., `test_clear_defaults_to_wiping_everything` — Запрос без параметров чистит очередь целиком — дефолт проверяем по сигнатуре., `test_empty_queue_is_not_an_error`, `test_routes_are_registered`
- `tests/cabinet/test_admin_full_sync_lock.py` — Python-модуль
  Классы: нет
  Функции: `test_full_sync_route_answers_409_while_another_run_is_in_progress`
- `tests/cabinet/test_admin_legal_pages_routes.py` — Python-модуль
  Классы: нет
  Функции: `test_admin_legal_pages_routes_registered`, `test_legal_responses_expose_env_lock_flag`, `test_set_display_mode_commits`, `test_set_display_mode_env_locked_conflict`, `test_set_display_mode_env_locked_same_value_allowed`, `test_require_language_rejects_unknown`
- `tests/cabinet/test_admin_referral_levels_routes.py` — Python-модуль
  Классы: `TestValidation` (3 методов), `TestPartialUpdate` (2 методов), `TestSchemeSwitch` (3 методов), `TestDeletion` (1 методов), `TestTermsEndpointUnderLevels` (3 методов), `TestLegacyImportEndpoint` (2 методов), `TestDepthEndpoint` (3 методов), `TestLevelsModeSetting` (3 методов), `TestLevelsModeEndpoint` (5 методов), `TestLevelsPayloadReportsTheMode` (2 методов), `TestBotAndCabinetAgree` (3 методов)
  Функции: `test_referral_level_routes_registered`, `test_each_url_reaches_its_own_handler` — Наличия пути в списке МАЛО — важно, какой обработчик его получит., `wired`
- `tests/cabinet/test_admin_remnawave_geocheck.py` — Python-модуль
  Классы: нет
  Функции: `patched_service` — Подменяет фабрику сервиса в роутере на заранее собранный дубль., `test_geocheck_routes_are_registered`, `test_geocheck_routes_require_expected_permission`, `test_geocheck_request_rejects_ip_and_interface_together`, `test_geocheck_request_rejects_malformed_ip`, `test_geocheck_request_accepts_ipv4_and_ipv6`, `test_geocheck_request_rejects_malformed_interface`, `test_geocheck_request_accepts_interface_names`, `test_geocheck_request_blank_strings_mean_default_route`, `test_start_geocheck_returns_job_id`, `test_start_geocheck_forwards_selected_route`, `test_start_geocheck_on_old_panel_names_required_version` — 404 = у панели нет такого эндпоинта; админ должен узнать почему, а не «ошибка»., `test_start_geocheck_propagates_panel_error_message`, `test_get_geocheck_maps_running_job`, `test_get_geocheck_maps_completed_result_to_snake_case`, `test_get_geocheck_maps_failed_job`, `test_get_geocheck_unknown_job_is_404`
- `tests/cabinet/test_admin_send_user_message.py` — Python-модуль
  Классы: нет
  Функции: `test_send_message_success`, `test_send_message_email_only_user_rejected` — Email-only юзер → 400 с кодом no_telegram_id, бот не создаётся., `test_send_message_forbidden_maps_to_400_and_closes_session` — Юзер заблокировал бота → 400 с кодом forbidden, сессия бота закрыта., `test_send_message_user_not_found`, `test_send_message_permission_registered` — users:send_message должен существовать в реестре RBAC — иначе
- `tests/cabinet/test_admin_settings_forms_persist.py` — Python-модуль
  Классы: `TestPartnerSettings` (4 методов), `TestTicketSettings` (1 методов)
  Функции: `isolated_settings`, `test_no_cabinet_route_rewrites_dotenv` — Сторож: .env — не хранилище настроек; в контейнере это не тот файл или его нет.
- `tests/cabinet/test_admin_stats_today_local_day.py` — Python-модуль
  Классы: нет
  Функции: `test_recent_payments_today_total_uses_local_day`, `test_dashboard_income_today_comes_from_statistics_not_from_chart` — Дашборд не пересчитывает «сегодня» из графика по строке даты UTC.
- `tests/cabinet/test_admin_subscription_panel_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_admin_subscription_response_preserves_own_panel_identity`
- `tests/cabinet/test_admin_sync_extinguishes_stale_panel_date.py` — Python-модуль
  Классы: нет
  Функции: `test_future_panel_date_of_an_expired_subscription_is_extinguished`, `test_past_panel_date_is_left_alone` — В панели уже прошлое: это настоящая дата окончания, её не трогаем., `test_live_subscription_pushes_its_own_date`, `test_sync_to_panel_endpoint_extinguishes_a_future_panel_date` — Та же кнопка в карточке пользователя — у неё своя копия сборки запроса.
- `tests/cabinet/test_admin_sync_records_panel_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_single_mode_update_records_user_panel_id_on_new_subscription`, `test_single_mode_leaves_row_unlinked_when_another_row_holds_the_id` — Колонка частично уникальна: id у соседней строки — не пишем и не падаем., `test_sync_to_panel_endpoint_records_panel_id_on_selected_subscription`
- `tests/cabinet/test_admin_tariff_change_keeps_extra_devices.py` — Python-модуль
  Классы: нет
  Функции: `no_global_cap`, `test_admin_change_carries_extra_devices`, `test_global_cap_applies_without_tariff_cap`, `test_user_switch_keeps_paid_devices_in_spofy`
- `tests/cabinet/test_admin_tariff_panel_tag.py` — Python-модуль
  Классы: нет
  Функции: `test_create_normalizes_panel_tag_to_upper_case`, `test_create_rejects_tags_the_panel_would_reject`, `test_create_without_tag_stores_null`, `test_update_empty_string_clears_tag_and_missing_field_keeps_it`, `test_list_exposes_panel_tag`, `test_trial_duration_days_round_trips_and_null_means_global`, `test_trial_duration_days_must_be_positive`
- `tests/cabinet/test_admin_traffic_light_rows.py` — Python-модуль
  Классы: нет
  Функции: `test_light_user_map_gives_same_table_as_orm`, `test_light_rows_keep_statuses_and_primary_subscription`, `test_enrichment_and_spending_match_orm`, `test_concurrent_requests_share_one_user_map_load`, `test_waiter_loads_itself_when_shared_load_fails`
- `tests/cabinet/test_admin_traffic_period_days.py` — Python-модуль
  Классы: нет
  Функции: `test_dates_are_read_only_where_they_are_assigned` — Чтение start_dt/end_dt не должно жить вне ветки, которая их задаёт., `test_period_days_is_set_in_every_branch` — Обе ветки разбора дат обязаны задать period_days.
- `tests/cabinet/test_admin_user_activity.py` — Python-модуль
  Классы: нет
  Функции: `test_activity_route_registered`, `test_activity_sources_shape`, `test_activity_dedup_filters_in_sql` — Транзакции, покрытые событиями/начислениями, исключаются на уровне SQL;, `test_activity_unknown_user_404`, `test_activity_unknown_type_400`, `test_activity_merges_and_sorts_desc` — Записи из разных источников сливаются и сортируются по времени убыванию., `test_activity_types_filter_limits_sources`, `test_button_click_sources_split_by_type` — Клики бота и действия кабинета — раздельные источники одной таблицы.
- `tests/cabinet/test_admin_user_detail_subscription_ownership.py` — Python-модуль
  Классы: нет
  Функции: `owned_subscription`, `foreign_subscription`, `ownership_boundary` — Make the authoritative lookup return only the subscription owned by OWNER_ID., `panel_service`, `test_authoritative_subscription_lookup_constrains_id_and_user_id` — Would fail if a route reverted to an id-only subscription lookup., `test_subscription_reads_and_device_delete_accept_owned_subscription` — Every BP-S route uses the selected owned subscription in either mode., `test_subscription_reads_and_device_delete_reject_foreign_and_absent_without_panel_access` — No rejected BP-S request may construct or call the panel client in either mode., `test_panel_info_validates_supplied_subscription_before_unconfigured_service_access` — Would fail if panel-info checks service configuration before ownership., `test_panel_info_does_not_fall_back_to_user_panel_id_for_selected_unlinked_subscription` — Would fail if a selected null-link subscription leaked legacy panel information., `test_selected_actions_pin_sync_to_the_selected_identity_when_legacy_mode_is_enabled` — A supplied subscription id must opt out of all single-tariff fallbacks., `test_selected_sync_uses_only_selected_panel_id_when_legacy_mode_is_enabled` — The helper itself must not substitute the user's legacy panel user id., `test_selected_sync_with_no_panel_link_does_not_substitute_legacy_identity` — A null selected link must cause no panel access, even in legacy mode., `test_selected_devices_return_selected_subscription_device_limit`, `test_subscription_actions_reject_foreign_or_absent_ids_before_mutation` — Would fail if action selection trusted an eagerly loaded subscription list., `test_subscription_actions_accept_an_owned_subscription` — An ownership guard must not reject the requested user's own subscription., `test_selected_reset_returns_unsuccessful_when_panel_deactivation_fails`, `test_selected_reset_without_link_does_not_substitute_legacy_identity`
- `tests/cabinet/test_admin_user_remnawave_resolver.py` — Python-модуль
  Классы: нет
  Функции: `test_resolver_route_is_registered_before_user_id_route`, `test_resolver_requires_users_read_permission`, `test_resolver_returns_the_exact_matching_subscription` — Would fail if the resolver returned a user-level or primary subscription ID., `test_resolver_accepts_a_short_uuid_for_subscriptions_without_a_panel_id` — Would fail if the resolver only understood numeric panel ids., `test_resolver_rejects_unusable_identifiers_without_any_lookup` — Would fail if garbage input were guessed from user data or hit the database., `test_resolver_rejects_an_identifier_present_only_on_the_legacy_user_field` — Would fail if the route reused legacy user-level resolution., `test_resolver_treats_a_physically_absent_deleted_subscription_as_not_found` — Would fail if absent/deleted records were accidentally resolved., `test_resolver_rejects_duplicate_subscription_mappings_as_a_conflict` — Would fail if corrupted mappings silently selected one subscription.
- `tests/cabinet/test_admin_users_list_filters.py` — Python-модуль
  Классы: нет
  Функции: `test_expires_within_days`, `test_active_within_minutes`, `test_has_restrictions`, `test_has_subscription`, `test_no_purchases`, `test_search_matches_email` — Одно поле поиска: адрес целиком и его кусок находят человека через `search`., `test_traffic_used_percent_min` — «Трафик на исходе»: израсходовано от N % лимита, исчерпанные тоже; безлимит и истёкшие — нет., `test_connected_now_matches_any_panel_key` — «Онлайн» = подключён к VPN: id панели у пользователя, у подписки или Telegram ID аккаунта., `test_route_marks_connected_rows_and_filters_online`, `test_route_passes_sort_direction` — Направление сортировки доходит до выборки; без него — привычный порядок ключа., `test_route_refuses_online_filter_without_panel` — Панель молчит — «онлайн» не угадываем и не отдаём всех: честная ошибка, а строки без отметки., `test_filters_combine`, `test_route_declares_new_filters`
- `tests/cabinet/test_admin_users_multi_tariff.py` — Python-модуль
  Классы: нет
  Функции: `test_expired_skips_anyone_who_still_has_a_live_tariff` — «Истекшие» — это кто остался без доступа, а не у кого нашлась старая истёкшая строка., `test_active_still_finds_anyone_with_a_live_tariff`, `test_limited_and_disabled_follow_the_same_rule` — Исчерпанный трафик и отключение — тоже «доступа нет», и тоже только без живых тарифов., `test_expired_tariff_of_a_live_person_still_found_by_tariff_filter` — Отбор по тарифу — про тариф, а не про доступ: истёкшая строка живого человека остаётся видна., `test_row_shows_the_tariff_that_got_the_person_into_the_view` — «Трафик на исходе»: в строке должен быть забитый тариф, а не пустой соседний., `test_row_shows_the_expired_tariff_in_the_expired_view`
- `tests/cabinet/test_app_config_cache.py` — Python-модуль
  Классы: нет
  Функции: `api`, `test_second_request_does_not_call_panel`, `test_user_link_does_not_leak_to_next_request`, `test_stale_config_is_served_when_panel_fails`
- `tests/cabinet/test_audit_log_redaction.py` — Python-модуль
  Классы: нет
  Функции: `test_sensitive_fields_are_redacted_recursively`, `test_secret_setting_value_is_redacted_using_url_key`, `test_non_secret_setting_value_remains_visible`
- `tests/cabinet/test_auto_login_single_use.py` — Python-модуль
  Классы: нет
  Функции: `test_replayed_auto_login_token_is_rejected`
- `tests/cabinet/test_balance_topup_provider_contract.py` — Python-модуль
  Классы: нет
  Функции: `anyio_backend`, `checkout`, `test_lower_schema_bound_does_not_bypass_provider_minimum`, `test_nonpositive_topup_remains_invalid`, `test_unavailable_method_rejected_before_payment_creation`
- `tests/cabinet/test_best_value_reaches_every_showcase.py` — Python-модуль
  Классы: нет
  Функции: `test_gift_config_marks_the_highlighted_period`, `test_gift_config_marks_the_highlighted_tariff`, `test_gift_config_marks_nothing_without_a_highlight` — Без отметки оператора витрина остаётся ровной — как была., `test_every_client_period_model_carries_the_best_value_flag`, `test_admin_only_exceptions_still_exist` — Список исключений не должен гнить: исчезнувшая модель прячет новую слепую., `test_the_guard_actually_sees_the_showcases` — Сторож бесполезен, если ничего не находит: три известные витрины обязаны
- `tests/cabinet/test_branding_animation_ink.py` — Python-модуль
  Классы: нет
  Функции: `test_update_accepts_only_ink_or_none`, `test_stored_legacy_config_is_returned_as_is`, `test_default_is_ink_and_off`
- `tests/cabinet/test_branding_favicon.py` — Python-модуль
  Классы: нет
  Функции: `test_without_logo_returns_png_monogram_of_the_first_letter`, `test_empty_name_falls_back_to_v`, `test_unset_name_uses_build_default`, `test_render_failure_falls_back_to_svg`, `test_monogram_png_is_a_square_raster_with_the_letter_drawn`, `test_corner_ratio_stays_below_the_safari_plate_threshold`, `test_with_logo_serves_a_rounded_tile_with_short_cache`, `test_rounded_tile_is_cached_until_the_logo_file_changes`, `test_svg_logo_is_served_as_is`, `test_unreadable_logo_falls_back_to_the_raw_file`, `test_logo_endpoint_keeps_its_hour_cache`, `test_monogram_escapes_and_uppercases`
- `tests/cabinet/test_branding_flags_and_analytics.py` — Python-модуль
  Классы: нет
  Функции: `store`, `test_flag_setting`, `test_public_flags_keep_their_defaults`, `test_oidc_needs_client_id`, `test_analytics_update_returns_same_shape_as_get`
- `tests/cabinet/test_branding_manifest.py` — Python-модуль
  Классы: нет
  Функции: `test_manifest_uses_branding_name_and_theme_colors`, `test_manifest_icons_are_fetchable_urls_not_data_uris`, `test_light_background_when_dark_theme_is_disabled`, `test_broken_stored_colors_fall_back_to_defaults`, `test_empty_name_uses_build_default`, `test_start_url_accepts_only_a_same_site_path`, `test_icon_version_changes_with_logo_name_and_colors`, `test_logo_icon_is_an_opaque_square_of_the_exact_size`, `test_full_bleed_logo_fills_the_whole_tile_with_its_own_color` — Логотип — сплошная плитка (красный квадрат). На фоне тёмной темы maskable-вариант, `test_full_bleed_logo_with_baked_rounded_corners_gets_its_color_in_the_corners` — Скругление, запечённое в PNG: углы прозрачные, остальной край — цвет логотипа., `test_logo_with_a_varied_edge_keeps_the_theme_background` — Фото или градиент до краёв: единого цвета нет — угадывать нельзя, остаётся фон темы., `test_without_logo_icon_is_a_monogram_on_the_accent`, `test_svg_logo_falls_back_to_monogram`, `test_unreadable_logo_falls_back_to_monogram_with_a_warning`, `test_unsupported_icon_size_is_404`, `test_readable_text_matches_the_cabinet_choice`
- `tests/cabinet/test_broadcast_audience.py` — Python-модуль
  Классы: нет
  Функции: `test_every_existing_dropdown_option_is_available_as_a_condition`, `rule`, `test_rows_are_evaluated_strictly_from_top_to_bottom`, `test_long_mixed_audience_keeps_top_down_results_and_compiles`, `test_not_equal_activity_includes_users_without_activity`, `test_not_equal_tariff_excludes_every_user_with_any_matching_subscription`, `test_email_promo_group_rule_preserves_existing_group_filter`, `test_expiring_preserves_daily_tariff_exclusion`, `test_preview_matches_telegram_and_email_delivery_after_preferences`, `test_send_stores_rules_and_passes_them_to_delivery`, `test_email_send_uses_its_own_audience`, `test_direct_email_user_rule_rejects_unverified_recipient`, `test_preview_rejects_mismatched_field_and_value`, `test_atomic_subscription_conditions_can_match_different_subscriptions`, `test_expired_status_excludes_any_live_subscription_including_trial`, `test_atomic_expiring_includes_live_trials_and_preserves_daily_exclusions`, `test_traffic_thresholds_treat_null_as_zero_for_preview_and_delivery`, `test_traffic_thresholds_dates_and_zero_are_independent`, `test_user_autocomplete_matches_any_part_and_uses_stable_id`, `test_atomic_audience_rejects_invalid_values_and_cross_channel_fields`, `test_preview_without_users_read_shows_count_but_no_people` — У роли Marketer есть broadcasts:*, но нет users:read: размер аудитории — да,, `test_user_search_requires_users_read` — Поиск по части ника/почты выгружает людей из базы — одного права на рассылки мало., `test_unreadable_stored_audience_does_not_break_history`, `test_bot_history_names_cabinet_audience`, `test_all_reaches_deleted_users_but_not_blocked`
- `tests/cabinet/test_broadcast_media_caption_limit.py` — Python-модуль
  Классы: нет
  Функции: `test_markup_does_not_count_towards_caption_limit`, `test_visible_text_over_limit_is_rejected`
- `tests/cabinet/test_broadcast_media_validation.py` — Python-модуль
  Классы: нет
  Функции: `test_send_rejects_media_caption_over_1024`, `test_send_checks_the_caption_that_is_actually_sent` — Если у медиа своя подпись, ограничение относится к ней, а не к message_text., `test_media_file_id_must_look_like_a_telegram_file_id`
- `tests/cabinet/test_cabinet_autopay_update.py` — Python-модуль
  Классы: нет
  Функции: `test_update_autopay_saves_the_flag`, `test_enable_autopay_rejected_for_trial`
- `tests/cabinet/test_daily_price_display.py` — Python-модуль
  Классы: `TestDailyGroupPrice` (3 методов), `TestPurchaseOptionsDailyPrice` (2 методов)
  Функции: нет
- `tests/cabinet/test_deleted_user_revival.py` — Python-модуль
  Классы: нет
  Функции: `db`, `test_dependencies_auto_revives_deleted_user_with_valid_init_data` — REGRESSION: signed initData proving same telegram_id → revive in place., `test_dependencies_rejects_deleted_user_without_init_data` — Without a fresh signature, return structured 403 — never auto-revive., `test_dependencies_rejects_deleted_user_with_mismatched_init_data` — initData proving DIFFERENT telegram_id → cross-account 401, NOT revival., `test_dependencies_blocks_revival_for_blacklisted_deleted_user` — A DELETED + blacklisted row must NOT be revived. Banned stays banned., `test_dependencies_blacklist_runs_before_status_check_for_no_init_data` — REGRESSION: blacklisted+DELETED without initData must still return, `test_dependencies_preserves_blocked_status_with_generic_message` — Status=BLOCKED is an admin action, not inactivity — generic 403., `test_dependencies_active_user_still_passes_through` — Negative-control: ACTIVE user is unaffected by all the new branches., `test_dependencies_auto_revive_persists_via_db_commit` — Pin the caller-owns-commit contract at the dependency boundary., `test_dependencies_rejects_deleted_user_with_invalid_init_data` — initData header present but signature INVALID → falls back to no-proof path., `test_dependencies_deleted_email_only_user_without_telegram_id` — Email-only DELETED user (telegram_id=None) → 403 account_deleted, no AttributeError.
- `tests/cabinet/test_device_addon_prorate.py` — Python-модуль
  Классы: нет
  Функции: `test_device_addon_prorates_to_full_remaining_period` — Device add-on scales with the actual remaining days — no one-month cap., `test_no_upper_cap_long_subscription_costs_more_than_one_month` — A year-long subscription must charge ~12× the monthly rate, not a flat month., `test_short_remainder_is_prorated_down` — 5 days left → pay for ~5 days, not a full month., `test_one_ruble_floor_for_paid_devices` — Tiny prorated amounts floor to 1₽ (100 kopeks)., `test_free_devices_cost_nothing` — Zero chargeable monthly price → free, no floor applied., `test_multi_device_scales_linearly` — N devices = N × per-device prorated price., `test_bot_and_cabinet_formulas_agree` — The bot (calculate_prorated_price) and the cabinet inline math must match.
- `tests/cabinet/test_device_info_reason_codes.py` — Python-модуль
  Классы: `TestReductionInfo` (3 методов), `TestDevicePrice` (4 методов)
  Функции: `multi_tariff`, `test_every_unavailable_answer_carries_a_code` — Сторож: новый отказ без кода снова покажет человеку фразу на чужом языке.
- `tests/cabinet/test_device_ownership.py` — Python-модуль
  Классы: нет
  Функции: `test_collect_panel_user_ids_deduplicates_and_preserves_order` — user.remnawave_id first, then unique subscription ids in declared order., `test_collect_panel_user_ids_handles_classic_mode_user_only` — Classic mode: only user.remnawave_id, no subscriptions array., `test_collect_panel_user_ids_handles_multi_tariff_no_top_id` — Multi-tariff: top-level user.remnawave_id often None, sub ids only., `test_collect_panel_user_ids_returns_empty_when_no_panel_attached`, `test_collect_panel_user_ids_ignores_legacy_uuid_column` — Только remnawave_id: юзер с одними легаси-UUID панели не привязан., `test_verify_finds_hwid_on_first_panel`, `test_verify_finds_hwid_on_non_primary_subscription_panel` — REGRESSION: multi-tariff user with device on sub-B's panel user must pass., `test_verify_returns_false_when_hwid_on_no_panel`, `test_verify_short_circuits_after_first_hit` — We stop iterating panels as soon as we find the device — fewer remote calls., `test_verify_degrades_open_on_remnawave_failure` — Degrade-open contract: panel unreachable → True so renames don't break., `test_verify_does_not_degrade_open_on_unusable_panel_id` — Битая ссылка в НАШЕЙ БД — не сбой панели: такой id пропускается, проверка закрыта., `test_verify_skips_unusable_id_but_still_checks_remaining_panels` — Один непригодный id не должен обрывать обход остальных панелей юзера., `test_verify_returns_false_when_user_has_no_panel_id` — No panel id on user or any subscription → False (nothing to validate against).
- `tests/cabinet/test_email_auth_gate.py` — Python-модуль
  Классы: `Reached`
  Функции: `test_db_row_overrides_env`, `test_env_applies_when_no_db_row`, `test_require_raises_403_with_machine_code`, `test_handler_refuses_before_touching_anything`, `test_handler_proceeds_when_enabled`, `test_every_email_and_password_route_is_gated` — Новый /email/* или /password/* роут без гейта — красный тест, а не дыра в проде., `test_linked_providers_follow_the_same_switch` — Список способов входа в профиле читает тот же переключатель, что UI и роуты., `test_db_value_parsed_like_settings_editor` — Строку пишут и админский переключатель ('true'), и общий редактор настроек, и, `test_garbage_db_value_falls_back_to_env`
- `tests/cabinet/test_email_auth_gate_http.py` — Python-модуль
  Классы: нет
  Функции: `test_disabled_in_admin_refuses_register_and_login_over_http` — Админ выключил email-вход в кабинете (строка в БД), окружение говорит «включён»:, `test_enabled_in_admin_lets_request_through_the_gate` — Обратная сторона: строка 'true' в БД при выключенном окружении — запрос проходит гейт, `test_db_disabled_blocks_all_email_routes_without_mutations_or_tokens` — Прямой HTTP-вызов, включая OTP, не обходит DB-запрет при включённом env., `test_public_email_config_matches_db_override_over_http` — TG-079: the login page sees the effective toggle, not SMTP/env alone.
- `tests/cabinet/test_email_broadcast_scoped_targets.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_scoped_targets`, `test_promo_group_target_counts_and_fetches_the_same_people`, `test_single_user_target_reaches_exactly_that_user`, `test_send_rejects_targets_nobody_can_receive`, `test_email_filters_list_promo_groups_with_counts`, `test_multi_tariff_user_gets_one_email_not_one_per_subscription` — Мультитариф: JOIN по подпискам размножал человека — письмо уходило по разу на подписку.
- `tests/cabinet/test_email_change_otp_security.py` — Python-модуль
  Классы: нет
  Функции: `test_verify_blocked_and_code_not_checked_when_ip_rate_limited`, `test_verify_per_account_cap_burns_pending_change`, `test_request_change_rejects_unowned_admin_email`, `test_verify_and_apply_rejects_wrong_code_and_applies_correct`
- `tests/cabinet/test_email_from_header.py` — Python-модуль
  Классы: нет
  Функции: `test_non_ascii_from_name_keeps_single_valid_address`, `test_ascii_from_name_unaffected`
- `tests/cabinet/test_email_layout.py` — Python-модуль
  Классы: нет
  Функции: `test_default_layout_is_the_previous_wrapper` — Без сохранённой обёртки письма выглядят ровно как раньше., `test_default_layout_contains_every_placeholder_the_editor_offers`, `test_custom_layout_applies_to_default_templates`, `test_custom_layout_falls_back_to_ru_for_other_languages`, `test_custom_layout_applies_to_editor_fragments_but_not_full_documents`, `test_layout_without_content_slot_is_ignored` — Обёртка без {content} проглотила бы тело каждого письма — её не берём., `test_render_keeps_content_raw_and_escapes_text_values`, `test_layout_can_use_bare_unsubscribe_url_for_its_own_link_text` — Свой текст отписки вместо готового блока: {unsubscribe_url} доступен в обёртке., `test_layout_sees_recipient_vars_from_default_and_override_paths` — {username}/{email} доступны в обёртке — рендер письма отдаёт ей получателя., `test_override_fragment_keeps_unsubscribe_link` — Маркетинговый override третьего уровня раньше терял ссылку отписки в подвале., `test_cache_is_stale_until_loaded_and_fresh_after`, `test_rendered_override_refreshes_layout_cache_first` — Каждая отправка проходит через get_rendered_override — там и подтягивается обёртка., `test_refresh_survives_database_errors` — Недоступная база — это «обёртки нет», а не потерянное письмо., `test_editor_lists_layout_first_with_placeholders_intact`, `test_layout_preview_puts_sample_letter_inside_custom_layout`, `test_saving_layout_without_content_slot_is_rejected`, `test_saving_layout_refreshes_cache_and_uses_fixed_subject`
- `tests/cabinet/test_email_login_deleted_oracle.py` — Python-модуль
  Классы: нет
  Функции: `test_email_login_does_not_return_account_deleted_code` — REGRESSION: /email/login must not expose `code: account_deleted`., `test_email_login_returns_generic_401_for_deleted_users` — The DELETED branch in /email/login must raise 401 with 'Invalid email or password'., `test_email_login_status_check_runs_before_email_verification_gate` — REGRESSION: status check must come before the email-verification gate.
- `tests/cabinet/test_email_merge_otp_flow.py` — Python-модуль
  Классы: нет
  Функции: `test_email_conflict_sends_code_not_token` — Knowing the victim's email mails a code to THEM — no merge token is issued., `test_verify_wrong_code_rejected`, `test_verify_correct_code_issues_token`, `test_execute_rejects_non_initiator` — A leaked token can't be executed by anyone but the authenticated initiator.
- `tests/cabinet/test_email_plaintext_conversion.py` — Python-модуль
  Классы: нет
  Функции: `test_style_block_content_is_stripped`, `test_script_block_content_is_stripped`, `test_style_block_stripped_case_insensitive_and_multiline`, `test_entities_unescaped_amp_last`, `test_blank_line_runs_are_collapsed`, `test_real_default_template_produces_clean_plain_text` — Регрессия на живом шаблоне: дефолтное письмо верификации собирается на, `test_unclosed_style_block_does_not_leak_css` — Битый шаблон (частый случай для кастомных писем из админки): открытый, `test_send_email_plain_part_is_clean` — End-to-end: send_email должен положить в text/plain часть очищенный текст,
- `tests/cabinet/test_email_redesign.py` — Python-модуль
  Классы: нет
  Функции: `test_actionable_email_has_deep_link_button`, `test_no_placeholder_or_python_artifacts_left`, `test_auth_emails_have_button_and_plain_link`, `test_email_change_code_puts_code_in_subject_and_big_block`, `test_expiring_subject_uses_russian_plural`, `test_known_subscription_links_straight_to_its_renew_screen`, `test_inliner_styles_default_layout_once_and_skips_foreign_documents`, `test_inliner_keeps_explicit_styles_last`, `test_plain_text_keeps_button_link_and_drops_preheader`, `test_payment_reminder_uses_shared_layout`
- `tests/cabinet/test_email_registration_throttle.py` — Python-модуль
  Классы: нет
  Функции: `test_windows_come_from_settings_and_are_checked_in_order`, `test_tripped_slow_window_returns_429_with_its_retry_after`, `test_zero_disables_a_window`, `test_standalone_registration_uses_the_throttle` — Боевой обработчик зовёт общий дроссель, а не свой минутный лимит.
- `tests/cabinet/test_email_rendering_integrity.py` — Python-модуль
  Классы: нет
  Функции: `test_default_template_renders_clean_for_every_language`, `captured_send` — Перехватывает send_email и притворяется, что SMTP настроен., `test_verification_email_uses_unified_template`, `test_password_reset_email_uses_unified_template`, `test_email_change_code_uses_unified_template`, `test_custom_override_bypasses_default_rendering`, `test_wrap_full_document_is_not_double_wrapped`, `test_wrap_fragment_gets_base_template_once`, `test_wrap_styled_fragment_gets_minimal_wrapper`, `test_editor_default_roundtrips_through_override_render` — Сохранение дефолта из редактора как override не ломает письмо.
- `tests/cabinet/test_email_reply_to.py` — Python-модуль
  Классы: нет
  Функции: `smtp_ready`, `test_reply_to_is_set_when_configured` — Настроенный адрес попадает в Reply-To, From остаётся прежним., `test_no_reply_to_header_by_default` — Пустая настройка — поведение как раньше, лишнего заголовка нет., `test_broken_reply_to_is_dropped` — Мусор из .env не должен ни ломать письмо, ни дописывать чужой заголовок., `test_reply_to_is_trimmed` — Пробелы вокруг адреса обязаны срезаться до сборки заголовка.
- `tests/cabinet/test_email_send_failures.py` — Python-модуль
  Классы: `TestUnreachableServer` (4 методов), `TestServerRefusal` (3 методов), `TestUnexpectedErrors` (1 методов)
  Функции: `service`
- `tests/cabinet/test_email_template_editor.py` — Python-модуль
  Классы: нет
  Функции: `test_editor_exposes_every_email_template_type` — Жалоба из «Багов»: письма уходят, а поменять их шаблон нельзя., `test_every_template_type_has_sample_context_for_all_vars`, `test_default_template_renders_for_editor` — Каждый тип из списка редактора должен иметь рабочий дефолтный шаблон., `test_editor_payload_keeps_placeholders_not_sample_values` — Редактор получает {placeholder}-токены, а не подставленные примеры., `test_verification_template_placeholder_survives_roundtrip` — Сценарий бага: сохранить дефолтный шаблон как override и отправить письмо., `test_substitute_escapes_html_in_body`, `test_substitute_subject_strips_newlines_without_escaping`, `test_substitute_none_value_becomes_empty`, `test_override_without_required_var_falls_back_to_default` — Сломанный override (без {verification_url}) отбрасывается → дефолт., `test_override_with_required_var_is_used`, `test_required_var_with_empty_value_does_not_reject_override` — Пустое значение переменной не должно отбрасывать override., `test_preview_substitutes_sample_values_into_custom_body`, `test_preview_substitutes_common_vars_into_custom_body` — Общие переменные ({cabinet_url}, {service_name}) работают в любом шаблоне., `test_override_render_injects_common_vars` — Боевой рендер override подставляет общие переменные без участия вызывающего кода., `test_common_vars_exposed_to_editor` — Редактор получает список общих переменных для всех типов., `test_recipient_common_vars_never_leak_as_literals` — Даже если отправитель не передал username/email — литерал {username} не уходит в письмо., `test_preview_default_template_uses_sample_values`, `test_saving_template_without_required_placeholder_is_rejected_with_clear_error` — Раньше такой override молча подменялся стандартным письмом при отправке —, `test_saving_template_with_required_placeholder_passes`, `test_legacy_placeholder_names_resolve_in_sample_context` — 7 марта редактор переименовал переменные; шаблоны на старых именах должны жить., `test_override_with_legacy_placeholder_renders_value` — Шаблон пользователя с {new_end_date} — в письме дата, а не литерал., `test_saving_template_with_unknown_placeholder_is_rejected`, `test_saving_template_with_legacy_placeholder_is_allowed`
- `tests/cabinet/test_email_type_switch.py` — Python-модуль
  Классы: нет
  Функции: `test_disabled_setting_switches_types_off`, `test_always_on_types_ignore_the_setting`, `test_set_enabled_writes_setting_through_configuration_service`, `test_endpoint_refuses_to_disable_always_on_types`, `test_promo_email_is_skipped_when_disabled`, `test_switch_module_is_free_of_side_effects_on_import`, `test_delivery_service_skips_disabled_type` — Основной путь уведомлений: отключённый тип не уходит, включённый — уходит.
- `tests/cabinet/test_email_unsubscribe.py` — Python-модуль
  Классы: нет
  Функции: `smtp_ready` — Делает email_service «настроенным» и подменяет SMTP-соединение., `test_token_roundtrip` — Свежий токен опознаётся: отдаёт user_id и категорию., `test_token_email_is_case_insensitive` — Регистр адреса не должен ломать ссылку из письма., `test_token_rejects_tampering` — Подменённый user_id не проходит проверку подписи., `test_token_dies_with_old_email` — Смена адреса обесценивает старые ссылки — токен привязан к email., `test_parse_token_survives_garbage` — Мусор в query-параметре не должен ронять публичный эндпоинт., `test_build_url_empty_when_disabled` — Выключенная отписка не должна протаскивать битую ссылку в письмо., `test_build_url_uses_cabinet_url_by_default` — Без явного EMAIL_UNSUBSCRIBE_BASE_URL берём публичный путь кабинета., `test_send_email_adds_one_click_headers` — List-Unsubscribe + One-Click — то, из чего Gmail рисует свою кнопку., `test_transactional_email_has_no_unsubscribe_headers` — Письмо со сбросом пароля не должно предлагать отписку., `test_unsubscribe_url_is_header_injection_safe` — Перенос строки в URL не должен дописать чужой заголовок., `test_base_template_renders_footer_link` — Ссылка в футере — для клиентов, которые не рисуют кнопку из заголовка., `test_base_template_without_url_has_no_dangling_footer` — У транзакционных писем футер остаётся прежним., `test_common_context_exposes_unsubscribe_placeholder` — {unsubscribe_url} обязан резолвиться, иначе он утечёт в письмо литералом., `test_email_broadcast_filters_by_category` — Тумблеры кабинета обязаны резать email-рассылку так же, как Telegram., `test_get_does_not_unsubscribe` — GET по ссылке не должен ничего менять., `test_post_applies_and_answers_html_to_browser` — POST из формы: отписка применяется, браузеру отдаём страницу результата., `test_post_answers_bare_200_to_mail_client` — One-click от Gmail: пустой 200, без HTML., `test_parse_token_rejects_ids_outside_int4` — Публичный эндпоинт не должен падать на подобранном id., `test_mailto_with_crlf_is_dropped` — mailto уходит в тот же заголовок — перенос строки дописал бы свой., `test_marketing_email_blocked_after_unsubscribe` — Отписавшийся не должен получать промо и winback — ради этого всё и делалось., `test_marketing_email_carries_unsubscribe_url` — У маркетингового письма ссылка отписки обязана быть., `test_transactional_email_has_no_unsubscribe` — Транзакционному письму ссылка отписки не положена., `test_email_broadcast_path_applies_category_filter` — Проверяем не хелпер, а то, что путь рассылки его ЗОВЁТ., `test_signature_is_compared_in_constant_time` — Сравнение подписи — только hmac.compare_digest.
- `tests/cabinet/test_free_tariff_purchase.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `test_free_tariff_can_be_purchased` — Настроенная нулевая цена — законная покупка, а не ошибка конфигурации., `test_unlimited_tariff_clears_old_device_cap_without_addon_charge`, `test_unlimited_tariff_checkout_on_postgres`, `test_unpriced_period_is_still_rejected` — Цена периода не проставлена (None) — это как раз неверная настройка., `test_unknown_period_is_still_rejected` — Период, которого у тарифа нет, отклоняется как и раньше., `test_free_tariff_renewal_option_is_offered` — Бесплатный период должен быть в списке продления, а не пропадать из него., `test_free_tariff_renewal_goes_through` — Продление бесплатного тарифа не должно падать «неверным периодом»., `test_unpriced_renewal_period_is_still_dropped` — Непроставленная цена периода — по-прежнему не предлагаем продление.
- `tests/cabinet/test_gift_routes.py` — Python-модуль
  Классы: нет
  Функции: `bypass_rate_limit` — Disable rate limiting for route tests., `test_branding_gift_enabled_routes` — get_gift_enabled and update_gift_enabled in branding read/write the shared setting., `test_gift_config_when_disabled` — When gift feature is disabled, /gift/config returns is_enabled=False and user balance., `test_gift_config_filters_tariffs_and_orders` — Only active tariffs with show_in_gift=True are returned, ordered by display_order then id., `test_gift_config_personalized_quote_fields` — Personalized discounts (promo group & active promo offer) populate quote fields., `test_purchase_gift_balance_success` — Balance checkout creates a paid GuestPurchase with cabinet idempotency and debits balance., `test_purchase_gift_balance_directed_and_notification` — Directed gift persists recipient details and invokes claim notification., `test_purchase_gift_balance_insufficient_balance` — When balance is insufficient, raises 400 Insufficient balance., `test_purchase_gift_restricted_user` — Restricted buyer receives 403 Forbidden., `test_purchase_gift_disabled_feature` — When gift feature is disabled, purchase raises 400 Gift feature is not enabled., `test_purchase_gift_tariff_not_found_or_inactive` — Inactive or non-gift tariffs raise 404 Tariff not found or inactive., `test_purchase_gift_invalid_period` — Requesting unconfigured period raises 400 Price is not configured for this period., `test_purchase_gift_self_gift_prevention` — Self-gifting by username or email raises 400 Cannot gift to yourself., `test_purchase_gift_telegram_unresolvable_warning` — When a recipient telegram username is not in DB and unresolvable via Bot API, warning is returned., `test_purchase_gift_balance_returns_canonical_fields` — Balance gift purchase returns additive canonical gift_code, bot_claim_url, cabinet_claim_url., `test_get_gift_purchase_status_pending_has_no_claim_fields` — Pending purchase status returns is_claimable=False and no claim credentials., `test_get_gift_purchase_status_paid_code_only` — Paid code-only gift status returns canonical code and links with legacy 12-char token., `test_get_gift_purchase_status_directed_gift` — Directed gift status populates recipient value and claim artifacts for the buyer., `test_get_gift_purchase_status_delivered_has_no_claim_actions` — Delivered gift retains metadata but exposes no reusable claim actions/links., `test_get_gift_purchase_status_uniform_404_for_non_buyer` — Querying another buyer's purchase token raises 404 to avoid token existence oracle., `test_get_gift_purchase_status_absent_bot_or_cabinet_config` — When bot username or cabinet URL is not configured, canonical code is still returned and missing URLs are None., `test_get_sent_gifts_contract_and_channel_parity` — get_sent_gifts returns canonical claim fields for claimable gifts and omits them for delivered gifts., `test_get_sent_gifts_includes_bot_origin_gifts` — Gifts purchased via Telegram bot appear in cabinet /gift/sent with canonical claim artifacts., `test_landing_purchase_status_canonical_fields_parity` — _build_purchase_status_response in landing routes includes additive canonical fields., `test_historical_gifts_derive_canonical_codes_without_migration` — Historical gift rows in DB seamlessly derive canonical GIFT_<59> public codes without migration., `test_activate_gift_backward_compatibility_short_codes_and_canonical` — Cabinet /gift/activate endpoint accepts 8-char, 12-char, GIFT- prefix, canonical GIFT_, and full URLs., `test_get_gift_purchase_status_empty_token_prefix_returns_404` — Passing empty or prefix-only token like 'GIFT_' returns 404 even if user owns purchases., `test_purchase_gift_gateway_success` — Gateway mode creates a payment via PaymentService and does not debit user balance., `test_purchase_gift_gateway_provider_error` — When payment provider returns None, raises 502 Bad Gateway., `test_purchase_gift_gateway_invalid_response` — When payment provider returns no payment_url, raises 502 Bad Gateway., `test_purchase_gift_gateway_consumes_one_time_promo_offer` — P1 Gateway Discount: personal one-time promo discount is applied and consumed on successful payment creation., `test_purchase_gift_gateway_provider_error_rolls_back_promo_offer` — P1 Gateway Discount: provider failure or exception cleanly rolls back promo offer consumption., `test_purchase_gift_gateway_internal_adapter_commit_is_deferred_until_url_validation` — An adapter commit must not persist promo consumption before the route validates its result., `test_purchase_gift_gateway_concurrent_requests_apply_promo_at_most_once` — P1 Gateway Concurrency: when 2 gateway requests run with 1 personal discount,, `test_purchase_gift_gateway_pending_has_no_claim_fields` — Gateway gift purchase returns null claim fields while in pending state.
- `tests/cabinet/test_happ_crypto_button_urls.py` — Python-модуль
  Классы: `TestCabinetResolveButtonUrl` (4 методов), `TestBotResolveButtonUrl` (2 методов), `TestCreateDeepLink` (4 методов), `TestBotCreateDeepLink` (2 методов)
  Функции: нет
- `tests/cabinet/test_incy_crypt_button_urls.py` — Python-модуль
  Классы: `TestCabinetButtons` (3 методов), `TestBotButtons` (3 методов)
  Функции: `decrypted_url`, `incy_enabled`
- `tests/cabinet/test_info_display_mode_gating.py` — Python-модуль
  Классы: нет
  Функции: `test_visibility_defaults_all_true`, `test_visibility_hides_bot_only_sections`, `test_rules_endpoint_404_when_bot_only`, `test_privacy_endpoint_404_when_bot_only`, `test_offer_endpoint_404_when_bot_only`, `test_faq_list_empty_when_bot_only`
- `tests/cabinet/test_info_documents_language_fallback.py` — Python-модуль
  Классы: нет
  Функции: `test_empty_row_falls_back_to_default_language` — Пустая строка на zh (или одни пробелы) не должна подменять собой документ на ru., `test_filled_document_is_returned_as_is` — Заполненный документ на запрошенном языке не трогается., `test_no_text_anywhere_keeps_stub` — Нет текста и на языке по умолчанию — прежнее поведение, встроенная заглушка., `test_rules_without_language_row_use_default_language` — Правил на zh нет — берутся правила ru, а не встроенный текст., `test_rules_with_empty_language_row_use_default_language` — Пустая строка на zh — как и у остальных документов, откат на ru, а не пустой экран., `test_rules_in_requested_language_are_kept`, `test_rules_fall_back_to_built_in_stub_when_nothing_is_filled`
- `tests/cabinet/test_invite_only_auth.py` — Python-модуль
  Классы: нет
  Функции: `test_http_mapping_distinguishes_policy_and_infrastructure_errors`, `test_public_adapter_short_circuits_when_invite_only_is_disabled`, `test_cabinet_gate_forwards_verified_admin_identity`, `test_every_signed_telegram_arm_revives_its_own_deleted_account` — initData, widget and OIDC all prove the same identity, so all three must revive., `test_non_deleted_inactive_account_without_admin_proof_is_refused`
- `tests/cabinet/test_invite_only_landing.py` — Python-модуль
  Классы: нет
  Функции: `test_find_guest_purchase_user_is_non_mutating_for_existing_email_user`, `test_landing_access_uses_existing_user_and_requested_channel`, `test_web_gift_claim_denies_missing_user_before_account_mutation`, `test_bot_gift_claim_link_uses_safe_prefix_threshold`, `test_paid_fulfillment_rechecks_access_before_find_or_create`, `test_paid_gift_fulfillment_never_creates_recipient_user`
- `tests/cabinet/test_invite_only_oauth.py` — Python-модуль
  Классы: нет
  Функции: `test_current_oauth_provider_must_be_trusted_for_admin_email_recovery`
- `tests/cabinet/test_landing_activate_endpoint.py` — Python-модуль
  Классы: нет
  Функции: `open_gate` — Пропускаем рейт-лимит и определение IP — проверяется не они., `test_activation_reaches_the_service`, `test_service_error_becomes_its_own_http_status` — Отказ сервиса должен доезжать до клиента своим кодом, а не пятисоткой.
- `tests/cabinet/test_linked_providers_forgets_email.py` — Python-модуль
  Классы: нет
  Функции: `test_google_row_names_the_email_that_unlinking_forgets`, `test_nothing_is_forgotten_once_a_password_exists`, `test_email_verified_elsewhere_is_not_tied_to_the_provider`
- `tests/cabinet/test_login_limit_and_pool_503.py` — Python-модуль
  Классы: нет
  Функции: `test_valid_signature_is_not_limited_by_shared_ip`, `test_invalid_signature_is_limited_by_ip`, `test_invalid_signature_over_limit_gets_429`
- `tests/cabinet/test_media_token_security.py` — Python-модуль
  Классы: нет
  Функции: `test_token_roundtrip`, `test_token_is_bound_to_file_id`, `test_token_rejects_tampered_and_garbage`, `test_token_rejects_expired`, `test_download_rejects_missing_token`, `test_token_lifetime_can_be_shortened`, `test_signed_media_url_is_https_behind_proxy`
- `tests/cabinet/test_media_upload_topic.py` — Python-модуль
  Классы: нет
  Функции: `test_upload_staging_respects_notification_destination`
- `tests/cabinet/test_media_xss_hardening.py` — Python-модуль
  Классы: нет
  Функции: `test_raster_images_served_inline_with_their_type`, `test_non_raster_forced_to_download_as_octet_stream`, `test_html_is_never_text_html`, `test_svg_is_never_image_svg_xml`, `test_hardening_headers_always_present`, `test_filename_sanitized_against_header_injection`, `test_empty_filename_falls_back`, `test_blocked_upload_lists_cover_active_content`
- `tests/cabinet/test_my_avatar.py` — Python-модуль
  Классы: нет
  Функции: `test_picks_the_smallest_size_that_is_still_sharp`, `test_falls_back_to_the_largest_when_all_are_small`, `test_no_photos_means_no_avatar`, `test_file_id_is_cached_including_the_absence_of_a_photo`, `test_telegram_error_does_not_break_the_cabinet`, `test_route_returns_signed_media_url`, `test_route_without_telegram_account_returns_nothing`
- `tests/cabinet/test_new_ticket_message.py` — Python-модуль
  Классы: нет
  Функции: `test_text_only_has_no_media`, `test_legacy_single_media_fields`, `test_media_items_win_and_first_becomes_primary`
- `tests/cabinet/test_oauth_email_merge_revival.py` — Python-модуль
  Классы: нет
  Функции: `db`, `test_email_merge_revives_deleted_user_when_both_verified` — REGRESSION: with BOTH IdP and local row email_verified, a DELETED row gets revived., `test_email_merge_blocks_409_when_local_email_unverified` — SECURITY: local row with email_verified=False must NOT be merged., `test_email_merge_active_user_links_without_revive` — An ACTIVE local user found by email gets the provider linked, NOT revived.
- `tests/cabinet/test_oauth_link_conflict.py` — Python-модуль
  Классы: нет
  Функции: `test_identity_on_another_account_offers_merge_instead_of_dead_end` — Соцсеть на аккаунте #2 -> токен слияния #1 <- #2; сама привязка не делается., `test_relinking_over_occupied_slot_is_refused_not_overwritten` — User already has a *different* Google linked -> 409, old one preserved., `test_same_identity_is_idempotent_no_op` — Re-linking the identity already on this account is a harmless no-op.
- `tests/cabinet/test_oauth_link_email_backfill.py` — Python-модуль
  Классы: нет
  Функции: `test_backfills_verified_email_when_user_has_none`, `test_does_not_overwrite_existing_email`, `test_skips_backfill_when_email_owned_by_another_account_but_still_links`, `test_does_not_backfill_unverified_provider_email`
- `tests/cabinet/test_oauth_redirect_uri_per_origin.py` — Python-модуль
  Классы: нет
  Функции: `origins`, `test_allowed_mirror_returns_to_itself` — Разрешённое зеркало завершает OAuth на своём же домене., `test_trailing_slash_matches_on_both_sides` — Слэш в конце — у заголовка или в настройке — не должен ломать совпадение., `test_unknown_origin_falls_back_to_canonical` — Чужой Origin не должен получать authorization code., `test_lookalike_origin_is_not_accepted` — Совпадение точное: домен-двойник с суффиксом не проходит., `test_missing_origin_falls_back_to_canonical` — Запрос без Origin — прежнее поведение канонического домена., `test_canonical_origin_allowed_even_without_the_list` — Свой домен работает, даже если список разрешённых пуст., `test_wildcard_in_the_list_does_not_open_everything` — CABINET_ALLOWED_ORIGINS='*' не должен пускать произвольный домен., `test_authorize_stores_redirect_uri_in_state_and_keeps_it_out_of_the_url` — Выбранный адрес возврата уезжает в state, но не в ссылку авторизации., `test_authorize_from_unknown_origin_stores_canonical` — С чужого домена в state попадает канонический адрес, а не присланный., `test_linking_init_uses_the_request_origin` — Привязка провайдера с зеркала тоже возвращается на зеркало., `test_linking_exchange_reuses_the_redirect_uri_from_state` — Обмен кода при привязке идёт с тем же адресом, что и на init.
- `tests/cabinet/test_oauth_revival_security.py` — Python-модуль
  Классы: нет
  Функции: `test_email_merge_requires_local_user_email_verified` — Source-level guard: the email-merge branch checks user.email_verified., `test_revived_log_field_uses_pre_revival_snapshot` — `revived=<bool>` in the logger.info call must come from a snapshot, `test_revive_called_without_commit_kwarg` — Architect's call: revive_deleted_user no longer accepts `commit=`., `test_revive_service_does_not_commit` — Hard pin: revive_deleted_user implementation does not commit.
- `tests/cabinet/test_oauth_server_complete_confirmation.py` — Python-модуль
  Классы: нет
  Функции: `test_server_complete_without_confirmation_is_rejected_and_keeps_state`, `test_confirmed_server_complete_links_without_email_backfill`, `test_preview_shows_masked_target_account_without_consuming_state`, `test_preview_rejects_login_state`
- `tests/cabinet/test_panel_user_id_single_mode_fallback.py` — Python-модуль
  Классы: нет
  Функции: `test_single_mode_falls_back_to_subscription_account`, `test_single_mode_prefers_user_account_when_present`
- `tests/cabinet/test_pool_hot_path.py` — Python-модуль
  Классы: нет
  Функции: `test_request_connection_is_released_before_channel_check`, `setting_reads`, `test_settings_are_read_from_database_once`, `test_missing_setting_is_cached_too`, `test_cache_expires`, `test_write_is_visible_at_once`
- `tests/cabinet/test_promo_group_recalculation_routes.py` — Python-модуль
  Классы: нет
  Функции: `test_routes_registered`, `test_status_url_is_not_swallowed_by_the_group_id_route` — ``/{group_id}`` объявлен раньше и принимает любую строку — «recalculate» дал бы 422., `test_permissions_follow_the_action`, `recalculation`, `test_post_starts_a_pass_and_returns_its_state`, `test_post_during_a_pass_reports_it_was_queued`, `test_get_reports_state_without_starting_anything`
- `tests/cabinet/test_promo_offer_broadcast_notify.py` — Python-модуль
  Классы: нет
  Функции: `test_delivery_runs_off_plain_ids` — В сервис рассылок уходят голые telegram_id, без ORM-объектов сессии запроса., `test_nothing_queued_without_telegram_recipients` — Некому слать в Telegram — запись рассылки не заводится., `test_promo_preferences_filter_telegram_and_email_notifications`
- `tests/cabinet/test_promo_offer_broadcast_progress.py` — Python-модуль
  Классы: нет
  Функции: `test_broadcast_creates_tracked_delivery` — Отправка сегменту заводит запись рассылки с числом получателей и возвращает её id., `test_broadcast_without_notification_skips_delivery_record` — Без send_notification офферы создаются, но рассылку заводить не за чем., `test_segments_endpoint_returns_counts_for_every_segment` — Кабинет получает охват по каждому сегменту, а не только по выбранному.
- `tests/cabinet/test_promo_offer_email_notify.py` — Python-модуль
  Классы: нет
  Функции: `test_send_promo_offer_email_skips_when_smtp_not_configured`, `test_send_promo_offer_email_renders_template_and_sends`, `test_send_promo_offer_email_prefers_db_override`, `test_promo_offer_email_template_registered` — Дефолтный шаблон promo_offer должен резолвиться из EmailNotificationTemplates., `test_email_fanout_counts_sent_and_failed` — Фан-аут работает на скалярных таргетах (email, language, username) и, `test_email_fanout_empty_targets_noop`
- `tests/cabinet/test_promocode_error_contract.py` — Python-модуль
  Классы: нет
  Функции: `test_activate_returns_structured_error_code` — Every error code must reach the client as ``detail.code`` verbatim., `test_unknown_error_code_falls_back_to_server_error` — An unmapped code degrades to a stable ``server_error`` code, not prose., `test_activation_attempts_are_rate_limited` — Перебор кодов упирается в лимит до обращения к сервису промокодов.
- `tests/cabinet/test_promocode_traffic_roundtrip.py` — Python-модуль
  Классы: нет
  Функции: `test_traffic_survives_create` — Указанный при создании трафик попадает в строку и в ответ., `test_traffic_is_updatable` — Правка меняет трафик, а не отвечает 200 со старым значением.
- `tests/cabinet/test_purchase_tariff_refund_on_failure.py` — Python-модуль
  Классы: нет
  Функции: `test_persistence_wrapped_in_refund_guard` — REGRESSION: both persistence branches (extend + create) must sit inside, `test_refund_helper_uses_fresh_user_and_refund_transaction` — REGRESSION: ``_refund_charge`` must re-fetch the user via, `test_refund_helper_records_failed_refund_when_credit_fails` — REGRESSION: ``add_user_balance`` swallows its own errors and returns False, `test_extend_subscription_post_commit_cleanup_is_best_effort` — REGRESSION: ``extend_subscription`` commits the extension, then runs, `test_charge_precedes_guard_and_delivery_steps_stay_outside` — Keep period compensation after charging; daily staging is atomic instead., `test_trial_conversion_stays_enabled_in_extend_branch` — REGRESSION: the ``extend_subscription`` call must NOT pass
- `tests/cabinet/test_purchase_tariff_traffic_reset_policy.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_follows_the_settings`, `test_free_tariff_change_does_not_hand_out_a_new_quota` — Общее правило переключений: бесплатный прыжок между тарифами счётчик не обнуляет., `test_route_does_not_hardcode_the_panel_reset`, `test_bot_counter_is_kept_when_the_panel_counter_is_kept` — Иначе бот показывает расход 0, а панель — настоящий, до следующей синхронизации., `test_bot_counter_is_reset_together_with_the_panel`, `test_callers_that_do_not_decide_keep_the_previous_behaviour` — Бот при покупке тарифа сбрасывает панель всегда — и счётчик в базе обнуляется, как раньше.
- `tests/cabinet/test_referral_reward_choice.py` — Python-модуль
  Классы: `TestPermissionIsEnforcedServerSide` (2 методов), `TestOwnership` (2 методов), `TestNullIsAValue` (4 методов)
  Функции: `allowed`, `stub_terms` — Ответ эндпоинта собирается тем же get_referral_terms — здесь он не предмет., `options`
- `tests/cabinet/test_remnawave_import_fallback.py` — Python-модуль
  Классы: нет
  Функции: `test_fallback_is_usable_in_except_clause`
- `tests/cabinet/test_remnawave_sync_timeout.py` — Python-модуль
  Классы: нет
  Функции: `test_sync_timeout_constant_is_sane`, `test_inline_sync_is_time_bounded`, `test_timeout_defers_to_fallback_and_returns_promptly`
- `tests/cabinet/test_renewal_single_tariff_mode.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `test_expired_subscription_gets_tariff_periods_without_multi_tariff`, `test_resolve_subscription_without_multi_tariff_loads_the_tariff` — Любой маршрут, взявший подписку через resolve_subscription, может читать её тариф.
- `tests/cabinet/test_reset_trial_actually_reopens_trial.py` — Python-модуль
  Классы: нет
  Функции: `test_paid_once_but_nothing_left_gets_the_trial_back`, `test_expired_trial_of_a_former_payer_is_wiped_and_reopened`, `test_new_trial_after_the_reset_closes_it_again` — Сброс одноразовый: взял новый триал — снова закрыто, второй раз не выдаст., `test_live_paid_subscription_gets_an_honest_refusal` — Живая платная подписка сама закрывает триал — кнопка обязана сказать это, а не врать.
- `tests/cabinet/test_route_shadowing.py` — Python-модуль
  Классы: нет
  Функции: `cabinet_routes`, `test_no_literal_route_is_shadowed`, `test_guard_detects_shadowing` — Сама проверка обязана быть чувствительной, иначе она молча зелёная.
- `tests/cabinet/test_rules_cache_updates.py` — Python-модуль
  Классы: нет
  Функции: `isolated_rules_cache`, `test_cabinet_save_updates_warm_bot_rules`, `test_failed_rules_write_keeps_committed_cache`
- `tests/cabinet/test_sales_stats_period_local_day.py` — Python-модуль
  Классы: нет
  Функции: `test_preset_days_start_at_local_midnight`, `test_custom_dates_without_zone_are_local_calendar_days`, `test_custom_dates_with_zone_are_kept_as_instants`
- `tests/cabinet/test_settings_choice_types.py` — Python-модуль
  Классы: `TestChoiceKeyNormalisation` (2 методов)
  Функции: `test_every_listed_option_is_accepted` — Вариант, показанный админу, обязан сохраняться., `test_boolean_setting_accepts_both_shapes` — Кабинет шлёт настоящий bool, бот — строку. Принимать надо обе формы., `test_string_choices_still_reject_unknown_values` — Контроль: смягчение сравнения не должно открыть дорогу чему угодно., `test_setting_without_choices_is_not_restricted` — Ограничение задаётся списком, а не самим фактом проверки.
- `tests/cabinet/test_settings_writes_are_committed.py` — Python-модуль
  Классы: нет
  Функции: `isolated_settings` — Настройки — глобальный объект: возвращаем значения после теста., `test_set_value_survives_a_session_without_commit` — Сама запись настройки обязана коммитить — на неё полагаются все вызовы., `test_levels_mode_route_persists` — Переключение режима из кабинета доезжает до базы., `test_chain_depth_route_persists` — Глубина цепочки — та же поверхность, тот же дефект., `test_reward_scheme_route_persists` — Схема наград — и она тоже., `test_email_type_switch_persists` — Выключатель писем по типу — четвёртое место с тем же дефектом., `test_batch_writers_commit_themselves` — Кто отказался от коммита внутри записи — обязан коммитить сам.
- `tests/cabinet/test_spofy_subpage.py` — Python-модуль
  Классы: нет
  Функции: `auto_on`, `owner`, `topup`, `test_router_hidden_without_key`, `test_short_key_counts_as_unset`, `test_wrong_key_rejected`, `test_right_key_passes`, `test_resolve_rejects_malformed_short_uuid`, `test_unknown_method_rejected`, `test_tagging_refuses_a_cart_other_than_the_priced_one`, `test_renewal_cart_mirrors_cabinet_extend_cart`, `test_renewal_cart_rejects_trial_and_unknown_period`, `test_tariff_cart_for_trial_user`, `test_tariff_cart_refuses_daily`, `test_device_offer_quotes_each_count_from_the_bot`, `test_device_offer_stops_at_first_unavailable_count`, `test_offer_survives_unexpected_errors_in_parts`, `fresh_checkout_serializer`, `test_completion_only_processes_subpage_carts`, `test_completion_skips_when_global_switch_on`, `test_completion_needs_fresh_intent`, `test_completion_ignores_plain_topups`, `test_tagging_rewrites_source_and_intent`, `test_unbound_cart_is_never_completed`, `test_unrelated_topup_does_not_buy_an_abandoned_cart`, `test_payment_smaller_than_price_never_reaches_into_balance`, `test_small_provider_rounding_is_tolerated`, `test_two_identical_carts_one_payment_buys_only_one`, `test_binding_marks_price_and_requested_amount`, `clocked_carts` — Настоящий UserCartService на фейковых часах — время в тесте крутим сами., `test_payment_two_hours_after_checkout_still_completes` — Оплата пришла через 2 часа после оформления. Старые TTL (корзина 1 ч,, `test_old_short_ttls_reproduce_the_lost_purchase` — Контроль к предыдущему тесту: со старыми TTL (1 ч / 30 мин) та же оплата, `test_pinned_price_preferred_over_recomputed`, `test_completion_passes_the_checkout_bound_price` — spofy_price_kopeks уходит в исполнителя: пересчёт (промо истекло, пропорция, `test_orphan_topup_without_intent_offers_return_to_cart` — Метка намерения протухла раньше корзины: покупку не исполняем, но деньги на, `test_orphan_topup_without_any_cart_points_to_buy` — Корзины нет вовсе (истекла/перезаписана): деньги на балансе, ведём к покупке., `test_completed_purchase_does_not_duplicate_notification` — Покупка состоялась — юзера уже уведомил исполнитель покупки, дубль не шлём., `test_orphan_notification_respects_the_notifications_switch` — Глобальный выключатель уведомлений гасит и orphan-уведомление (зеркало, `test_checkout_works_with_global_auto_purchase_off`, `test_renew_checkout_tops_up_full_price_and_never_charges`, `test_amount_raised_to_method_minimum`, `test_restricted_user_cannot_checkout`, `test_devices_checkout_saves_cabinet_cart`, `test_devices_checkout_refuses_a_swapped_cart` — W1: кабинет перезаписал общий слот корзины между save и tag → 409, без пополнения., `test_devices_unavailable`, `test_traffic_package_must_exist`, `test_concurrent_same_checkout_replays_one_payment`, `test_concurrent_different_checkout_gets_409`, `test_offer_for_trial_user_lists_tariffs_not_renewal`, `test_unexpected_checkout_error_is_a_502_with_its_type`, `test_checkout_binds_the_cart_to_its_payment`, `test_cart_ttls_cover_payment_link_lifetime` — Метка намерения не должна умирать раньше корзины, а корзина — раньше реальной, `test_wait_branch_times_out_with_409_instead_of_hanging` — Первый checkout завис (платёжка не отвечает). Второй с тем же fingerprint раньше, `november_third`, `test_snapshot_gives_next_traffic_reset_day`, `test_snapshot_reset_day_is_today_while_reset_is_pending`, `test_snapshot_has_no_reset_day_without_a_reset`, `test_disabled_subscription_is_refused_before_any_cart`, `test_offer_reason_for_disabled_subscription`
- `tests/cabinet/test_spofy_subpage_open_event.py` — Python-модуль
  Классы: нет
  Функции: `test_open_is_recorded_once_a_day`, `test_event_name_does_not_mute_funnel_nudges`
- `tests/cabinet/test_spofy_subpage_owner_loader.py` — Python-модуль
  Классы: нет
  Функции: `test_owner_comes_from_the_cabinet_user_loader`, `test_blocked_owner_is_still_refused`
- `tests/cabinet/test_spofy_subpage_return_url.py` — Python-модуль
  Классы: нет
  Функции: `anyio_backend`, `provider` — Everything around the provider call, which is the mock returned here., `test_page_invoice_returns_to_the_page_not_to_the_cabinet`, `test_cabinet_topup_keeps_the_cabinet_return_url`, `test_cabinet_topup_right_after_a_page_invoice_is_unaffected`, `test_page_without_a_return_url_behaves_as_before`, `test_unsafe_return_url_is_never_handed_to_the_provider`, `test_plain_https_return_url_is_accepted`
- `tests/cabinet/test_subscription_requires_tariff_flag.py` — Python-модуль
  Классы: нет
  Функции: `tariffs_mode`, `classic_mode`, `test_paid_subscription_without_tariff_requires_tariff`, `test_subscription_with_tariff_does_not_require_tariff`, `test_trial_without_tariff_does_not_require_tariff` — Пробная подписка идёт своим путём (покупка тарифа), признак — только для платных., `test_list_item_carries_the_flag_for_paid_subscription_without_tariff` — Список подписок (мультитариф) тоже говорит кабинету, что подписке нужен тариф.
- `tests/cabinet/test_support_config_external_url.py` — Python-модуль
  Классы: нет
  Функции: `test_contact_mode_with_telegram_username`, `test_contact_mode_with_external_url`, `test_both_mode_exposes_external_url`, `test_both_mode_with_telegram_username`, `test_tickets_mode_ignores_contact`, `test_empty_contact_yields_no_url`
- `tests/cabinet/test_support_ws_contract.py` — Python-модуль
  Классы: нет
  Функции: `test_shared_error_contract_uses_integer_or_null_retry_after`, `test_support_ws_rejects_query_token_auth`, `test_support_ws_rejects_missing_subprotocol`, `test_support_ws_accepts_bearer_and_echoes_supported_subprotocol`, `test_ticket_snapshot_keeps_assignment_fields_explicitly_nullable`, `test_owner_ticket_reply_respects_reply_block`, `test_owner_ws_reply_rejected_for_globally_blocked_user` — REGRESSION: бан в поддержке обходился через веб-сокет., `test_owner_ws_reply_rejected_when_tickets_disabled` — REGRESSION: при SUPPORT_SYSTEM_MODE=contact сокет продолжал принимать ответы., `test_owner_ws_reply_notifies_legacy_admin_websocket`, `test_support_ws_reply_notifies_legacy_user_websocket`, `test_privileged_ws_reply_writes_permission_audit_without_sensitive_payload`, `test_privileged_ws_status_update_writes_permission_audit`, `test_upload_lifecycle_makes_media_attachable_only_after_finish`, `test_upload_finish_rejects_checksum_mismatch`, `test_upload_begin_requires_ticket_id` — Uploads must be anchored to a visible ticket; a ticketless begin is rejected, `test_upload_begin_enforces_active_transfer_cap` — A single session cannot pin unbounded memory by opening endless transfers;, `test_ticket_create_declared_out_of_scope_in_ready_event`, `test_ws_reply_idempotent_retry_replays_without_duplicate` — An identical retry under the same idempotencyKey must replay the cached, `test_ws_owner_reply_sets_open_status_and_resets_sla` — A user (owner) reply must move the ticket to 'open' and clear the SLA, `test_pick_message_prefers_id_then_last`, `test_bridge_message_added_broadcasts_contract_message_created`, `test_bridge_message_added_noops_when_ticket_missing`, `test_bridge_ticket_created_broadcasts_opening_message`, `test_bridge_status_changed_broadcasts_status_updated`, `test_register_support_ticket_event_bridge_is_idempotent`, `test_bridge_only_emits_whitelisted_event_names`, `test_bridge_consumes_cabinet_emit_payload`, `test_bridge_listener_is_nonblocking_and_isolates_failures`, `test_schedule_bridge_coerces_non_dict_payload_to_empty`
- `tests/cabinet/test_sync_to_panel_relinks_recreated_account.py` — Python-модуль
  Классы: нет
  Функции: `test_recreated_account_is_written_to_both_tables`, `test_account_found_by_short_uuid_also_replaces_the_dead_link` — Тот же перекос возникал и без создания новой учётки., `test_live_recorded_id_is_left_alone` — Живую связь не трогаем: затирать её было бы хуже исходной болезни., `test_missing_panel_account_is_not_reported_as_synced` — Пустая панельная сторона — это расхождение, а не «синхронизировано»., `test_unreadable_panel_is_not_reported_as_missing` — Панель не ответила — это «не прочитали», а не «аккаунта нет»., `test_sync_stamp_is_not_set_when_the_link_did_not_move` — Отметка «синхронизировано» не ставится поверх необновлённой связи.
- `tests/cabinet/test_system_errors_permissions.py` — Python-модуль
  Классы: нет
  Функции: `test_section_is_registered`, `test_permission_is_registered`, `test_every_permission_required_by_cabinet_routes_is_registered` — Ратчет: право, проверяемое роутом, но не заведённое в реестре, не выдать никому., `test_bootstrap_roles_only_grant_registered_permissions` — То же с другой стороны: роль из bootstrap раздаёт только права из реестра.
- `tests/cabinet/test_tariff_traffic_locale.py` — Python-модуль
  Классы: нет
  Функции: `test_tariff_response_localizes_traffic_without_changing_limits`
- `tests/cabinet/test_telegram_auth_jwks.py` — Python-модуль
  Классы: нет
  Функции: `test_build_public_keys_handles_mixed_jwks` — Real Telegram JWKS (RSA + EC + OKP + EC-secp256k1) must not raise., `test_build_public_keys_loads_ec_and_okp_keys` — EC P-256 + Ed25519 + EC secp256k1 keys should all parse with pyjwt 2.11+., `test_build_public_keys_skips_unsupported_kty` — Unknown kty (e.g. future-Telegram-quantum key) is silently skipped, not crashes., `test_build_public_keys_skips_jwk_without_kid` — JWK без kid не может быть selected'ом по header'у токена — пропускаем., `test_build_public_keys_returns_tuple_compatible_with_pyjwt_decode` — Возврат должен быть (public_key, alg) — иначе validate_telegram_oidc_token упадёт., `test_build_public_keys_defaults_alg_when_jwk_omits_it` — JWK без поля `alg` → берём _KTY_DEFAULT_ALG[kty]; alg всё равно не пустой.
- `tests/cabinet/test_telegram_consent_keeps_credential.py` — Python-модуль
  Классы: нет
  Функции: `test_widget_428_leaves_the_payload_unconsumed`, `test_widget_retry_with_consent_consumes_payload_once_and_creates_account`, `test_widget_existing_user_is_still_one_time`, `test_oidc_428_leaves_the_token_unconsumed`, `test_oidc_retry_with_consent_consumes_token_once_and_creates_account`, `test_oidc_existing_user_is_still_one_time`
- `tests/cabinet/test_telegram_init_data_freshness.py` — Python-модуль
  Классы: нет
  Функции: `test_signed_init_data_age_boundary`, `test_forged_or_expired_data_never_authenticates`
- `tests/cabinet/test_telegram_login_claims_phantom.py` — Python-модуль
  Классы: нет
  Функции: `test_phantom_is_claimed_instead_of_creating_a_second_account`, `test_without_phantom_user_is_created_as_before`, `test_without_username_phantom_is_not_even_looked_up`, `test_lost_claim_race_returns_the_existing_user` — claim_phantom вернул (False, existing): telegram_id уже завёл бот — берём его запись., `test_failed_claim_without_fallback_falls_through_to_create`
- `tests/cabinet/test_telegram_ticket_media_flow.py` — Python-модуль
  Классы: `LocalTelegramFiles` (7 методов)
  Функции: `test_upload_create_reply_reload_download` — Both cabinet sides preserve IDs and bytes; downloads require file-bound tokens.
- `tests/cabinet/test_telegram_widget_replay.py` — Python-модуль
  Классы: нет
  Функции: `test_widget_login_is_one_time_and_24h`, `test_widget_link_is_one_time_and_24h`
- `tests/cabinet/test_telegram_widget_signed_fields.py` — Python-модуль
  Классы: нет
  Функции: `test_widget_signature_survives_cabinet_only_fields`, `test_tampered_signed_field_still_rejected`, `test_only_telegram_fields_are_passed`
- `tests/cabinet/test_ticket_admin_author.py` — Python-модуль
  Классы: нет
  Функции: `test_cabinet_admin_reply_stores_admin_id` — REGRESSION: reply_to_ticket в admin_tickets.py должен писать admin.id,, `test_support_ws_reply_stores_actor_id_for_admin` — REGRESSION: _handle_ticket_reply в support_ws.py должен писать, `test_bot_admin_reply_still_stores_admin_id` — Пин существующей (корректной) семантики бот-пути: add_message получает
- `tests/cabinet/test_ticket_cabinet_guards.py` — Python-модуль
  Классы: нет
  Функции: `user`, `test_create_ticket_rejects_blocked_user` — REGRESSION: заблокированный в поддержке пользователь не должен создавать, `test_add_message_rejects_blocked_user` — REGRESSION: дозапись в тикет тоже должна упираться в глобальную блокировку., `test_expired_block_does_not_reject` — Истёкшая блокировка не считается: CRUD возвращает None, guard молчит., `test_create_ticket_rejects_second_open_ticket` — REGRESSION: второй незакрытый тикет через кабинет создать нельзя., `test_add_message_not_limited_by_open_ticket_check` — Лимит открытых тикетов относится только к созданию: отвечать в свой, `test_get_ticket_respects_disabled_mode` — REGRESSION: при SUPPORT_SYSTEM_MODE=contact чтение тикета должно давать, `test_add_message_respects_disabled_mode` — REGRESSION: при выключенных тикетах дозапись в существующий тикет, `test_create_ticket_respects_disabled_mode` — Пин существующего поведения create_ticket., `test_get_tickets_respects_disabled_mode` — Пин существующего поведения списка тикетов.
- `tests/cabinet/test_ticket_media_file_id_oracle.py` — Python-модуль
  Классы: нет
  Функции: `test_foreign_signing_subject_is_rejected`, `test_media_items_are_validated_too`, `test_real_telegram_file_id_is_accepted`
- `tests/cabinet/test_ticket_user_close.py` — Python-модуль
  Классы: нет
  Функции: `test_closes_own_open_ticket`, `test_already_closed_is_not_closed_again`, `test_someone_elses_ticket_is_404`
- `tests/cabinet/test_traffic_packages_discount.py` — Python-модуль
  Классы: нет
  Функции: `tariff_packages` — A subscription on a tariff with two traffic packages., `test_traffic_packages_expose_promo_group_discount` — A 20% traffic promo-group discount surfaces on every package., `test_traffic_packages_no_discount_when_group_has_none` — No promo discount → no discount fields, raw price unchanged., `test_traffic_packages_respect_apply_discounts_to_addons_flag` — When the promo group opts out of addon discounts, traffic stays full price., `test_traffic_packages_apply_discount_in_tariff_mode` — Tariff-mode packages go through the same discount path as classic mode.
- `tests/cabinet/test_trial_subscription_not_deletable.py` — Python-модуль
  Классы: нет
  Функции: `test_expired_trial_cannot_be_deleted`, `test_expired_paid_subscription_still_deletable`
- `tests/cabinet/test_unlink_forgets_provider_email.py` — Python-модуль
  Классы: нет
  Функции: `test_unlink_forgets_the_email_that_only_this_provider_attested`, `test_unlink_keeps_the_email_once_a_password_made_it_a_login`, `test_unlink_keeps_an_email_verified_elsewhere`, `test_unlinking_another_provider_leaves_the_email_alone`
- `tests/cabinet/test_verification_resend.py` — Python-модуль
  Классы: нет
  Функции: `test_windows_come_from_settings`, `test_address_key_is_a_digest_and_ignores_case` — Ключ лимита оседает в Redis и в его логах — сам адрес туда попадать не должен., `test_one_inbox_is_protected_across_addresses` — Лимит по IP не спасает чужой ящик: окно по адресу отдаёт 429 само по себе., `test_zero_disables_the_address_window`, `test_pending_address_gets_a_fresh_link`, `test_unknown_address_answers_the_same_and_sends_nothing`, `test_verified_address_answers_the_same_and_keeps_its_token`, `test_throttle_stops_the_send`
- `tests/cabinet/test_webhook_email_templates.py` — Python-модуль
  Классы: нет
  Функции: `test_every_webhook_type_has_email_template_in_every_language` — Новый WEBHOOK_* тип без email-шаблона — регресс к «почта молча пропущена»., `test_webhook_email_language_fallback_to_ru`, `test_webhook_email_localized_subjects_differ_from_ru` — en — не заглушка: тема отличается от русской., `test_device_name_substitution_and_placeholder_hygiene`, `test_device_name_is_html_escaped`, `test_winback_types_have_email_template_in_every_language`, `test_winback_discount_renders_percent_everywhere`, `test_winback_expired_1d_escapes_end_date`
- `tests/cabinet/test_websocket_client_gone_is_not_an_error.py` — Python-модуль
  Классы: нет
  Функции: `test_known_disconnects_are_recognised`, `test_real_failures_are_not_mistaken_for_a_disconnect`, `test_cabinet_socket_stays_quiet_when_client_is_gone`, `test_cabinet_socket_still_reports_a_real_failure`, `test_cabinet_socket_survives_a_disconnect_while_refusing` — Отказ неавторизованному тоже пишет в сокет — и тоже может не застать клиента.
- `tests/cabinet/test_websocket_dates_are_iso.py` — Python-модуль
  Классы: нет
  Функции: `sent`, `test_renewed_event_carries_iso_utc_date`, `test_activated_event_carries_iso_utc_date`, `test_naive_datetime_is_treated_as_utc`, `test_missing_date_is_an_empty_string`, `test_no_caller_sends_a_human_formatted_date` — Ни один вызов notify_user_* не подсовывает в поле даты отформатированную строку.

### tests/ci

- `tests/ci/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/ci/test_workflow_versions.py` — Python-модуль
  Классы: нет
  Функции: `test_every_action_is_pinned_to_a_single_version` — Одно действие — одна версия во всём репозитории., `test_all_actions_are_pinned` — Плавающих ссылок вроде @main или @master быть не должно., `test_python_version_is_the_same_everywhere` — Тесты, линтер и аудит обязаны идти на одной версии Python., `test_python_version_matches_pyproject` — CI не должен проверять код на версии, которую проект не поддерживает., `test_postgres_image_matches_production_compose` — Тестовая база должна быть той же версии, что и боевая.

### tests/contracts

- `tests/contracts/fixtures/`
- `tests/contracts/test_local_day_guard.py` — Python-модуль
  Классы: нет
  Функции: `find_violations`, `test_known_utc_sites_still_exist` — Список исключений не должен пережить переименование: каждая функция обязана существовать., `test_detector_sees_every_idiom` — Сторож не ослеп: на синтетическом примере находит все пять идиом., `test_app_has_no_hand_made_utc_days`
- `tests/contracts/test_public_registration_gate.py` — Python-модуль
  Классы: нет
  Функции: `test_every_public_user_mutation_is_gated_or_narrowly_trusted`, `test_gated_helpers_are_called_only_after_the_gate`, `test_legacy_guest_find_or_create_wrapper_cannot_reappear_in_public_routes`, `test_registration_twins_bind_the_locked_gift_symmetrically`, `test_no_admission_branch_binds_the_locked_gift_twice`, `test_registration_twins_never_bind_the_gift_unguarded` — A raw bind_locked_gift in a twin would surface a lost race as a 500, not a denial.
- `tests/contracts/test_remnawave_client_paths_match_spec.py` — Python-модуль
  Классы: нет
  Функции: `test_client_calls_only_endpoints_that_exist_in_panel_spec`, `test_legacy_allowlist_entries_are_really_absent_from_spec` — Если ручка из allowlist вернулась в спецификацию, запись устарела — убрать.
- `tests/contracts/test_renewal_applies_tariff_traffic_rule.py` — Python-модуль
  Классы: нет
  Функции: `collect_offenders`, `test_every_renewal_applies_the_tariff_traffic_rule`, `test_known_exceptions_still_exist` — Список исключений не должен протухать: переименовали функцию — обнови причину.
- `tests/contracts/test_sync_surfaces_share_one_function.py` — Python-модуль
  Классы: нет
  Функции: `test_full_sync_is_one_function_everywhere`, `test_full_sync_only_reads_the_panel` — Полная синхронизация и расписание в панель не пишут: истина там, бот её забирает., `test_from_panel_and_to_panel_share_service_methods`, `test_per_user_pushes_share_the_account_field_set`, `test_sync_surfaces_never_reset_devices` — Сброс HWID-устройств — это про продление, а не про синхронизацию: массовый проход

#### tests/contracts/fixtures

- `tests/contracts/fixtures/remnawave_api_3_4_3_endpoints.json` — файл

### tests/crud

- `tests/crud/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/crud/test_admin_dashboard_bulk_stats.py` — Python-модуль
  Классы: нет
  Функции: `test_bulk_campaign_statistics_equal_single`, `test_bulk_campaign_statistics_empty_input`, `test_servers_with_connections_single_query`, `test_tariff_stats_grouped_query_matches_per_tariff_counts`
- `tests/crud/test_autopay_default_on_trial_conversion.py` — Python-модуль
  Классы: нет
  Функции: `test_helper_applies_the_env_default`, `test_helper_respects_a_disabled_default`, `test_trial_conversion_enables_autopay_by_default`, `test_free_relabel_without_conversion_leaves_autopay_alone` — ``convert_trial=False`` — бесплатная смена тарифа, триал остаётся триалом., `test_renewal_of_a_paid_subscription_does_not_touch_autopay` — Пользователь выключил автоплатёж на платной подписке — продление не включает его обратно.
- `tests/crud/test_create_user_race.py` — Python-модуль
  Классы: `TestViolatedConstraint` (5 методов), `TestCreateUserHappyPath` (1 методов), `TestCreateUserRaceCondition` (4 методов), `TestCreateUserSequenceDesync` (2 методов), `TestCreateUserUnknownIntegrityError` (1 методов)
  Функции: нет
- `tests/crud/test_email_alias_lookup.py` — Python-модуль
  Классы: нет
  Функции: `test_alias_of_an_existing_mailbox_is_found`, `test_different_mailboxes_are_not_matched`, `test_like_wildcards_in_the_local_part_are_escaped` — «_» — обычный символ в адресе, но джокер в LIKE., `test_own_alias_is_not_taken_even_next_to_a_stranger` — LIMIT 1 без исключения себя мог вернуть своего же юзера и скрыть чужого., `test_degenerate_and_unknown_addresses_do_not_query`
- `tests/crud/test_extend_expired_keeps_tariff_traffic_limit.py` — Python-модуль
  Классы: нет
  Функции: `test_expired_tariff_renewal_keeps_tariff_limit_when_fixed_limit_is_zero`, `test_expired_tariff_renewal_ignores_fixed_limit_value` — И ненулевая глобальная настройка тарифу не указ: у тарифа свой лимит., `test_expired_unlimited_tariff_stays_unlimited`, `test_unlimited_tariff_renewal_drops_a_leftover_limit` — Жалоба 2026-09-15: грейс оставил в подписке лимит «расход + 1 ГБ» (103 ГБ), `test_expired_renewal_keeps_active_topup_on_top_of_tariff_base`, `test_expired_renewal_drops_expired_topup_and_returns_to_tariff_base`, `test_expired_renewal_heals_zeroed_limit_in_selectable_mode` — Подписка, которой прошлый баг уже выдал безлимит, при продлении возвращается к тарифу., `test_custom_traffic_tariff_keeps_the_chosen_base`, `test_custom_traffic_tariff_falls_back_to_tariff_default_when_base_is_lost`, `test_active_tariff_renewal_keeps_tariff_base_plus_active_topup`, `test_active_tariff_renewal_heals_zeroed_limit` — Продление ещё живой подписки тоже возвращает лимит тарифа — иначе тот, кто, `test_expired_renewal_with_reset_off_heals_zeroed_limit`, `test_active_renewal_heals_zeroed_limit_but_keeps_active_topup`, `test_active_renewal_of_unlimited_tariff_stays_unlimited`, `test_reset_off_expired_renewal_keeps_the_limit`
- `tests/crud/test_free_tariff_day_reset.py` — Python-модуль
  Классы: нет
  Функции: `test_is_free_paid_periodic`, `test_is_free_zero_periodic`, `test_is_free_mixed_is_not_free`, `test_is_free_empty_prices_not_free`, `test_is_free_daily_zero`, `test_is_free_daily_paid`, `test_paid_sub_carries_days`, `test_free_source_does_not_carry`, `test_trial_does_not_carry_by_default`, `test_trial_carries_only_when_add_on_and_reset_off`, `test_reset_free_days_overrides_trial_add` — Ядро фикса: TARIFF_SWITCH_RESET_FREE_DAYS=true перебивает, `test_carry_trial_helper_matrix`, `test_is_free_source_tariff_true`, `test_is_free_source_tariff_false_for_paid`, `test_is_free_source_tariff_handles_missing`, `test_is_free_source_tariff_safe_on_error` — Любая ошибка lookup → False (переносим дни как раньше, смена не падает).
- `tests/crud/test_promocode_crud.py` — Python-модуль
  Классы: нет
  Функции: `test_create_promocode_with_promo_group_id` — Test creating a promocode with promo_group_id, `test_create_promocode_without_promo_group_id` — Test creating a promocode without promo_group_id (other types), `test_get_promocode_by_code_loads_promo_group` — Test that get_promocode_by_code loads promo_group relationship, `test_get_promocodes_list_loads_promo_groups` — Test that get_promocodes_list loads promo_group relationships
- `tests/crud/test_real_payment_methods.py` — Python-модуль
  Классы: нет
  Функции: `test_excludes_only_non_gateway_methods` — MANUAL (отдельная строка) и BALANCE (двойной счёт) — единственные исключения., `test_covers_every_gateway_in_enum` — Любой реальный шлюз из enum обязан быть в списке (защита от будущих пропусков)., `test_includes_previously_missing_gateways` — Jupiter / Donut / Lava — те самые забытые шлюзы — теперь учитываются.
- `tests/crud/test_referral_earnings_filter.py` — Python-модуль
  Классы: `TestLevelPaymentCap` (4 методов), `TestLevelUnlockThreshold` (4 методов)
  Функции: `test_referee_directed_days_are_excluded` — Строка награды приглашённому не должна попадать в заработок владельца user_id., `test_predicate_keeps_every_referrer_reason` — Предикат обязан отбрасывать ТОЛЬКО награды приглашённому., `test_distinct_referral_id_does_not_count_own_inviter` — «Сколько у меня рефералов» через DISTINCT referral_id.
- `tests/crud/test_tariff_panel_tag_crud.py` — Python-модуль
  Классы: нет
  Функции: `test_create_upper_cases_tag`, `test_update_blank_clears_and_missing_keeps`, `test_invalid_tag_is_rejected_before_write`, `test_trial_duration_days_persists`
- `tests/crud/test_today_metrics_local_day.py` — Python-модуль
  Классы: нет
  Функции: `test_new_users_today_counts_from_local_midnight`, `test_subscriptions_purchased_today_counts_from_local_midnight`
- `tests/crud/test_transactions_today_local_day.py` — Python-модуль
  Классы: нет
  Функции: `test_income_today_starts_at_local_midnight`, `test_transactions_count_today_starts_at_local_midnight`, `test_revenue_by_period_groups_by_local_calendar_day`, `test_revenue_by_period_for_one_day_is_today_only`
- `tests/crud/test_trial_subscription_idempotency.py` — Python-модуль
  Классы: нет
  Функции: `test_expired_subscription_does_not_block_new_trial_single_tariff` — В single-tariff режиме EXPIRED-подписка не блокирует создание нового триала, `test_integrity_error_on_commit_returns_concurrent_subscription_single_tariff` — Та же защита от гонки в режиме без multi-tariff: используем
- `tests/crud/test_user_search_conditions.py` — Python-модуль
  Классы: нет
  Функции: `test_in_range_number_matches_telegram_id`, `test_bigint_max_boundary_still_matches_telegram_id`, `test_number_over_bigint_max_falls_back_to_text_only`, `test_very_long_number_falls_back_to_text_only`, `test_text_search_matches_email_column` — Одно поле поиска в кабинете: email ищется тем же `search`, отдельного поля нет., `test_text_search_never_touches_telegram_id`
- `tests/crud/test_users_list_filter_sort_matrix.py` — Python-модуль
  Классы: нет
  Функции: `test_every_filter_works_with_every_sort`, `test_sorting_never_duplicates_a_user_with_several_subscriptions` — Мультитариф: сортировка не должна повторять человека и съедать строки страницы.
- `tests/crud/test_users_list_subscription_end_sort.py` — Python-модуль
  Классы: нет
  Функции: `test_order_by_subscription_end_soonest_first_then_no_sub`, `test_active_daily_subscriptions_do_not_hog_the_top` — Суточные тарифы обязаны быть исключены — иначе сортировка бесполезна., `test_sort_follows_the_subscription_status_filter` — Связка «покажи истёкших + отсортируй по дате» обязана работать.

### tests/database

- `tests/database/crud/`
- `tests/database/migration_loader.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/tariff_checkout.py` — Python-модуль
  Классы: `QuickRenewalPanel` (1 методов)
  Функции: `checkout`
- `tests/database/test_addon_cart_purchase_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_saved_addon_cart_postgres`
- `tests/database/test_admin_expiry_reset_postgres.py` — Python-модуль
  Классы: `Panel` (4 методов)
  Функции: `test_reset_does_not_regain_paid_days_from_panel`, `test_expired_update_sends_closing_date_in_first_patch`, `test_reset_preserves_local_reset_when_expiry_patch_fails`
- `tests/database/test_admin_notification_rollback_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_event_failure_logs_original_error_and_rolls_back`, `test_admin_event_does_not_repeat_cryptobot_credit`, `test_topup_reload_failure_does_not_read_expired_orm_in_error_log`, `test_rollback_failure_also_logs_scalar_identity`
- `tests/database/test_admin_trial_device_cap_postgres.py` — Python-модуль
  Классы: `Panel` (4 методов)
  Функции: `test_admin_trial_conversion_sends_selected_cap`, `test_explicit_multi_callback_after_mode_change_is_rejected`
- `tests/database/test_atomic_addon_cart_panel_down_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel_down`, `retry_queue`, `test_button_devices_while_panel_is_down_charge_once_and_retry`, `test_topup_traffic_while_panel_is_down_charge_once_and_retry`, `test_traffic_grant_failure_leaves_money_untouched` — Выдача трафика упала в базе — списания нет (раньше: списано, трафика нет, возврат упал).
- `tests/database/test_atomic_addon_panel_down_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel_down` — Панель отвечает 502 на любой запрос., `retry_queue`, `test_bot_traffic_paid_while_panel_is_down_is_recorded_and_retried`, `test_cabinet_traffic_paid_while_panel_is_down_is_recorded_and_retried`, `test_bot_device_change_paid_while_panel_is_down_shows_success_and_retries`, `test_bot_add_devices_paid_while_panel_is_down_is_recorded_and_retried`, `test_cabinet_devices_paid_while_panel_is_down_answers_success_and_retries`
- `tests/database/test_atomic_gift_activation_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_two_concurrent_activations_of_one_gift_extend_once`
- `tests/database/test_atomic_instant_switch_postgres.py` — Python-модуль
  Классы: нет
  Функции: `retry_queue`, `test_paid_switch_while_panel_is_down_is_recorded_and_retried`, `test_switch_failure_after_charge_leaves_money_untouched` — Сбой между доплатой и сменой тарифа — нет ни списания, ни смены (раньше: списано, тариф старый)., `test_second_click_while_first_switch_is_charging_does_not_charge_again`
- `tests/database/test_atomic_tariff_double_click_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_second_click_while_first_is_charging_does_not_charge_again`, `test_renewal_after_the_first_one_finished_still_charges` — Осознанное второе продление (после того как первое закончилось) — как раньше, списывает.
- `tests/database/test_autopay_races_postgres.py` — Python-модуль
  Классы: нет
  Функции: `quiet_settings`, `worker`, `test_imported_subscription_with_autopay_off_never_charges`
- `tests/database/test_cabinet_daily_resume_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_trial_cannot_be_paid_through_resume`, `test_expired_daily_resume_and_retry`, `test_restricted_account_cannot_resume_but_can_pause`
- `tests/database/test_central_purchase_hook.py` — Python-модуль
  Классы: нет
  Функции: `yandex_spy` — Patch the Yandex service hooks plus the other lazy side-effects., `test_completed_subscription_payment_fires_once` — Completed SUBSCRIPTION_PAYMENT → fire_purchase_bg(user_id, abs(amount)) once., `test_deposit_does_not_fire` — DEPOSIT is a balance top-up, not a purchase → no purchase event., `test_gift_payment_does_not_fire` — GIFT_PAYMENT is not a self-purchase → no purchase event., `test_refund_does_not_fire` — REFUND must never count as a purchase conversion., `test_not_completed_subscription_payment_does_not_fire_inline` — A pending (is_completed=False) SUBSCRIPTION_PAYMENT must not fire inline., `test_commit_false_does_not_fire_inline` — commit=False defers all side-effects → nothing fires from create_transaction., `test_negative_stored_amount_fires_positive_abs` — SUBSCRIPTION_PAYMENT is stored as a negative debit; the conversion event, `test_deferred_subscription_payment_fires_once` — emit_transaction_side_effects on a completed SUBSCRIPTION_PAYMENT → fires once., `test_deferred_deposit_does_not_fire` — Deferred DEPOSIT side-effects must not fire a purchase event., `test_deferred_not_completed_does_not_fire` — Deferred SUBSCRIPTION_PAYMENT that isn't completed must not fire., `test_deferred_negative_amount_fires_positive_abs` — Deferred path must also pass the positive abs() amount., `test_single_transaction_does_not_double_fire` — One purchase = one fire. The inline (commit=True) path and the deferred
- `tests/database/test_classic_device_migration_postgres.py` — Python-модуль
  Классы: `Panel` (4 методов)
  Функции: `test_selected_classic_devices_are_priced_and_preserved`, `test_classic_migration_limits`, `test_classic_custom_telegram_selected_purchase`, `test_cabinet_daily_classic_price_matches_charge`, `test_daily_selected_classic_devices`, `test_repeated_daily_purchase_does_not_charge_twice`, `test_daily_selected_trial_keeps_conversion_marker`, `test_saved_cart_return_keeps_selected_classic_and_requotes`, `test_custom_traffic_survives_saved_checkout`, `test_cart_distinguishes_default_from_explicit_base_traffic`, `test_restored_trial_keeps_conversion_notice`
- `tests/database/test_daily_auto_purchase_atomic_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_daily_auto_activation_is_atomic`, `test_daily_activation_mixed_entries_debit_once`, `test_daily_manual_failure_rolls_back_before_retry`, `test_daily_trial_conversion_and_auto_overlap`, `test_daily_single_subscription_manual_and_auto_overlap`
- `tests/database/test_daily_promo_days_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_daily_promo_days_defer_charge_and_keep_access`, `test_parallel_daily_workers_charge_only_once`
- `tests/database/test_daily_purchase_cleanup_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_daily_completion_preserves_new_checkout`, `test_daily_completion_does_not_consume_unrelated_cart`
- `tests/database/test_daily_topup_resume_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `seed`, `payments`, `test_daily_topup_obeys_settings_and_repeat`, `test_daily_topup_preserves_eligibility_guards`, `test_payment_hook_keeps_topup_and_notification_when_daily_disabled`, `test_daily_topup_reads_database_setting_override`, `test_two_topups_charge_one_day`, `test_failed_resume_rolls_back_payment`
- `tests/database/test_device_cart_target_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_device_quote_proration_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_errors.py` — Python-модуль
  Классы: нет
  Функции: `test_bare_missing_greenlet_sqlalchemy_2_0`, `test_missing_greenlet_wrapped_in_statement_error_sqlalchemy_2_1`, `test_other_database_errors_are_not_missing_greenlet`
- `tests/database/test_expired_tariff_limit_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_tariff_renewal_preserves_base_and_only_active_purchases`
- `tests/database/test_gift_cart_completion_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_committed_gift_cleanup_preserves_new_cart_and_single_debit`
- `tests/database/test_gift_requote_consent_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_gift_new_price_requires_consent_before_any_debit`
- `tests/database/test_gift_selection_identity_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_second_selection_while_first_result_waits_has_separate_idempotent_payment`
- `tests/database/test_guest_existing_email_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_guest_purchase_gift_idempotency.py` — Python-модуль
  Классы: нет
  Функции: `test_guest_purchase_model_has_idempotency_key_column` — GuestPurchase model must have idempotency_key column and ux_guest_purchases_idempotency_key index., `test_multiple_null_idempotency_keys_are_allowed` — Multiple legacy guest purchases with NULL idempotency_key must be allowed., `test_duplicate_non_null_idempotency_key_is_rejected` — Duplicate non-null idempotency_key must trigger uniqueness violation., `test_migration_0107_upgrade_downgrade_upgrade_lifecycle` — Verify revision 0107 upgrade, downgrade, and upgrade on a SQLite database with legacy null rows.
- `tests/database/test_leaf_modules_import_cycle.py` — Python-модуль
  Классы: нет
  Функции: `test_leaf_modules_do_not_reach_monitoring`
- `tests/database/test_legacy_subscription_addons_refused_postgres.py` — Python-модуль
  Классы: нет
  Функции: `tariffs_mode_with_classic_prices` — Режим тарифов без мультитарифа; классические цены заданы — без сторожа продажа бы состоялась., `test_device_purchase_is_refused_for_legacy_subscription`, `test_device_price_is_refused_for_legacy_subscription`, `test_traffic_purchase_is_refused_for_legacy_subscription`, `test_traffic_packages_are_empty_for_legacy_subscription`
- `tests/database/test_local_date_expr_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_day_buckets_ignore_session_timezone`, `test_local_date_expr_respects_dst_transitions`, `test_separate_expressions_group_together` — Прод 2026-09-12: имя зоны уходило bind-параметром, каждое вхождение — своим ($1, $4, $5),
- `tests/database/test_local_day_groupings_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_sales_stats_route_groups_by_local_day`, `test_sales_stats_custom_period_groups_by_local_day`
- `tests/database/test_merge_deleted_webhook_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `test_late_deleted_event_after_email_telegram_merge_preserves_paid_subscription`, `test_deleted_event_targets_only_current_identity`, `test_rotated_short_id_keeps_legacy_numeric_identity`, `test_deleted_event_resolved_before_merge_commit_cannot_clear_survivor_identity`
- `tests/database/test_migration_chain.py` — Python-модуль
  Классы: нет
  Функции: `test_single_head`, `test_revision_ids_are_unique`, `test_every_revision_reaches_base` — Разрыв в down_revision оставил бы часть миграций неприменёнными.
- `tests/database/test_miniapp_purchase_atomic_postgres.py` — Python-модуль
  Классы: нет
  Функции: `isolated_purchase`, `test_failure_restores_balance_promo_rights_and_ledger`, `test_failed_purchase_preserves_new_or_trial_subscription`, `test_cancellation_rolls_back_checkout_and_releases_locks`, `test_in_flight_purchase_blocks_autopay_for_the_same_due_cycle`, `test_panel_rollback_keeps_committed_payment_and_rights`, `test_auxiliary_rollback_does_not_report_paid_purchase_as_failure`
- `tests/database/test_mode_switch_keeps_panel_account_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `test_account_created_in_single_mode_is_found_by_both_resolvers`, `test_old_multi_rows_without_user_account_still_resolve_in_single_mode` — Строки, созданные ДО правки: аккаунт только у подписки. Одиночный режим всё равно находит его.
- `tests/database/test_paid_daily_reset_intent_postgres.py` — Python-модуль
  Классы: `Panel` (4 методов)
  Функции: `panel`, `charge`, `due`, `test_delivery_failure_and_restart`, `test_foreign_subscription_owner_prevents_reset`
- `tests/database/test_paid_expiry_live_panel.py` — Python-модуль
  Классы: нет
  Функции: `test_paid_expiry_recovers_against_real_panel`
- `tests/database/test_paid_expiry_restart_postgres.py` — Python-модуль
  Классы: `Panel` (8 методов)
  Функции: `isolated_renewal`, `test_paid_expiry_survives_restart_and_stale_event`, `test_restart_recovers_expiry_until_panel_confirms_without_charging_again`, `test_old_panel_ack_cannot_clear_newer_local_intent`, `test_recovery_does_not_revive_ineligible_subscriptions`, `test_bonus_extension_pending_vs_confirmed_panel_change`, `test_pending_intent_does_not_prevent_actual_expiry`, `test_daily_charge_persists_recoverable_expiry`
- `tests/database/test_paid_reset_migration_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_intent_migration_upgrade_downgrade_and_safety`
- `tests/database/test_panel_account_reuse_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_single_tariff_follows_user_account_only`, `test_single_tariff_adopts_subscription_account_when_user_has_none` — Аккаунт создан в мультитарифе (записан у подписки), оператор вернулся в одиночный режим:, `test_single_tariff_does_not_steal_account_held_by_another_user`
- `tests/database/test_panel_identity_recovery_postgres.py` — Python-модуль
  Классы: `Panel` (8 методов)
  Функции: `test_identity_sync_repairs_only_proven_dead_links`
- `tests/database/test_panel_import_billing_postgres.py` — Python-модуль
  Классы: нет
  Функции: `account`, `service`, `seed`, `test_import_reads_configured_trial_marker`
- `tests/database/test_panel_import_subscription_identity_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_created_from_panel_carries_panel_id`, `test_update_from_panel_binds_row_left_empty_by_old_import`, `test_migration_binds_only_unambiguous_rows`
- `tests/database/test_payment_button_config_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_saved_names_order_and_reset_reach_telegram_without_restart`
- `tests/database/test_pending_expiry_migration_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_pending_expiry_migration_preserves_existing_rights`
- `tests/database/test_pool_config.py` — Python-модуль
  Классы: нет
  Функции: `test_sqlite_uses_nullpool_without_kwargs` — Для SQLite пул не применяется — kwargs пустые (NullPool без пулинга)., `test_postgres_pool_kwargs_read_from_settings` — Настраиваемые знобы берутся из settings, безопасные дефолты — фиксированы., `test_pool_defaults_preserve_legacy_values` — Дефолты совпадают с прежними захардкоженными значениями (без регрессии)., `test_pool_size_clamped_to_at_least_one` — pool_size=0 у QueuePool означает «без лимита» — клампим к >= 1., `test_max_overflow_clamped_to_nonnegative`, `test_pool_timeout_clamped_to_at_least_one`, `test_invalid_values_fall_back_to_defaults` — Мусор в env не должен ронять старт — откатываемся к дефолтам., `test_custom_env_values_are_applied` — Числа из env (как строки) корректно парсятся., `test_live_engine_is_wired_with_pool_kwargs` — Боевой engine реально получает kwargs из хелпера — это и есть фикс #3000., `test_custom_pool_values_reach_a_real_engine` — End-to-end: настроенные значения долетают через create_async_engine в пул.
- `tests/database/test_postgres_fixture_guard.py` — Python-модуль
  Классы: нет
  Функции: `test_missing_url_skips_by_default` — Окружение без PostgreSQL не должно ронять прогон., `test_missing_url_fails_when_postgres_is_required` — С поднятым флагом отсутствие базы — падение, а не пропуск., `test_requirement_flag_accepts_usual_spellings`, `test_requirement_flag_ignores_everything_else`, `test_blank_url_counts_as_absent` — Пустая переменная — это отсутствие базы, а не адрес из пробелов., `test_ci_workflow_runs_postgres_tests_for_real` — CI обязан поднимать базу и требовать, чтобы тесты на ней прошли.
- `tests/database/test_primary_subscription_in_session_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_same_row_as_full_load_when_preloaded`, `test_falls_back_to_full_load_when_not_in_session`, `test_none_without_subscriptions`, `test_expires_overdue_active_like_full_load`, `test_people_without_preloaded_subscriptions_one_query` — Как синк теперь: в сессии люди и тарифы, подписок нет — строка одной выборкой, связи из сессии., `test_subscription_without_tariff_gets_empty_relation`, `test_load_subscriptions_of_fills_collections_for_people_in_session` — Деактивация в синке: подписки поднимаются пачкой тем, кого нет в панели — без ленивой подгрузки.
- `tests/database/test_promo_group_crud_schedules_recalculation_postgres.py` — Python-модуль
  Классы: нет
  Функции: `scheduled`, `test_creating_a_group_with_threshold_schedules_recalculation`, `test_only_a_threshold_change_schedules_recalculation_on_update`, `test_deleting_a_group_schedules_recalculation_while_thresholds_remain`, `test_refused_deletion_of_default_group_schedules_nothing`
- `tests/database/test_promo_group_recalculation_postgres.py` — Python-модуль
  Классы: нет
  Функции: `silence_per_user_admin_notifications` — Пересчёт не должен слать админам уведомление на каждого человека., `no_background_recalculation` — CRUD групп ставит пересчёт в фон — здесь пересчёт вызывается руками., `test_recalculation_moves_everyone_to_the_group_their_spending_earned`, `test_raised_threshold_moves_user_down_to_the_group_he_still_earns`, `test_without_auto_groups_nothing_is_checked`
- `tests/database/test_promocode_panel_failure_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_trial_provisioning_failure_releases_usage_and_allows_retry`, `test_existing_subscription_promo_survives_panel_rollback`, `test_failed_trial_cleanup_waits_for_concurrent_paid_conversion`, `test_trial_compensation_preserves_another_users_committed_activation`
- `tests/database/test_reachability_batches_schema_parity.py` — Python-модуль
  Классы: нет
  Функции: `both`, `test_columns_match`, `test_indexes_match`, `test_column_types_match`, `test_jobs_reference_batches`, `test_downgrade_removes_batches`
- `tests/database/test_referral_levels_schema_parity.py` — Python-модуль
  Классы: нет
  Функции: `both`, `test_reward_levels_columns_match`, `test_reward_levels_indexes_match` — Именно это и расходилось: create_all делает ix_..._id, миграция — не делала., `test_new_earning_columns_match`, `test_no_duplicate_tariff_foreign_key` — Миграция не должна вешать второй FK поверх созданного по модели., `test_column_shapes_match`, `test_threshold_columns_are_not_nullable` — Порог и флаг подсчёта читаются напрямую в расчёт награды., `test_downgrade_removes_everything_it_added` — Откат обязан возвращать базу к исходному виду., `test_upgrade_is_idempotent` — Повторный прогон на уже обновлённой базе не должен падать.
- `tests/database/test_referrer_attachment_race_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_two_referrers_have_one_winner`
- `tests/database/test_reissue_devices_postgres.py` — Python-модуль
  Классы: `Panel` (3 методов)
  Функции: `test_reissue_resets_selected_hwid_and_preserves_new_link`
- `tests/database/test_remaining_purchase_traffic_reset_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_guest_nonrenewal_keeps_existing_panel_reset_policy`, `test_paid_existing_purchase_preserves_traffic_contract`
- `tests/database/test_renewal_hwid_postgres.py` — Python-модуль
  Классы: `Panel` (5 методов)
  Функции: `test_same_tariff_90_day_purchase_preserves_hwid`
- `tests/database/test_renewal_survives_stale_panel_snapshot_postgres.py` — Python-модуль
  Классы: нет
  Функции: `single_tariff_mode_quiet`, `test_paid_renewal_is_not_undone_by_a_stale_panel_snapshot`, `test_autopay_does_not_charge_again_after_a_stale_panel_snapshot`
- `tests/database/test_renewal_traffic_reset_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_paid_renewal_resets_bot_and_panel_together`
- `tests/database/test_saved_tariff_source_change_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_saved_source_change_respects_single_switch_policy`
- `tests/database/test_saved_traffic_cart_policy_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_simple_purchase_traffic_reset_postgres.py` — Python-модуль
  Классы: `PanelBoundary`
  Функции: нет
- `tests/database/test_squad_catalog_restrictions_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_last_assigned_squad_deletion_preserves_restriction_and_disables_sales`, `test_partial_deletion_and_explicit_all_servers_keep_their_meaning`
- `tests/database/test_subscription_deletion_identity_postgres.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `subscription`, `seed`, `test_deletion_spares_referenced_identity`, `test_shared_short_identity_survives_legacy_or_foreign_reference`, `test_unavailable_identity_lookup_spares_possible_sibling`, `test_foreign_owner_numeric_identity_is_not_deleted`, `test_single_tariff_checks_short_uuid_of_actual_panel_target`, `test_cabinet_rejects_unowned_or_live_subscription`
- `tests/database/test_subscription_link_refresh_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_url_refresh_invalidates_only_its_stale_crypto`, `test_cabinet_regenerates_crypto_for_the_changed_url`
- `tests/database/test_tariff_cart_restore_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_tariff_panel_tag_schema_parity.py` — Python-модуль
  Классы: нет
  Функции: `test_model_declares_both_columns`, `test_migration_adds_the_same_columns_as_the_model`, `test_migration_is_idempotent_on_a_table_that_already_has_the_columns`
- `tests/database/test_tariff_purchase_traffic_reset_postgres.py` — Python-модуль
  Классы: `PanelBoundary`
  Функции: `test_tariff_purchase_uses_same_reset_decision_in_db_and_panel`, `test_expired_tariff_renewal_preserves_and_prices_extra_devices`
- `tests/database/test_tariff_source_lock_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_source_is_resolved_after_wallet_lock`
- `tests/database/test_telegram_tariff_renewal_atomic_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_tariff_renewal_failure_does_not_leave_a_debit`, `test_tariff_renewal_commits_paid_days_even_when_panel_fails`, `test_tariff_manual_charge_blocks_autopay_for_same_cycle`, `test_tariff_renewal_rechecks_stale_subscription_before_charge`, `test_tariff_switch_commits_target_and_payment_despite_panel_failure`
- `tests/database/test_telegram_user_filters_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_traffic_filter_returns_exact_people_for_every_sort`, `test_traffic_filter_excludes_overdue_subscription_before_status_update`, `test_traffic_row_ignores_stale_subscription_with_higher_usage`
- `tests/database/test_topup_classic_cart_postgres.py` — Python-модуль
  Классы: `CartStorage` (6 методов)
  Функции: `cart_service`
- `tests/database/test_topup_confirm_button_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_confirm_button_renews_and_charges_once`, `test_two_simultaneous_taps_charge_once` — Денег хватает на несколько продлений, второе нажатие приходит, пока первое ещё списывает.
- `tests/database/test_topup_exact_amount_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_rejected_prefill_then_exact_retry_creates_exact_pending_invoice`
- `tests/database/test_unlimited_device_addons_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_unlimited_devices_cannot_be_sold_additional_slots`, `test_unlimited_granted_after_debit_refunds_and_preserves_limit`, `test_concurrent_device_increase_refunds_with_balanced_ledger`, `test_auto_device_purchase_holds_subscription_lock_through_debit` — Автопокупка: между списанием и выдачей чужая транзакция не может поменять лимит подписки.
- `tests/database/test_unpaid_trial_visibility_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/database/test_user_balance_lock_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_user_lock_blocks_second_session` — Пока одно зачисление держит строку пользователя, второе ждёт., `test_concurrent_topups_do_not_lose_money` — Два одновременных зачисления складываются, а не затирают друг друга., `test_lock_returns_fresh_values_not_the_cached_object` — Блокировка обязана отдавать значения из БД, а не из кеша сессии.
- `tests/database/test_user_panel_identity_backfill_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_migration_fills_user_account_only_when_unambiguous`
- `tests/database/test_users_list_filter_sort_matrix_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_every_filter_works_with_every_sort`
- `tests/database/test_users_list_segments_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_segment_returns_exactly_its_people`, `test_expiring_segment_is_paid_only` — «Истекают за 7 дней» — платные, у которых срок скоро; триалы и просроченные не сюда., `test_no_subscription_segment`, `test_sorting_by_end_date_keeps_every_person_of_the_segment`, `test_route_rows_carry_the_segment_for_the_chip` — Чип строки читает subscription_status: у классического триала он «trial», у просроченного — «expired»., `test_stat_cards_count_the_same_segments` — Плитки над списком считают по тем же правилам, что и выборки.
- `tests/database/test_users_list_sort_direction_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_every_sort_goes_both_ways`, `test_people_without_a_value_stay_at_the_bottom`
- `tests/database/test_users_statistics_blocked_count.py` — Python-модуль
  Классы: нет
  Функции: `test_blocked_counts_only_the_blocked_status`
- `tests/database/test_wheel_rtp_postgres.py` — Python-модуль
  Классы: нет
  Функции: нет

#### tests/database/crud

- `tests/database/crud/test_subscription.py` — Python-модуль
  Классы: нет
  Функции: `test_create_trial_subscription_uses_all_available_squads_by_default`, `test_extend_subscription_convert_trial_false_keeps_trial` — Bug #629889 guardrail: subscription_crud.extend_subscription(tariff_id=..., convert_trial=False), `test_extend_subscription_default_converts_trial_on_purchase` — Default convert_trial=True (a real tariff purchase) still clears is_trial., `test_is_trial_already_used_gate` — Единый гейт триала (раньше дублировался в 4 местах purchase.py)., `test_subscription_property_ignores_pending_trial_draft` — Незавершённый платный триал не должен подставляться как основная подписка.
- `tests/database/crud/test_wipe_trial_panel_lookup.py` — Python-модуль
  Классы: нет
  Функции: `api`, `patched_service` — Подменяем SubscriptionService целиком: нужен только его API-клиент., `db`, `test_disable_mode_keeps_single_tariff_user_identity` — Аккаунт остаётся (отключённым) — users.remnawave_id обязан остаться с ним:, `test_delete_mode_still_clears_single_tariff_user_identity` — Регресс-стража: в режиме delete аккаунта больше нет — ссылку на него стираем.

### tests/external

- `tests/external/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/external/test_cryptobot_service.py` — Python-модуль
  Классы: нет
  Функции: `anyio_backend`, `test_create_invoice_uses_make_request`, `test_make_request_returns_none_without_token`, `test_verify_webhook_signature`, `test_verify_webhook_signature_without_token`
- `tests/external/test_pay2328_client.py` — Python-модуль
  Классы: нет
  Функции: `service`, `test_request_signature_matches_documented_algorithm`, `test_slashes_are_not_escaped`, `test_webhook_with_valid_signature_is_accepted`, `test_webhook_with_bad_signature_is_rejected`, `test_webhook_with_changed_amount_is_rejected`, `test_unconfigured_service_rejects_webhooks`
- `tests/external/test_remnawave_3_0_0.py` — Python-модуль
  Классы: нет
  Функции: `test_coerce_panel_user_id_accepts_ints_and_digit_strings`, `test_coerce_panel_user_id_rejects_everything_else` — Мусорный идентификатор обязан падать на границе клиента, а не уходить в панель:, `test_invalid_user_id_error_is_a_remnawave_api_error` — Вызывающий код ловит RemnaWaveAPIError — новый тип не должен пролетать мимо., `test_is_user_not_found_error_recognises_only_real_absence`, `test_is_user_not_found_error_never_true_for_invalid_local_id` — Битая ссылка в БД бота — это баг данных, а не «в панели нет пользователя»., `test_parsed_user_has_numeric_id_and_no_uuid_field` — 3.0.0 удалил ``uuid`` из UsersSchema — датакласс не должен его воскрешать., `test_get_user_by_id_uses_numeric_path`, `test_get_user_by_id_rejects_uuid_before_any_request`, `test_update_user_body_is_keyed_on_id_not_uuid` — UpdateUserCommand.RequestBodySchema в 3.0.0 не имеет поля ``uuid``: zod срежет, `test_update_user_coerces_digit_string_id_to_number`, `test_update_user_rejects_uuid_before_any_request`, `test_user_actions_are_addressed_by_numeric_id`, `test_resolve_user_sends_exactly_one_identifier`, `test_resolve_user_rejects_zero_or_multiple_identifiers` — Панель требует ровно одно поле — отсекаем локально, не тратя запрос на 400., `test_resolve_user_returns_none_when_panel_has_no_such_user`, `test_resolve_user_propagates_non_not_found_errors` — 400 — это отказ панели обработать запрос, а не «пользователя нет»:, `test_resolve_user_returns_none_on_empty_response_envelope`, `test_extend_user_expiration_sends_days_body`, `test_extend_user_expiration_requires_at_least_one_day` — days < 1 панель отвергнет валидацией — запрос не отправляем вовсе., `test_extend_user_expiration_rejects_uuid_before_any_request`, `test_remove_device_body_uses_numeric_user_id_not_user_uuid` — 2.8.0 переименовал ``userUuid`` -> ``userId`` в HWID-командах, 3.0.0 сделал его, `test_remove_device_coerces_digit_string_user_id`, `test_remove_device_with_uuid_fails_without_touching_panel` — Протухший uuid в БД бота: сообщаем о неудаче, но не шлём заведомо битый запрос., `test_reset_user_devices_uses_single_delete_all_call` — Раньше это был цикл из N удалений с эвристикой «успех, если упало меньше, `test_reset_user_devices_with_uuid_fails_without_touching_panel`, `test_get_user_devices_is_addressed_by_numeric_id`, `test_delete_user_returns_true_on_empty_body` — 3.0.0: DELETE отвечает 204 (синхронно) либо 202 (в очередь) — тела нет,, `test_empty_body_actions_return_true_without_reading_response` — Bulk-операции сквадов и рестарт ноды выполняются в фоне:, `test_add_many_users_sends_numeric_ids`, `test_add_many_users_rejects_invalid_ids_before_request`, `test_bulk_squad_actions_skip_request_for_empty_id_list`, `test_restart_node_sends_force_restart_body_default_false`, `test_restart_node_forwards_force_restart_true`, `test_restart_all_nodes_sends_force_restart_body`, `test_users_page_stream_omits_cursor_on_first_page`, `test_users_page_stream_passes_cursor_when_given`, `test_users_page_stream_keeps_cursor_as_string` — Запрос коерсит курсор в число (z.coerce.number), а ответ отдаёт его строкой —, `test_users_page_stream_clamps_size_to_panel_contract` — Контракт панели (zod): size строго 1..1000, иначе 400 «Validation failed», `test_users_stream_follows_cursor_until_exhausted`, `test_users_stream_stops_when_next_cursor_is_null_even_if_has_more_true` — Defensive: a null nextCursor terminates the scan regardless of hasMore., `test_find_users_by_telegram_id_filters_in_query_string` — ``GET /api/users/by-telegram-id/{id}`` удалён — поиск живёт в query-фильтре, `test_find_users_by_email_filters_in_query_string` — ``GET /api/users/by-email/{email}`` удалён — тот же query-фильтр стрима., `test_find_users_passes_all_supported_filters`, `test_find_users_sends_no_filters_when_none_given`, `test_find_users_follows_cursor_and_honours_max_results`, `test_find_users_stops_early_once_max_results_reached`, `test_happ_encrypt_404_disables_panel_endpoint_and_falls_back` — 2.8.0 removed POST /api/system/tools/happ/encrypt → 404 must disable further, `test_happ_encrypt_non_404_error_keeps_endpoint_enabled` — A transient 5xx must NOT permanently disable happ-encrypt (only a 404 = removed)., `test_happ_api_fallback_caches_by_subscription_url` — The client is recreated per request — the crypt5 cache must live on the class, `test_happ_api_fallback_cooldown_after_failure` — A Happ API outage must not stall hot paths — one failure pauses further calls., `test_happ_api_fallback_rejects_unexpected_payload_per_url` — A non-happ:// body is a per-URL problem: never cached as a link, never retried,, `test_happ_api_fallback_4xx_does_not_poison_global_cooldown` — A 4xx rejection of one URL must not disable the fallback for everyone., `test_happ_api_fallback_429_arms_cooldown_not_per_url_ban` — 429 is service throttling: pause globally, but the URL must stay retryable., `test_enrich_uses_external_fallback_only_in_cryptolink_mode` — enrich runs on every get_user_by_*: subscription URLs must not go to the, `test_happ_api_fallback_disabled_by_setting` — HAPP_CRYPTOLINK_API_FALLBACK_ENABLED=false must skip the external service., `test_happ_local_encryption_roundtrip` — Локальное шифрование должно давать happ://crypt4/<base64>, расшифровываемый, `test_happ_local_encryption_real_key_single_rsa4096_block` — Со вшитым ключом Happ v4 (RSA-4096) шифртекст — один блок в 512 байт,, `test_happ_local_encryption_rejects_oversized_payload` — PKCS#1 v1.5 вмещает size_in_bytes()-11: слишком длинная ссылка -> None,, `test_happ_local_encryption_disabled_by_setting` — HAPP_CRYPTOLINK_LOCAL_ENCRYPTION_ENABLED=false должен пропустить локальный, `test_happ_local_encryption_stable_for_same_url` — Паддинг PKCS#1 v1.5 случайный, поэтому без кэша каждый вызов давал бы новую, `test_enrich_uses_local_encryption_without_network` — С локальным шифрованием enrich заполняет crypt-ссылку в любом режиме бота,, `test_delete_all_devices_reports_failure_when_devices_remain` — Панель может ответить 200, оставив устройства — это не успех., `test_delete_all_devices_reports_success_when_panel_is_empty`, `test_update_user_sends_null_tag_to_clear_it` — В контракте панели ``tag`` в PATCH — optional + nullable: не прислать = не, `test_update_user_leaves_tag_alone_when_not_given`
- `tests/external/test_remnawave_3_4_3_contract.py` — Python-модуль
  Классы: нет
  Функции: `test_is_user_not_found_error_matches_panel_error_codes`, `test_create_user_retries_without_external_squad_on_a018`, `test_update_user_retries_without_external_squad_on_a182_not_found`, `test_update_user_still_retries_on_a039_update_error`, `test_update_user_does_not_retry_when_external_squad_was_not_sent` — Без externalSquadUuid в запросе повтор бессмыслен — ошибка уходит вызывающему., `test_get_system_stats_has_no_tz_parameter`, `test_get_user_devices_all_is_a_single_unpaginated_request`
- `tests/external/test_remnawave_geocheck.py` — Python-модуль
  Классы: нет
  Функции: `test_request_geocheck_posts_to_connections_endpoint`, `test_request_geocheck_default_mode_sends_empty_json_body` — requestBody у команды required: «по умолчанию» — это ``{}``, а не отсутствие тела., `test_request_geocheck_sends_ip_only`, `test_request_geocheck_sends_interface_only`, `test_request_geocheck_rejects_ip_and_interface_together` — Панель выбирает один источник маршрута; отправлять оба — молча неоднозначно., `test_request_geocheck_ignores_blank_values`, `test_request_geocheck_raises_when_panel_returns_no_job_id`, `test_get_geocheck_result_uses_job_id_path`, `test_get_geocheck_result_returns_completed_payload`, `test_parse_node_exposes_ips`, `test_parse_node_ips_defaults_to_empty_list`
- `tests/external/test_remnawave_hosts.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_node_exposes_active_inbound_uuids_for_host_linking`, `test_parse_node_without_config_profile_has_no_inbounds`
- `tests/external/test_remnawave_rate_limit.py` — Python-модуль
  Классы: нет
  Функции: `test_429_retries_with_growing_delays_until_success`, `test_429_honours_retry_after_header`, `test_429_sets_shared_throttle_for_other_requests`, `test_request_waits_for_shared_throttle_before_sending`, `test_429_after_all_retries_is_transient_and_not_logged_as_error`
- `tests/external/test_remnawave_remove_device.py` — Python-модуль
  Классы: нет
  Функции: `test_remove_device_posts_numeric_user_id_in_body` — Тело запроса — {'userId': int, 'hwid': str}; никакого userUuid., `test_remove_device_coerces_digit_string_id_to_int` — БД отдаёт BigInteger, но JSON/FSM могут донести строку — коерсим до запроса., `test_remove_device_rejects_uuid_id_without_hitting_the_panel` — Протухший UUID вместо id — наша битая ссылка, а не запрос к панели., `test_success_when_target_hwid_absent_from_remaining_list`, `test_failure_when_panel_acks_but_hwid_still_present`, `test_404_is_treated_as_success`, `test_other_api_error_is_failure`, `test_transient_exception_is_failure`, `test_bare_ack_without_device_list_is_success` — Panels that reply with just an ack (no devices echo) keep the old behaviour., `test_empty_response_is_success`, `test_reset_user_devices_is_a_single_delete_all_call`, `test_reset_user_devices_coerces_digit_string_id_to_int`, `test_reset_user_devices_rejects_uuid_id_without_hitting_the_panel`, `test_reset_user_devices_404_is_success` — Пользователя/устройств уже нет — цель достигнута., `test_reset_user_devices_failure_is_reported`, `test_reset_user_devices_requires_evidence_of_an_empty_list`
- `tests/external/test_remnawave_request_pacing.py` — Python-модуль
  Классы: `SimpleNamespaceLike` (1 методов)
  Функции: `pace` — Фальшивые часы: «сон» двигает их вперёд, реального ожидания нет., `test_no_pacing_by_default`, `test_requests_beyond_the_minute_budget_wait_for_the_window`, `test_window_slides_and_frees_a_slot_after_a_minute`
- `tests/external/test_remnawave_reset_single_attempt.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_does_not_replay_unacknowledged_post`, `test_reset_connection_loss_is_one_attempt`, `test_raw_reset_ack_precedes_optional_enrichment`, `test_reset_marker_presence_is_not_confused_with_missing_or_invalid`, `test_invalid_reset_marker_is_rejected_before_it_can_be_used_as_baseline`
- `tests/external/test_users_stream_size_clamp.py` — Python-модуль
  Классы: нет
  Функции: `test_stream_size_clamped_to_panel_contract`
- `tests/external/test_wata_webhook.py` — Python-модуль
  Классы: `DummyPaymentService` (1 методов), `StubPublicKeyProvider` (2 методов)
  Функции: `anyio_backend`, `test_verify_signature_success`, `test_verify_signature_fails_with_invalid_signature`, `test_verify_signature_fails_without_public_key`
- `tests/external/test_xrocket_pay_api.py` — Python-модуль
  Классы: нет
  Функции: `test_create_invoice_uses_pay_api`, `test_error_without_envelope_is_failure`, `test_get_invoice_by_query_and_404_is_expired`, `test_rate_from_pay_api_without_token`, `test_signature`, `test_webhook_events_map_to_legacy`

### tests/fixtures

- `tests/fixtures/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/fixtures/gift_callbacks.py` — Python-модуль
  Классы: нет
  Функции: `bind_gift_action`
- `tests/fixtures/local_day.py` — Python-модуль
  Классы: нет
  Функции: `use_timezone` — Переключить settings.TIMEZONE на ``name`` и вернуть саму зону., `zone_where_local_date_differs_from_utc` — Зона, в которой прямо сейчас другая календарная дата, чем в UTC., `reset_local_timezone_cache` — Сбросить кэш зоны после теста, чтобы подмена не утекла в соседей.
- `tests/fixtures/loopback.py` — Python-модуль
  Классы: нет
  Функции: `loopback_reachable`
- `tests/fixtures/paid_reset_panel.py` — Python-модуль
  Классы: `PaidResetPanelMixin` (5 методов)
  Функции: нет
- `tests/fixtures/postgres_db.py` — Python-модуль
  Классы: нет
  Функции: `postgres_dsn` — URL тестовой базы из окружения или ``None``., `postgres_is_required` — Требует ли окружение, чтобы тесты на PostgreSQL действительно шли., `require_postgres_dsn` — URL живого PostgreSQL, иначе пропуск теста (или падение, если требуется)., `real_asyncpg` — Снимает заглушку ``sys.modules['asyncpg']``, поставленную conftest., `postgres_database` — URL тестовой базы, в которой уже создана полная схема проекта., `truncate_tables` — Очищает переданные таблицы вместе со счётчиками идентификаторов., `postgres_engine` — Движок к тестовой базе; переданные таблицы очищаются до и после теста., `postgres_session` — Одна сессия к тестовой базе (зеркало ``memory_session``, но на PostgreSQL)., `postgres_sessions` — Несколько независимых сессий, каждая на своём соединении., `lock_waiter_appeared` — Дождалась ли база сессии, стоящей в очереди за блокировкой., `wait_for_lock_waiter` — То же, но отсутствие соперника — сразу падение теста.
- `tests/fixtures/promocode_fixtures.py` — Python-модуль
  Классы: нет
  Функции: `sample_promo_group` — Sample PromoGroup object for testing, `sample_user` — Sample User object for testing, `sample_promocode_balance` — Balance type promocode, `sample_promocode_subscription` — Subscription days type promocode, `sample_promocode_promo_group` — Promo group type promocode, `sample_promocode_invalid` — Invalid/expired promocode, `mock_db_session` — Mock AsyncSession, `mock_has_user_promo_group` — Mock has_user_promo_group function, `mock_add_user_to_promo_group` — Mock add_user_to_promo_group function, `mock_get_promo_group_by_id` — Mock get_promo_group_by_id function, `mock_get_user_by_id` — Mock get_user_by_id function, `mock_get_promocode_by_code` — Mock get_promocode_by_code function, `mock_check_user_promocode_usage` — Mock check_user_promocode_usage function, `mock_create_promocode_use` — Mock create_promocode_use function, `mock_remnawave_service` — Mock RemnaWaveService, `mock_subscription_service` — Mock SubscriptionService, `make_promocode_valid` — Helper to make promocode appear valid (is_valid property)
- `tests/fixtures/real_redis.py` — Python-модуль
  Классы: нет
  Функции: `ensure_real_redis` — Снять заглушку и вернуть перезагруженный ``app.utils.redis_client``.
- `tests/fixtures/redis_pipeline.py` — Python-модуль
  Классы: `SequentialPipelineMixin` (1 методов)
  Функции: нет
- `tests/fixtures/sqlite_memory.py` — Python-модуль
  Классы: нет
  Функции: `ensure_real_aiosqlite` — Снять заглушку sys.modules['aiosqlite'] из conftest перед созданием engine., `memory_session` — Сессия к :memory: БД, где созданы только переданные таблицы.

### tests/handlers

- `tests/handlers/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/handlers/test_addon_cart_resume.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_topup_auto_purchases_addon_cart`, `test_topup_without_intent_leaves_addon_cart_alone` — Документирует старую поломку: корзина без флага — «нет свежего намерения»., `test_button_resumes_addon_cart_instead_of_corrupting_it`, `test_button_with_still_insufficient_balance_sends_back_to_topup`, `test_button_reports_failure_without_deleting_cart`, `test_devices_cart_uses_the_same_button_path`, `test_manual_resume_goes_through_dispatcher_as_manual`, `test_manual_success_text_has_no_word_automatically`, `test_every_addon_cart_in_code_carries_topup_intent`
- `tests/handlers/test_admin_buy_subscription_context.py` — Python-модуль
  Классы: нет
  Функции: `case`, `invoke`, `test_explicit_subscription_retained`, `test_explicit_missing_or_foreign_never_falls_back`, `test_legacy_unpinned_uses_profile_subscription`, `test_tariff_mode_requires_tariff_before_pricing`, `test_selected_tariff_controls_period_buttons`, `test_removed_tariff_period_rejected_before_money`
- `tests/handlers/test_admin_ticket_helpers.py` — Python-модуль
  Классы: нет
  Функции: `test_deny_non_staff`, `test_audit_carries_ticket_owner_contacts`, `test_audit_failure_is_swallowed`
- `tests/handlers/test_admin_user_block_actions.py` — Python-модуль
  Классы: нет
  Функции: `test_confirm_screens_lead_to_action_and_back`, `test_block_result_has_back_to_user`
- `tests/handlers/test_balance_quick_topup.py` — Python-модуль
  Классы: нет
  Функции: `test_stale_query_is_not_reported_as_topup_error` — Устаревший запрос по дороге — предупреждение декоратора, а не отчёт об ошибке., `test_provider_failure_is_reported_once_without_second_answer`, `test_unknown_method_is_reported_with_a_message`, `test_repeated_taps_are_acknowledged_while_provider_is_still_waiting`, `test_already_expired_tap_does_not_create_payment`, `test_answers_the_tap_before_calling_the_provider`, `test_invalid_amount_alerts_immediately`
- `tests/handlers/test_balance_topup_retry_hint.py` — Python-модуль
  Классы: нет
  Функции: `payment_environment`, `state`, `user`, `test_nonfinite_amount_never_reaches_payment_provider`, `test_rejected_purchase_topup_keeps_input_open_until_user_retries`, `test_minimum_hint_only_suggests_an_accepted_whole_ruble_amount`, `test_retry_at_exact_fractional_minimum_does_not_lose_a_kopeck`, `test_manual_amount_reaches_other_payment_routes_without_float_truncation`
- `tests/handlers/test_broadcast_custom_buttons.py` — Python-модуль
  Классы: нет
  Функции: `test_keyboard_passes_icon_custom_emoji_id`, `test_schema_roundtrips_icon_custom_emoji_id`, `test_schema_defaults_to_none_and_rejects_garbage`
- `tests/handlers/test_broadcast_message_without_text.py` — Python-модуль
  Классы: нет
  Функции: `test_message_without_text_is_rejected`, `test_text_message_is_saved`
- `tests/handlers/test_confirm_saved_cart_after_topup.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `state`, `confirm_handlers` — Прежние обработчики «Подтвердить» — здесь только запоминают, с чем их позвали., `test_renewal_tap_goes_straight_to_existing_confirm`, `test_purchase_tap_goes_straight_to_existing_confirm`, `test_changed_checkout_opens_the_screen_instead_of_charging`, `test_money_spent_since_the_message_opens_the_still_short_screen`, `test_one_tap_is_only_for_periods_from_the_price_list`, `test_special_checkouts_stay_on_the_screen`, `test_missing_cart_gets_the_previous_alert`, `test_disabled_tariff_gets_the_previous_alert_and_cart_is_dropped`, `test_everything_else_takes_the_previous_resume_path` — Кнопка не наша, корзина другого вида или сообщение уже нельзя изменить — прежний обработчик., `test_second_tap_while_first_is_processing_is_not_queued_for_a_charge`, `test_failed_confirm_does_not_leave_the_person_locked_out`, `real_renewal` — Настоящее продление: списание, срок и запись о платеже — в базе; панель и админ-чат — заглушки., `test_one_tap_renews_and_charges_exactly_once` — 589 ₽ пополнено, на балансе 689 ₽ + 1 ₽: одно нажатие — продление на 180 дней и одно списание., `test_old_button_does_not_charge_again_even_if_cart_survived` — Денег на два продления, корзина осталась (её не удалил кабинет): старая кнопка ведёт на экран., `real_purchase` — Настоящая покупка из корзины: резерв платежа, списание и подписка — в базе., `test_one_tap_purchase_creates_subscription_and_charges_exactly_once`, `test_callback_copy_keeps_message_and_bot_and_changes_only_data` — Прежнему обработчику уходит копия нажатия: ответ и правка сообщения идут тем же ботом.
- `tests/handlers/test_connect_in_a_minute.py` — Python-модуль
  Классы: нет
  Функции: `test_new_user_sees_one_thought_and_trial`, `test_per_month_price_on_long_periods`
- `tests/handlers/test_custom_days_quote_metadata.py` — Python-модуль
  Классы: нет
  Функции: `test_custom_days_metadata_matches_exact_period_quote`
- `tests/handlers/test_custom_tariff_preview_devices.py` — Python-модуль
  Классы: нет
  Функции: `test_custom_preview_shows_inherited_devices_and_checkout_price`
- `tests/handlers/test_daily_bot_resume_traffic_reset.py` — Python-модуль
  Классы: нет
  Функции: `test_bot_resume_resets_traffic_when_enabled` — RESET_TRAFFIC_ON_PAYMENT=true — оплата возобновления обнуляет счётчик и в панели, и у себя., `test_bot_resume_keeps_traffic_when_disabled` — Выключатель выключен — счётчик не трогаем (прежнее поведение)., `test_bot_resume_leaves_daily_reset_to_panel` — Панель обнуляет сама раз в сутки — свой сброс не добавляем, иначе две квоты за день., `test_bot_resume_lifts_panel_limit_after_paid_reset` — Подписка была в лимите трафика: после оплаты со сбросом лимит в панели снимается явно., `test_bot_unpause_without_charge_keeps_traffic` — Снятие своей паузы у активной подписки — не оплата: денег не берём и счётчик не трогаем.
- `tests/handlers/test_device_list_hwid.py` — Python-модуль
  Классы: нет
  Функции: `test_bot_device_list_exposes_full_hwid`, `test_device_hwid_stays_on_its_page`
- `tests/handlers/test_device_rename_cancel.py` — Python-модуль
  Классы: нет
  Функции: `test_cancel_button_reopens_device_list`, `test_typed_cancel_reopens_device_list`, `test_valid_name_saves_and_reopens`, `test_empty_after_normalize_keeps_state_for_retry`
- `tests/handlers/test_gift_activation_feedback.py` — Python-модуль
  Классы: нет
  Функции: `test_callback_success_is_html_with_subscription_and_menu_buttons`, `test_callback_error_is_html_and_not_a_dead_end`, `test_unknown_gift_deeplink_says_not_found_instead_of_silent_menu`
- `tests/handlers/test_gift_deeplink_activation.py` — Python-модуль
  Классы: `TestGiftDeeplinkActivation` (7 методов), `TestGiftSubscriptionActivationMultiTariff`, `TestGiftSubscriptionActivationSingleTariff` (3 методов), `TestGiftProvisioningInvariants` (2 методов), `TestGiftOverAnotherSubscription` (5 методов)
  Функции: нет
- `tests/handlers/test_gift_share_screens.py` — Python-модуль
  Классы: `TestAccessControl` (4 методов), `TestQrScreen` (3 методов), `TestCopyTextScreen` (3 методов), `TestGiftCardOwnership` (2 методов)
  Функции: `wired`, `test_both_screens_are_registered` — Кнопка без обработчика молча ничего не делает., `test_card_offers_both_buttons`
- `tests/handlers/test_info_menu_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_legal_entry_shown_by_default`, `test_legal_entry_hidden_when_all_documents_disabled`
- `tests/handlers/test_leftover_input_state.py` — Python-модуль
  Классы: нет
  Функции: `test_subscription_deeplink_drops_leftover_input_step`, `test_promo_input_does_not_bring_back_previous_input_step`, `test_language_switch_works_during_input_step_and_drops_it`, `test_language_handler_accepts_any_state_but_registration_language_step`
- `tests/handlers/test_legacy_subscription_addons.py` — Python-модуль
  Классы: нет
  Функции: `test_traffic_topup_is_refused_for_legacy_subscription`, `test_device_change_is_refused_for_legacy_subscription`
- `tests/handlers/test_legacy_subscription_switch_list.py` — Python-модуль
  Классы: нет
  Функции: `test_legacy_subscription_sees_tariffs_when_switching_is_disabled`, `test_expired_legacy_subscription_sees_tariffs` — Истёкшая старая подписка переводится на тариф той же строкой, а не покупкой с нуля., `test_legacy_subscription_list_does_not_say_unknown_tariff` — Человеку не пишем «Текущий: Неизвестно» — у старой подписки тарифа просто нет., `test_legacy_subscription_period_confirmation_does_not_say_unknown_tariff` — Экран подтверждения после выбора тарифа тоже без «Текущий тариф: Неизвестно».
- `tests/handlers/test_menu_legal_pages.py` — Python-модуль
  Классы: нет
  Функции: `visible`, `test_missing_user_gets_alert_and_no_screen`, `test_hidden_section_is_not_loaded`, `test_no_document_alert`, `test_long_offer_pages_with_own_callbacks`, `test_callback_page_number`
- `tests/handlers/test_no_undefined_texts_in_handlers.py` — Python-модуль
  Классы: нет
  Функции: `test_handlers_never_use_undefined_texts`
- `tests/handlers/test_page_html_is_telegram_safe.py` — Python-модуль
  Классы: нет
  Функции: `visible` — Все инфо-разделы показываются в боте., `test_faq_page_drops_unsupported_markup`, `test_privacy_policy_drops_unsupported_markup`, `test_public_offer_drops_unsupported_markup`, `test_service_rules_drop_unsupported_markup`, `test_allowed_formatting_survives` — Преобразование не должно съедать разметку, ради которой её и писали., `test_long_page_is_split_without_breaking_a_tag` — Нарезка идёт по преобразованному тексту, иначе тег рвётся посередине., `test_registration_privacy_policy_drops_unsupported_markup`, `test_registration_privacy_policy_of_bare_tags_falls_back_to_default`, `test_registration_rules_drop_unsupported_markup`, `test_registration_rules_of_bare_tags_fall_back_to_default`, `test_registration_sends_rules_only_through_the_converter` — Любая новая отправка правил из start.py обязана идти через _rules_for_telegram.
- `tests/handlers/test_panel_down_after_charge.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `state`, `panel_down` — Панель отвечает 502 на любой запрос — как 02.11.2026., `admin_chat` — Уведомление в админ-чат: читает те же поля, что настоящее, и запоминает их., `test_renewal_paid_while_panel_is_down_shows_success_not_error` — 179 ₽ списаны, срок продлён — человек видит «Подписка продлена», а не «попробуйте ещё раз»., `test_purchase_paid_while_panel_is_down_shows_payment_accepted` — Первая покупка: списано 179 ₽, подписка создана — «Оплата принята», корзина удалена., `test_tariff_switch_paid_while_panel_is_down_records_the_payment` — Доплата за «С Обходами» списана — запись о платеже есть и человек видит «Тариф изменён»., `test_nothing_is_reloaded_when_the_session_was_not_rolled_back`, `test_my_subscription_sync_survives_panel_outage` — Ссылки ещё нет (купил во время сбоя): экран «Моя подписка» не должен падать на синхронизации., `test_my_subscription_screen_opens_while_panel_is_down` — Тот же случай целиком: нажатие «Моя подписка» заканчивается экраном, а не тишиной., `test_my_subscription_asks_the_panel_once_while_it_is_down` — Обычный человек со ссылкой: панель не ответила на первый запрос — остальные не делаем., `test_my_subscription_does_not_repeat_a_failed_devices_request` — Панель ответила на первые запросы и упала на устройствах: тот же запрос второй раз не шлём.
- `tests/handlers/test_payment_check_ownership.py` — Python-модуль
  Классы: нет
  Функции: `test_platega_foreign_payment_is_not_checked_with_provider`, `test_platega_own_payment_still_checked`, `test_cryptobot_foreign_payment_hidden`
- `tests/handlers/test_payment_status_answers.py` — Python-модуль
  Классы: нет
  Функции: `test_platega_unpaid_payment_is_explained_in_words`, `test_platega_failed_payment_says_money_was_not_charged`, `test_platega_paid_payment_keeps_its_answer`, `test_pay2328_unknown_status_is_not_shown_raw`
- `tests/handlers/test_promo_segment_counts.py` — Python-модуль
  Классы: нет
  Функции: `test_promo_segment_counts_match_recipient_lists` — Для каждого промо-сегмента SQL-счётчик равен длине списка получателей., `test_promo_segment_counts_are_not_all_zero` — Явные ожидания — паритет сам по себе прошёл бы и на двух одинаково пустых ветках., `test_expired_segment_edge_cases` — Каждый расходившийся случай — в отдельной БД, чтобы ошибки не сокращались., `test_unknown_segment_counts_zero` — Неизвестный ключ не роняет запрос и не показывает мусорный охват.
- `tests/handlers/test_referral_command.py` — Python-модуль
  Классы: нет
  Функции: `test_menu_has_only_start_and_referral`, `test_referral_command_sends_screen`
- `tests/handlers/test_referral_invite.py` — Python-модуль
  Классы: нет
  Функции: `test_create_invite_message_wraps_links_in_code`, `test_referral_qr_cache_tracks_link_and_owner`
- `tests/handlers/test_referral_invite_text.py` — Python-модуль
  Классы: нет
  Функции: `test_share_text_has_no_markup`, `test_russian_share_text_reads_naturally`, `test_days_phrase`
- `tests/handlers/test_referral_settings_screen.py` — Python-модуль
  Классы: `TestVisibility` (3 методов), `TestCurrentStateIsVisible` (3 методов), `TestSaving` (7 методов), `TestDaysTargetFollowsTheKindChoice` (2 методов), `TestAmountsAreShown` (2 методов)
  Функции: `allowed`, `sides` — Суммы сторон считает движок по настоящей БД — здесь она не предмет., `subs`, `test_every_handler_is_registered` — Обработчик без регистрации — кнопка, которая молча ничего не делает.
- `tests/handlers/test_resolve_subscription_footgun_guard.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/handlers/test_sbp_recurring_handlers.py` — Python-модуль
  Классы: нет
  Функции: `test_autopay_menu_daily_tariff_has_no_sbp_entry`, `test_toggle_autopay_enable_blocked_for_trial`, `test_stale_sbp_button_answers_unavailable`, `test_tariff_confirm_keyboards_have_no_sbp_button`
- `tests/handlers/test_show_tariffs_list_single_skip.py` — Python-модуль
  Классы: нет
  Функции: `test_show_tariffs_list_single_tariff_skips_list_and_proceeds` — Один тариф из get_tariffs_for_user → не рисуем список, сразу _proceed с skip_selection., `test_show_tariffs_list_multiple_tariffs_shows_list` — Два и больше тарифов → список как раньше, без авто-перехода., `test_select_tariff_wrapper_parses_id_and_delegates` — select_tariff остаётся тонкой обёрткой: парсит id и зовёт _proceed без skip_selection., `test_proceed_skip_selection_uses_back_to_menu` — Схлопнутый выбор: клавиатура периодов с back_callback=back_to_menu., `test_proceed_normal_selection_uses_menu_buy_back` — Обычный выбор из списка: клавиатура периодов с back_callback=menu_buy., `test_back_target_survives_a_redraw_of_the_custom_screen` — «Назад» не должен деградировать при перерисовке конфигуратора.
- `tests/handlers/test_stars_gift_purchase_problem.py` — Python-модуль
  Классы: нет
  Функции: `test_missing_purchase_is_a_problem`, `test_pending_purchase_is_applied`, `test_purchase_paid_by_another_payment_is_a_problem`, `test_redelivery_of_the_same_charge_is_fine`
- `tests/handlers/test_start_invite_only.py` — Python-модуль
  Классы: нет
  Функции: `test_registration_invite_payload_preserves_original_start_parameter`, `test_telegram_access_evaluation_forwards_identity_and_lock`, `test_create_user_with_registration_invite_commits_gift_atomically`, `test_invite_denial_includes_support_button_when_contact_is_configured`, `test_invite_denial_renders_without_button_when_contact_is_empty`, `test_pending_gift_drain_delegates_to_the_shared_claim_service` — Активация из FSM идёт через общий claim-сервис, а не через собственный запрос., `test_already_claimed_gift_is_reported_instead_of_ignored` — Ссылка, которую уже забрал другой человек, обязана отвечать, а не молчать.
- `tests/handlers/test_start_menu_keyboard_same_as_back.py` — Python-модуль
  Классы: нет
  Функции: `test_start_has_no_own_copy_of_the_menu_keyboard`, `test_start_keyboard_is_the_back_to_menu_keyboard`, `test_start_menu_has_cart_button_all_subscriptions_and_respects_text_mode` — Корзина есть, первая подписка истекла, вторая активна — как у «Назад в меню».
- `tests/handlers/test_start_menu_media.py` — Python-модуль
  Классы: нет
  Функции: `test_video_takes_precedence_over_logo`, `test_without_video_falls_back_to_logo`, `test_removed_video_returns_to_logo` — Удаление видео в кабинете сразу возвращает прежнее поведение., `test_long_caption_goes_to_plain_text` — Подпись длиннее лимита Telegram нельзя приложить ни к видео, ни к фото., `test_video_send_failure_still_delivers_menu` — Битый file_id не должен оставлять пользователя без меню., `test_video_used_even_when_logo_mode_disabled` — Видео — самостоятельная настройка, не зависит от ENABLE_LOGO_MODE., `test_answer_path_sends_video` — /start отвечает через message.answer — видео обязано работать и там., `test_answer_path_without_video_delegates_unchanged` — Без видео поведение обязано остаться ровно прежним (патченный answer)., `test_answer_path_falls_back_when_video_broken`, `test_answer_path_long_caption_delegates_to_text`
- `tests/handlers/test_start_retroactive_referral_window.py` — Python-модуль
  Классы: нет
  Функции: `test_start_referral_respects_account_age`, `test_new_user_still_saves_pending_referral`
- `tests/handlers/test_start_subid.py` — Python-модуль
  Классы: `TestSplitStartParamSubid` (9 методов)
  Функции: нет
- `tests/handlers/test_start_subid_drain.py` — Python-модуль
  Классы: нет
  Функции: `test_drain_calls_upsert_subid_with_pending_value` — Happy path: FSM has pending_subid → drain calls upsert_subid with, `test_drain_is_noop_when_no_pending_subid` — No pending_subid in FSM → drain returns without calling upsert. This is the, `test_drain_is_noop_when_pending_subid_is_empty_string` — Empty-string subid (defensive — parser rejects this, but a future bug or, `test_drain_swallows_upsert_failure` — When upsert_subid raises (DB transient, FK violation), the drain must catch, `test_drain_is_noop_when_get_data_returns_none` — state.get_data() returning None (aiogram quirk on fresh state) → drain treats, `test_drain_function_imported_from_start_module` — The drain function must remain importable as a public(ish) symbol on
- `tests/handlers/test_subscription_deeplinks.py` — Python-модуль
  Классы: нет
  Функции: `test_action_is_recognised_only_for_renew_and_traffic`, `test_source_is_the_tail_after_the_first_underscore`, `test_paid_subscription_gets_the_renewal_button_and_the_source_is_recorded`, `test_expired_paid_subscription_still_goes_to_renewal`, `test_no_subscription_or_plain_trial_goes_straight_to_tariff_choice`, `test_trial_with_a_tariff_keeps_the_renewal_screen`, `test_lifetime_subscription_is_told_there_is_nothing_to_renew`, `test_english_user_gets_english_tariff_choice`, `test_failed_event_write_does_not_break_the_answer`, `test_traffic_keeps_its_button_and_writes_no_event`, `test_traffic_without_subscription_falls_through_to_plain_start`, `test_start_with_channel_link_opens_tariff_choice_instead_of_referral_refusal`, `test_start_with_channel_link_opens_renewal_for_a_paid_subscription`, `test_start_with_channel_link_for_deleted_account_is_a_plain_start` — Удалённому — обычный /start; метка не должна уйти дальше как реферальный код.
- `tests/handlers/test_subscription_gift_button_fallbacks.py` — Python-модуль
  Классы: `TestGiftButtonFallbacks` (6 методов)
  Функции: `mock_user`, `simulate_missing_gift_keys` — Simulate missing GIFT_* keys in locale files while preserving other keys.
- `tests/handlers/test_subscription_gift_catalog.py` — Python-модуль
  Классы: `TestSubscriptionGiftEntryVisibility` (7 методов), `TestSubscriptionGiftCatalogFlow` (12 методов), `TestGiftHandlerRegistrationAndCollision` (1 методов)
  Функции: `mock_db_user`, `mock_db`, `mock_callback`, `memory_state`
- `tests/handlers/test_subscription_gift_code_activation.py` — Python-модуль
  Классы: `TestGiftCodeActivationEntryAndIsolation` (7 методов), `TestGiftCodeInputAndResultMapping` (10 методов)
  Функции: нет
- `tests/handlers/test_subscription_gift_history.py` — Python-модуль
  Классы: `TestGiftMenuVisibilityAndEmptyHistory` (5 методов), `TestGiftPaginationAndOwnership` (7 методов), `TestGiftRecoveryDetail` (1 методов), `TestSourceNeutralPresentation` (2 методов)
  Функции: `mock_db_user`, `mock_db`, `mock_callback`, `memory_state`
- `tests/handlers/test_subscription_gift_purchase.py` — Python-модуль
  Классы: `TestGiftBalanceConfirmation` (7 методов), `TestGiftReplayAndPresentation` (9 методов)
  Функции: `mock_db_user`, `mock_db`, `mock_bot`, `mock_callback`, `memory_state`, `sample_quote`, `sample_purchase_result`
- `tests/handlers/test_subscription_link_visibility.py` — Python-модуль
  Классы: нет
  Функции: `link_env`, `test_device_help_uses_display_link_and_existing_hide_policy`
- `tests/handlers/test_support_decisions.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_decision`, `test_only_admin_chat_buttons_are_recognised`, `test_not_recognised_without_admin_chat`, `test_admin_yes_is_recorded_and_buttons_removed`, `test_admin_no_is_recorded`, `test_stranger_cannot_decide`, `test_decision_is_kept_when_message_cannot_be_edited`, `test_write_failure_is_reported`, `test_middleware_routes_decision_from_admin_chat`, `test_middleware_drops_decision_from_foreign_group`
- `tests/handlers/test_tariff_extend_subscription_id.py` — Python-модуль
  Классы: нет
  Функции: `test_confirm_keyboard_puts_subscription_id_first_period_last`, `test_extend_keyboard_embeds_subscription_id_before_tariff_and_period`
- `tests/handlers/test_tariff_list_price_30_days.py` — Python-модуль
  Классы: нет
  Функции: `test_list_shows_the_30_day_price_not_the_shortest_period`, `test_integer_period_keys_are_found_too`, `test_tariff_without_a_30_day_period_keeps_the_old_wording`, `test_discount_is_taken_for_the_30_day_period_and_keeps_its_icon`
- `tests/handlers/test_tariff_preview_price_matches_engine.py` — Python-модуль
  Классы: нет
  Функции: `test_preview_uses_engine_price_with_extra_devices`
- `tests/handlers/test_tariff_switch_subscription_resolution.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/handlers/test_telegram_ticket_video.py` — Python-модуль
  Классы: `RecordingBot` (5 методов)
  Функции: `test_ticket_handler_preserves_media`, `test_attachment_button_delivers_original_photo_and_video`, `test_video_ticket_view_exposes_attachments`, `test_user_notification_delivers_admin_attachment`, `test_admin_notification_delivers_attachment_to_ticket_topic`
- `tests/handlers/test_ticket_album_and_split_text.py` — Python-модуль
  Классы: нет
  Функции: `quiet_ticket_side_effects`, `test_album_creates_one_ticket_with_every_photo`, `test_split_long_text_is_kept_whole`, `test_short_text_is_processed_without_waiting`, `test_reply_album_lands_in_one_reply`, `test_throttling_lets_ticket_input_parts_through`
- `tests/handlers/test_ticket_group_card_refresh.py` — Python-модуль
  Классы: нет
  Функции: `admin_and_crud`, `test_close_in_group_redraws_the_group_card_without_fsm_buttons`, `test_permanent_block_in_group_redraws_the_card_and_skips_the_private_view`, `test_unblock_in_group_redraws_the_card`, `test_private_chat_keeps_the_admin_view` — В личке админа поведение прежнее: полный экран тикета с FSM-кнопками.
- `tests/handlers/test_ticket_group_reply.py` — Python-модуль
  Классы: нет
  Функции: `test_extract_ticket_id`, `test_admin_reply_to_ticket_card_is_accepted`, `test_other_group_messages_are_ignored`, `test_anonymous_group_admin_maps_to_first_admin`, `test_anonymous_bot_from_other_chat_is_rejected`, `test_tickets_command_detected`, `test_tickets_command_ignored_for_strangers`, `test_middleware_routes_admin_reply`, `test_middleware_still_drops_ordinary_group_messages`, `test_card_text_has_reply_marker_and_hint`
- `tests/handlers/test_ticket_message_not_truncated.py` — Python-модуль
  Классы: нет
  Функции: `test_handlers_do_not_slice_user_text`, `test_handlers_enforce_shared_length_limit`
- `tests/handlers/test_ticket_notification_escaping.py` — Python-модуль
  Классы: нет
  Функции: `test_reply_preview_is_escaped`, `test_escaping_does_not_split_entities_on_the_cut` — Обрезка идёт до экранирования, поэтому `&quot;` не разрывается., `test_plain_reply_is_unchanged`
- `tests/handlers/test_ticket_one_step.py` — Python-модуль
  Классы: нет
  Функции: `quiet`, `test_create_button_asks_for_the_question_at_once`, `test_first_message_becomes_the_ticket`, `test_photo_without_text_still_creates_a_ticket`, `test_title_is_the_first_line_cut_to_the_limit`, `test_title_step_is_gone`
- `tests/handlers/test_ticket_reply_closed.py` — Python-модуль
  Классы: нет
  Функции: `test_closed_ticket_offers_new_ticket_instead_of_reply_input`, `test_reply_blocked_ticket_does_not_ask_for_text`, `test_open_ticket_still_asks_for_reply`, `test_foreign_ticket_is_not_found`
- `tests/handlers/test_ticket_user_wording.py` — Python-модуль
  Классы: нет
  Функции: `test_creation_confirmation_uses_locale`, `test_ticket_card_says_obrashchenie`
- `tests/handlers/test_ticket_view_opens_last_page.py` — Python-модуль
  Классы: нет
  Функции: `test_opens_on_the_last_page_when_no_page_requested`, `test_explicit_page_from_pagination_button_wins`
- `tests/handlers/test_topup_provider_retry_ranges.py` — Python-модуль
  Классы: `ProviderSettings` (1 методов)
  Функции: `test_rejection_keeps_selection_and_shows_exact_enterable_range`, `test_currency_rejection_offers_a_ruble_input_range`
- `tests/handlers/test_trial_deeplink_duration.py` — Python-модуль
  Классы: нет
  Функции: `free_trial`, `activate`, `test_deeplink_trial_matches_tariff_and_cabinet_preview`, `test_deeplink_trial_duration_persisted_on_postgres`
- `tests/handlers/test_unknown_message_to_support.py` — Python-модуль
  Классы: нет
  Функции: `test_text_message_offers_send_to_support`, `test_sticker_gets_no_send_button`, `test_creates_ticket_and_notifies_admins`, `test_appends_to_open_ticket`, `test_second_tap_does_not_duplicate`
- `tests/handlers/test_unlimited_device_callbacks.py` — Python-модуль
  Классы: нет
  Функции: `test_unlimited_callbacks_stop_before_pricing_or_debit`
- `tests/handlers/test_withdrawal_confirm_binding.py` — Python-модуль
  Классы: нет
  Функции: `test_details_screen_puts_nonce_into_confirm_button`, `test_stale_confirm_does_not_create_request`, `test_error_retires_confirm_button`, `test_legacy_button_without_nonce_still_works`
- `tests/handlers/test_withdrawal_group_card.py` — Python-модуль
  Классы: нет
  Функции: `approved`, `test_approve_in_group_leaves_only_the_next_action`, `test_approve_in_private_keeps_profile_and_navigation`
- `tests/handlers/test_withdrawal_input_guards.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_withdrawal_amount`, `test_bad_amount_reprompts_and_keeps_state`, `test_valid_amount_moves_to_details`, `test_photo_instead_of_details_reprompts`, `test_sticker_instead_of_promocode_reprompts`

### tests/integration

- `tests/integration/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/integration/test_cross_channel_gift_lifecycle.py` — Python-модуль
  Классы: нет
  Функции: `test_lifecycle_bot_purchase_to_bot_activation` — 1. Bot purchase -> Bot activation:, `test_lifecycle_bot_purchase_to_cabinet_activation` — 2. Bot purchase -> Cabinet activation:, `test_lifecycle_cabinet_balance_purchase_to_bot_activation` — 3. Cabinet balance purchase -> Bot activation:, `test_lifecycle_cabinet_purchase_to_cabinet_activation` — 5. Cabinet purchase -> Cabinet activation:, `test_recovery_of_all_purchase_origins_in_bot_my_gifts` — 6. Recovery of each successful source in bot "My gifts":, `test_backward_compat_historical_full_token_derives_canonical_representation` — Historical full-token gifts receive canonical representation without database migration., `test_backward_compat_legacy_short_codes_in_cabinet_and_strict_in_bot` — Legacy short codes (8-char, 12-char, GIFT-<12>) succeed in cabinet but are rejected in bot., `test_backward_compat_directed_gift_callbacks_and_landing_public_email` — Directed gift callbacks (claim_bound_gift_for_user) and public landing email gifts work seamlessly., `test_lifecycle_cabinet_gateway_purchase_after_webhook_to_bot_activation` — 4. Cabinet gateway purchase after paid webhook -> Bot activation:
- `tests/integration/test_promocode_promo_group_flow.py` — Python-модуль
  Классы: нет
  Функции: `test_promo_group_promocode_full_workflow` — Integration test: Full workflow of promo group promocode, `test_duplicate_promo_group_assignment_edge_case` — Edge case: User already has promo group from previous promocode, `test_missing_promo_group_graceful_failure` — Edge case: Promocode references deleted/non-existent promo group

### tests/live

- `tests/live/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет

### tests/middlewares

- `tests/middlewares/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/middlewares/test_admin_report_stdlib_logger.py` — Python-модуль
  Классы: нет
  Функции: `stdlib_logger` — Stdlib-логгер с консольным formatter'ом бота и подключённым процессором., `test_stdlib_error_report_keeps_type_message_logger_and_traceback`
- `tests/middlewares/test_admin_report_unreachable_user.py` — Python-модуль
  Классы: нет
  Функции: `test_unreachable_user_report_has_reason_and_user_instead_of_traceback`, `test_real_errors_still_carry_the_traceback`
- `tests/middlewares/test_alert_plain_text.py` — Python-модуль
  Классы: нет
  Функции: `test_custom_emoji_tag_becomes_plain_emoji`, `test_html_tags_and_entities_are_removed`, `test_long_text_is_cut_to_telegram_limit`, `test_plain_text_is_untouched`, `test_locale_alerts_have_no_tags_after_tidy`, `test_regular_messages_keep_html`
- `tests/middlewares/test_button_stats_commands.py` — Python-модуль
  Классы: нет
  Функции: `test_start_command_logged`, `test_command_payload_not_stored` — Payload диплинков (webauth_/GIFT_/coupon_ токены) не должен попадать в лог., `test_command_with_bot_mention_normalized`, `test_plain_text_logged_without_content` — Обычное сообщение — факт без содержимого: промокоды и переписка в журнал не попадают., `test_middleware_registered_for_messages` — Пин: middleware подключён и к message-апдейтам (иначе команды не видны).
- `tests/middlewares/test_channel_checker_blocked_user.py` — Python-модуль
  Классы: нет
  Функции: `fake_logger`, `test_unreachable_user_does_not_reach_admins`, `test_real_send_failure_still_reported`, `test_prompt_is_delivered_when_user_is_reachable`, `test_blocked_user_pressing_stale_button_is_swallowed` — 403 на edit_text не должен долетать до GlobalErrorMiddleware., `test_unexpected_edit_failure_still_propagates`, `test_deactivation_notice_to_blocked_user_is_quiet` — Отписавшийся от канала и заблокировавший бота давал сразу два отчёта админам., `test_real_notification_failure_still_reported`
- `tests/middlewares/test_channel_checker_payload.py` — Python-модуль
  Классы: `TestPayloadFunctions` (7 методов)
  Функции: нет
- `tests/middlewares/test_chat_type_filter_group_callbacks.py` — Python-модуль
  Классы: нет
  Функции: `test_private_chat_passes_everything`, `test_group_messages_are_still_dropped`, `test_group_ticket_card_buttons_reach_handlers`, `test_fsm_and_menu_callbacks_stay_blocked_in_groups` — FSM-ввод в группе не работает (privacy mode), меню админки в общем чате не место., `test_every_button_of_the_group_card_is_allowed_in_groups` — Сторож: новая кнопка в групповой карточке без разрешения в фильтре — падение здесь, а не у оператора., `test_fsm_buttons_are_not_group_safe`
- `tests/middlewares/test_invite_only_admin_recovery.py` — Python-модуль
  Классы: нет
  Функции: `test_blocked_env_admin_still_reaches_the_bot` — BLOCKED is set automatically when a user mutes the bot — it must not lock the owner out., `test_refresh_remnawave_description_uses_numeric_panel_id`
- `tests/middlewares/test_logging_redaction.py` — Python-модуль
  Классы: нет
  Функции: `test_webauth_token_is_masked`, `test_gift_code_is_masked`, `test_card_number_is_masked`, `test_regular_text_and_short_callbacks_are_kept`, `test_long_callback_names_are_kept`
- `tests/middlewares/test_maintenance_expected_errors.py` — Python-модуль
  Классы: нет
  Функции: `test_stale_callback_logged_quietly`, `test_blocked_bot_logged_quietly`, `test_unexpected_bad_request_stays_error`
- `tests/middlewares/test_rich_error_report.py` — Python-модуль
  Классы: нет
  Функции: `test_rich_error_report_structure`, `test_rich_error_report_none_when_oversized`, `test_send_error_uses_rich_and_clears_buffer`, `test_send_error_falls_back_to_document_when_rich_unavailable`, `test_rich_error_report_renders_a_plain_note_without_code_block` — Запись без трейса (например, «сообщение некуда доставить») — обычный абзац,
- `tests/middlewares/test_stale_callback_answer.py` — Python-модуль
  Классы: нет
  Функции: `test_phrase_matcher_covers_both_telegram_wordings`, `test_stale_answer_becomes_warning_and_returns_true`, `test_other_errors_on_answer_still_raise`, `test_stale_phrases_on_other_methods_are_not_swallowed` — Middleware узкий: только ответ на нажатие. Редактирование сообщения — не его дело., `test_successful_request_passes_through`, `test_bot_factory_installs_the_middleware_for_every_bot` — Все боты (основной, из кабинета, из фоновых задач) создаются фабрикой — защита общая.
- `tests/middlewares/test_transient_telegram_noise.py` — Python-модуль
  Классы: нет
  Функции: `test_dropped_get_updates_is_transient`, `test_transient_error_is_found_through_cause_chain`, `test_raw_socket_drop_from_aiogram_is_transient` — aiohttp иногда отдаёт обрыв без обёртки aiogram., `test_unrelated_error_is_not_suppressed`, `test_processor_suppresses_only_the_transport_noise` — Сквозной путь: событие пишется в базу, но в чат уходит только настоящая ошибка., `test_socket_drop_from_another_client_is_not_telegram_noise` — ClientOSError бывает у любого aiohttp-клиента — платёжки, панель; их не глушим.

### tests/migrations

- `tests/migrations/test_0127_user_reminders.py` — Python-модуль
  Классы: нет
  Функции: `test_revision_chain`, `test_builtin_is_shipped_disabled_with_all_languages`, `test_models_roundtrip`
- `tests/migrations/test_0128_dpichecker_actions.py` — Python-модуль
  Классы: нет
  Функции: `test_revision_chain`, `test_upgrade_matches_model_and_downgrade_drops`

### tests/services

- `tests/services/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/services/panel_sync/`
- `tests/services/test_abandoned_payment_nudge.py` — Python-модуль
  Классы: нет
  Функции: `test_sends_after_ten_minutes_with_amount_and_methods`, `test_too_fresh_payment_is_left_alone`, `test_not_repeated_within_a_day`, `test_skips_user_who_paid_afterwards`, `test_paid_payment_is_not_abandoned`, `test_discount_is_really_locked_for_twenty_minutes`, `test_no_discount_line_without_discount`, `test_cryptobot_invoice_is_covered`, `test_abandoned_cart_gets_one_message_and_is_extended`, `test_cart_reminder_skips_who_already_bought_after_the_cart` — Корзина в боте, а купил в кабинете через 10 минут: «К оплате: N ₽» ему не пишем., `test_cart_reminder_still_goes_if_the_purchase_was_before_the_cart` — Купил месяц, через полчаса собрал новую корзину и бросил — напоминание о ней нужно., `test_cart_wave2_skips_who_already_bought_after_the_cart`, `test_fresh_cart_is_left_alone`, `test_cart_without_missing_balance_has_only_resume_button`, `test_spofy_subpage_cart_is_not_nudged`, `test_referral_prompt_after_purchase_once`, `test_referral_prompt_waits_three_minutes`, `test_reminder_is_not_sent_long_after_the_payment`, `test_email_only_user_gets_a_payment_email_not_a_telegram_message`, `test_email_only_user_with_unverified_email_gets_nothing`, `test_email_only_user_gets_a_cart_email`, `test_reminder_email_text_has_the_phrase`, `test_abandoned_topup_wave2_sends_a_day_after_wave1`, `test_abandoned_topup_wave2_needs_wave1_first`, `test_abandoned_topup_wave2_skips_user_who_paid_afterwards`, `test_cart_wave2_is_due_while_the_cart_still_lives` — Корзина живёт CART_TTL_SECONDS. Раньше вторая волна ждала 24 часа и не уходила ни разу., `test_abandoned_cart_wave2_sends_while_cart_is_alive`, `test_abandoned_cart_wave2_ignores_fresh_cart`, `test_no_trial_wave3_sends_after_wave2`, `test_no_trial_wave3_waits_for_wave2`
- `tests/services/test_account_merge_service.py` — Python-модуль
  Классы: `TestComputeAuthMethods` (6 методов), `TestBuildSubscriptionPreview` (3 методов), `TestBuildUserPreview` (2 методов), `TestGetMergePreview` (4 методов), `TestExecuteMergeValidation` (6 методов), `TestExecuteMergeOAuthTransfer` (2 методов), `TestExecuteMergeTelegramTransfer` (2 методов), `TestExecuteMergeEmailTransfer` (2 методов), `TestExecuteMergeKeepsWhatThePagePromises` (11 методов), `TestExecuteMergeBalance` (3 методов), `TestExecuteMergePartnerStatus` (4 методов), `TestExecuteMergeReferralCommission` (2 методов), `TestExecuteMergeSecondaryDeleted` (3 методов), `TestExecuteMergeSubscription` (7 методов), `TestExecuteMergeSubscriptionMultiTariff`, `TestExecuteMergeBulkUpdates` (1 методов), `TestExecuteMergeSelfReferralPrevention` (6 методов), `TestRemnawaveDeleteMode` (4 методов)
  Функции: нет
- `tests/services/test_addon_cart_real_purchase.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_topup_really_buys_traffic_from_saved_cart`, `test_topup_really_buys_devices_from_saved_cart`, `test_button_really_buys_traffic_and_says_so`, `test_button_really_buys_devices_and_says_so`, `test_partial_topup_keeps_cart_and_intent`, `test_shared_topup_hook_buys_traffic_for_every_provider` — Третья причина: хук проверял только total_price, у корзины докупки — price_kopeks., `test_every_payment_provider_calls_the_shared_topup_hook` — Сторож: новая платёжка без общего хука не соберётся — корзина после неё не сработает.
- `tests/services/test_admin_chat_group_button_guard.py` — Python-модуль
  Классы: нет
  Функции: `test_strip_keeps_urls_and_allowed_actions_drops_the_rest`, `test_strip_returns_none_when_nothing_survives`, `service`, `test_group_chat_gets_only_safe_buttons_on_both_send_paths`, `test_group_chat_sends_without_keyboard_when_all_buttons_are_dead`, `test_private_admin_chat_keeps_the_keyboard_untouched`
- `tests/services/test_admin_notification_hardening.py` — Python-модуль
  Классы: нет
  Функции: `test_redact_telegram_secrets`, `test_redact_telegram_secrets_handles_multiple_tokens`, `admin_service`, `test_send_message_retries_on_flood_control` — RetryAfter on attempt 1 → returns at once, background retry sleeps once and succeeds., `test_send_message_respects_global_admin_switch`, `test_send_message_gives_up_after_three_flood_errors` — Three consecutive RetryAfter → background retry stops after two sleeps., `test_send_message_does_not_wait_for_flood_pause` — The caller often holds a DB connection, so the pause must happen after it got its answer., `test_send_message_caps_retry_after_at_30s` — retry_after=120 from Telegram must be clamped to 30s to avoid blocking the flush task., `webhook_service`, `test_node_event_coalescing_keeps_one_flush_task` — 7 concurrent enqueues land in one buffer with one scheduled flush task., `test_node_event_buffer_overflow_counts_dropped_events` — Past BUFFER_MAX, events are dropped but counted in overflow., `test_coalesced_summary_truncates_and_reports_overflow` — 50 unique nodes + 7 overflow → 40 lines + 'truncated' line + 'отброшено' line., `test_coalesced_summary_single_event_omits_count_suffix` — One event → header without '× N' suffix., `test_coalesced_summary_dedupes_by_name_and_address` — Same (name, address) repeated 5 times → 1 line, header shows × 5 total., `test_enqueue_tracks_flush_task_in_pending_set` — Active flush task is held in the strong-ref set; auto-removed after completion., `test_stop_drains_buffered_events` — Pending events in the coalesce window get flushed on stop()., `test_stop_is_idempotent_when_buffer_empty` — Calling stop() with no pending events sends nothing and doesn't crash., `test_enqueue_blocked_after_stop` — After stop() the service refuses new enqueues — no orphaned flush tasks., `test_send_message_logs_clamped_retry_after` — retry_after=120 → log includes both clamped value (30) and original (120)., `test_telegram_notifier_processor_redacts_token_in_traceback` — If a future aiogram leaks the bot token in exc str / traceback, it gets redacted.
- `tests/services/test_admin_notification_promo_group.py` — Python-модуль
  Классы: нет
  Функции: `test_promo_group_resolved_after_refresh_dropped_the_relationship` — Точное воспроизведение прода: refresh сбросил связь, уведомление не должно упасть., `test_promo_group_returned_when_already_loaded`, `test_user_without_promo_group_returns_none`, `test_loaded_relationship_never_triggers_io_for_unloaded` — Хелпер обязан отдавать None, а не лезть в базу., `test_loaded_relationship_falls_back_for_non_orm_objects` — Тестовые фейки не инспектируются SQLAlchemy — для них работает обычный getattr.
- `tests/services/test_admin_notification_username_links.py` — Python-модуль
  Классы: нет
  Функции: `test_referrer_info_links_the_referrer_username` — Реферер в уведомлении о пополнении — та же ссылка, что и у плательщика., `test_referrer_info_keeps_non_telegram_login_as_text` — OAuth-логин из кабинета не является Telegram-логином — ссылки быть не должно., `test_referrer_info_without_username_falls_back_to_id` — Без логина остаётся прежний вид — идентификатор, без пустой ссылки., `test_new_ticket_notification_links_username` — Текст уведомления о новом тикете содержит ссылку, а не голый @логин., `test_new_ticket_notification_without_username_has_no_stray_at` — Без логина строка остаётся текстом-заглушкой, без осиротевшей собаки.
- `tests/services/test_admin_payments_platega_listing.py` — Python-модуль
  Классы: нет
  Функции: `test_ordinary_platega_topup_is_not_duplicated` — Пополнение через Platega видно по своей строке в platega_payments — один раз., `test_pending_platega_payment_still_listed` — Существующая логика pending-платежей не изменилась., `test_details_do_not_confuse_ids_between_tables` — Детали ``/platega/{payment_id}`` открывают строку platega_payments, а не транзакцию с тем же id.
- `tests/services/test_attach_referrer_if_missing.py` — Python-модуль
  Классы: нет
  Функции: `db`, `test_no_op_when_user_already_has_referrer`, `test_no_op_when_no_pending_and_no_code`, `test_attaches_referrer_from_explicit_code`, `test_attaches_referrer_from_redis_pending_when_no_code` — REGRESSION: this is the exact race the user reported., `test_explicit_code_takes_precedence_over_redis` — Explicit URL/state-provided code wins over a stale Redis entry., `test_rejects_self_referral_by_id`, `test_rejects_self_referral_by_telegram_id` — Different DB user IDs but same Telegram account → still self-referral., `test_rejects_self_referral_by_email`, `test_commit_failure_rolls_back_and_returns_none` — If the DB commit fails, the helper rolls back and reports None., `test_registration_event_failure_still_keeps_attachment` — If process_referral_registration raises, the referrer attachment survives., `test_user_without_telegram_id_skips_redis_fallback` — Email-only user (no telegram_id) must not query Redis., `test_invalid_pending_referrer_id_type_is_handled` — Malformed Redis payload (referrer_id is a string that can't int()), `test_process_referral_registration_skips_duplicate_pending_row` — REGRESSION: a second call for the same (referrer, referral) must NOT, `test_process_referral_registration_inserts_first_pending_row` — Negative-control: when no existing pending row, INSERT proceeds normally., `test_helper_lazy_creates_bot_when_caller_omits_it` — Cabinet endpoints don't have a bot in scope; the helper must, `test_cabinet_retroactive_calls_pass_none_for_referral_code` — Source-level pin: the three retroactive attach call sites in, `test_concurrent_attach_uses_conditional_update_not_unconditional_write` — REGRESSION: the helper must use ``UPDATE ... WHERE referred_by_id IS NULL``, `test_concurrent_attach_loser_does_not_fire_event` — When ``rowcount == 0`` (another session already attached), the, `test_helper_uses_caller_supplied_bot_when_provided` — When the bot caller already has a bot (start.py passes message.bot),
- `tests/services/test_auto_extend_description_plural.py` — Python-модуль
  Классы: нет
  Функции: `test_format_days_declension_ru` — The Russian declension matters at the user-visible boundary —, `test_autopay_description_uses_correct_plural_for_one_day` — End-to-end shape: the autopay path renders, `test_autopay_description_uses_correct_plural_for_few_days`, `test_autopay_description_uses_correct_plural_for_many_days`
- `tests/services/test_auto_extend_inactive_tariff.py` — Python-модуль
  Классы: нет
  Функции: `test_try_auto_extend_skips_when_target_tariff_is_inactive` — Operator deactivated the tariff → user must NOT be billed even though
- `tests/services/test_auto_extend_trial_traffic_limit.py` — Python-модуль
  Классы: нет
  Функции: `test_trial_conversion_adopts_unlimited_tariff_limit` — The reported case: unlimited (0) paid tariff must win over the trial's 10 GB., `test_trial_conversion_falls_back_to_subscription_tariff_id` — When the cart has no tariff_id, resolve via the subscription's tariff_id., `test_explicit_cart_traffic_is_preserved` — An explicit (custom) cart traffic value must NOT be overwritten by the tariff., `test_non_trial_renewal_is_untouched` — Ordinary (non-trial) renewal: no tariff lookup, return the cart value as-is.
- `tests/services/test_autopay_cannot_renew_notice.py` — Python-модуль
  Классы: нет
  Функции: `tariffs_mode`, `test_inactive_tariff_tells_user_once`, `test_unpriced_period_tells_user_once`, `test_price_error_tells_user_once_and_cycle_survives`, `test_low_balance_keeps_its_own_notice` — Нехватка денег — штатный путь (свой текст «пополните»), новое сообщение не шлём., `test_guard_reports_inactive_tariff_but_wrapper_keeps_contract`, `test_locale_has_cannot_renew_texts`
- `tests/services/test_autopay_fail_and_expiring_once.py` — Python-модуль
  Классы: нет
  Функции: `test_failed_autopay_and_expiry_reminder_come_as_one_message`, `test_expiry_reminder_still_goes_when_the_failure_notice_was_not_delivered`, `test_without_autopay_the_expiry_reminder_is_unchanged`
- `tests/services/test_autopay_fail_notifications.py` — Python-модуль
  Классы: нет
  Функции: `test_config_defaults_present`, `test_state_dict_roundtrip`, `test_state_from_none_is_empty`, `test_first_failure_outside_final_window_returns_first`, `test_silent_between_first_and_final_when_no_repeat`, `test_final_reminder_inside_window`, `test_max_cap_blocks_after_two`, `test_post_expiry_blocked_when_cap_reached`, `test_max_zero_disables_all`, `test_late_first_failure_inside_window_sends_final_only`, `test_repeat_interval_sends_after_elapsed`, `test_repeat_interval_not_yet_elapsed_stays_silent`, `test_full_cycle_default_yields_exactly_two_then_silence` — Core guarantee: across ticks from window-open through post-expiry, default config, `test_fresh_cycle_allows_notifications_again` — A renewal advances end_date → caller loads a FRESH state for the new cycle_token., `test_load_save_state_in_memory_roundtrip` — With Redis returning nothing, the in-memory fallback must persist state across, `test_cleanup_evicts_old_cycles` — In-memory state for cycles whose end_date is >72h in the past must be evicted., `test_maybe_notify_sends_first_then_silent` — _maybe_notify_autopay_failure sends on first failure, records state, and stays, `test_maybe_notify_final_when_inside_window` — When the first failure lands inside the final window, the wrapper sends a final, `test_final_not_starved_by_repeats_when_cap_reached` — max=2 + repeats=6h: first + repeat exhaust the cap, but the final still fires, `test_final_fires_even_if_interval_steps_past_window` — If the monitoring tick jumps over the final window (4h → expired), the still-unsent, `test_max_one_still_delivers_final` — Even with max=1 the final is guaranteed (cap bounds repeats, not the final)., `test_load_reads_redis_on_inmemory_miss` — Cross-restart durability: on an in-memory miss, _load must consult Redis and, `test_save_persists_with_ttl_floor` — _save writes key/value/TTL to Redis; the TTL is floored at 60s so a near-zero, `test_email_only_path_uses_cause_specific_reason` — Non-Telegram (email) users: the reason text reflects the failure cause —, `test_email_only_final_reminder_reason` — Email users get the distinct final-reminder wording when the cycle reaches the window.
- `tests/services/test_autopay_free_period.py` — Python-модуль
  Классы: нет
  Функции: `tariffs_mode`, `test_free_period_is_renewed` — Бесплатный период продлевается — куплен же он был как обычный., `test_unpriced_period_is_still_skipped` — Цена периода не проставлена — продлевать нечего, поведение прежнее., `test_paid_period_still_needs_money` — Платный период без денег на балансе по-прежнему не продлевается.
- `tests/services/test_autopay_period.py` — Python-модуль
  Классы: нет
  Функции: `test_resolve_autopay_period_candidate_with_tariff`, `test_resolve_autopay_period_candidate_falls_back_to_global_when_tariff_has_no_periods` — When the tariff has no priced periods, validation falls back to the global allowlist, `test_resolve_autopay_period_candidate_falls_back_to_global_when_no_tariff` — Classic-mode (no tariff) subscriptions still need bounded periods — the global, `test_resolve_autopay_period_candidate_rejects_when_both_allowlists_empty` — Fail-closed: with no allowlist available anywhere, ANY candidate is rejected and the, `test_resolve_autopay_period_candidate_swallows_broken_tariff` — A tariff whose ``get_available_periods`` raises (corrupted period_prices, ORM lazy-load, `test_update_subscription_autopay_sentinel_does_not_touch_period_when_omitted` — Legacy callers (autopay.py:154, autopay.py:188, miniapp.py:3733) invoke with positional, `test_update_subscription_autopay_explicit_none_clears_period` — When the user clicks "По умолчанию" in the period picker, the handler passes, `test_update_subscription_autopay_explicit_int_sets_period`, `test_autopay_period_unset_sentinel_is_module_private` — The sentinel must stay a private object — exporting it would tempt callers to, `test_set_autopay_period_default_suffix_clears_override` — Suffix `default` → clear the per-subscription override (passes period_days=None)., `test_set_autopay_period_valid_int_writes_period` — Suffix matching a valid tariff period → write it to the subscription., `test_set_autopay_period_invalid_int_alerts_without_writing` — Suffix matching an integer NOT in the tariff allowlist → alert the user and do NOT
- `tests/services/test_backup_covers_all_payments.py` — Python-модуль
  Классы: нет
  Функции: `test_every_payment_table_is_exported`, `test_export_list_has_no_phantom_payment_tables` — Обратная сторона: модель в списке, а таблицы уже нет., `test_payment_table_is_cleared_on_restore` — Восстановление «с заменой» должно чистить и таблицы платежей.
- `tests/services/test_backup_schedule_skip.py` — Python-модуль
  Классы: нет
  Функции: `test_skips_all_missed_hourly_slots_in_one_step`, `test_skips_missed_15min_slots`, `test_future_next_run_advances_by_one_interval`
- `tests/services/test_backup_scheduler.py` — Python-модуль
  Классы: нет
  Функции: `service`, `test_backup_time_interpreted_in_configured_timezone`, `test_backup_time_rolls_to_next_day_by_local_clock`, `test_utc_timezone_keeps_legacy_behavior`, `test_naive_reference_is_treated_as_utc` — Naive reference не должен интерпретироваться в системной зоне хоста —, `test_format_local_renders_next_run_in_configured_timezone` — Лог-время запуска выводится в settings.TIMEZONE (с меткой зоны), чтобы, `test_invalid_timezone_falls_back_to_utc`, `test_concurrent_starts_leave_exactly_one_loop` — РЕГРЕССИЯ #3030: 6 конкурентных start_auto_backup (холодный старт) не, `test_stop_without_running_task_is_noop`
- `tests/services/test_backup_service_list.py` — Python-модуль
  Классы: нет
  Функции: `backup_dir` — Isolated backup directory under pytest's tmp_path., `service` — A minimally-mocked BackupService bound to a temp backup dir., `test_get_backup_list_skips_empty_tar_gz` — Empty .tar.gz must not raise — it's marked corrupted and listing continues., `test_get_backup_list_recovers_other_files_when_one_is_empty` — One bad file doesn't poison the rest of the listing., `test_get_backup_list_handles_truncated_gzip` — Truncated/corrupted gzip → caught as known-corruption, not as bare Exception., `test_get_backup_list_handles_garbage_json` — Non-archive JSON backup with garbage content → corrupted entry, not crash., `test_get_backup_list_corrupted_entries_do_not_log_as_error` — Known corruption logs as warning, not error — TelegramNotifierProcessor
- `tests/services/test_backup_terminate_backends.py` — Python-модуль
  Классы: нет
  Функции: `test_terminates_other_sessions_and_counts`, `test_best_effort_on_privilege_error`
- `tests/services/test_balance_history_pages.py` — Python-модуль
  Классы: нет
  Функции: `test_pages_cover_every_operation_once`, `test_same_amount_in_different_minutes_is_not_merged`, `test_handler_shows_pages_and_empty_state_with_buttons`, `test_locales_have_history_and_unknown_method_texts`
- `tests/services/test_broadcast_bad_request_logging.py` — Python-модуль
  Классы: нет
  Функции: `test_bad_request_is_logged_once_per_cause_with_telegram_text`, `test_each_distinct_cause_gets_its_own_error_entry`, `test_blocked_users_are_still_counted_quietly` — «chat not found» — это не сбой рассылки, а ушедший пользователь: без error.
- `tests/services/test_broadcast_email_mirror.py` — Python-модуль
  Классы: нет
  Функции: `test_tg_emoji_becomes_its_fallback_and_spoiler_plain_text`, `test_allowed_tags_kept_rest_stripped_and_escaped`, `test_unclosed_tags_are_closed`, `test_subject_is_first_non_empty_line_without_tags`, `test_subject_is_cut_to_90_chars_and_has_fallback`, `test_callback_buttons_become_one_cabinet_link_url_buttons_stay`, `test_no_cabinet_link_without_configured_cabinet`, `test_callback_custom_button_alone_gives_cabinet_link`, `test_only_users_without_telegram_and_with_verified_email`, `test_category_unsubscribe_is_respected`, `test_should_mirror_skips_resume_and_personal_sends`, `test_start_broadcast_starts_mirror_for_regular_broadcast`, `test_start_broadcast_skips_mirror`, `test_start_broadcast_respects_switch`, `test_broadcast_with_email_channel_is_not_mirrored`, `test_start_from_config_checks_channel_before_selecting`, `test_mirror_sends_to_all_and_cleans_up`, `test_daily_limit_waits_for_next_day_and_keeps_queue_in_file`, `test_daily_limit_is_shared_between_broadcasts`, `test_queue_resumes_from_file_after_restart`, `test_photo_is_attached`, `test_photo_download_failure_sends_without_it`, `test_failure_streak_returns_people_to_queue`, `test_wait_lasts_until_next_utc_day`
- `tests/services/test_broadcast_email_render.py` — Python-модуль
  Классы: нет
  Функции: `test_fragment_gets_branded_layout_with_recipient_and_unsubscribe`, `test_custom_layout_applies_to_broadcasts_too`, `test_full_document_is_sent_as_is_with_unsubscribe_placeholder`, `test_system_broadcast_has_no_unsubscribe_link`, `test_email_render_endpoint_matches_delivery`
- `tests/services/test_broadcast_per_recipient_keyboard.py` — Python-модуль
  Классы: нет
  Функции: `test_keyboard_factory_builds_personal_keyboard_per_recipient` — Каждому получателю уходит своя клавиатура, а не одна общая., `test_blocked_recipients_counted_separately` — Заблокировавшие бота идут в blocked, а не в общую кучу ошибок., `test_without_factory_shared_keyboard_is_used` — Обычные рассылки не затронуты: без фабрики уходит общая клавиатура.
- `tests/services/test_bypass_downgrade.py` — Python-модуль
  Классы: нет
  Функции: `enforcing`, `test_paid_bypass_subscription_with_exhausted_quota_is_eligible`, `test_ineligible`, `test_limited_status_is_still_eligible`, `test_without_squads_configured_nothing_is_eligible`, `test_suspended_subscription_goes_to_bypass_off_unlimited_and_active`, `test_not_suspended_subscription_keeps_tariff_squads_and_limit`, `test_bypass_returns_once_quota_is_no_longer_exhausted`, `test_mode_false_ignores_leftover_marks`, `test_tariff_squad_sync_keeps_suspended_account_in_bypass_off`, `test_import_does_not_take_bypass_off_as_a_tariff_change`, `test_suspended_snapshot_recognition`, `test_limited_webhook_suspends_instead_of_limiting`, `test_limited_webhook_for_ineligible_subscription_falls_through`, `test_observe_mode_only_logs`, `test_traffic_reset_webhook_restores_and_says_bypass_is_back`, `test_traffic_reset_without_mark_keeps_the_usual_message`, `test_reconcile_suspends_missed_webhook_and_restores_after_purchase`, `test_reconcile_is_idempotent`, `test_reconcile_repushes_when_panel_limited_the_account_anyway`, `test_rollback_mode_false_clears_marks_silently`, `test_deeplinks_answer_with_one_button`, `test_traffic_deeplink_without_subscription_falls_through`
- `tests/services/test_campaign_attribution.py` — Python-модуль
  Классы: нет
  Функции: `test_returns_none_for_empty_slug`, `test_returns_none_when_campaign_not_found`, `test_partner_cannot_be_attributed_to_own_campaign` — Иначе партнёр накрутит себе регистрацию по собственной ссылке., `test_partner_own_campaign_stops_before_any_write` — Отказ обязан случиться ДО привязки реферала, а не только в бонусе., `test_existing_registration_blocks_second_bonus`, `test_successful_attribution_applies_bonus`, `test_unsuccessful_bonus_returns_none`, `test_partner_is_attached_as_referrer` — Кампания партнёра должна проставить его реферером — иначе он не, `test_link_partner_referral_writes_the_referrer` — Сам факт вызова ничего не гарантирует — проверяем результат., `test_existing_referrer_is_not_overwritten_by_campaign_partner` — Кто привёл первым, тот и получает комиссию — перебивать нельзя., `test_errors_are_swallowed_and_rolled_back` — Привязка кампании — побочный эффект: она не имеет права уронить
- `tests/services/test_campaign_bonus_expired_user.py` — Python-модуль
  Классы: нет
  Функции: `test_apply_campaign_bonus_refreshes_user_before_attribute_access` — Пользователь перечитывается асинхронно на входе — до любых sync-чтений, `test_apply_campaign_bonus_survives_refresh_failure` — Сбой refresh (например, PendingRollbackError) не роняет начисление —
- `tests/services/test_cart_cleanup_redis.py` — Python-модуль
  Классы: `PublicationProbe` (4 методов)
  Функции: `carts`, `test_finished_cart_does_not_delete_replacement`, `test_completed_global_and_subscription_aliases_are_both_removed`, `test_new_save_of_same_options_is_preserved`, `test_dispatch_completion_preserves_new_topup_intent`, `test_legacy_cart_cleanup_compares_payload`, `test_repriced_revision_still_cleans_its_aliases`, `test_subscription_only_cleanup_consumes_its_own_intent`, `test_save_publishes_matching_aliases_and_intent`, `test_old_intent_does_not_authorize_unconfirmed_replacement`, `test_independently_confirmed_subscription_carts_remain_eligible`, `test_expired_source_intent_cannot_use_neighbor_intent`, `test_stale_collected_revision_cannot_use_replacement_intent`, `test_legacy_global_intent_requires_explicit_confirmation`, `test_explicit_intent_clear_revokes_all_sources`, `test_topup_priority_uses_actual_cart_permission`, `test_old_gift_completion_preserves_replacement_and_independent_intent`, `test_old_gift_failure_or_update_cannot_overwrite_replacement`, `test_gift_metadata_update_preserves_ttl_and_other_source_permission`, `test_manual_gift_cleanup_preserves_replacement`, `test_gift_resume_does_not_delete_subscription_cart`, `test_manual_gift_shortfall_resume_preserves_new_selection`, `test_initial_gift_shortfall_does_not_replace_new_checkout`, `test_conditional_gift_publication_checks_snapshot_at_redis_boundary`, `test_conditional_gift_publication_fails_closed_without_redis`, `test_gift_resume_does_not_restore_cart_replaced_during_quote`, `test_manual_gift_requote_requires_explicit_confirmation_before_new_price_intent`, `test_price_metadata_change_always_revokes_original_permission`
- `tests/services/test_channel_check_uncertain.py` — Python-модуль
  Классы: нет
  Функции: `test_member_check_returns_true_when_user_is_member`, `test_member_check_returns_false_on_confirmed_user_not_found` — A BadRequest with 'user not found' is a confirmed non-membership —, `test_member_check_returns_none_on_network_error` — Transient network error must NOT be treated as 'not a member' —, `test_member_check_returns_none_on_bot_removed_from_channel` — Bot's own access loss is the operator's problem, not the user's —, `test_member_check_returns_none_on_unknown_bad_request` — Unrecognised BadRequest message — treat as uncertain rather than, `test_member_check_returns_none_on_double_rate_limit_failure` — Telegram is rate-limiting us hard — the user is not at fault., `test_member_check_returns_none_on_generic_exception` — Any unexpected error keeps the user's access., `test_check_user_subscriptions_preserves_last_known_on_uncertain` — Integration: when API check is uncertain (None), the public result
- `tests/services/test_checkout_squad_validation.py` — Python-модуль
  Классы: нет
  Функции: `test_only_fresh_valid_catalog_can_block_checkout`, `test_catalog_failure_preserves_existing_outage_checkout_semantics`, `test_preflight_is_bounded`, `test_cancellation_propagates`
- `tests/services/test_combo_promocode.py` — Python-модуль
  Классы: нет
  Функции: `test_combo_applies_both_days_and_balance` — Оба эффекта применяются: подписка продлена И баланс пополнен., `test_combo_days_failure_prevents_balance_credit` — Нет подписки → блок дней падает ДО начисления баланса: add_user_balance, `test_single_balance_type_untouched` — Одиночный BALANCE-код по-прежнему только пополняет баланс., `test_cabinet_bonus_set_requires_at_least_one_component` — Кабинетная валидация: в наборе должна быть хотя бы одна составляющая., `test_combo_grants_traffic` — Трафик из набора начисляется той же подписке, что и дни., `test_combo_without_traffic_does_not_touch_it` — traffic_gb=0 — начисления нет, старые коды ведут себя как прежде., `test_traffic_reactivates_limited_subscription` — Трафик чаще всего дарят тому, у кого он кончился, — подписка в LIMITED., `test_traffic_not_granted_on_unlimited_subscription` — Безлимит: Subscription.add_traffic ничего не делает — и обещать нечего., `test_target_subscription_picked_once_per_activation` — Дни и трафик обязаны попасть в ОДНУ подписку — выбор делается один раз., `test_traffic_only_applies_to_the_bonus_set_type` — Трафик — составляющая набора. Код другого типа его не раздаёт., `test_traffic_only_on_unlimited_does_not_burn_the_code` — Трафик — единственная составляющая, а подписка безлимитная: попытка не сгорает., `test_unlimited_subscription_keeps_other_bonuses` — Если в наборе есть что-то ещё — оно начисляется, а код не откатывается.
- `tests/services/test_crypto_fast_check.py` — Python-модуль
  Классы: нет
  Функции: `test_fast_lane_checks_only_fresh_unpaid_crypto_invoices`, `test_fast_lane_off_by_default_switch`, `test_crypto_screens_have_no_emoji_before_the_method_title`
- `tests/services/test_daily_charge_reset_policy_guard.py` — Python-модуль
  Классы: нет
  Функции: `test_detector_still_sees_every_known_site` — Детектор не ослеп: каждое известное место суточной оплаты он находит сам., `test_every_daily_charge_site_asks_the_policy` — Каждое место суточной оплаты — найденное, а не перечисленное — спрашивает общее правило., `test_daily_charge_sync_never_hardcodes_reset` — Решение о сбросе приходит выражением, а не константой в вызове синхронизации.
- `tests/services/test_daily_charge_traffic_reset.py` — Python-модуль
  Классы: нет
  Функции: `panel`, `test_charge_resets_traffic_when_enabled` — RESET_TRAFFIC_ON_PAYMENT=true — списание обнуляет счётчик и в панели, и у себя., `test_charge_keeps_traffic_when_disabled` — Выключатель выключен — счётчик остаётся нетронутым (прежнее поведение)., `test_charge_leaves_reset_to_panel_on_daily_strategy` — У тарифа суточный сброс панели — свой сброс не делаем, иначе две квоты за день.
- `tests/services/test_daily_limited_recovery.py` — Python-модуль
  Классы: нет
  Функции: `test_limited_subscription_is_charged_and_restored` — Наступили следующие сутки, счётчик будет обнулён — подписка снова активна., `test_limited_subscription_waits_for_next_day` — Сутки ещё не прошли — не возвращаем: иначе за день можно выбрать две квоты., `test_limited_subscription_untouched_when_reset_disabled` — Обнуления не будет — брать деньги нельзя, лимит так и остался бы исчерпанным., `test_limited_subscription_left_to_panel_on_daily_strategy` — Панель обнуляет счётчик сама раз в сутки — она же и снимет лимит.
- `tests/services/test_daily_reload_subscription.py` — Python-модуль
  Классы: нет
  Функции: `test_reload_daily_subscription_refetches_and_returns_loaded_object`, `test_reload_query_eager_loads_user_and_tariff` — The re-fetch must carry selectinload options for user AND tariff.
- `tests/services/test_daily_resume_traffic_reset.py` — Python-модуль
  Классы: нет
  Функции: `test_cabinet_resume_resets_traffic` — Возобновление с оплатой обнуляет счётчик, когда выключатель включён., `test_cabinet_resume_keeps_traffic_when_disabled` — Выключатель выключен — счётчик не трогаем., `test_cabinet_resume_leaves_daily_reset_to_panel` — Панель обнуляет сама раз в сутки — свой сброс не добавляем., `test_cabinet_resume_lifts_panel_limit_after_paid_reset` — Подписка была в лимите трафика: после оплаты со сбросом лимит в панели снимается явно., `test_cabinet_overdue_active_resumes_instead_of_pausing`
- `tests/services/test_daily_subscription_traffic_reset.py` — Python-модуль
  Классы: нет
  Функции: `test_defers_drop_when_panel_resets_and_user_over_limit` — MONTH + used 130 > нового лимита 100 → понижение ОТКЛАДЫВАЕТСЯ до сброса панели., `test_applies_drop_cleanly_when_user_under_limit` — MONTH + used 40 <= нового лимита 100 → лимит понижается, сброса used нет., `test_no_reset_tariff_resets_used_when_over_limit` — NO_RESET (панель сама не сбрасывает) + used 130 > 100 → лимит вниз + сброс used (clamp)., `test_forces_drop_after_grace_even_if_panel_resets` — MONTH, но докупка просрочена >40д → не ждём вечно: понижаем + добиваем used., `test_traffic_reset_only_loop_runs_processor` — #630055: с ВЫКЛЮЧЕННЫМИ суточными тарифами джоба сброса докупок всё равно
- `tests/services/test_daily_topup_resume_traffic_reset.py` — Python-модуль
  Классы: нет
  Функции: `test_topup_resume_resets_traffic_when_enabled` — RESET_TRAFFIC_ON_PAYMENT=true — списание после пополнения обнуляет счётчик и в панели, и у себя., `test_topup_resume_keeps_traffic_when_disabled` — Выключатель выключен — счётчик не трогаем (прежнее поведение)., `test_topup_resume_leaves_daily_reset_to_panel` — Панель обнуляет сама раз в сутки — свой сброс не добавляем, иначе две квоты за день., `test_topup_resume_lifts_panel_limit_after_paid_reset` — Подписка была в лимите трафика: после оплаты со сбросом лимит в панели снимается явно., `test_topup_resume_does_not_charge_limited_when_reset_impossible` — Списание счётчик не обнулит — деньги за сутки в лимите не берём, подписку не трогаем.
- `tests/services/test_daily_traffic_reset_policy.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_when_setting_enabled` — Выключатель включён — суточное списание обнуляет счётчик, как и любая оплата., `test_no_reset_when_setting_disabled` — Выключатель выключен — поведение прежнее, счётчик не трогаем., `test_no_reset_when_panel_already_resets_daily` — Панель сама обнуляет раз в сутки — второй сброс дал бы две квоты за день., `test_no_reset_when_global_strategy_is_daily` — У тарифа режим не задан — стратегия берётся из общей настройки., `test_reset_for_weekly_panel_strategy` — Недельный сброс панели суточную квоту не покрывает — обнуляем сами., `test_missing_tariff_falls_back_to_global` — Тариф не передан — решает общая настройка, без падения., `test_lift_uses_owner_account_in_single_tariff` — В одиночном режиме аккаунт панели — у пользователя, не у подписки.
- `tests/services/test_device_addon_cart_price.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_button_buys_lifetime_device_at_one_time_price`, `test_recomputed_price_equals_cabinet_quote` — Сравнение с настоящей ценой кабинета: разъедутся формулы — упадёт здесь., `test_seat_inside_tariff_is_added_without_a_charge`, `test_page_cart_paid_by_its_payment_keeps_checkout_price` — Цена, под которую пришли деньги, по-прежнему важнее пересчёта., `test_menu_offers_only_carts_payable_from_the_bot`, `test_price_helpers`
- `tests/services/test_device_addons_carry_over.py` — Python-модуль
  Классы: нет
  Функции: `test_monthly_devices_do_not_move_to_ultima`, `test_ultima_devices_move_down`, `test_same_device_price_moves`, `test_rule_matrix`, `test_unlimited_new_base_stays_unlimited`, `test_every_call_site_passes_tariffs` — Без old_tariff/new_tariff правило молча не применится — следим за всеми вызовами.
- `tests/services/test_disposable_email_service.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_extra_domains_tolerates_separators_case_and_at_sign`, `test_operator_extra_domains_block_even_without_fetched_list`, `test_parent_domain_matches_for_both_lists`, `test_disabled_flag_and_malformed_email`
- `tests/services/test_email_retry_service.py` — Python-модуль
  Классы: нет
  Функции: `test_backoff_outlives_short_lived_codes` — Фиксируем сам факт расхождения: без срока бэкофф шлёт письма после смерти кода., `test_expired_item_is_killed_without_sending`, `test_live_item_is_still_sent`, `test_item_without_expiry_is_unrestricted`, `test_auth_emails_declare_a_deadline` — Три письма с секретом внутри обязаны передавать срок годности в очередь., `test_body_is_purged_after_successful_delivery`, `test_body_is_purged_when_attempts_run_out`, `test_body_survives_between_attempts` — Пока попытки не исчерпаны, тело нужно — иначе повторять будет нечего., `test_stop_is_safe_without_start`, `test_pending_letters_are_closed_when_smtp_is_absent`, `test_absent_smtp_is_reported_once_not_per_letter` — Одно сообщение на всё время, и не ошибкой: это настройка, а не сбой доставки., `test_queue_resumes_after_smtp_appears`
- `tests/services/test_email_topup_notifications.py` — Python-модуль
  Классы: нет
  Функции: `sent` — Перехватывает send_notification роутера., `test_topup_notification_sent_for_email_user`, `test_topup_notification_skipped_for_telegram_user`, `test_topup_notification_skipped_without_email`, `test_topup_notification_swallows_router_errors`, `test_topup_hook_notifies_before_auto_purchase` — Порядок каналов: письмо о пополнении уходит ДО автопокупки из корзины,, `test_auto_purchase_notification_activated`, `test_auto_purchase_notification_renewed`, `test_auto_purchase_notification_skipped_for_telegram_user`, `test_auto_purchase_notification_swallows_errors`, `test_real_topup_template_renders_with_helper_context`, `test_real_activated_template_renders_with_helper_context`, `test_real_renewed_template_renders_with_helper_context`, `test_trial_conversion_labeled_activated_not_renewed` — Пин: сайты автопокупки тарифа/суточного/extend не должны помечать
- `tests/services/test_env_admin_block_protection.py` — Python-модуль
  Классы: нет
  Функции: `env_admin`, `test_predicate_covers_admin_ids_and_admin_emails`, `test_admin_panel_ban_refuses_env_admin`, `test_cabinet_disable_user_refuses_env_admin`, `test_blocked_users_scan_skips_env_admin`, `test_cabinet_restores_stale_blocked_admin_with_invite_only_off` — The gate only emits VERIFIED_ADMIN while invite-only is on — recovery must not depend on it., `test_cabinet_still_refuses_a_blocked_ordinary_user`, `test_middleware_heals_the_stale_blocked_flag_on_an_env_admin` — Letting the admin through is not enough — the flag also suppresses reactivation.
- `tests/services/test_expiring_notification_autopay_price.py` — Python-модуль
  Классы: нет
  Функции: `test_extra_devices_price_turns_promise_into_low_balance_warning`, `test_enough_balance_keeps_the_promise_with_real_cost`, `test_without_real_price_falls_back_to_tariff_period_price`, `test_autopay_renewal_price_uses_the_charge_calculation`, `test_autopay_renewal_price_is_none_when_calculation_fails`
- `tests/services/test_expiring_notification_days_placeholder.py` — Python-модуль
  Классы: нет
  Функции: `test_expiring_paid_supports_days_placeholder`
- `tests/services/test_expiry_asks_the_panel_first.py` — Python-модуль
  Классы: нет
  Функции: `test_alive_in_the_panel_is_not_expired_and_takes_the_panel_date`, `test_expired_in_the_panel_is_expired_in_the_bot`, `test_silent_panel_falls_back_to_the_bot_date` — Панель не отвечает — последняя известная истина у бота, гасим по ней.
- `tests/services/test_format_email_datetime.py` — Python-модуль
  Классы: нет
  Функции: `test_default_format_is_locale_independent` — The fallback shape must be ``DD.MM.YYYY, HH:MM`` — no month, `test_explicit_fmt_arg_overrides_settings` — Caller-provided ``fmt`` wins over the global setting — lets, `test_settings_override_takes_effect_without_restart` — An admin who updates ``EMAIL_DATE_FORMAT`` via system_settings, `test_empty_or_invalid_setting_falls_back_to_default` — Operator misconfiguration (empty / non-string) must not crash, `test_localizes_to_configured_timezone` — UTC datetime gets shifted to ``settings.TIMEZONE`` before formatting., `test_naive_datetime_is_treated_as_utc` — Some legacy paths still pass naive datetimes. Treat them as, `test_iso_string_is_parsed_and_reformatted` — Legacy callers that pre-isoformat'd their datetime get parsed, `test_unparseable_string_passes_through` — If the caller pre-formatted the string in some custom shape we, `test_empty_input_returns_placeholder` — ``None`` / empty must not render the literal Python repr or, `test_custom_placeholder_respected`, `test_non_datetime_non_string_input_returns_placeholder` — Garbage input (int, list, etc.) → placeholder. Defensive., `test_no_microseconds_in_output` — REGRESSION (2026-05-18): user saw, `test_no_offset_in_output` — Non-UTC TZ values also must not leak the offset into the email., `test_notification_delivery_service_uses_format_email_datetime` — ``notify_subscription_expiring`` and ``notify_autopay_success``, `test_auto_purchase_service_sends_machine_dates_to_the_cabinet` — Даты в WebSocket-событиях кабинета — не для человека., `test_helper_signature_is_stable` — The helper is called from 9+ production sites. Lock its
- `tests/services/test_friend_days_reward.py` — Python-модуль
  Классы: нет
  Функции: `test_both_get_days_when_friend_connects`, `test_reward_is_given_only_once`, `test_no_inviter_no_reward`, `test_old_account_is_not_a_friend`, `test_no_cap_on_number_of_friends`, `test_inviter_on_trial_is_rewarded_too`, `test_inviter_without_active_subscription_gets_nothing_but_friend_does`, `test_expired_friend_subscription_gets_nothing`
- `tests/services/test_fsm_pool_redis.py` — Python-модуль
  Классы: нет
  Функции: `redis_url`, `test_fsm_burst_waits_for_real_pool_and_releases_connections`, `test_cancelled_pool_waiters_leave_connection_reusable`
- `tests/services/test_full_sync_lock.py` — Python-модуль
  Классы: нет
  Функции: `test_second_full_sync_is_refused_while_first_runs`, `test_lock_is_released_after_a_failure`, `test_scheduler_sees_a_manual_full_sync_as_running`
- `tests/services/test_funnel_app_idle.py` — Python-модуль
  Классы: нет
  Функции: `test_known_app_name`, `test_unknown_app_is_empty_string`, `test_no_devices_or_panel_error_is_none`, `test_texts`, `test_no_bypass_step_when_trial_has_no_bypass`
- `tests/services/test_gift_action_callbacks.py` — Python-модуль
  Классы: нет
  Функции: `action_payload` — Versioned callback contract, independent of handler admission checks., `test_old_gift_action_cannot_purchase_or_cancel_current_selection`, `test_bound_keyboard_keeps_labels_navigation_and_telegram_callback_limit`
- `tests/services/test_gift_claim_notify.py` — Python-модуль
  Классы: нет
  Функции: `test_email_recipient_and_buyer_both_get_claim_link`, `test_telegram_recipient_is_not_auto_dmed_but_buyer_still_gets_link`, `test_send_failure_never_raises`, `test_non_gift_purchase_is_a_noop`, `test_email_recipient_gets_admin_override_when_saved` — Жалоба из «Багов»: шаблон письма нельзя было поменять со стандартного., `test_override_lookup_uses_the_gift_template_type_and_claim_context` — Override ищется под тем же типом, что и дефолт, и с тем же контекстом (ссылка на claim)., `test_buyer_backstop_uses_its_own_template_and_admin_override` — Письмо покупателю со ссылкой раньше было зашито в код на двух языках —, `test_disabled_types_are_not_sent` — Выключатель писем: отключённый тип пропускается, остальные уходят.
- `tests/services/test_gift_claim_service.py` — Python-модуль
  Классы: нет
  Функции: `test_claim_gift_bot_origin_canonical_code` — Claiming a bot-origin gift via canonical GIFT_<59> code binds and delivers subscription., `test_claim_gift_cabinet_origin_telegram_deeplink` — Claiming a cabinet/landing origin gift via Telegram deep-link URL binds and delivers., `test_claim_gift_web_url_and_full_token_inputs` — Claiming via cabinet claim URL and raw 64-char token works identically., `test_legacy_short_code_support_flag` — Legacy short codes succeed when allow_legacy_short=True and fail with GiftClaimNotFoundError when False., `test_self_claim_rejected` — Buyer attempting to claim their own gift raises GiftClaimSelfActivationError and does not mutate purchase., `test_claim_already_owned_by_another_user_rejected` — Attempting to claim a gift bound or delivered to another user raises GiftClaimAlreadyOwnedError., `test_idempotent_repeated_claim_by_same_user` — Repeated claim by the SAME user returns DELIVERED purchase without reactivating or extending twice., `test_unactivatable_status_rejected` — Gifts in FAILED, PENDING, or other unactivatable statuses raise GiftClaimNotActivatableError., `test_malformed_or_nonexistent_input_raises_not_found` — Malformed strings, bad schemes, empty strings, and non-existent tokens raise GiftClaimNotFoundError., `test_claim_bound_gift_for_user_directed_callback` — claim_bound_gift_for_user by purchase_id activates directed gifts for the bound claimant., `test_activation_failure_rolls_back_cleanly` — When underlying activate_purchase fails, exception propagates and transaction rolls back., `test_underscore_wildcard_code_does_not_match_foreign_gift` — `_` в коде — литерал, а не LIKE-wildcard: код из подчёркиваний не забирает чужой подарок.
- `tests/services/test_gift_confirmation_selection.py` — Python-модуль
  Классы: нет
  Функции: `test_confirmation_preserves_selection_changed_during_purchase`, `test_success_does_not_clear_selection_started_during_result_delivery`, `test_success_delivery_failure_keeps_checkout_for_idempotent_retry`
- `tests/services/test_gift_fsm_redis.py` — Python-модуль
  Классы: `MutationProbe` (6 методов)
  Функции: `test_new_selection_survives_at_fsm_write_boundary`, `test_conditional_fsm_update_supports_absent_keys_and_configured_ttl`, `test_conditional_fsm_redis_failure_does_not_fall_back_to_unconditional_clear`, `test_legacy_checkout_identity_creation_cannot_overwrite_new_selection`, `test_gift_resume_cannot_overwrite_selection_at_fsm_write`, `test_conditional_fsm_transition_sets_both_ttls_and_preserves_other_fields`, `test_invalid_fsm_transition_ttl_never_partially_changes_selection`, `test_bound_cancel_preserves_changes_at_atomic_fsm_write`, `test_period_selection_preserves_cart_permissions_and_atomic_fsm`, `test_navigation_rejects_selection_changed_at_redis_write`, `test_readonly_navigation_does_not_extend_fsm_ttl_or_cart_permission`
- `tests/services/test_gift_history_service.py` — Python-модуль
  Классы: нет
  Функции: `test_list_sender_gifts_source_neutral_and_status_filtering` — History returns bot-, cabinet-, and landing-origin gifts for the buyer,, `test_list_sender_gifts_stable_ordering_with_equal_timestamps` — Ordering must be strictly `created_at DESC, id DESC` for deterministic pagination., `test_list_sender_gifts_pagination_and_boundary_clamping` — Pagination metadata must be accurate and limit/offset parameters clamped., `test_list_sender_gifts_returns_more_than_legacy_fifty_item_cap` — The cabinet's 100-item request must not be silently truncated to the old 50-item cap., `test_list_sender_gifts_graceful_on_missing_deleted_tariff` — If a tariff was deleted (ON DELETE SET NULL), the history item must load gracefully., `test_safe_recipient_display_formatting` — Safe recipient display formats username or masked email without leaking private data (names, IDs)., `test_get_sender_gift_exact_owner_and_status_checks` — get_sender_gift returns the item only if buyer_id matches and status is eligible., `test_has_sender_gifts_lightweight_existence_query` — has_sender_gifts returns boolean indicating if buyer owns any eligible gifts., `test_gift_history_item_immutability_and_artifacts` — GiftHistoryItem is a frozen immutable dataclass that builds canonical claim artifacts., `test_gift_history_service_is_purely_read_only` — History queries must never modify database state or create transactions.
- `tests/services/test_gift_navigation_selection.py` — Python-модуль
  Классы: нет
  Функции: `test_gift_navigation_preserves_selection_changed_during_loading`, `test_back_periods_carries_original_snapshot_into_render_helper`
- `tests/services/test_gift_payment_log_safety.py` — Python-модуль
  Классы: нет
  Функции: `test_gift_payment_paths_do_not_log_purchase_token_fragments`
- `tests/services/test_gift_purchase_service.py` — Python-модуль
  Классы: нет
  Функции: `test_is_gift_enabled_reflects_cabinet_gift_setting` — Missing or non-true CABINET_GIFT_ENABLED disables the service., `test_list_gift_offers_returns_empty_when_feature_disabled` — When CABINET_GIFT_ENABLED is missing or false, catalog is empty., `test_list_gift_offers_filters_and_orders_tariffs` — Catalog only contains active, show_in_gift tariffs with prices, ordered by display_order then id., `test_list_gift_offers_applies_sender_discounts_and_clamps` — Sender promo-group and promo-offer discounts are applied in quotes and clamped to >= 1 kopek., `test_quote_gift_purchase_success_and_errors` — quote_gift_purchase returns typed GiftQuote on valid selection and raises typed errors on invalid ones., `test_purchase_gift_from_balance_success_bot_mode` — Successful balance purchase: exact debit, GIFT_PAYMENT transaction, promo offer consumed, paid purchase created., `test_purchase_gift_from_balance_cabinet_recipient` — Cabinet mode with GiftRecipient persists recipient fields and custom transaction description., `test_purchase_gift_insufficient_balance_rolls_back` — Insufficient balance raises typed error and leaves DB untouched., `test_purchase_gift_restricted_user` — User with restriction_subscription cannot buy gifts., `test_purchase_gift_stale_expected_price_rejected` — If expected price does not match fresh price calculation, fail without debit., `test_idempotent_replay_and_conflict` — Repeating same idempotency key returns original result; changing input raises conflict., `test_replay_never_attaches_another_gifts_transaction` — Повтор обязан вернуть списание ИМЕННО этого подарка либо ничего.
- `tests/services/test_gift_selection_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_period_selection_uses_its_own_checkout_and_preserves_newer_fsm`
- `tests/services/test_gift_token_prefix_threshold.py` — Python-модуль
  Классы: нет
  Функции: `test_generated_token_is_64_chars`, `test_threshold_accepts_every_legitimate_truncation`, `test_threshold_rejects_the_old_short_floor`, `test_canonical_bot_gift_claim_link_meets_threshold` — Canonical build_bot_gift_claim_link produces links accepted by the threshold., `test_legacy_12_char_slice_is_rejected_by_threshold` — Legacy 12-char slice is strictly rejected by the 48-char security threshold.
- `tests/services/test_gift_topup_flow.py` — Python-модуль
  Классы: `MockRedis` (6 методов), `TestGiftInsufficientBalanceAndCart` (6 методов), `TestGiftTopupSuccessKeyboardAndResume` (8 методов), `TestGiftAutoPurchaseAndIsolation` (7 методов), `TestGiftAutoPurchaseDeliveryAndPriceChangeSafeguards` (6 методов)
  Функции: `mock_redis`, `test_cart_service`, `mock_db_user`, `mock_db`, `mock_bot`, `mock_callback`, `memory_state`, `sample_quote`, `sample_purchase_result`
- `tests/services/test_grace_access_sqlite_safety.py` — Python-модуль
  Классы: нет
  Функции: `test_sqlite_delete_guard_preserves_open_snapshot_and_cascades_completed_history`, `test_sqlite_predelete_noop_write_blocks_a_concurrent_pending_insert`, `test_sqlite_user_lock_blocks_a_new_subscription_during_full_delete`, `test_sqlite_delete_guard_also_blocks_user_cascade`
- `tests/services/test_guest_notification_switch.py` — Python-модуль
  Классы: нет
  Функции: `test_disabled_main_email_does_not_silence_credentials`, `test_enabled_main_email_sends_both`
- `tests/services/test_guest_purchase_campaign.py` — Python-модуль
  Классы: нет
  Функции: `test_campaign_is_attributed_after_delivery`, `test_purchase_without_slug_is_skipped`, `test_gift_is_not_attributed_to_recipient` — Гифт активирует получатель, а по рекламе приходил покупатель — записать, `test_attribution_failure_does_not_propagate` — Подписка уже доставлена и оплачена — упасть здесь значит уронить
- `tests/services/test_guest_purchase_daily_tariff.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/services/test_guest_purchase_existing_email_takeover.py` — Python-модуль
  Классы: нет
  Функции: `test_existing_passwordless_user_gets_no_credentials`, `test_concurrent_create_race_gives_no_credentials` — Ветка IntegrityError (пользователь создан параллельно) — то же правило.
- `tests/services/test_guest_purchase_fulfillment.py` — Python-модуль
  Классы: нет
  Функции: `test_fulfill_purchase_passes_purchase_context_to_user_resolution`
- `tests/services/test_guest_purchase_referral_code.py` — Python-модуль
  Классы: нет
  Функции: `test_new_email_user_is_created_with_referral_code` — A landing-page email purchase must persist `referral_code` on the new, `test_new_telegram_user_is_created_with_referral_code` — Same guarantee for the telegram-username guest-purchase branch., `test_existing_email_user_without_referral_code_is_backfilled` — Legacy users created before the fix (with referral_code=NULL) must be, `test_existing_email_user_with_referral_code_is_not_overwritten` — Idempotency: if the user already has a referral_code, do not regenerate
- `tests/services/test_http_logging_safety.py` — Python-модуль
  Классы: нет
  Функции: `http_error`, `test_http_errors_do_not_leak_headers`, `test_chained_group_traceback_and_original_exception`, `test_persisted_context_and_traceback_are_safe`, `test_telegram_traceback_is_safe`, `test_container_cycles_and_header_strings`, `test_reused_exception_in_cause_and_group_cannot_leak_url`, `test_telegram_interpolated_headers_are_redacted`, `test_stdlib_record_is_not_persisted_in_context`, `test_exception_object_as_exc_info_keeps_traceback`, `test_provider_retries_and_final_failure_use_safe_logs`
- `tests/services/test_invite_only_settings.py` — Python-модуль
  Классы: нет
  Функции: `test_invite_only_defaults_are_backward_compatible`, `test_invite_only_settings_are_exposed_in_registration_access_category`
- `tests/services/test_invoice_failure_alert.py` — Python-модуль
  Классы: нет
  Функции: `clean_state`, `send`, `test_blocked_provider_alerts_on_first_refusal`, `test_ordinary_failures_need_threshold`, `test_success_resets_the_count`, `test_old_failures_fall_out_of_the_window`, `test_cooldown_stops_repeats_then_reminds`, `test_block_is_not_silenced_by_a_recent_failure_alert`, `test_providers_are_counted_separately`, `test_telegram_failure_does_not_reach_the_client`, `test_method_blocked_reaches_admins_from_real_payment`, `test_network_failure_of_cryptobot_waits_for_threshold`
- `tests/services/test_legal_consent.py` — Python-модуль
  Классы: нет
  Функции: `test_both_documents_required_by_default`, `test_setting_disables_the_gate`, `test_prechecked_flag_is_reported`, `test_document_hidden_from_web_is_not_required` — Документ только для бота нельзя прочитать в кабинете — галочки по нему нет., `test_empty_document_is_not_required`, `test_no_documents_at_all_disables_the_gate` — Иначе установка без юр. документов заблокировала бы регистрацию всем., `test_broken_document_read_does_not_block_login`, `test_missing_documents_reports_unchecked_boxes`, `test_record_consent_writes_a_row_per_document`, `test_record_consent_with_no_documents_is_a_noop`, `test_gate_rejects_missing_consent`, `test_gate_passes_with_full_consent`, `test_gate_is_transparent_when_disabled` — Выключенная настройка не должна ломать регистрацию без чекбоксов.
- `tests/services/test_live_menu.py` — Python-модуль
  Классы: `FakeRedis` (6 методов)
  Функции: `env`, `test_live_menu_is_wired` — Пины: при переносе на новый upstream эти строки теряются молча, а остальные тесты зелёные., `test_press_on_live_menu_forgets_it_and_passes_through` — Нажатие на живом меню — дальше подменю: фон это сообщение больше не трогает., `test_try_edit_remembers_live_menu`, `test_try_send_remembers_live_menu_only_when_enabled`, `test_live_menu_fingerprint_tracks_only_visible_changes` — Меню показывает целые ГБ: доли гигабайта не повод править сообщение., `test_sub_gigabyte_change_goes_to_db_without_edit`, `test_subscription_changed_after_snapshot_keeps_db_value` — Сброс трафика коммитит БД до вызова панели: снимок, взятый чуть позже, ещё со старым расходом., `test_visible_change_edits_the_same_message`, `test_new_menu_during_build_is_not_overwritten`, `test_press_during_edit_is_not_undone` — Нажали на меню, пока фон ждал ответа Telegram: запись снимка не возвращает ключ., `test_telegram_errors`, `test_flood_limit_aborts_the_pass`, `test_busy_bot_skips_the_pass`, `test_load_or_switch_off_during_pass_stops_it` — Нагрузка или выключение в кабинете посреди прохода: остальные меню не трогаем., `test_panel_down_still_redraws_from_db_but_backs_off`, `test_interval_backs_off_under_load_and_resets_when_idle`
- `tests/services/test_log_level_resolver.py` — Python-модуль
  Классы: нет
  Функции: `test_resolves_canonical_uppercase_names`, `test_resolves_lowercase_names` — REGRESSION: ``LOG_LEVEL=warning`` from .env must NOT return, `test_resolves_mixed_case_and_whitespace` — Whitespace and mixed-case variants normalize to the canonical level., `test_lowercase_does_not_return_the_logger_function` — The exact failure mode: the ``logging`` module has BOTH, `test_unknown_or_empty_falls_back_to_default`, `test_non_string_input_falls_back_to_default` — The resolver accepts only str input. Anything else → default., `test_default_argument_is_respected` — Custom default values flow through the fallback paths., `test_resolver_output_is_acceptable_to_structlog` — REGRESSION smoke: ``make_filtering_bound_logger`` must accept
- `tests/services/test_main_menu_button_cabinet_mode.py` — Python-модуль
  Классы: нет
  Функции: `test_back_to_menu_is_not_in_cabinet_path_mapping` — REGRESSION: ``back_to_menu`` must NOT be a key in, `test_back_to_menu_is_not_in_cabinet_style_mapping` — Dead config caught: if ``back_to_menu`` were styled per-section, `test_build_miniapp_or_callback_button_falls_through_for_back_to_menu` — Belt-and-suspenders: even in cabinet mode, calling, `test_build_main_menu_button_returns_callback_button` — The dedicated helper always returns a callback button. No mode, `test_build_main_menu_button_body_does_not_reference_cabinet_mode` — Pin the design contract: ``build_main_menu_button`` ignores, `test_topup_success_keyboard_main_menu_button_is_callback` — Source-level pin: ``app/services/payment/common.py`` must use, `test_no_other_callsite_wraps_back_to_menu_in_miniapp_helper` — AST-based scan: no callsite anywhere in ``app/`` may invoke, `test_home_button_key_is_not_in_broadcast_cabinet_path_mapping` — Structural pin (per architect-review top priority): the foot-gun, `test_home_button_key_is_not_in_cabinet_miniapp_button_keys` — Belt-and-suspenders set-membership pin., `test_topup_success_keyboard_renders_callback_main_menu_button_in_cabinet_mode` — REGRESSION (behavioural): ``build_topup_success_keyboard``,
- `tests/services/test_maintenance_restart.py` — Python-модуль
  Классы: `TestCacheDoesNotResurrectManualMode` (3 методов), `TestEnvPinning` (2 методов), `TestPanelWarnsWhenEnvLocked` (2 методов), `TestReferralKeysAreEditable` (1 методов)
  Функции: `service`
- `tests/services/test_marketing_review_fixes.py` — Python-модуль
  Классы: нет
  Функции: `test_topup_message_says_amount_and_new_balance_without_transaction_id`, `test_topup_message_without_known_balance_has_no_balance_line`, `test_bypass_tariff_is_not_shown_as_a_traffic_cap`, `test_traffic_warning_key_changes_with_limit`, `test_panel_expiry_reminders_yield_to_bot`, `test_panel_reminders_are_fallback_when_bot_notifications_off`, `test_texts_follow_owner_terms`
- `tests/services/test_mass_send_queue.py` — Python-модуль
  Классы: нет
  Функции: `test_job_is_processed_in_batches_and_the_admin_gets_the_summary`, `test_restart_continues_from_the_saved_position_without_resending`, `test_stopping_the_bot_keeps_the_job_resumable`, `test_an_error_marks_the_job_failed_and_tells_the_admin`, `test_a_cancelled_job_is_not_processed`, `test_finished_jobs_are_not_resumed`, `test_broadcast_config_survives_a_round_trip`, `test_interrupted_broadcast_is_resumed_from_its_position`, `test_decision_log_records_counts_and_never_breaks_the_caller`
- `tests/services/test_menu_layout_service.py` — Python-модуль
  Классы: нет
  Функции: `test_build_button_connect_direct_mode_with_url` — Тест: кнопка connect с open_mode=direct и валидным URL должна создавать WebAppInfo., `test_build_button_connect_direct_mode_with_subscription_url` — Тест: кнопка connect с open_mode=direct должна получать URL из подписки., `test_build_button_connect_callback_mode` — Тест: кнопка connect с open_mode=callback должна создавать callback кнопку., `test_build_button_connect_direct_mode_fallback_to_callback` — Тест: кнопка connect с open_mode=direct без URL должна fallback на callback., `test_saved_connect_layout_hides_inactive_subscription_without_link`
- `tests/services/test_monitoring_cycle_connection_postgres.py` — Python-модуль
  Классы: нет
  Функции: `test_channel_checks_do_not_leave_outer_connection_idle_in_transaction`
- `tests/services/test_monitoring_notification_switches.py` — Python-модуль
  Классы: нет
  Функции: `test_global_switch_stops_monitoring_notification_queries`, `test_expiration_state_updates_even_when_notifications_are_disabled`
- `tests/services/test_monitoring_send_timeout.py` — Python-модуль
  Классы: нет
  Функции: `test_text_send_times_out_and_skips`, `test_photo_send_times_out_and_skips`
- `tests/services/test_monitoring_session_recovery.py` — Python-модуль
  Классы: нет
  Функции: `test_failed_step_leaves_session_usable_for_next_step`, `test_failed_monitoring_log_does_not_break_session`, `test_daily_charges_continue_after_failed_subscription`, `test_daily_charges_skip_subscription_deleted_mid_run`
- `tests/services/test_monitoring_warning_dedupe.py` — Python-модуль
  Классы: нет
  Функции: `test_traffic_warning_sent_once_when_redis_is_down`, `test_blocked_user_is_not_retried_every_cycle`, `test_local_mark_expires`, `test_low_balance_alert_sent_once_when_redis_is_down`, `test_expiring_reminders_query_count_does_not_grow_per_subscription`, `test_expiring_reminders_survive_one_broken_subscription`
- `tests/services/test_notification_delivery_preferences.py` — Python-модуль
  Классы: нет
  Функции: `test_global_switch_blocks_regular_notifications`, `test_transactional_messages_bypass_global_switch`, `test_per_user_preferences_block_matching_notifications`, `test_referral_switch_is_enforced_by_unified_delivery`, `test_blocked_user_does_not_receive_unrelated_notifications`, `test_promo_opt_out_suppresses_the_message_but_keeps_the_discount` — Отказ от промо-уведомлений глушит СООБЩЕНИЕ, но не отбирает скидку.
- `tests/services/test_notification_settings_in_db.py` — Python-модуль
  Классы: нет
  Функции: `isolated_settings` — Настройки — глобальный объект: значения возвращаются после теста; файла по умолчанию нет., `test_keys_are_bot_settings_in_the_user_notifications_category`, `test_getters_read_live_settings_not_the_file`, `test_getters_clamp_bad_values`, `test_legacy_file_is_imported_once_and_never_overrides_the_db`, `test_missing_or_broken_legacy_file_is_ignored`, `test_followups_do_not_query_when_all_three_switches_are_off` — Все три выключены — мониторинг не ходит в базу и ничего не шлёт.
- `tests/services/test_paid_daily_reset_worker_budget.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_recovery_wall_budget_preserves_expiry_queue_progress`
- `tests/services/test_panel_conflict_reported_once.py` — Python-модуль
  Классы: `Row`
  Функции: `test_conflict_is_reported_as_an_error_only_once`, `test_queue_parks_a_conflicted_subscription_instead_of_retrying`, `test_queue_still_retries_an_ordinary_failure`, `test_recovery_scan_skips_a_parked_subscription_until_the_pause_ends`, `test_a_new_purchase_on_a_parked_subscription_is_retried_at_once`, `test_cabinet_purchase_reloads_objects_after_the_panel_sync_before_using_them`
- `tests/services/test_panel_deletion_respects_delete_mode.py` — Python-модуль
  Классы: нет
  Функции: `test_panel_deletion_is_gated_or_explicitly_deliberate`, `test_deliberate_list_has_no_stale_entries` — Список исключений не должен пережить сами удаления.
- `tests/services/test_panel_online.py` — Python-модуль
  Классы: нет
  Функции: `test_api_sorts_users_by_online_at_like_panel_table`, `test_collects_accounts_until_mark_is_older_than_window`, `test_never_connected_account_ends_the_list`, `test_pages_through_while_whole_page_is_online`, `test_page_limit_stops_runaway_listing`, `test_window_matches_panel_green_dot`, `test_user_is_connected_by_any_of_his_panel_keys`, `test_cached_between_calls_and_none_when_panel_fails`, `test_panel_failure_is_remembered_so_list_does_not_wait_again` — Панель лежит — список открывается сразу без отметок, а не ждёт таймаут на каждом открытии., `test_who_is_online_is_recounted_at_request_time_not_at_fetch_time` — Ответ панели живёт в кэше 20 секунд — «онлайн» за это время обязан гаснуть сам., `test_snapshot_gives_each_row_its_own_mark` — Строке списка нужна отметка, а не готовое «да/нет»: по ней кабинет сам гасит точку., `test_several_accounts_of_one_person_give_the_freshest_mark` — Мультитариф: у человека несколько аккаунтов панели — считается самый свежий.
- `tests/services/test_panel_user_id_resolvers.py` — Python-модуль
  Классы: нет
  Функции: `test_bot_single_tariff_falls_back_to_user`, `test_bot_no_subscription_uses_user_panel_id`, `test_bot_never_returns_legacy_uuid` — Пустой remnawave_id не должен подмениться легаси-uuid'ом ни в одном режиме., `test_cabinet_single_tariff_uses_user_panel_id`, `test_cabinet_no_subscription_uses_user_panel_id`, `test_cabinet_never_returns_legacy_uuid`
- `tests/services/test_payer_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_username_is_not_prefixed_twice`, `test_name_is_used_without_username`, `test_telegram_user_without_any_names_is_named_by_id`, `test_verified_email_is_the_contact`, `test_email_user_is_identified_by_internal_id`, `test_broken_telegram_name_does_not_reach_the_provider` — Обрезанный эмодзи (одинокий суррогат) и управляющие символы из имени не уходят в запрос., `test_whitespace_only_fields_fall_through`, `test_overlong_values_are_cut`, `test_platega_metadata_has_both_string_fields`, `test_guest_with_email_contact`, `test_guest_with_telegram_contact`, `test_guest_without_contact_is_still_filled`, `test_resolve_user_payer_reads_the_user`, `test_resolve_user_payer_without_the_user_is_still_filled`, `test_resolve_user_payer_survives_a_database_error` — Данные плательщика не имеют права сорвать создание платежа., `test_resolve_guest_payer_reads_the_purchase`, `test_resolve_guest_payer_without_the_purchase_is_still_filled`, `test_platega_email_never_blocks_payment` — Почту не спрашиваем и платёж из-за неё не отклоняем — всегда валидный адрес., `test_platega_metadata_without_email_falls_back_to_synthetic`, `test_web_user_with_invalid_email_still_pays`, `test_telegram_user_is_identified_by_telegram_id_and_username`, `test_unverified_email_is_never_the_contact` — Адрес назначается до подтверждения, Wata фискализирует платёж — чек чужому ящику не нужен.
- `tests/services/test_payment_common.py` — Python-модуль
  Классы: нет
  Функции: `anyio_backend`, `test_send_payment_success_notification_recovers_missing_greenlet`
- `tests/services/test_payment_error_navigation.py` — Python-модуль
  Классы: нет
  Функции: `test_stars_enrollment_error_has_back_and_support`, `test_stars_processing_crash_has_back_and_support`, `test_platega_creation_failure_without_alternatives_has_navigation`
- `tests/services/test_payment_fallback.py` — Python-модуль
  Классы: нет
  Функции: `test_failed_provider_is_removed_and_others_stay`, `test_no_alternatives_returns_none`, `test_text_has_amount`, `test_cryptobot_payload_gives_kopeks`, `test_answer_creation_failed_offers_other_methods`, `test_answer_creation_failed_falls_back_to_old_text`, `test_payment_error_keyboard_hides_support_when_disabled`, `test_exact_mode_removes_only_that_method`
- `tests/services/test_payment_problem_alerts.py` — Python-модуль
  Классы: нет
  Функции: `test_alert_text_escapes_and_lists_details`, `test_alert_goes_to_errors_topic_with_given_bot`, `test_alert_without_bot_and_notifications_off_is_quiet`, `test_alert_never_raises`, `test_guest_purchase_amount_mismatch_alerts_once`, `test_xrocket_paid_invoice_without_amount_alerts_once`, `test_platega_paid_payment_for_missing_user_alerts`
- `tests/services/test_payment_provider_configured.py` — Python-модуль
  Классы: нет
  Функции: `test_every_listed_provider_has_both_predicates` — Список ниже — контракт с create_payment_router, а не украшение., `test_enabled_is_flag_and_configured`, `test_enabled_is_flag_when_credentials_are_present` — С заполненными кредами включение решает только флаг., `test_missing_credential_disables_the_provider` — Убрали любую креду — провайдер не настроен и не включён.
- `tests/services/test_payment_reversal_alert.py` — Python-модуль
  Классы: нет
  Функции: `test_paid_platega_payment_reversal_alerts_and_keeps_is_paid`, `test_late_pending_on_paid_payment_is_not_an_alert`
- `tests/services/test_payment_screens_plain.py` — Python-модуль
  Классы: нет
  Функции: `test_payment_button_names_use_premium_icons`, `test_payment_screen_titles_start_without_emoji`, `test_every_method_button_gets_a_premium_icon`, `test_screen_titles_have_no_leading_emoji`
- `tests/services/test_payment_service_cryptobot.py` — Python-модуль
  Классы: `StubCryptoBotService` (2 методов), `DummySession` (4 методов), `DummyLocalPayment` (1 методов), `StubCryptoBotService` (2 методов)
  Функции: `anyio_backend`, `test_create_cryptobot_payment_success`, `test_create_cryptobot_payment_returns_none_when_service_missing`, `test_create_cryptobot_payment_handles_empty_response`
- `tests/services/test_payment_service_modularity.py` — Python-модуль
  Классы: нет
  Функции: `test_payment_service_exposes_provider_methods` — Каждый mixin обязан добавить публичный метод в PaymentService., `test_payment_service_mro_contains_all_mixins` — Убеждаемся, что сервис действительно включает все mixin-классы.
- `tests/services/test_payment_service_pay2328.py` — Python-модуль
  Классы: `StubPay2328Service` (3 методов), `DummySession` (4 методов), `DummyLocalPayment` (1 методов)
  Функции: `anyio_backend`, `test_create_pay2328_payment_success`, `test_create_pay2328_payment_returns_none_without_service`, `test_create_pay2328_payment_handles_empty_response`, `test_sync_pay2328_payment_status_success`, `test_sync_pay2328_payment_status_without_response`, `test_replayed_webhook_does_not_touch_credited_payment`, `test_refund_status_is_recorded_without_second_credit`, `test_non_paid_statuses_never_credit`, `test_manual_review_status_alerts_admins_once`, `test_waiting_statuses_do_not_alert`, `test_cabinet_names_every_pay2328_status`
- `tests/services/test_payment_service_platega.py` — Python-модуль
  Классы: `DummySession` (2 методов), `DummyLocalPayment` (1 методов), `StubPlategaService` (3 методов)
  Функции: `anyio_backend`, `test_create_platega_payment_success`, `test_create_platega_payment_respects_limits_and_configuration`, `test_create_platega_payment_handles_service_errors`, `test_get_platega_active_methods_parses_and_filters`, `test_get_platega_active_methods_returns_default`, `test_platega_method_display_helpers`
- `tests/services/test_payment_service_stars.py` — Python-модуль
  Классы: `DummyBot` (3 методов), `DummySession` (4 методов), `DummySubscription` (1 методов), `DummyUser` (1 методов), `DummyTransaction` (1 методов), `DummySubscriptionService` (2 методов)
  Функции: `anyio_backend` — Ограничиваем anyio тесты только бэкендом asyncio., `test_create_stars_invoice_calculates_stars` — Количество звёзд должно рассчитываться по курсу с округлением вниз и нижним порогом 1., `test_create_stars_invoice_enforces_minimum_star` — При слишком маленькой сумме минимум должен составлять 1 звезду., `test_create_stars_invoice_uses_explicit_stars` — Если передано значение stars_amount, функция должна использовать его напрямую., `test_create_stars_invoice_rejects_invalid_rate` — Отрицательный или нулевой курс должен приводить к исключению., `test_create_stars_invoice_requires_bot` — Без экземпляра бота и stars_service функция должна отказывать.
- `tests/services/test_payment_service_wata.py` — Python-модуль
  Классы: `DummySession` (3 методов), `DummyLocalPayment` (1 методов), `StubWataService` (2 методов), `DummyWataPayment` (1 методов)
  Функции: `anyio_backend`, `test_wata_service_format_datetime_accepts_utc`, `test_wata_service_parse_datetime_returns_naive_utc`, `test_create_wata_payment_success`, `test_create_wata_payment_respects_amount_limits`, `test_create_wata_payment_returns_none_without_service`, `test_process_wata_webhook_updates_status`, `test_declined_other_attempt_keeps_paid_status_without_alert`, `test_real_reversal_of_paid_payment_still_alerts`, `test_decline_alerts_when_paid_transaction_is_unknown`, `test_process_wata_webhook_finalizes_paid`, `test_process_wata_webhook_returns_false_when_payment_missing`
- `tests/services/test_payment_service_webhooks.py` — Python-модуль
  Классы: `DummyBot` (2 методов), `FakeScalarResult` (6 методов), `FakeResult` (9 методов), `FakeSession` (8 методов)
  Функции: `anyio_backend`, `test_process_cryptobot_webhook_success`, `test_process_pay2328_webhook_success`
- `tests/services/test_pinned_message_recipients.py` — Python-модуль
  Классы: нет
  Функции: `test_collects_active_ids_in_batches_and_skips_email_only`, `test_broadcast_and_unpin_reach_the_same_people`
- `tests/services/test_platega_decline_notice.py` — Python-модуль
  Классы: нет
  Функции: `test_declined_payment_gets_one_message_with_retry_and_other_method`, `test_webhook_retries_do_not_repeat_the_message`, `test_status_button_pressed_before_the_webhook_does_not_lose_the_message` — «Проверить статус» уже записал CANCELED — вебхук всё равно пишет, один раз., `test_retry_button_is_dropped_when_the_method_is_switched_off`, `test_general_reminder_does_not_follow_the_decline_message` — Через 10 минут воронка шлёт «Оплата не завершена» — тому, кому уже написали об отказе, не шлёт., `test_expired_invoice_stays_silent`, `test_invoice_created_outside_the_bot_stays_silent`, `test_person_who_already_made_a_new_invoice_is_not_disturbed`, `test_person_who_paid_meanwhile_is_not_told_the_payment_failed`, `test_undelivered_message_is_marked_and_does_not_break_the_webhook`
- `tests/services/test_platega_payer_metadata.py` — Python-модуль
  Классы: нет
  Функции: `test_telegram_user_payment_carries_telegram_id_and_username`, `test_email_user_payment_carries_internal_id_and_email`, `test_explicit_payer_is_sent_as_is`, `test_payment_without_user_and_payer_is_still_filled`, `test_landing_guest_payment_carries_the_guest`
- `tests/services/test_platega_reuse_pending_link.py` — Python-модуль
  Классы: нет
  Функции: `test_second_press_gets_the_same_live_link`, `test_dead_or_unknown_link_is_replaced_by_a_new_payment` — Провайдер отменил платёж (или не ответил) — новый платёж, как раньше., `test_paid_link_is_not_handed_out_again`, `test_other_amount_or_method_gets_its_own_payment`, `test_old_expiring_or_foreign_payment_is_not_reused` — Кто вернулся по напоминанию на 10-й минуте, получает новую ссылку — как раньше., `test_handler_shows_the_reused_link_without_creating`
- `tests/services/test_platega_service.py` — Python-модуль
  Классы: нет
  Функции: `test_sanitize_description_limits_utf8_bytes`, `test_sanitize_description_returns_clean_value`, `test_create_payment_defaults_to_v1_endpoint`, `test_create_payment_uses_v2_endpoint_when_configured`, `test_base_url_version_suffix_forces_version_and_is_stripped` — Обход из #2934 (PLATEGA_BASE_URL=…/v2) не должен собирать /v2/v2/… и не, `test_get_transaction_stays_unversioned`, `test_unknown_api_version_falls_back_to_v1`, `test_parse_redirect_url_accepts_v1_field`, `test_parse_redirect_url_accepts_v2_field`, `test_parse_redirect_url_missing_or_empty`, `test_base_url_version_suffix_is_case_insensitive` — A manually appended suffix may be uppercase ('/V2'); it must still be stripped, `test_v2_url_field_reaches_returned_redirect_url` — END-TO-END regression for #2934: a v2 create response carrying the link in, `test_create_payment_sends_payer_metadata`, `test_create_payment_requires_the_payer` — Забыть плательщика нельзя: без него магазин отключат.
- `tests/services/test_platega_subscriptions_schema.py` — Python-модуль
  Классы: нет
  Функции: `test_model_table_and_columns`, `test_model_fk_is_set_null_and_nullable`, `test_migration_0140_upgrade_downgrade_idempotent`
- `tests/services/test_promo_deeplink.py` — Python-модуль
  Классы: нет
  Функции: `test_link_parsing`, `env`, `test_new_user_code_is_kept_for_registration`, `test_registered_user_gets_it_applied_now`, `test_used_code_tells_the_person`, `test_unknown_code_is_answered_and_counts_as_a_guess` — Раньше параметр уходил в реферальную ветку: «Вы уже зарегистрированы… реферальная ссылка…»., `test_expired_or_exhausted_code_is_named`, `test_campaign_named_promo_is_not_counted_as_a_guess`, `test_blocked_guesser_gets_no_oracle`, `test_bad_format_is_not_checked_but_answered`
- `tests/services/test_promo_group_auto_assign_notify_user.py` — Python-модуль
  Классы: нет
  Функции: `delivery`, `test_discounts_skip_zero_and_junk_periods_and_sort`, `test_telegram_user_gets_escaped_message_with_discounts`, `test_email_only_user_goes_through_router_without_bot`, `test_group_without_discounts_uses_neutral_text`, `test_switch_off_sends_nothing_and_failures_never_raise`, `test_locale_keys_exist_and_format`, `test_email_template_escapes_and_lists_discounts`, `test_email_type_is_editable_in_cabinet`, `test_assignment_notifies_user_once_and_recalculation_stays_silent`, `test_recalculation_passes_notify_user_false`
- `tests/services/test_promo_group_lock_leak.py` — Python-модуль
  Классы: нет
  Функции: `test_no_lock_when_no_group_matches`, `test_no_lock_without_spending`, `test_lock_is_released_if_group_disappears_after_locking`
- `tests/services/test_promo_group_recalculation_scheduler.py` — Python-модуль
  Классы: `Announcer` (2 методов), `GatedRunner` (2 методов)
  Функции: `test_schedule_runs_one_pass_and_announces_it`, `test_requests_during_a_pass_collapse_into_one_more_pass`, `test_runner_failure_is_recorded_and_still_announced`, `test_schedule_without_event_loop_is_refused_quietly`, `admin_chat`, `test_summary_is_silent_when_nobody_changed`, `test_summary_is_sent_once_when_someone_changed`, `test_summary_is_sent_when_the_pass_failed`, `test_summary_text_lists_failures_only_when_there_are_any`
- `tests/services/test_promo_send_summary.py` — Python-модуль
  Классы: нет
  Функции: `test_skipped_users_are_counted_separately`, `test_topup_notification_survives_broken_session`, `test_subscription_event_is_retried_in_a_fresh_session`, `test_tariff_offer_is_sent_every_time_without_protections` — Админ отправляет сколько угодно раз: прежнее предложение и чужая скидка не мешают.
- `tests/services/test_promocode_rollback_keeps_user_usable.py` — Python-модуль
  Классы: нет
  Функции: `test_failed_trial_activation_keeps_user_attributes_loaded`
- `tests/services/test_promocode_service.py` — Python-модуль
  Классы: нет
  Функции: `test_activate_promo_group_promocode_success` — Test successful activation of PROMO_GROUP type promocode, `test_activate_promo_group_user_already_has_group` — Test activation when user already has the promo group, `test_activate_promo_group_group_not_found` — Test activation when promo group doesn't exist (deleted/invalid), `test_activate_promo_group_assignment_error` — Test activation when promo group assignment fails, `test_activate_promo_group_assigned_by_value` — Test that assigned_by parameter is correctly set to 'promocode', `test_activate_promo_group_description_includes_group_name` — Test that result description includes promo group name, `test_promocode_data_includes_promo_group_id` — Test that returned promocode data includes promo_group_id, `test_activate_trial_promocode_uses_all_available_squads_when_tariff_has_no_restrictions`, `test_subscription_days_promo_keeps_trial_a_trial` — Bug #629889 (class): a days-promocode on a TRIAL must NOT flip is_trial., `test_activation_aborts_when_usage_slot_cannot_be_claimed` — F18/F17: the atomic conditional increment is the authoritative gate., `test_trial_promo_refunds_instead_of_fake_success_when_subscription_exists` — F15: a trial promo that can't create/extend must raise (refund), not fake success.
- `tests/services/test_promocode_tariff_days.py` — Python-модуль
  Классы: нет
  Функции: `env`, `test_plain_days_code_has_no_tariff`, `test_user_without_subscription_gets_the_tariff`, `test_live_trial_is_converted_and_keeps_remaining_days`, `test_expired_subscription_does_not_carry_days`, `test_same_tariff_is_just_extended`, `test_higher_tariff_is_never_downgraded`, `test_lower_paid_tariff_is_upgraded`, `test_panel_failure_reloads_objects_and_queues_the_sync` — Сбой панели откатывает сессию: объекты перечитываются, синхронизация — в очередь с тем же сбросом трафика.
- `tests/services/test_purchase_register_handlers_lint.py` — Python-модуль
  Классы: нет
  Функции: `test_register_handlers_does_not_shadow_module_imports` — No name imported at module-level may also be bound inside register_handlers., `test_subscription_states_is_module_level_only` — Explicit narrow guard for the exact 2026-05-16 incident.
- `tests/services/test_purchase_source_marker.py` — Python-модуль
  Классы: нет
  Функции: `test_source_is_unknown_by_default`, `test_explicit_source_and_subpage_flag`, `test_cart_source`, `test_purchase_from_bot_and_cabinet_is_marked`, `test_other_categories_and_unknown_source_are_untouched`, `test_subpage_cart_routes_to_subpage_topic`, `test_bot_middleware_sets_bot_source`, `test_auto_purchase_after_topup_uses_cart_source`
- `tests/services/test_quick_amounts_disable.py` — Python-модуль
  Классы: нет
  Функции: `test_normalize_keeps_explicit_empty_list_as_disabled`, `test_normalize_none_means_defaults`, `test_normalize_dedup_and_sort_unchanged`, `test_effective_empty_list_disables_buttons`, `test_effective_none_falls_back_to_defaults`, `test_effective_custom_list_still_filtered_by_bounds`
- `tests/services/test_quick_amounts_service.py` — Python-модуль
  Классы: нет
  Функции: `test_normalize_none_returns_none`, `test_normalize_sorts_and_dedupes`, `test_normalize_empty_list_means_disabled`, `test_normalize_rejects_non_list`, `test_normalize_rejects_non_int_items`, `test_normalize_rejects_non_positive_items`, `test_normalize_rejects_more_than_ten_items`, `test_normalize_caps_after_dedupe`, `test_effective_returns_defaults_when_not_configured`, `test_effective_filters_by_min_max`, `test_effective_returns_empty_when_all_filtered_out`
- `tests/services/test_recreate_deleted_panel_user.py` — Python-модуль
  Классы: нет
  Функции: `test_not_found_by_status_404`, `test_not_found_by_error_code_without_404`, `test_a018_is_a_create_failure_not_absence` — 3.4.3: A018 = «Failed to create user» (500). Раньше код считал его «юзера нет», `test_404_for_another_entity_is_not_user_absence` — 404 у панели имеет 27 причин; чужой 404 (внешний сквад A182) не должен плодить дубли., `test_other_errors_are_not_not_found`, `test_plain_400_is_not_not_found` — 3.0.0: user-маршруты параметризованы ``z.coerce.number().positive()``, поэтому, `test_invalid_user_id_error_is_never_not_found` — ``RemnaWaveInvalidUserIdError`` — баг в данных бота (протухший UUID/None в, `test_coerce_panel_user_id_rejects_non_numeric_identifiers` — Мусорный идентификатор отсекается на границе клиента и не доходит до сети., `test_recreate_active_delegates_to_create_flow`, `test_recreate_trial_is_also_alive`, `test_recreate_skips_expired_status` — Истёкшую подписку не пересоздаём: админ удалил панель-юзера намеренно., `test_recreate_skips_active_status_with_past_end_date` — Статус ACTIVE, но end_date уже прошёл (scheduled job ещё не отработал) — не пересоздаём., `test_update_addresses_panel_by_numeric_id` — 3.0.0: гейт «обновлять или создавать» и сам PATCH идут по числовому, `test_update_skips_panel_when_no_panel_id` — Пустой ``remnawave_id`` — обновлять нечего: запроса в панель быть не должно, `test_update_recreates_deleted_panel_user`, `test_update_does_not_recreate_on_other_api_errors`, `test_update_does_not_recreate_on_invalid_panel_user_id` — Битый локальный идентификатор (клиент отсёк его до сети) — НЕ повод считать,, `test_update_does_not_recreate_on_plain_400` — Голая 400 VALIDATION от панели (3.0.0 отвечает так на непригодный id) тоже, `test_update_recreates_on_a063_without_404` — A063 без статуса 404 — тоже маркер «панель-юзера нет»: пересоздаём., `test_update_does_not_recreate_on_a039_fk_violation` — A039 — FK violation на externalSquadUuid (панель жива, стейловый сквад),, `test_update_does_not_recreate_for_expired_subscription` — Пуш DISABLED в удалённого панель-юзера: молча пропускаем, панель не засоряем., `test_single_tariff_gate_updates_by_user_panel_id_without_searching` — Single-tariff: привязка живёт в ``users.remnawave_id``., `test_single_tariff_gate_falls_back_to_stream_search_before_creating` — Привязки нет → сперва ищем существующего юзера в панели, только потом создаём., `test_legacy_panel_uuid_column_is_read_only_by_the_two_modules_that_own_it`, `test_monitoring_update_happy_path_reaches_panel` — Регрессия: self._gb_to_bytes не существовал у MonitoringService — метод падал, `test_monitoring_update_recreates_deleted_panel_user`, `test_monitoring_update_does_not_recreate_on_other_api_errors`, `test_monitoring_update_does_not_recreate_on_invalid_panel_user_id` — Тот же контракт в рутинном синке: битый локальный id — не «юзера нет»., `test_monitoring_update_does_not_recreate_on_plain_400`, `test_monitoring_update_does_not_recreate_on_a018_create_failure` — 3.4.3: A018 = «Failed to create user» (500) — сбой записи, а не «юзера нет»., `test_validation_adopts_panel_id_and_keeps_the_recovery_key`, `test_validation_cleans_only_when_the_panel_denies_the_short_uuid`, `test_validation_never_cleans_on_a_panel_error` — Таймаут — не доказательство отсутствия аккаунта., `test_single_mode_prefers_exact_keys_over_ambiguous_telegram_search` — Точный ключ обязан побеждать неоднозначный поиск по telegramId., `test_single_mode_uses_the_subscription_own_panel_id` — `subscriptions.remnawave_id` — тоже точный адрес, и в single-tariff его не спрашивали., `test_create_does_not_break_on_the_partial_unique_index` — Соседняя подписка уже держит этот панельный аккаунт — запись обязана уступить., `test_stale_panel_id_still_gets_rescued_by_short_uuid` — Протухший числовой id не должен отменять спасение по shortUuid., `test_short_uuid_adoption_respects_the_partial_unique_index` — Привязка по shortUuid обязана уступить, если аккаунт держит соседняя строка., `test_degraded_short_uuid_endpoint_does_not_abort_a_resolvable_sync` — Деградация точного ключа не должна ронять то, что решается другим ключом., `test_degraded_short_uuid_endpoint_still_refuses_to_create_a_duplicate` — Но если больше НИЧЕМ не опознали — создавать нельзя, надо честно упасть., `test_foreign_account_is_cleaned_not_re_anchored` — Несовпадение владельца обязано вести в очистку, а не в перепривязку., `test_short_uuid_rescue_refuses_a_foreign_account` — И сама перепривязка обязана проверять владельца., `test_ownership_mismatch_is_not_rescued_by_a_telegram_less_account` — Несовпадение владельца нельзя «спасать» аккаунтом без telegramId.
- `tests/services/test_referral_days_target_choice.py` — Python-модуль
  Классы: нет
  Функции: `choice_on`, `test_chosen_subscription_wins_over_the_automatic_pick` — Автоподбор взял бы подписку с самым поздним сроком — выбор важнее., `test_without_the_setting_the_choice_is_ignored` — Выключенная настройка возвращает прежний автоподбор — целиком., `test_a_foreign_subscription_is_never_used` — Ссылка живёт в строке пользователя и переживает что угодно., `test_a_stale_choice_falls_back_instead_of_refusing` — Удалённая подписка не должна отменять награду., `test_the_rule_tariff_still_wins_over_the_choice` — Тариф в правиле — указание админа, куда дни обязаны лечь., `test_days_actually_land_in_the_chosen_subscription` — Сквозная проверка: не только выбор цели, но и само продление.
- `tests/services/test_referral_grant_days.py` — Python-модуль
  Классы: `TestDaysLandWhereConfigured` (3 методов), `TestMissingSubscription` (3 методов), `TestTrialIsNeverConverted` (2 методов), `TestPanelSyncFailure` (1 методов), `TestPanelRollback` (1 методов), `TestSubscriptionOnAnotherTariff` (1 методов), `TestStatesWhereDaysMustNotLand` (3 методов), `TestClassicMode` (2 методов), `TestPanelSync` (2 методов)
  Функции: `no_panel_sync` — Remnawave в тестах не поднимается — синхронизация подменяется.
- `tests/services/test_referral_ledger_orientation.py` — Python-модуль
  Классы: нет
  Функции: `test_allowed_files_still_exist` — Исключение для удалённого или переименованного файла — мусор, который прикроет чужой., `test_referral_id_grouping_excludes_referee_rows`, `test_ratchet_actually_sees_the_guarded_sites` — Сам храповик должен что-то находить, иначе он молча деградирует в no-op.
- `tests/services/test_referral_levels_safety.py` — Python-модуль
  Классы: `TestCacheInvalidation` (2 методов), `TestCacheReload` (1 методов), `TestBackupCoverage` (1 методов), `TestMergeChainRepair` (3 методов), `TestAsyncSessionHazards` (2 методов), `TestCacheGeneration` (1 методов), `TestFirstTopupClaim` (1 методов)
  Функции: нет
- `tests/services/test_referral_notification_kinds.py` — Python-модуль
  Классы: нет
  Функции: `test_registered_notice_carries_its_own_type`, `test_welcome_notice_carries_referrer_and_promise`, `test_every_referral_kind_obeys_referral_switch`, `test_registered_template_never_mentions_money`, `test_welcome_template_names_referrer_and_promise`, `test_welcome_template_without_promise_skips_bonus_line`
- `tests/services/test_referral_notification_names_the_user.py` — Python-модуль
  Классы: нет
  Функции: `test_delivery_failure_log_names_the_user`
- `tests/services/test_referral_notify_texts.py` — Python-модуль
  Классы: нет
  Функции: `test_commission_leads_with_amount_and_says_what_it_buys`, `test_spend_line_without_withdrawal`, `test_first_topup_promises_next_percent`, `test_new_friend_quest_line_only_for_inviter_who_gets_the_days`, `test_money_message_survives_a_failed_summary`, `test_buttons_are_one_per_row_with_invite_first`, `test_notification_buttons_reach_the_real_screens`, `test_telegram_gets_the_keyboard`
- `tests/services/test_referral_reward_levels.py` — Python-модуль
  Классы: `TestChainWalk` (4 методов), `TestSchemeGate` (1 методов), `TestMoneyPerLevel` (6 методов), `TestTriggers` (2 методов), `TestActiveBonusSelection` (3 методов), `TestRefereeSide` (3 методов), `TestGranting` (7 методов), `TestNullPercentIsZero` (2 методов), `TestLevelNotifications` (6 методов), `TestRewardFormatting` (1 методов), `TestProgramDescription` (4 методов), `TestInvitePromise` (2 методов), `TestDepthHonesty` (2 методов), `TestUngrantablePromises` (4 методов), `TestRefereeRowsStayOutOfReferrerTotals` (1 методов), `TestGeneratedTextIsLocalized` (5 методов), `TestLegacyImportPercent` (4 методов), `TestDepthOnThePayoutPath` (2 методов), `TestThresholdGatesThePayout` (4 методов)
  Функции: `chain` — Цепочка 4 → 3 → 2 → 1 и схема 'levels'., `granting` — Обвязка выдачи: начисления и записи ledger'а собираются в списки.
- `tests/services/test_referral_rewards_baseline.py` — Python-модуль
  Классы: `TestTopupBranches` (5 методов), `TestCommissionPercent` (3 методов), `TestNoMultiLevelYet` (1 методов)
  Функции: `wired` — Общая обвязка: реферал → реферер, без похода в БД и Telegram.
- `tests/services/test_referral_service.py` — Python-модуль
  Классы: нет
  Функции: `test_referral_notification_respects_notification_switches`, `test_referral_notification_enabled_sends_telegram_message`, `test_disabled_referral_notifications_skip_email_delivery`, `test_commission_accrues_before_minimum_first_topup`, `test_first_topup_inviter_gets_fixed_plus_commission` — Inviter bonus should be fixed bonus + commission, not max(fixed, commission)., `test_first_payment_commission_percent_overrides_flat_percent`, `test_recurring_commission_percent_uses_paid_referrals_tier`, `test_second_small_topup_uses_recurring_tier_not_first_payment_percent`, `test_parse_recurring_commission_tiers_handles_edge_cases`, `test_calculate_recurring_commission_tier_boundary`, `test_registration_notice_to_email_referrer_uses_registered_template`, `test_welcome_notice_to_email_referee_uses_welcome_template`, `test_reward_notice_keeps_bonus_template_by_default`, `test_non_referral_type_is_rejected`, `test_registration_of_email_only_pair_never_sends_bonus_email` — Сквозной: регистрация реферала, оба участника без Telegram.
- `tests/services/test_referral_tier_mode.py` — Python-модуль
  Классы: `TestDefaultIsChain` (3 методов), `TestSelection` (5 методов), `TestPayout` (10 методов), `TestReferee` (2 методов), `TestLadderText` (3 методов), `TestProgress` (5 методов), `TestTextMatchesPayout` (9 методов), `TestChainModeIsUntouchedByTheNewArguments` (4 методов), `TestProgressFormatting` (4 методов), `TestModeNormalisation` (2 методов), `TestChainRefereePromise` (3 методов), `TestRestoreInvalidatesLevelCache` (2 методов), `TestImpossiblePercentIsNotPromised` (3 методов)
  Функции: `tiers` — Режим рангов, цепочка 4 → 3 → 2 → 1 и управляемое число рефералов.
- `tests/services/test_referral_tier_mode_db.py` — Python-модуль
  Классы: нет
  Функции: `tier_mode`, `test_threshold_counts_only_direct_referrals` — Порог отвечает на «насколько вырос сам партнёр», а не «сколько под ним всего»., `test_active_only_counts_those_who_topped_up`, `test_tier_is_chosen_from_real_rows` — Сквозной путь: строки БД → выбор ранга → начисленная сумма., `test_inactive_referrals_do_not_open_a_tier` — Порог по «с пополнением» не берётся накруткой пустых аккаунтов., `test_payment_cap_reads_this_tier_only` — Строки ДРУГИХ уровней не должны исчерпывать лимит ранга., `test_payment_cap_does_stop_this_tier` — Контроль к предыдущему: свои строки лимит исчерпывают., `test_progress_reports_real_counts`, `test_chain_mode_still_pays_the_whole_chain` — Контроль: режим по умолчанию не изменился ни на строку., `test_level_repair_would_flatten_a_rank` — Показывает УЩЕРБ, от которого защищает гейт ниже., `test_merge_gates_level_repair_on_chain_mode` — Сторож на вызов: пересчёт уровней запускается только в режиме цепочки., `test_average_income_counts_every_rank` — «Средний доход с реферала» брал срез level==1 — верный только для цепочки., `test_cap_applies_to_an_earning_made_in_the_same_second` — Лимит обязан считать начисление, сделанное сразу после создания правила., `test_margin_does_not_swallow_older_history` — Контроль: запас на границе не должен втягивать историю прежних схем.
- `tests/services/test_referral_tier_wiring.py` — Python-модуль
  Классы: `TestCabinetTerms` (4 методов), `TestBotInviteScreen` (1 методов)
  Функции: `spies` — Подменяет описания на шпионов, записывающих переданные аргументы.
- `tests/services/test_referral_user_choice.py` — Python-модуль
  Классы: `TestDefaultsAreOff` (4 методов), `TestRewardKindChoice` (5 методов), `TestLadderMatchesTheChoice` (3 методов)
  Функции: `wired`
- `tests/services/test_referral_withdrawal_amount_guard.py` — Python-модуль
  Классы: нет
  Функции: `test_create_rejects_non_positive_and_below_minimum`, `test_approve_refuses_negative_request`
- `tests/services/test_referral_withdrawal_spent_commission.py` — Python-модуль
  Классы: нет
  Функции: `test_unspent_referral_replay`, `test_spent_commission_is_not_withdrawable`, `test_pending_request_is_reserved_from_wallet`, `test_unspent_is_capped_by_recorded_earnings`
- `tests/services/test_registration_access_service.py` — Python-модуль
  Классы: `FakeValidator` (2 методов)
  Функции: `reader`, `context`, `test_access_matrix`, `test_non_telegram_channel_cannot_create_or_revive_when_enabled`, `test_web_gift_claim_is_admitted_by_the_gift_token_it_carries` — The 64-char token the web claim requires is the same bearer invite the deep link wraps., `test_web_gift_claim_without_resolvable_gift_stays_denied`, `test_web_gift_claim_respects_disabled_gift_invites`, `test_active_user_does_not_touch_settings_or_validator`, `test_validator_error_is_fail_closed_for_new_user`, `test_gift_flag_is_forwarded_to_validator`, `test_invite_validator_protocol_stub_is_not_executable`
- `tests/services/test_registration_invite_service.py` — Python-модуль
  Классы: `ScalarResult` (2 методов), `GiftScalars` (3 методов), `GiftResult` (2 методов), `FakeDB` (3 методов)
  Функции: `test_inactive_referrer_is_not_an_invitation`, `test_active_referrer_grants_invitation`, `test_active_campaign_grants_invitation`, `test_gift_is_not_accepted_when_gift_invites_are_disabled`, `test_claimable_gift_is_returned_and_bound_without_commit`, `test_self_gift_does_not_grant_invitation`, `test_early_gift_validation_does_not_lock_row`
- `tests/services/test_remnawave_devices_stats.py` — Python-модуль
  Классы: нет
  Функции: `test_devices_statistics_aggregates_nested_byapp_2_8_0`, `test_devices_statistics_prefers_top_level_byapp_2_7_x`, `test_devices_statistics_explicit_none_byapp_aggregates_nested` — byApp explicitly None (not just absent) must still trigger nested aggregation., `test_devices_statistics_platform_without_byapp_is_skipped_not_fatal` — A platform lacking byApp (or with a malformed non-list byApp) is skipped; siblings still aggregate., `test_devices_statistics_none_counts_coerced_to_zero` — Present-but-null counts must not leak None into the response (defensive)., `test_devices_statistics_empty_byplatform_yields_empty_byapp`
- `tests/services/test_remnawave_expiration_webhook.py` — Python-модуль
  Классы: нет
  Функции: `test_new_and_old_events_both_registered`, `test_canonical_hours_map_to_legacy_messages`, `test_reads_receiver_meta_key_not_raw_meta` — Regression: the handler reads data['_meta'] (receiver contract). A payload, `test_non_canonical_negative_picks_nearest_before_message`, `test_non_canonical_positive_uses_expired_message`, `test_missing_or_invalid_meta_sends_nothing`, `test_no_subscription_sends_nothing`, `test_webhook_expiry_respects_user_days_threshold`, `test_new_2_8_0_api_token_admin_events_registered` — 2.8.0 added service.api_token_created/deleted — surfaced as admin notifications., `test_user_modified_syncs_used_traffic_from_nested_user_traffic` — usedTrafficBytes lives nested in userTraffic (ExtendedUsersSchema); the, `test_user_modified_used_traffic_falls_back_to_flat_key` — Old panels send a flat usedTrafficBytes — keep the fallback working.
- `tests/services/test_remnawave_identity_backfill.py` — Python-модуль
  Классы: нет
  Функции: `panel_user`, `subscription`, `bot_user`, `test_short_uuid_is_the_exact_key`, `test_stored_short_uuid_unknown_to_panel_does_not_fall_back` — The panel user was deleted., `test_unique_telegram_id_resolves_when_no_short_uuid`, `test_multi_tariff_ambiguity_is_refused_without_a_discriminator`, `test_multi_tariff_short_id_suffix_disambiguates`, `test_email_only_user_resolves_by_email`, `test_duplicate_email_is_refused`, `test_no_surviving_identifier_is_reported_not_guessed`, `test_already_claimed_panel_user_is_not_reused_via_username` — Two subscriptions must never converge on one panel account., `test_index_tolerates_missing_fields` — Panel rows legitimately have null telegramId/email; indexing must not crash., `test_exact_only_defers_rows_without_a_short_uuid` — Pass 1 must not consume weak matches., `test_exact_only_still_reports_a_dead_short_uuid` — A stored shortUuid the panel does not know is a verdict, not a deferral., `test_exact_match_wins_over_a_lower_numbered_weak_match` — The regression this was written for., `test_rerun_does_not_reassign_an_already_persisted_panel_id` — `claimed` must be primed from rows a previous run already wrote., `test_dry_run_writes_nothing`, `test_conflict_between_different_users_rolls_back` — Один панельный аккаунт, на который претендуют РАЗНЫЕ пользователи., `test_sibling_rows_of_one_user_are_not_a_conflict` — Штатное состояние single-tariff, а не ошибка., `test_rerun_does_not_invent_a_conflict_for_a_sibling` — Повторный прогон — штатный сценарий, а не исключение., `test_live_subscription_wins_the_panel_id_not_the_expired_one` — id достаётся живой строке, а не самой старой., `test_id_moves_to_the_live_row_when_only_the_dead_one_kept_the_short_uuid` — Самая частая форма в single-tariff, и сортировкой её не решить., `test_between_two_live_rows_the_later_end_date_wins` — Пинит саму сортировку, а не перенос id., `test_transfer_does_not_leave_the_target_marked_unresolved` — Отчёт — единственная поверхность принятия решения для оператора., `test_grace_session_on_the_donor_row_still_gets_an_id` — Перенос id не должен обесточивать grace-сессию строки-донора., `test_session_of_a_deleted_panel_account_is_not_given_the_live_one` — Сессия удалённого аккаунта не должна получить живой аккаунт владельца., `test_single_tariff_session_resolves_by_the_user_uuid_it_actually_stores` — Реальная форма однотарифных данных: в сессии лежит uuid ПОЛЬЗОВАТЕЛЯ., `test_session_resolves_when_its_subscription_was_linked_by_an_earlier_run` — Карта uuid обязана праймиться из уже записанных строк., `test_panel_id_already_owned_by_another_user_is_reported_not_assigned` — `users.remnawave_id` уникальна глобально — второй претендент идёт в отчёт., `test_blocked_strongest_evidence_does_not_fall_through_to_a_weaker_one` — Заблокированная подписочная улика НЕ должна спускаться к телеграм-ветке., `test_account_claimed_by_another_users_subscription_is_not_given_away` — Аккаунт, разобранный подпиской ДРУГОГО пользователя, нельзя отдать по telegram_id., `test_one_uuid_pointing_at_two_accounts_is_dropped_not_coin_flipped` — Противоречивый uuid нельзя разрешать «как повезёт»., `test_uuid_clash_discovered_during_matching_is_also_dropped` — Коллизия, всплывшая в `assign`, а не при прайминге, — тот же случай., `test_user_takes_the_exact_id_from_a_previously_linked_subscription` — Точный id соседней строки бьёт догадку по telegram_id., `test_user_with_two_different_panel_accounts_is_reported_not_guessed` — Две подписки на РАЗНЫЕ аккаунты — угадывать нечего, нужна строка в отчёте., `test_a_dead_persisted_id_does_not_beat_a_live_telegram_match` — Сохранённый id, которого в панели уже нет, не должен ничего решать., `test_every_write_is_recorded_in_the_audit_trail` — Прогон обязан оставлять построчный след того, что записал., `test_audit_filename_reflects_the_kind_of_run_not_the_commit_flag` — Холостой прогон — это `dryrun`, а не `conflicts`., `test_username_match_refuses_account_without_identity` — Имя совпало с шаблоном, но у аккаунта нет ни Telegram id, ни почты — не наш., `test_username_match_refuses_account_of_another_person` — Имя совпало, но Telegram id в аккаунте чужой — это чей-то ещё аккаунт., `test_username_still_disambiguates_duplicate_email` — Почтовый пользователь с двумя аккаунтами на одну почту: имя по шаблону выбирает наш., `test_backfill_leaves_manually_created_panel_account_alone` — Сквозной прогон: аккаунт с именем по шаблону, но без личности, остаётся ничьим.
- `tests/services/test_remnawave_service_sync.py` — Python-модуль
  Классы: нет
  Функции: `test_deduplicate_prefers_latest_expire_date`, `test_deduplicate_prefers_active_status_on_same_expire`, `test_deduplicate_ignores_records_without_expire_date`, `test_get_or_create_user_handles_unique_violation`, `test_get_or_create_user_creates_new`
- `tests/services/test_remnawave_username.py` — Python-модуль
  Классы: нет
  Функции: `test_format_remnawave_username_within_max_without_suffix` — Default behaviour stays bounded by REMNAWAVE_USERNAME_MAX_LENGTH., `test_format_remnawave_username_reserves_room_for_caller_suffix` — reserve_suffix_chars=N → base fits in MAX-N so caller can append safely., `test_format_remnawave_username_email_user_default_template` — Email-only user with the bundled default template still fits., `test_format_remnawave_username_does_not_go_below_min_with_huge_reserve` — If caller asks for more reserve than the cap allows, base falls back to MIN., `test_format_remnawave_username_repro_38_char_bug` — Exact production payload from log.rw/ARVm79dH must come out ≤ 36 chars., `test_build_subscription_username_production_repro` — Production repro through the high-level helper used by all 3 callers., `test_build_subscription_username_empty_suffix_is_legacy_format` — suffix='' → equivalent to plain format_remnawave_username (single-tariff path)., `test_build_subscription_username_handles_pathological_long_suffix` — Suffix longer than MAX_LENGTH: helper must still produce a string ≤ MAX_LENGTH., `test_skeleton_detector_falls_back_when_username_template_renders_constant` — Template `user_{username}` for email-only user (no TG username) renders to, `test_skeleton_detector_falls_back_when_template_has_no_variables` — A template with no variables (admin misconfig) is itself degenerate —, `test_skeleton_detector_does_not_trigger_for_telegram_users` — TG users with a real @username are NOT degenerate — the template renders, `test_skeleton_detector_uses_user_id_when_template_references_it` — Template that references {user_id} (which always has a value) must NOT, `test_cyrillic_full_name_is_transliterated` — Issue #1659: кириллица в {full_name} должна транслитерироваться, а не выпадать., `test_ascii_full_name_stays_unchanged` — Латинские имена не должны меняться транслитерацией., `test_transliterate_cyrillic_preserves_case_and_non_cyrillic`, `test_transliterated_long_cyrillic_name_respects_max_length` — Транслитерация удлиняет строку (щ → shch) — итог всё равно должен влезать в лимит.
- `tests/services/test_repurchase_after_subscription_delete.py` — Python-модуль
  Классы: нет
  Функции: `delete_mode`, `test_stale_user_level_id_is_healed_by_the_update_path` — База уже в битом состоянии (подписку удалили до фикса): покупка обязана сама выйти на новый аккаунт.
- `tests/services/test_reset_subscription.py` — Python-модуль
  Классы: нет
  Функции: `test_reset_subscription_zeroes_fields`, `test_reset_with_panel_singletariff_falls_back_to_user_panel_id`, `test_reset_with_panel_no_panel_id_skips_panel`, `test_reset_with_panel_survives_panel_error` — A panel disable failure must not block the bot-side reset (best effort)., `test_user_modified_does_not_resurrect_disabled_end_date` — A user.modified webhook carrying a stale FUTURE expireAt must NOT restore the, `test_user_modified_still_syncs_end_date_for_active` — Regression guard: ACTIVE subs still get end_date synced from the panel.
- `tests/services/test_runtime_settings_restart.py` — Python-модуль
  Классы: нет
  Функции: `test_cabinet_switches_remain_effective_after_loading_committed_db`, `test_disabling_smtp_closes_existing_queue_without_delivery`
- `tests/services/test_settings_categories.py` — Python-модуль
  Классы: нет
  Функции: `test_setting_lands_in_expected_category`, `test_no_setting_falls_into_a_single_verb_category` — Категория из одного глагола — признак забытой привязки в CATEGORY_KEY_OVERRIDES., `test_every_setting_is_exposed_unless_explicitly_excluded` — Ни одна настройка не должна пропасть из админки молча.
- `tests/services/test_settings_excluded_keys.py` — Python-модуль
  Классы: нет
  Функции: `test_identity_and_auth_secrets_are_excluded`, `test_excluded_keys_have_no_editable_definition`
- `tests/services/test_settings_numeric_units.py` — Python-модуль
  Классы: нет
  Функции: `test_devices_selection_disabled_amount_is_not_a_price`, `test_devices_selection_disabled_amount_zero_stays_plain`, `test_money_keys_keep_currency_formatting`
- `tests/services/test_settings_secret_masking.py` — Python-модуль
  Классы: нет
  Функции: `test_is_secret_key_matches_secret_names`, `test_is_secret_key_ignores_plain_names`, `test_numeric_settings_with_secretish_names_are_not_masked`, `test_no_nonstring_definition_value_is_ever_masked` — Sweep every real setting definition: a masked value must always be a string., `test_string_secret_is_masked`, `test_unset_secret_is_not_masked`
- `tests/services/test_shutdown_notification.py` — Python-модуль
  Классы: нет
  Функции: `test_docker_stop_is_a_planned_shutdown_with_a_hint`, `test_ctrl_c_is_named`, `test_unknown_signal_is_named_by_its_name`, `test_polling_crash_is_a_failure_with_the_error_and_advice`, `test_long_error_is_cut`, `test_without_start_time_there_is_no_uptime`, `test_uptime_format`, `admin_chat`, `test_planned_stop_goes_to_the_infrastructure_topic`, `test_crash_goes_to_the_errors_topic_with_a_contact_button`, `test_disabled_notifications_send_nothing`, `test_send_failure_does_not_raise`, `test_main_does_not_shadow_datetime_locally` — Локальный ``from datetime import datetime`` в ветке делает имя локальным для всей, `test_shutdown_notice_is_sent_before_services_are_stopped` — Docker даёт на остановку ~10 секунд: сообщение — первым делом, пока сессия жива.
- `tests/services/test_spofy_subpage_admin_marker.py` — Python-модуль
  Классы: нет
  Функции: `test_mark_goes_to_the_title_line`, `test_context_is_off_by_default_and_resets`, `test_send_message_marks_and_routes_subpage_purchases`, `test_regular_purchases_are_untouched`, `test_cart_completion_runs_inside_the_context`, `test_topup_notification_is_marked_when_a_subpage_purchase_is_pending`
- `tests/services/test_spofy_subpage_bound_price.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_completion_charges_the_checkout_price_not_the_recomputed_one` — Пересчёт на момент исполнения (осталось 40 дней) дал бы 2666 ₽ при балансе, `test_same_cart_without_bound_price_behaves_as_before` — Бот-корзина без spofy_price_kopeks: пересчёт (2666 ₽) выше баланса (2000 ₽), `test_orphan_topup_sends_notification_on_real_path` — Сквозная проверка через completion: корзина страницы есть, а метки намерения
- `tests/services/test_spofy_ux_round.py` — Python-модуль
  Классы: нет
  Функции: `test_info_prompt_has_no_hardcoded_legal_links`, `test_expired_webhook_after_monitoring_does_not_notify_twice`, `test_expired_webhook_first_still_notifies`, `test_device_added_always_notifies_the_owner` — Уведомление о новом устройстве приходит всегда, в том числе в первые сутки: это полезная, `test_bandwidth_threshold_says_gb_left_and_bypass_note`, `test_bandwidth_threshold_regular_note_without_bypass`, `test_threshold_text_formats_in_ru_and_en`, `test_followups_skip_quiet_hours`, `bypass_on`, `test_trial_needs_the_include_trial_switch`, `test_bypass_quota_flag`, `test_trial_suspension_sends_trial_text`, `test_trial_texts_explain_unlimited_regular_servers`, `test_device_rows_use_disconnect_icon_and_add_slot_button`, `test_no_add_slot_button_by_default`, `test_all_slots_taken`
- `tests/services/test_stars_payload_amount.py` — Python-модуль
  Классы: нет
  Функции: `test_parser_extracts_amount_kopeks_from_known_payload_shapes`, `test_parser_returns_none_for_unrecognised_shapes`, `test_plausibility_accepts_lossless_round_trip` — At rate=1.0 with integer rubles, payload == reconstructed exactly., `test_plausibility_accepts_sub_ruble_drift` — 50.50 ₽ requested → 50 ⭐ × 1.0 = 50.00 ₽ reconstructed → 50 kopeks drift, well within tolerance., `test_plausibility_accepts_20pct_drift` — A 20% rate change between invoice creation and payment must NOT trip the guard., `test_plausibility_rejects_inflated_payload` — A payload claiming 10× the reconstructed amount is pathological — fall back to stars×rate., `test_plausibility_rejects_zero_or_negative`, `test_plausibility_uses_minimum_100_kopek_floor_for_tiny_amounts` — For tiny amounts (e.g. 50 kopeks reconstructed), 20% would be 10 — too tight., `test_negative_control_old_rate_was_lossy` — Regression cover: the pre-fix flow under rate=1.3 lost 0.50 ₽ on a 150 ₽ top-up., `test_negative_control_at_new_rate_is_lossless_for_integer_rubles` — At rate=1.0 with integer rubles, payload and reconstructed agree exactly.
- `tests/services/test_stars_unapplied_to_balance.py` — Python-модуль
  Классы: нет
  Функции: `test_credit_is_deposit_keyed_by_charge_id_and_idempotent`, `test_credit_failure_alerts_admins_and_returns_none`, `test_wheel_disabled_credits_balance_and_says_so_honestly`, `test_wheel_daily_limit_credit_is_deposit_not_refund`
- `tests/services/test_startup_logo_prewarm.py` — Python-модуль
  Классы: нет
  Функции: `test_prewarm_caches_file_id_and_deletes_message`, `test_prewarm_skips_when_already_cached`, `test_prewarm_no_target_chat_skips`, `test_prewarm_is_best_effort_on_timeout`
- `tests/services/test_startup_notification_summary.py` — Python-модуль
  Классы: нет
  Функции: `test_healthy_start_shows_every_section_and_no_warnings`, `test_problems_are_called_out_explicitly`, `test_metric_that_failed_is_a_dash_not_a_zero`, `test_version_and_panel_status_are_escaped`, `test_counts_only_live_subscriptions_and_last_day_deposits`, `test_rich_view_renders_the_same_sections` — Сбой rich-рендера молча уводит в классический вид — ломку здесь никто бы не заметил.
- `tests/services/test_structlog_reserved_kwargs.py` — Python-модуль
  Классы: нет
  Функции: `test_no_reserved_kwargs_in_log_calls`, `test_guard_detects_a_planted_call` — Сторож обязан быть чувствительным, иначе он молча зелёный., `test_reserved_kwarg_really_raises` — Не теория: такой вызов действительно падает на настоящем structlog., `test_guard_sees_every_logger_shape` — Сторож обязан узнавать логгер во всех формах, которые встречаются в коде., `test_guard_does_not_fire_on_unrelated_code` — И не должен срабатывать на том, что логгером не является.
- `tests/services/test_subscription_auto_purchase_service.py` — Python-модуль
  Классы: `DummyTexts` (2 методов)
  Функции: `test_auto_purchase_saved_cart_after_topup_success`, `test_race_guard_fresh_updated_at_without_subscription_payment_allows_purchase` — Свежий updated_at без SUBSCRIPTION_PAYMENT (только deposit) не блокирует автопокупку., `test_race_guard_fresh_updated_at_with_subscription_payment_skips_purchase` — Свежий updated_at + свежий SUBSCRIPTION_PAYMENT → пропуск автопокупки (защита от двойного списания)., `test_auto_purchase_skipped_without_topup_intent` — Без свежего намерения корзина НЕ покупается, даже если она сохранена и
- `tests/services/test_subscription_dedup_service.py` — Python-модуль
  Классы: нет
  Функции: `test_collapses_report_scenario`, `test_never_removes_alive_even_if_outranked_by_date`, `test_disabled_duplicate_is_removed_active_survives`, `test_single_rows_untouched`
- `tests/services/test_subscription_deletion_panel_target.py` — Python-модуль
  Классы: нет
  Функции: `test_single_tariff_falls_back_to_the_user_account` — Однотарифный: колонка подписки пуста, но аккаунт есть — и его надо снять., `test_single_tariff_spares_account_of_a_live_sibling` — Однотарифный: живая соседка сидит на том же аккаунте — не трогаем его., `test_single_tariff_ignores_dead_sibling` — Мёртвая соседка ничего не держит — аккаунт всё равно отключаем., `test_single_tariff_uses_subscription_id_when_user_has_none` — Историческая строка: id остался только на подписке — работаем по нему., `test_single_tariff_deletion_disables_shared_account` — Однотарифный, соседок нет: доступ снят, аккаунт остался живым для новой покупки., `test_single_tariff_deletion_leaves_live_sibling_alone` — Уборка отработавшей строки не должна трогать аккаунт живой соседки.
- `tests/services/test_subscription_extend_cabinet_mode.py` — Python-модуль
  Классы: нет
  Функции: `cabinet_mode` — Полностью настроенный cabinet-режим: и режим меню, и URL кабинета., `test_single_tariff_cabinet_button_opens_cabinet`, `test_bot_mode_keeps_callback_button` — Вне cabinet-режима кнопка обязана остаться обычным callback'ом., `test_cabinet_mode_without_url_falls_back_to_callback` — Cabinet-режим без ``MINIAPP_CUSTOM_URL`` не должен ломать кнопку., `test_expired_notification_keyboard_opens_cabinet` — Сквозная проверка на том самом уведомлении из отчёта пользователя.
- `tests/services/test_subscription_service_sync.py` — Python-модуль
  Классы: нет
  Функции: `test_sync_picks_create_or_update_by_panel_id`, `test_missing_user_falls_to_create_which_reports_it` — Пользователя нет в базе: не падаем, create сам залогирует и вернёт None.
- `tests/services/test_support_settings_in_db.py` — Python-модуль
  Классы: нет
  Функции: `isolated_settings`, `test_keys_are_bot_settings_in_the_support_category`, `test_getters_read_live_settings`, `test_ticket_notification_flags_respect_global_switches`, `test_support_info_text_per_language_with_locale_fallback`, `test_legacy_file_is_imported_once_and_never_overrides_the_db`, `test_broken_legacy_file_is_left_to_a_human`
- `tests/services/test_sync_extinguishes_stale_panel_date.py` — Python-модуль
  Классы: нет
  Функции: `harness` — Один батч из одной истёкшей подписки, панельный id уже известен., `test_future_panel_date_of_an_expired_subscription_is_extinguished`, `test_past_panel_date_is_left_alone` — Настоящая дата окончания в панели — история, второго запроса быть не должно., `test_live_subscription_is_not_touched_twice` — У живой подписки дата уходит первым же запросом — гасить нечего.
- `tests/services/test_sync_from_panel_releases_transaction.py` — Python-модуль
  Классы: нет
  Функции: `events`, `db`, `service`, `test_import_releases_callers_transaction_before_loading_panel`, `test_import_rolls_back_after_failure_so_session_stays_usable`
- `tests/services/test_sync_from_panel_skips_foreign_accounts.py` — Python-модуль
  Классы: нет
  Функции: `db`, `service`, `test_import_skips_accounts_without_identity_and_says_so`
- `tests/services/test_sync_log_has_no_emails.py` — Python-модуль
  Классы: нет
  Функции: `test_email_goes_to_debug_only`
- `tests/services/test_sync_users_to_panel_adoption.py` — Python-модуль
  Классы: нет
  Функции: `harness` — Один батч из одной подписки, gracce-lease разрешён, клиент — мок., `test_single_tariff_writes_identity_onto_the_user` — Мутация «поменять ветки местами» схлопывала все подписки юзера на один id.
- `tests/services/test_system_error_log_service.py` — Python-модуль
  Классы: нет
  Функции: `test_token_is_redacted_in_every_persisted_field`, `test_redaction_keeps_the_rest_of_the_message`, `test_only_real_delivery_attempts_are_counted` — suppressed/skipped до Telegram не доходят — счётчик попыток они не двигают., `test_stop_flushes_what_is_already_queued` — При аварийном завершении в очереди лежат ровно те ошибки, что к нему привели., `test_stop_is_safe_without_start`
- `tests/services/test_system_settings_env_priority.py` — Python-модуль
  Классы: нет
  Функции: `test_env_override_prevents_set_value`, `test_env_override_prevents_reset_value`, `test_initialize_skips_db_value_for_env_override`, `test_set_value_applies_without_env_override`
- `tests/services/test_tariff_device_arbitrary_periods.py` — Python-модуль
  Классы: нет
  Функции: `test_device_price_follows_arbitrary_tariff_days`, `test_daily_rate_and_unlimited_devices_are_preserved`, `test_telegram_preview_uses_configured_fallback_device_rate`
- `tests/services/test_tariff_discount_offer.py` — Python-модуль
  Классы: нет
  Функции: `test_source_carries_the_tariff`, `test_ordinary_offer_source_is_unchanged`, `test_discount_only_for_its_tariff`, `test_ordinary_discount_is_unaffected`, `test_expired_discount_is_zero`, `test_engine_discounts_ultima_only`, `test_engine_without_offer_has_no_discount`, `test_tariff_purchase_code_always_passes_the_tariff`
- `tests/services/test_tariff_switch_common_period.py` — Python-модуль
  Классы: нет
  Функции: `test_month_left_costs_the_real_monthly_difference`, `test_long_remainder_uses_the_annual_rates`, `test_cost_is_positive_and_below_the_new_tariff_full_price`, `test_cheaper_target_is_free`, `test_without_common_period_falls_back_to_shortest_rates`
- `tests/services/test_tariff_switch_configured_prices.py` — Python-модуль
  Классы: нет
  Функции: `tariff`, `test_unconfigured_target_is_not_free`, `test_unconfigured_source_rejected_before_shortcuts`, `test_explicit_free_period_stays_valid`, `test_null_shorter_period_does_not_override_configured_price`, `test_telegram_list_omits_unconfigured_tariff`, `test_legacy_none_current_with_promo_group_uses_thirty_day_discount`
- `tests/services/test_tariff_switch_flows_use_policy.py` — Python-модуль
  Классы: нет
  Функции: `test_flow_computes_remaining_days_through_policy`, `test_flow_asks_policy_before_resetting_traffic`, `test_no_new_direct_readers_of_the_traffic_switch` — Новый читатель выключателя обязан объясниться здесь.
- `tests/services/test_tariff_switch_policy.py` — Python-модуль
  Классы: `TestTrafficReset` (3 методов)
  Функции: `test_live_subscription_costs_at_least_one_day` — Остаток в часах — не ноль: иначе переключение бесплатное., `test_expired_subscription_has_no_remaining_days` — Истёкшей подписке путь в покупку, а не в переключение., `test_naive_datetime_is_treated_as_utc` — SQLite отдаёт даты без таймзоны — сравнение не должно падать., `test_defaults_to_current_time`
- `tests/services/test_telegram_stars_rate.py` — Python-модуль
  Классы: нет
  Функции: `test_default_stars_rate_is_one_ruble_per_star` — REGRESSION: default rate must stay at 1.0 ₽/⭐., `test_integer_ruble_amounts_round_trip_losslessly` — REGRESSION: at rate=1.0, integer ruble top-ups credit back exactly., `test_rubles_to_stars_rejects_invalid_rate` — Defensive check: zero/negative rate must raise rather than divide-by-zero., `test_rubles_to_stars_clamps_to_minimum_one_star` — Even at rate=1.0, a 0 ₽ request must return ≥1 ⭐ (Telegram requires positive amount)., `test_rate_change_is_propagated_through_telegram_stars_service` — `TelegramStarsService.calculate_*` helpers must defer to settings — no hardcoded copies.
- `tests/services/test_telegram_transport_startup.py` — Python-модуль
  Классы: нет
  Функции: `test_webhook_without_url_rejects_startup`, `test_valid_transport_configuration_is_accepted`, `test_switch_to_polling_receives_pending_updates_from_old_webhook`, `test_webhook_mode_does_not_delete_webhook_or_start_polling`, `test_webhook_deletion_failure_aborts_startup`
- `tests/services/test_ticket_reply_email.py` — Python-модуль
  Классы: нет
  Функции: `sent` — Перехватывает send_notification роутера., `last_message` — Подменяет чтение последнего сообщения тикета (проверка на фото)., `test_email_user_gets_ticket_reply_email`, `test_photo_reply_marked_in_context`, `test_long_reply_is_previewed`, `test_telegram_user_does_not_get_email` — Юзеру с Telegram ответ уже ушёл в бот — письмо было бы дублем., `test_disabled_toggle_blocks_email`, `test_global_notifications_switch_does_not_mute_support_replies` — ENABLE_NOTIFICATIONS не должен глушить ответ поддержки только email-юзеру., `test_user_without_verified_email_is_skipped`, `test_delivery_failure_does_not_raise`, `test_template_renders_for_supported_languages`, `test_template_escapes_html_in_preview` — Ответ поддержки вида «откройте <config>» не должен ломать вёрстку письма., `test_template_mentions_photo_when_reply_has_one`
- `tests/services/test_topup_checkout_offer.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_button_data_round_trips_and_fits_telegram_limit`, `test_foreign_or_broken_button_data_is_rejected`, `test_only_bot_purchase_and_renewal_carts_are_one_tap`, `test_subpage_source_matches_the_subscription_page_service` — Признак корзины страницы подписки продублирован (иначе круговой импорт) — значения обязаны совпадать., `test_renewal_message_gets_confirm_button_instead_of_resume`, `test_purchase_message_gets_purchase_wording`, `test_lifetime_period_reads_as_a_word_and_tariff_name_is_escaped`, `test_english_user_gets_english_wording`, `test_message_without_resume_button_is_left_alone`, `test_no_offer_keeps_resume_button`, `test_failure_while_building_never_blocks_the_topup_message` — Деньги уже зачислены: сообщение обязано уйти, пусть и с прежней кнопкой., `test_unreadable_user_never_blocks_the_topup_message` — Объект пользователя отсоединён от сессии (чтение поля падает) — сообщение уходит прежним., `test_renewal_cart_that_balance_now_covers_is_offered`, `test_renewal_price_includes_extra_devices_of_the_subscription` — Докупленные устройства входят в цену продления — в кнопке та же сумма, что на экране выбора., `test_purchase_cart_without_subscription_is_offered`, `test_lifetime_purchase_is_offered`, `test_balance_below_price_keeps_the_checkout_screen`, `test_price_changed_since_selection_keeps_the_checkout_screen` — Человек видел другую сумму (скидка кончилась или цена выросла) — новую показывает экран., `test_other_carts_keep_the_previous_message`, `test_disabled_tariff_is_not_offered_and_cart_is_left_for_the_screen` — Решение о кнопке только читает: корзину с отключённым тарифом удалит экран, сказав причину., `test_unknown_user_is_not_offered`, `test_topup_success_message_for_renewal`, `test_topup_success_message_when_money_is_still_short`, `test_topup_success_message_without_cart_is_unchanged`, `test_second_resume_message_is_not_sent_after_confirm_button` — «Зачислено» уже несёт «Подтвердить» — «Оплата получена, покупка не оформлена» следом не идёт., `test_second_resume_message_is_still_sent_when_button_was_not_offered` — Денег не хватило — «Зачислено» ушло с прежней кнопкой, второе сообщение идёт как раньше., `test_confirm_button_suppresses_only_one_following_message` — Метка одноразовая: следующее пополнение без кнопки получает своё сообщение., `test_stars_message_gets_the_button_but_suppresses_nothing` — У оплаты звёздами сообщение про корзину уходит раньше — глушить после кнопки нечего., `test_next_topup_without_button_does_not_inherit_the_mark` — Метка относится к последнему сообщению: следующее «Зачислено» без кнопки её снимает., `test_offer_mark_expires`
- `tests/services/test_topup_expired_autopay_with_cart.py` — Python-модуль
  Классы: нет
  Функции: `cart_service`, `test_cart_for_same_tariff_no_longer_cancels_autopay_renewal` — Случай из аудита: выбрал тот же тариф на 14 дней, пополнил ровно на цену — подписка продлена., `test_chosen_period_is_kept_not_the_shortest`, `test_renewal_dearer_than_the_cart_price_is_left_to_the_person` — Корзина покупки без докупленных устройств дешевле продления с ними: молча не списываем больше., `test_money_for_another_purchase_is_not_spent_on_renewal`, `test_forgotten_cart_without_intent_renews_like_no_cart` — Корзина без метки намерения (забытая) больше не отменяет автопродление: самый короткий срок., `test_without_autopay_the_cart_still_waits_for_confirm`
- `tests/services/test_traffic_cycle.py` — Python-модуль
  Классы: нет
  Функции: `test_latest_cycle_date`, `test_due_once_per_cycle`, `test_local_day_decides`, `test_renewal_keeps_day_and_new_purchase_replaces_it`, `test_panel_does_not_reset_by_itself`, `test_row_is_locked_only_after_the_panel_answered`, `test_second_worker_does_not_write_the_reset_twice`, `test_not_due_subscription_never_reaches_the_panel`
- `tests/services/test_traffic_daily_check_schedule.py` — Python-модуль
  Классы: нет
  Функции: `test_daily_check_runs_at_local_midnight`, `test_daily_check_today_if_local_time_is_still_ahead`
- `tests/services/test_traffic_daily_sum.py` — Python-модуль
  Классы: нет
  Функции: `test_sums_per_node_totals`, `test_the_old_top_level_total_is_not_used` — Регрессия, ради которой всё и переписывалось., `test_falls_back_to_daily_breakdown_when_a_node_has_no_total`, `test_accepts_a_flat_list_of_series`, `test_tolerates_garbage_without_raising`, `test_daily_window_is_one_complete_previous_day` — Окно обязано быть ОДНИМИ полными сутками, и не текущими.
- `tests/services/test_traffic_monitoring_redis.py` — Python-модуль
  Классы: нет
  Функции: `service` — Создаёт экземпляр сервиса для тестов., `mock_cache` — Мок для cache сервиса., `sample_snapshot` — Пример snapshot данных: ключ — числовой id панельного юзера (Remnawave 3.0.0)., `stored_snapshot` — Тот же snapshot в том виде, в котором лежит в Redis: JSON не умеет числовые ключи., `test_redis_keys_are_versioned_for_panel_id_identity` — Префикс v3 — версия идентичности панельного юзера. До Remnawave 3.0.0 те же, `test_save_snapshot_to_redis_success` — Тест успешного сохранения snapshot в Redis., `test_save_snapshot_to_redis_failure` — Тест неудачного сохранения snapshot в Redis., `test_save_snapshot_to_redis_exception` — Тест обработки исключения при сохранении., `test_load_snapshot_from_redis_success` — Тест успешной загрузки snapshot из Redis: строковые ключи возвращаются к числовым id., `test_load_snapshot_from_redis_empty` — Тест загрузки когда snapshot отсутствует., `test_load_snapshot_from_redis_invalid_data` — Тест загрузки невалидных данных., `test_load_snapshot_from_redis_skips_non_numeric_keys` — Непригодный ключ (например, протухший UUID) пропускается поштучно, а не роняет, `test_load_snapshot_from_redis_exception` — Тест обработки исключения при загрузке., `test_get_snapshot_time_from_redis_success` — Тест получения времени snapshot., `test_get_snapshot_time_from_redis_empty` — Тест когда время отсутствует., `test_has_snapshot_redis_exists` — Тест has_snapshot когда snapshot есть в Redis., `test_has_snapshot_memory_fallback` — Тест has_snapshot с fallback на память., `test_has_snapshot_none` — Тест has_snapshot когда snapshot нет нигде., `test_get_snapshot_age_minutes_from_redis` — Тест возраста snapshot из Redis., `test_get_snapshot_age_minutes_memory_fallback` — Тест возраста snapshot из памяти., `test_get_snapshot_age_minutes_no_snapshot` — Тест возраста когда snapshot нет., `test_save_snapshot_redis_success` — Тест сохранения snapshot в Redis успешно., `test_save_snapshot_fallback_to_memory` — Тест fallback на память когда Redis недоступен., `test_get_current_snapshot_from_redis` — Тест получения snapshot из Redis., `test_get_current_snapshot_fallback_to_memory` — Тест fallback на память., `test_save_notification_to_redis` — Тест сохранения времени уведомления. Кулдаун заключён на числовой id панели., `test_get_notification_time_from_redis` — Тест получения времени уведомления., `test_should_send_notification_no_previous` — Тест should_send_notification когда уведомлений не было., `test_should_send_notification_cooldown_active` — Тест should_send_notification когда кулдаун активен., `test_should_send_notification_cooldown_expired` — Тест should_send_notification когда кулдаун истёк., `test_should_send_notification_memory_fallback_keyed_by_panel_id` — Fallback на память тоже заключён на числовой id — ключ должен совпасть., `test_record_notification_redis` — Тест record_notification сохраняет в Redis., `test_record_notification_fallback_to_memory` — Тест record_notification с fallback на память., `test_create_initial_snapshot_uses_existing_redis` — Тест что create_initial_snapshot использует существующий snapshot из Redis., `test_create_initial_snapshot_creates_new` — Тест создания нового snapshot когда в Redis пусто., `test_create_initial_snapshot_skips_user_without_panel_id` — Юзер без числового id непригоден как ключ snapshot — пропускаем, а не падаем., `test_cleanup_notification_cache_removes_old` — Тест очистки старых записей из памяти.
- `tests/services/test_traffic_monitoring_status_filter.py` — Python-модуль
  Классы: нет
  Функции: `service`, `test_disabled_and_expired_are_filtered_out` — DISABLED/EXPIRED отсекаются, ACTIVE/LIMITED остаются., `test_all_active_pass_through` — Когда все активны — ничего не теряется., `test_all_inactive_returns_empty` — Сплошь DISABLED/EXPIRED → пустой список (никого не проверяем)., `test_filter_applies_across_paginated_batches` — Фильтр работает на каждом батче; пагинация — по сырому размеру страницы.
- `tests/services/test_trial_abuse_rule.py` — Python-модуль
  Классы: нет
  Функции: `test_second_account_on_a_device_is_the_abuser_not_the_first`, `test_two_accounts_are_enough`, `test_same_bot_user_is_one_person`, `test_account_without_telegram_no_longer_hides_behind_one_telegram`, `test_paid_and_expired_accounts_are_never_punished`, `test_unknown_accounts_are_not_touched`, `test_new_device_of_a_second_account_punishes_both_accounts`, `test_paid_first_account_keeps_its_access_and_only_the_newcomer_is_punished`, `test_whole_group_punishment_can_be_switched_off`, `test_whitelisted_account_is_skipped_but_the_other_one_is_punished`, `test_owner_connecting_again_catches_the_whole_group_too`, `test_lone_owner_is_never_punished`, `test_non_trial_accounts_skip_the_panel_lookup`, `test_bogus_hwid_is_not_checked`, `test_realtime_switch`, `test_device_webhook_schedules_the_check_and_still_notifies`, `test_who_shows_real_name_username_and_telegram`, `test_who_for_email_only_account_and_for_unknown_account`, `test_who_html_links_to_the_telegram_profile_and_escapes`, `test_reason_names_the_first_account_on_the_device`, `test_group_targets_include_the_first_trial_account`, `test_group_targets_leave_a_paid_first_account_alone_and_ignore_clean_groups`, `test_big_device_with_a_noticeable_share_of_paid_accounts_is_left_alone`, `test_big_device_without_paid_accounts_is_still_a_farm`, `test_small_group_with_paid_account_keeps_the_old_rule`, `test_device_shared_with_another_person_is_suspicious`, `test_second_account_of_the_same_person_is_not_suspicious`, `test_panel_failure_never_blocks_an_honest_reward`, `test_friend_reward_is_blocked_for_a_shared_device`, `test_already_punished_account_gets_no_friend_reward`, `test_simultaneous_webhooks_of_one_device_punish_each_account_once` — Оба аккаунта подключаются одновременно: две проверки не должны наказать людей дважды., `test_account_whose_trial_is_already_gone_gets_no_warning`, `test_admin_summary_goes_to_the_trials_topic`
- `tests/services/test_trial_device_management.py` — Python-модуль
  Классы: нет
  Функции: `test_trial_user_sees_device_list`, `test_trial_still_cannot_buy_device_slots`
- `tests/services/test_ultima_deeplink.py` — Python-модуль
  Классы: нет
  Функции: `test_link_parsing`, `test_first_open_activates_and_records_the_source`, `test_second_open_while_active_shows_remaining_without_extending`, `test_reopen_after_expiry_inside_cooldown_gets_no_new_discount`, `test_cooldown_zero_allows_unlimited_reopening`, `test_without_a_template_the_link_falls_back_to_normal_start`, `test_already_owned_tariff_skips_the_offer` — ULTIMA уже куплен — скидка на его покупку бесполезна, идём в обычный /start.
- `tests/services/test_update_links_panel_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_update_links_fresh_row_to_the_account_it_updated`, `test_update_leaves_row_unlinked_when_sibling_row_holds_the_account`, `test_link_is_noop_for_already_linked_row`
- `tests/services/test_user_action_log_service.py` — Python-модуль
  Классы: нет
  Функции: `test_defaults`, `test_normalize_cabinet_path`, `test_should_log_gates`, `test_schedule_skips_when_gated`
- `tests/services/test_user_activity_trail.py` — Python-модуль
  Классы: нет
  Функции: `spawned`, `test_normalize_screen_path`, `test_screen_view_is_logged_with_prefix`, `test_screen_view_secret_never_reaches_the_log`, `test_same_screen_within_window_is_one_record`, `test_dedup_is_per_user_and_per_screen`, `test_screen_view_is_gated_by_flag`, `test_dedup_memory_is_bounded`, `test_activity_route_itself_is_not_logged_as_an_action` — Иначе каждый экран давал бы две записи: экран и «POST /cabinet/activity/screen»., `test_stale_user_is_bumped`, `test_fresh_user_is_left_alone`, `test_never_seen_user_is_bumped`, `test_naive_timestamp_is_treated_as_utc` — Старые строки без таймзоны не должны ронять авторизацию сравнением naive/aware., `test_cabinet_dependency_touches_last_activity`, `test_click_is_logged_with_label_and_screen`, `test_every_click_counts_no_dedup`, `test_click_label_is_trimmed_and_empty_is_dropped`, `test_click_rate_limit_per_user`, `test_events_route_accepts_batch_and_rejects_garbage`, `test_timeline_marks_screens_and_payments`, `test_bot_click_is_attributed_by_telegram_id`, `test_middleware_passes_telegram_id_and_keeps_tasks` — Пин: middleware зовёт запись с telegram_id и держит фоновую задачу сильной ссылкой., `test_stars_payment_message_is_logged`, `test_remember_task_holds_until_done`, `test_remember_task_ignores_non_tasks` — Тесты middleware подменяют create_task заглушкой, возвращающей None., `test_events_reach_the_admin_timeline_end_to_end` — Кабинет прислал экран и два нажатия — админ видит их с подписями, без сырых путей.
- `tests/services/test_user_created_event.py` — Python-модуль
  Классы: нет
  Функции: `test_emit_user_created_event_uses_persisted_user`
- `tests/services/test_user_device_alias.py` — Python-модуль
  Классы: нет
  Функции: `test_normalize_alias_basic`, `test_normalize_alias_caps_at_max_length`, `test_normalize_alias_preserves_unicode`, `test_attach_aliases_to_devices_sets_local_name_when_match`, `test_attach_aliases_to_devices_handles_empty_aliases`, `test_attach_aliases_to_devices_handles_missing_hwid` — Device without hwid key — alias merge must not crash, just yield None., `test_attach_aliases_to_devices_is_in_place_mutation` — The helper mutates each dict for cheap downstream rendering., `test_attach_aliases_empty_alias_string_falls_back_to_none` — `''` in the alias dict is treated as 'not set' so renderers fall back., `test_set_alias_rejects_empty_input` — set_alias is the explicit setter — empty input must raise, not silently delete., `test_set_alias_executes_on_conflict_update_touching_updated_at` — The compiled statement must update both `alias` AND `updated_at`., `test_set_alias_with_commit_false_does_not_commit` — commit=False defers commit to caller (cabinet route session middleware)., `test_set_alias_with_commit_true_does_commit` — commit=True (default) commits — used by bot FSM handler that has no session middleware., `test_upsert_alias_with_empty_input_calls_delete` — Legacy upsert wrapper: empty/whitespace input → delete_alias path.
- `tests/services/test_user_revival_service.py` — Python-модуль
  Классы: нет
  Функции: `db`, `test_revive_flips_status_to_active`, `test_revive_preserves_balance_and_referral_state` — The cabinet revival path is NOT a wipe — value-bearing fields stay., `test_revive_never_commits_caller_owns_transaction` — Architect's call: revive_deleted_user must NEVER commit., `test_revive_raises_when_already_active` — Misuse-guard: revive must NEVER silently no-op on ACTIVE rows., `test_revive_raises_on_blocked_user` — A BLOCKED admin-action row is a separate domain — revival is wrong here.
- `tests/services/test_web_auth_request_context.py` — Python-модуль
  Классы: нет
  Функции: `test_token_stores_requester_and_context_is_read_without_consuming`, `test_no_context_for_linked_or_missing_token`
- `tests/services/test_webhook_bandwidth_threshold.py` — Python-модуль
  Классы: нет
  Функции: `test_percent_comes_from_last_triggered_threshold`, `test_legacy_threshold_percent_field_still_accepted`, `test_zero_last_triggered_threshold_is_not_a_percent` — 0 — «порог ещё не срабатывал»; показывать «0%» нельзя, берём запасное значение.
- `tests/services/test_webhook_deleted_missing_user.py` — Python-модуль
  Классы: нет
  Функции: `test_deleted_event_for_already_removed_user_is_skipped`
- `tests/services/test_webhook_sibling_expiry.py` — Python-модуль
  Классы: нет
  Функции: `test_pre_multitariff_sibling_with_future_end_date_not_expired`, `test_sibling_not_expired_on_transient_api_error`, `test_sibling_not_expired_on_panel_validation_400` — 400 VALIDATION — не «пользователя нет»., `test_sibling_not_expired_when_local_panel_id_is_unusable` — Битый локальный идентификатор — баг данных бота, а не «юзера нет»., `test_sibling_genuinely_gone_is_still_expired` — Don't break legitimate expiry: panel says gone (None == 404) + past end_date -> expire., `test_intentional_panel_deletion_suppresses_sibling_sweep`, `test_single_tariff_sibling_with_its_own_live_account_is_not_expired` — Однотарифный режим не покрывался ни одним тестом., `test_single_tariff_sibling_without_any_live_account_is_expired` — А если и его собственный ключ панель не знает — истекаем, это и есть смысл цикла.
- `tests/services/test_webhook_user_modified_fields.py` — Python-модуль
  Классы: нет
  Функции: `service`, `test_panel_date_wins_for_a_live_subscription`, `test_disabled_subscription_does_not_get_its_days_back` — Обнуление админом: старая дата из панели вернула бы списанные дни., `test_panel_disabled_disables_the_subscription`, `test_webhook_never_declares_a_subscription_expired` — Истечение объявляет мониторинг: у него буфер и уведомления., `test_traffic_limit_and_nested_usage_are_synced` — Расширенная схема панели прячет расход в userTraffic, плоского поля там нет., `test_device_limit_is_never_taken_from_a_webhook` — Лимит устройств задаёт тариф в боте., `test_a_link_that_fails_validation_is_not_stored`, `test_a_valid_link_replaces_the_stored_one`, `test_every_event_stamps_the_subscription` — Метка защищает свежие данные от затирания медленным полным проходом.
- `tests/services/test_wheel_admin_notifier.py` — Python-модуль
  Классы: нет
  Функции: `test_free_spin_shows_prize_and_spins_left`, `test_stars_spin_and_promocode_are_escaped`, `test_grant_free_spins_is_an_extra_spin_row_outside_spin_stats`, `test_grant_rejects_non_positive_count`
- `tests/services/test_wheel_rtp.py` — Python-модуль
  Классы: нет
  Функции: `prize`, `distribution`, `test_auto_prize_expected_payout_matches_configured_budget`, `test_manual_probability_consumes_expected_payout_before_auto_prizes`, `test_infeasible_high_target_caps_probability_and_warns`, `test_no_zero_value_sector_warns_instead_of_claiming_target`, `test_manual_budget_excess_keeps_manual_chance_but_disables_auto_payout`, `test_multiple_zero_sectors_share_residual_probability`, `test_zero_probability_sector_cannot_win_at_random_zero`, `test_manual_only_tables_keep_relative_weights_and_report_normalization`, `test_valid_manual_override_is_unchanged`, `test_zero_only_table_reports_unreachable_positive_budget`
- `tests/services/test_wheel_spin_promocode.py` — Python-модуль
  Классы: нет
  Функции: `env`, `test_refused_without_spending_the_code`, `test_paid_subscription_gets_one_spin`, `test_refusal_text_is_not_the_generic_invalid_code`, `test_wheel_keyboard_only_for_spin_codes`, `test_spin_activation_sends_no_admin_message` — Уведомление ждёт Telegram внутри запроса, а поток кодов упирается в flood control.
- `tests/services/test_wheel_topup_spins.py` — Python-модуль
  Классы: нет
  Функции: `test_free_spins_counted_from_deposits_won_and_used`, `test_past_spending_counts_toward_progress_not_spins`, `test_free_spins_off_when_disabled`, `test_free_spin_allowed_past_daily_limit`, `test_no_free_spins_reason_points_to_topups`, `test_free_spin_rechecked_under_lock` — Два параллельных запроса: второй видит 0 спинов под блокировкой и ничего не выигрывает., `test_device_prize_is_bonus_on_top_of_paid_limit`, `test_device_prize_refused_goes_to_balance`, `test_expired_device_bonus_not_counted`, `test_discount_prize_sets_personal_discount`, `test_discount_prize_keeps_bigger_active_discount`, `test_prize_messages`, `test_spins_earned`, `test_spin_earned_message_has_wheel_button`, `test_notifier_ignores_non_topups`, `test_migration_0138_chain_and_prize_table`, `test_prize_rarity`, `test_migration_0139_threshold_and_palette`, `test_migration_0139_raises_seeded_prizes_and_leaves_admin_edits`, `test_prize_days_on_expired_subscription_start_from_now`, `test_days_prize_reactivates_only_expired`
- `tests/services/test_withdrawal_pending_reason.py` — Python-модуль
  Классы: нет
  Функции: `test_pending_request_reason_has_number_amount_and_date`, `test_without_pending_request_min_amount_reason_stays`
- `tests/services/test_withdrawal_reminders.py` — Python-модуль
  Классы: нет
  Функции: `reminder_settings`, `sent`, `test_stale_pending_request_gets_reminder`, `test_fresh_request_waits_out_the_limit`, `test_decided_request_is_silent` — Любой статус, кроме pending, — решение принято, напоминать не о чем., `test_cooldown_gates_repeats`, `test_disabled_flag_silences_everything`, `test_failed_send_keeps_request_for_next_round` — Не ушло — отметку не ставим, следующий круг попробует снова., `plain_sender` — Rich-рендер выключен: проверяем классический send_message с thread_id., `test_reminder_goes_to_withdrawal_topic_when_configured`, `test_reminder_falls_back_to_partners_topic`, `test_reminder_buttons_match_the_original_notification`, `test_waiting_time_reads_naturally` — Двое суток ожидания — «2 д 1 ч», а не «49 ч 0 мин».
- `tests/services/test_withdrawal_status_notifications.py` — Python-модуль
  Классы: нет
  Функции: `support_menu_on`, `test_rejection_without_reason_is_neutral_and_has_support_button`, `test_rejection_with_reason_shows_it_escaped`, `test_completed_has_no_support_button`, `test_bot_rejection_sends_support_button`, `test_cabinet_complete_notifies_user`, `test_notify_skips_users_without_telegram`
- `tests/services/test_xrocket_status_check.py` — Python-модуль
  Классы: нет
  Функции: `test_status_check_credits_lost_webhook_once`, `test_status_check_unpaid_invoice_changes_nothing`, `test_status_button_queries_provider_for_pending_payment`, `test_status_button_does_not_query_provider_for_foreign_payment`, `test_xrocket_is_in_manual_and_auto_check_lists`, `test_xrocket_client_has_request_timeout`, `test_deleted_invoice_is_reported_as_expired`, `test_non_json_answer_is_not_an_exception`, `test_deleted_invoice_leaves_the_autocheck_queue`
- `tests/services/test_yandex_purchase_hook.py` — Python-модуль
  Классы: нет
  Функции: `test_passes_cid_through_to_store_and_fires_purchase` — Frontend cached CID → backend stores it, then fires purchase event., `test_no_cid_still_fires_purchase_event` — If the separate /yandex-cid POST already completed, frontend may pass, `test_disabled_feature_skips_everything` — When offline conversions are off, neither store nor fire should run., `test_store_failure_does_not_block_purchase_event` — Even if persisting the CID throws, the purchase event must still fire —

#### tests/services/panel_sync

- `tests/services/panel_sync/test_blocked_user_stays_disabled.py` — Python-модуль
  Классы: нет
  Функции: `test_bulk_sync_does_not_reactivate_a_blocked_user`, `test_cabinet_sync_does_not_reactivate_a_blocked_user`
- `tests/services/panel_sync/test_deleted_squads.py` — Python-модуль
  Классы: `Panel` (4 методов)
  Функции: `test_deleted_squad_recovery_preserves_only_assigned_live_servers`, `test_all_assigned_squads_deleted_does_not_grant_unrelated_access`, `test_other_errors_do_not_trigger_squad_recovery`, `test_catalog_outage_preserves_original_failure_without_retry`, `test_normal_write_does_not_fetch_catalog`, `test_invalid_catalog_cannot_authorize_a_retry`, `test_generic_error_with_unchanged_catalog_is_not_retried`, `test_second_failure_is_propagated_without_retry_loop`, `test_recovery_through_real_http_client_and_catalog_parser`
- `tests/services/panel_sync/test_deleted_squads_live_panel.py` — Python-модуль
  Классы: нет
  Функции: `test_deleted_squads_against_real_panel`
- `tests/services/panel_sync/test_device_limit_enforcement.py` — Python-модуль
  Классы: нет
  Функции: `api_with_devices`, `test_explicit_cap_keeps_most_recent_registrations_and_removes_only_excess`, `test_unlimited_or_omitted_cap_never_removes_devices`, `test_failed_removal_is_not_reported_as_success_and_next_sync_retries`, `test_same_cap_with_legal_device_count_preserves_registrations`, `test_invalid_or_foreign_device_list_never_deletes_anything`, `test_device_reappearing_after_removal_requires_retry`
- `tests/services/panel_sync/test_expiry.py` — Python-модуль
  Классы: нет
  Функции: `test_live_subscription_keeps_its_own_date`, `test_expired_subscription_does_not_touch_the_date_on_update` — Главное свойство: поле не отправляется, панель хранит настоящую дату., `test_new_panel_account_gets_the_real_date_even_if_it_has_passed` — При СОЗДАНИИ панель принимает прошедшую дату — выдумывать не надо., `test_future_date_survives_even_for_an_inactive_subscription` — Заблокированный пользователь с ещё не истёкшей подпиской: дату не занижаем., `test_blocked_but_not_expired_subscription_still_pushes_its_real_date` — Блокировка — не истечение: дата в будущем, панель её примет и должна знать., `test_expired_subscription_extinguishes_a_future_date_in_the_panel` — Панель держит будущее — гасим ближайшим допустимым моментом., `test_expired_subscription_leaves_a_past_date_in_the_panel_alone` — В панели уже прошлое — это и есть настоящая история, переписывать нечего., `test_expired_subscription_without_a_known_panel_date_is_left_alone` — Что стоит в панели, неизвестно — молчим, как и раньше., `test_naive_panel_date_is_read_as_utc` — Панель отдаёт UTC; наивное значение нельзя считать локальным временем., `test_nobody_builds_the_date_by_hand`, `test_the_debt_list_only_names_modules_that_still_build_the_request` — Перевели модуль — убрать его отсюда, иначе список перестанет что-то значить., `test_every_module_sending_a_date_uses_the_shared_rule` — Кто сам кладёт дату в запрос к панели — обязан взять её из общего правила., `test_our_own_extinguished_date_is_not_moved_again`, `test_a_date_a_few_minutes_ahead_is_left_alone_too` — Отключённой подписке пять минут ничего не решают: доступ закрывает статус., `test_a_genuinely_live_panel_date_is_still_extinguished`
- `tests/services/panel_sync/test_fields.py` — Python-модуль
  Классы: нет
  Функции: `test_account_metadata_includes_tag_alongside_description`, `test_narrow_push_without_flags_sends_only_account_metadata`, `test_flags_add_exactly_their_fields`, `test_extra_fields_are_merged_without_losing_metadata`
- `tests/services/panel_sync/test_foreign_panel_owner.py` — Python-модуль
  Классы: нет
  Функции: `test_account_held_by_another_users_subscription_is_foreign`, `test_row_ownership_beats_a_user_level_id_picked_up_earlier` — Прошлая запись по почте успела проставить A ``users.remnawave_id`` — строка B всё равно главнее., `test_the_owner_sees_its_own_account_as_its_own`, `test_single_tariff_sibling_subscription_of_the_same_person_is_not_foreign` — В одиночном режиме все подписки человека адресуют один аккаунт — это штатно., `test_multi_tariff_sibling_subscription_owns_its_own_account` — В мультитарифе у каждой подписки свой аккаунт: соседняя подписка того же человека — чужой хозяин., `test_single_tariff_user_level_link_of_another_person_is_foreign` — Старые строки одиночного режима: адрес лежит только в ``users.remnawave_id``., `test_deleted_person_owns_nothing`, `test_unclaimed_account_is_not_foreign`, `test_resolve_skips_a_foreign_account_found_by_email`, `test_resolve_skips_a_foreign_user_level_id_and_keeps_searching` — Записанный когда-то id пользователя ведёт в чужой аккаунт — ищем свой дальше., `test_expired_subscription_never_writes_into_someone_elses_paid_account` — Шаг 3 из задачи: гашение 737 до now+5 мин. Теперь PATCH не уходит вовсе., `test_known_address_from_the_user_row_is_checked_too` — Продление передаёт готовый адрес — ``users.remnawave_id``, прилипший от прошлой записи по почте., `test_the_owner_still_writes_into_its_own_account` — Сторож не должен задеть хозяина: B продлевает — PATCH уходит как раньше., `test_monitoring_does_not_adopt_someone_elses_paid_date` — Истекает подписка A, по почте находится оплаченный B аккаунт — это не продление A., `test_bulk_push_skips_a_foreign_account_without_an_error`, `test_bulk_push_leaves_deleted_people_alone` — Мягко удалённая запись A продолжала гасить чужой аккаунт — обходной путь из задачи не работал.
- `tests/services/panel_sync/test_identity.py` — Python-модуль
  Классы: нет
  Функции: `test_exact_subscription_id_wins_in_multi_tariff`, `test_single_tariff_uses_the_user_level_id`, `test_stale_id_is_not_trusted_and_search_continues` — Панель ответила 404 на записанный id — связь протухла, ищем дальше., `test_short_uuid_is_checked_before_telegram` — У человека может быть несколько аккаунтов — неточный ключ берёт первый попавшийся., `test_email_is_the_last_resort`, `test_transient_error_on_short_uuid_forbids_guessing` — Точный ключ остался непроверенным: создавать нового нельзя, честно падаем., `test_transient_error_on_short_uuid_is_forgiven_when_another_key_identifies` — Если опознали по telegram — падать не из-за чего., `test_invalid_local_id_is_a_data_bug_and_is_raised` — Непригодный идентификатор бота — не «аккаунта нет»; уход в создание плодил бы дубли., `test_multi_tariff_filters_inexact_matches_by_subscription_suffix`, `test_multi_tariff_without_short_id_does_not_guess` — Без суффикса неточный ключ выбрал бы чужую подписку того же человека., `test_pinned_identity_never_falls_back_to_the_user_account` — Подменять личность выбранной подписки пользовательским id нельзя., `test_nothing_found_returns_an_empty_identity`
- `tests/services/panel_sync/test_liveness.py` — Python-модуль
  Классы: нет
  Функции: `test_active_subscription_of_an_active_user_is_live`, `test_trial_counts_as_live`, `test_blocked_user_is_never_live` — Блокировка обязана доезжать до панели: иначе синхронизация снимает бан., `test_deleted_user_is_never_live`, `test_expired_by_date_is_not_live_even_with_active_column`, `test_disabled_and_limited_columns_are_not_live`, `test_missing_end_date_is_not_live`, `test_naive_end_date_is_read_as_utc` — В базах до TIMESTAMPTZ дата приходит наивной — считаем её UTC, а не локальной., `test_user_without_status_attribute_is_treated_as_active` — Часть вызывающих отдаёт облегчённый объект без статуса — синк не роняем., `test_matches_actual_status_of_the_model` — Правило обязано совпадать с Subscription.actual_status — иначе разъедутся снова., `test_is_subscription_expired_matches_actual_status_of_the_model` — Вебхук и импорт отличают «истекла» от «отключена» этим же правилом — оно обязано совпадать с моделью., `test_is_subscription_expired_takes_an_explicit_clock`
- `tests/services/panel_sync/test_no_bypass.py` — Python-модуль
  Классы: нет
  Функции: `test_nobody_writes_to_the_panel_directly`
- `tests/services/panel_sync/test_package_is_self_contained.py` — Python-модуль
  Классы: нет
  Функции: `test_no_module_in_panel_sync_imports_subscription_service` — Ни на уровне модуля, ни лениво внутри функций., `test_record_identity_links_row_even_without_subscription_service` — Сценарий репорта: модуль сервиса на месте, но нужного имени в нём нет — связь всё равно пишется., `test_subscription_service_reexports_moved_helpers` — Внешний код, импортировавший помощники из сервиса подписок, получает те же объекты.
- `tests/services/panel_sync/test_paid_daily_reset_live_panel.py` — Python-модуль
  Классы: нет
  Функции: `test_real_panel_reset_ack_and_lost_response`
- `tests/services/panel_sync/test_paid_date_hold.py` — Python-модуль
  Классы: нет
  Функции: `test_earlier_panel_date_is_held_right_after_a_payment`, `test_later_panel_date_is_still_taken_after_a_payment` — Продлили ещё и в панели — это не откат, берём как раньше., `test_hold_expires_with_the_window_and_without_a_payment`, `test_minute_tolerance_is_not_a_hold` — Разница в пределах минуты и так не переносится — сторож на неё не реагирует., `test_stale_panel_does_not_expire_a_just_paid_subscription` — Старая дата панели уже прошла: статус «истекла» из неё тоже не берём., `test_real_panel_actions_still_apply_during_the_hold` — Отключение админом и лимит трафика — не следствие старой даты., `test_without_a_recent_payment_the_panel_still_expires_it`
- `tests/services/panel_sync/test_payload.py` — Python-модуль
  Классы: нет
  Функции: `test_gigabytes_become_bytes`, `test_unlimited_devices_are_explicit_in_create_and_update`, `test_zero_gigabytes_mean_unlimited`, `test_empty_squads_are_never_sent_on_update` — Пустой список для панели значит «снять все инбаунды» — так подписку глушили., `test_empty_squads_are_sent_as_empty_list_on_create` — У нового аккаунта снимать нечего, а поле обязательно., `test_multi_tariff_username_carries_the_subscription_suffix`, `test_multi_tariff_username_falls_back_to_subscription_id` — Пустой short_id: без запасного суффикса два тарифа получали одно имя,, `test_single_tariff_username_has_no_subscription_suffix`, `test_blocked_user_gets_disabled_status`, `test_live_subscription_gets_active_status_and_its_own_date`, `test_update_of_an_expired_subscription_extinguishes_a_future_panel_date`, `test_update_of_an_expired_subscription_keeps_a_past_panel_date`, `test_create_of_an_expired_subscription_carries_its_real_date` — POST панель принимает с прошедшей датой — выдумывать «минуту вперёд» не надо., `test_external_squad_is_taken_from_the_tariff`, `test_null_external_squad_is_never_sent` — Панель отвечает ошибкой A039 на null в externalSquadUuid., `test_update_payload_never_carries_username` — PATCH с username переименовал бы аккаунт в панели., `test_update_payload_carries_the_panel_user_id`, `test_only_fields_filter_keeps_the_addressee` — Узкие правки (описание, сквады) не должны тащить в панель соседние поля., `test_update_always_carries_the_tag_so_a_stale_one_is_cleared` — Тег — поле аккаунта, которым владеет бот, как описание. Не вычислил тега —, `test_create_omits_the_tag_when_there_is_none` — У нового аккаунта снимать нечего — поле в POST не идёт., `test_expired_subscription_of_an_active_user_sends_no_status_on_update`, `test_active_column_past_its_date_sends_no_status_on_update` — Мониторинг ещё не успел поставить EXPIRED — для панели это всё равно истечение, не отключение., `test_limited_subscription_sends_no_status_on_update` — Исчерпанный трафик панель считает сама; DISABLED сверху не снимался бы её же сбросом трафика., `test_disabled_subscription_sends_disabled_on_update` — Отключение в боте (обнуление админом) — настоящее решение, оно обязано доехать., `test_blocked_user_with_expired_subscription_sends_disabled_on_update` — Блокировка пользователя важнее истечения: панель обязана держать его выключенным., `test_expired_column_with_a_future_date_still_sends_disabled_on_update` — Противоречивое состояние (статус «истекла», дата в будущем) — гасим, как и раньше., `test_create_of_an_expired_subscription_sends_expired_status` — При создании панель принимает и EXPIRED — заведённый аккаунт сразу истёкший, а не отключённый., `test_create_of_a_limited_subscription_sends_limited_status`
- `tests/services/panel_sync/test_projection.py` — Python-модуль
  Классы: нет
  Функции: `test_reads_the_dictionary_shape_of_the_panel`, `test_reads_the_parsed_object_shape_of_the_client`, `test_reads_the_status_enum_of_the_client` — Клиент отдаёт статус перечислением, панель — строкой., `test_unparsable_date_does_not_explode`, `test_active_panel_moves_the_end_date_in_both_directions`, `test_disabled_panel_date_is_taken_too` — Панель — истина при любом статусе: у отключённого дата тоже переносится., `test_panel_active_resurrects_an_expired_row_with_the_panel_date` — Продлили руками в панели — бот берёт дату и снова считает подписку живой., `test_trial_stays_trial_when_the_panel_says_active` — Панель не различает триал и оплату — триал в боте остаётся триалом., `test_expired_in_the_panel_takes_the_panel_date_and_expires`, `test_a_few_seconds_of_difference_are_ignored`, `test_limited_in_the_panel_becomes_limited_in_the_bot`, `test_trial_past_its_date_takes_the_disabled_status_of_the_panel`, `test_silent_panel_does_not_expire_a_subscription_that_is_active_in_the_bot` — Панель не сказала статус — не гадаем; истечение по своей дате доводит мониторинг., `test_expired_trial_becomes_expired`, `test_traffic_is_carried_over`, `test_traffic_jitter_is_ignored`, `test_limits_are_read_from_the_panel` — Панель — истина и по лимитам: правка в панели приезжает в бота., `test_missing_limits_in_the_answer_keep_the_bot_values`, `test_squads_come_from_the_panel`, `test_empty_squad_list_means_the_panel_does_not_know`, `test_links_are_refreshed`, `test_status_can_be_frozen_for_a_subscription_just_touched_by_a_webhook` — Свежая оплата важнее любого снимка панели., `test_stale_snapshot_still_takes_the_date_of_a_live_account` — Продление, сделанное руками в панели, бот обязан увидеть., `test_snapshot_limited_is_limited_whatever_the_bot_counted` — Панель — истина: «исчерпана» переносится, даже если счётчик бота отстал., `test_snapshot_limited_overrides_a_locally_disabled_row`, `test_snapshot_expired_is_expired_whatever_the_bot_date_says` — Панель гасит аккаунт сама и знает об этом лучше бота., `test_stale_disabled_is_applied` — DISABLED — решение админа в панели, и донести его больше некому., `test_a_snapshot_older_than_the_row_does_not_touch_billing_fields`, `test_a_snapshot_newer_than_the_row_is_applied`, `test_a_webhook_stamp_also_counts_as_a_fresh_change`, `test_stale_snapshot_still_carries_traffic_and_links`, `test_admin_pull_takes_the_date_even_from_a_disabled_account` — Отключённый в панели остаётся отключённым, даже если дата прошла: так решила панель., `test_admin_pull_takes_the_limits_from_the_panel`, `test_all_policies_but_webhook_are_the_same_panel_truth` — Кнопка «из панели в бота», полный проход и фоновое чтение верят панели одинаково., `test_panel_active_without_a_date_keeps_the_status` — Дату не разобрали — статус не трогаем, а не гасим наугад., `test_reads_limits_from_both_shapes_of_the_answer`, `test_stale_bulk_snapshot_does_not_roll_back_squads_either` — Полный проход: подписку изменили после снимка — сквады снимка тоже устарели.
- `tests/services/panel_sync/test_record_identity_user_level.py` — Python-модуль
  Классы: нет
  Функции: `test_multi_tariff_records_account_for_user_without_one`, `test_multi_tariff_keeps_existing_user_account`
- `tests/services/panel_sync/test_runner_leaves_expired_status_to_the_panel.py` — Python-модуль
  Классы: нет
  Функции: `test_bulk_pass_does_not_disable_an_expired_subscription`
- `tests/services/panel_sync/test_runner_pacing.py` — Python-модуль
  Классы: нет
  Функции: `test_bulk_sync_never_resets_devices`, `test_throttled_panel_is_a_warning_not_an_error`, `test_batch_read_transaction_is_closed_before_panel_writes` — Живой лог: коммит в конце пачки падал с «connection is closed» — соединение, `test_batch_fetch_survives_a_dropped_connection`
- `tests/services/panel_sync/test_tags.py` — Python-модуль
  Классы: нет
  Функции: `test_normalize_upper_cases_and_treats_blank_as_absent`, `test_normalize_rejects_what_the_panel_rejects`, `test_tariff_tag_wins_for_paid_subscription`, `test_tariff_tag_wins_over_trial_tag_too`, `test_without_tariff_tag_trial_uses_global_trial_tag`, `test_without_tariff_tag_paid_uses_global_paid_tag`, `test_blank_tariff_tag_counts_as_absent`, `test_payload_resolves_tag_from_tariff_when_caller_passed_none`, `test_payload_keeps_explicit_tag_from_caller`, `test_without_a_configured_tag_the_account_gets_none` — «Тега нет» — тоже решение: в PATCH оно уезжает как null и снимает прежний
- `tests/services/panel_sync/test_writer.py` — Python-модуль
  Классы: нет
  Функции: `test_known_account_is_updated_not_created`, `test_unknown_account_is_created`, `test_panel_says_user_is_gone_so_it_is_recreated` — Протухший id в базе не должен ронять синхронизацию., `test_transient_panel_error_is_not_a_reason_to_create_a_duplicate`, `test_expired_subscription_extinguishes_a_future_date_known_in_advance` — Дата панели уже на руках — гасим тем же запросом, без второго., `test_expired_subscription_extinguishes_a_future_date_learned_from_the_answer` — Дату панели узнали только из ответа — гасим вторым запросом., `test_live_subscription_is_written_once`, `test_identity_is_written_onto_the_subscription`, `test_panel_id_taken_by_a_sibling_row_is_not_written` — Колонка частично уникальна: IntegrityError откатил бы уже сделанный PATCH., `test_single_tariff_records_the_account_on_the_user_too`, `test_only_fields_narrows_the_patch` — Узкая правка описания не должна тащить в панель дату и сквады., `test_recreated_account_replaces_the_stale_link` — Иначе следующий проход снова не найдёт аккаунт и заведёт ещё один дубль., `test_dead_id_is_relinked_to_the_account_that_already_exists` — Прошлая попытка завела аккаунт, но связь не записала: имя занято, и создание, `test_recreated_account_clears_the_dead_id_from_the_user_in_multi_tariff`, `test_extinguish_learned_from_the_answer_retries_with_a_bigger_margin` — Второй PATCH отвергнут как «прошлое» — повтор с большим запасом, а не ошибка прохода., `test_extinguish_known_in_advance_falls_back_to_status_first` — Дата уехала одним PATCH с остальными полями, и панель отвергла всё: поля важнее — шлём без даты, дату гасим отдельно., `test_a_second_rejection_is_a_real_error` — Если и большой запас панель считает прошлым, это не разъезд часов — ошибку не глотаем., `test_other_validation_errors_are_not_mistaken_for_clock_skew`, `test_paid_subscription_without_a_tag_clears_the_trial_tag_left_in_the_panel` — Жалоба 17.09: общий триальный тег задан, платный — нет, у тарифа тега нет., `test_patch_panel_account_clears_the_tag_only_when_told_to` — Карточка аккаунта: без ``tag`` в вызове поле не трогается, ``tag=None`` — снимает.

### tests/utils

- `tests/utils/__init__.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/utils/test_background.py` — Python-модуль
  Классы: нет
  Функции: `test_spawn_keeps_reference_until_task_finishes`, `test_failed_task_is_released_and_its_exception_consumed`, `test_spawn_passes_task_name`, `test_main_does_not_spawn_unreferenced_tasks` — Задачи запуска идут через spawn_background_task: иначе сборщик мусора может снять их на полпути.
- `tests/utils/test_chat_menu_button.py` — Python-модуль
  Классы: нет
  Функции: `test_disabled_does_not_touch_menu_button`, `test_enabled_sets_webapp_menu_button`, `test_falls_back_to_miniapp_custom_url`, `test_non_https_url_is_skipped`, `test_empty_text_defaults`
- `tests/utils/test_codeql_input_boundaries.py` — Python-модуль
  Классы: нет
  Функции: `parsing_deadline`, `test_unterminated_long_tag_is_bounded`, `test_unterminated_rich_blocks_are_bounded`, `test_rich_segmentation_preserves_existing_short_input_semantics`, `test_blacklist_conversion_uses_parsed_host_and_blob_path`
- `tests/utils/test_display_mode.py` — Python-модуль
  Классы: нет
  Функции: `test_normalize_display_mode_known_values`, `test_normalize_display_mode_fallback_to_both`, `test_visibility_matrix`, `test_config_defaults_are_both`, `test_settings_registered_in_info_pages_category`
- `tests/utils/test_email_alias.py` — Python-модуль
  Классы: `TestCanonicalEmail` (5 методов)
  Функции: нет
- `tests/utils/test_formatters_basic.py` — Python-модуль
  Классы: нет
  Функции: `test_format_datetime_handles_iso_strings` — ISO-строка должна корректно преобразовываться в отформатированный текст., `test_format_time_ago_returns_human_readable_text` — Разница во времени должна переводиться в человеко-понятную строку., `test_format_days_declension_handles_russian_rules` — Склонение дней в русском языке зависит от числа., `test_format_username_link_wraps_telegram_handle_in_anchor` — Rich-сообщения идут со skip_entity_detection=True — ссылка нужна явная., `test_format_username_link_does_not_double_the_at_sign` — Логин может прийти уже с собакой — в тексте она должна остаться одна., `test_format_username_link_returns_fallback_without_username` — Пустой логин отдаётся текстом-заглушкой, без собаки и без ссылки., `test_format_username_link_keeps_non_telegram_logins_as_text` — OAuth-регистрация кладёт в users.username логин Discord/Яндекса., `test_format_username_link_escapes_html_metacharacters` — Значение попадает и в href, и в текст — экранируем оба., `test_admin_dates_are_shown_in_operator_zone` — Жалоба 4.12.0: панель и «Моя подписка» — 18.09.2026 14:17, админка бота — 11:17 (UTC).
- `tests/utils/test_fsm_memory_rss.py` — Python-модуль
  Классы: нет
  Функции: `test_current_rss_is_read_from_statm_not_from_peak`, `test_falls_back_to_peak_without_proc`, `test_log_line_has_current_and_peak`
- `tests/utils/test_gift_links.py` — Python-модуль
  Классы: `TestBuildBotGiftClaimLink` (9 методов), `TestBuildCabinetGiftClaimLink` (5 методов), `TestBuildTelegramGiftShareUrl` (8 методов), `TestLandingGiftLinkIntegration` (1 методов), `TestBuildGiftPublicCode` (9 методов), `TestParseGiftClaimInput` (14 методов), `TestGiftClaimArtifacts` (6 методов)
  Функции: нет
- `tests/utils/test_incy_crypt1.py` — Python-модуль
  Классы: `TestEncryptIncyLink` (6 методов), `TestWrapIncyDeepLink` (12 методов)
  Функции: `decrypt` — Decrypt a crypt1 link the way the INCY client does., `incy_enabled`
- `tests/utils/test_legacy_subscription.py` — Python-модуль
  Классы: нет
  Функции: `tariffs_mode`, `test_paid_without_tariff_in_tariffs_mode_is_legacy`, `test_subscription_with_tariff_is_not_legacy`, `test_trial_without_tariff_is_not_legacy` — Пробная идёт своим путём (покупка тарифа), это не старая подписка., `test_missing_subscription_is_not_legacy`
- `tests/utils/test_lifetime.py` — Python-модуль
  Классы: нет
  Функции: `test_lifetime_period_threshold`, `test_formatters_say_forever_for_lifetime_and_days_otherwise`, `test_payment_descriptions`, `test_end_date_far_ahead_snaps_to_lifetime_end`, `test_model_normalizes_end_date_on_assignment`, `test_naive_far_date_is_also_lifetime`, `test_time_left_for_lifetime`, `test_apply_lifetime_period`, `test_apply_lifetime_period_keeps_regular_periods`, `test_subscription_keyboard_has_no_renew_for_lifetime`, `test_renewal_of_lifetime_subscription_is_refused_before_any_charge`, `test_subpage_snapshot_marks_lifetime`
- `tests/utils/test_local_day.py` — Python-модуль
  Классы: нет
  Функции: `test_bounds_of_moscow_day_are_utc_instants`, `test_moment_before_moscow_midnight_belongs_to_previous_day`, `test_local_date_follows_the_zone_not_utc`, `test_naive_moment_is_treated_as_utc`, `test_spring_forward_day_is_23_hours_long` — Границы считаются через ZoneInfo, а не через фиксированное смещение., `test_fall_back_day_is_25_hours_long`, `test_days_back_counts_calendar_days_across_dst`, `test_default_zone_comes_from_settings`, `test_utc_zone_keeps_utc_midnight`, `test_month_start_is_local_first_day_midnight_in_utc`, `test_month_start_before_local_midnight_is_previous_month`, `test_next_wall_clock_picks_the_next_local_time_today`, `test_next_wall_clock_rolls_over_to_the_earliest_time_tomorrow`, `test_next_wall_clock_keeps_the_local_hour_across_dst`
- `tests/utils/test_logo_resize_tempdir.py` — Python-модуль
  Классы: нет
  Функции: `test_oversized_logo_resized_into_writable_tempdir`, `test_small_logo_returned_unchanged`
- `tests/utils/test_min_device_limit.py` — Python-модуль
  Классы: нет
  Функции: `test_default_floor_is_tariff_device_limit`, `test_opt_in_restores_previous_behaviour` — Флаг возвращает прежний минимум 1 — для тех, кому нужно самоограничение., `test_without_usable_tariff_limit_floor_is_one` — Классический режим и битые значения не должны блокировать уменьшение., `test_no_tariff_at_all_floor_is_one`, `test_keyboard_hides_values_below_tariff_limit` — Кнопки с запрещёнными значениями не должны показываться вовсе., `test_keyboard_offers_lower_values_when_opted_in`
- `tests/utils/test_notification_keyboards.py` — Python-модуль
  Классы: нет
  Функции: `test_keyboard_skips_missing_buttons`, `test_keyboard_without_buttons_is_none`, `test_admin_links_need_cabinet_url`, `test_admin_links_point_to_cabinet`, `test_admin_card_skips_missing_user`, `test_brand_in_footer`
- `tests/utils/test_page_nav_row.py` — Python-модуль
  Классы: нет
  Функции: `test_middle_page_has_both_arrows`, `test_first_and_last_page_drop_one_arrow`, `test_custom_current_callback_and_prefix_with_ids`, `test_arrows_come_from_texts_when_given`
- `tests/utils/test_payment_button_config.py` — Python-модуль
  Классы: нет
  Функции: нет
- `tests/utils/test_pricing_utils.py` — Python-модуль
  Классы: `TestCalculatePricePerMonth` (4 методов), `TestBuildDynamicValues` (2 методов)
  Функции: нет
- `tests/utils/test_public_url.py` — Python-модуль
  Классы: нет
  Функции: `test_takes_scheme_and_host_from_proxy_headers`, `test_without_proxy_headers_link_is_unchanged`, `test_first_value_of_chained_headers_and_host_fallback`, `test_unknown_scheme_in_header_is_not_trusted`
- `tests/utils/test_quiet_hours.py` — Python-модуль
  Классы: нет
  Функции: `test_quiet_hours_wrap_midnight`, `test_equal_hours_mean_no_quiet_time`
- `tests/utils/test_redis_client.py` — Python-модуль
  Классы: нет
  Функции: `from_url` — Вызовы ``BlockingConnectionPool.from_url`` — через него фабрика строит пул., `test_factory_disables_maintenance_notifications`, `test_factory_defaults_to_settings_url_and_keeps_explicit_kwargs`, `test_factory_skips_config_on_old_redis_py` — redis-py без модуля maint_notifications: лишний kwarg уронил бы from_url., `test_factory_sizes_pool_from_settings_and_keeps_explicit_override` — «MaxConnectionsError: Too many connections»: у redis-py 8 пул по умолчанию на 100,, `test_every_redis_client_in_app_goes_through_factory` — Сторож: прямой ``from_url``/``Redis(`` в app/ вернул бы шум и обошёл общие настройки.
- `tests/utils/test_remnawave_auto_sync.py` — Python-модуль
  Классы: нет
  Функции: `test_parse_daily_time_list`, `test_calculate_next_run_same_day_in_configured_timezone` — REMNAWAVE_AUTO_SYNC_TIMES — локальное время оператора (.env.example так и обещает: «по МСК»),, `test_calculate_next_run_rollover_in_configured_timezone`, `test_perform_sync_rebuilds_service_on_each_run`
- `tests/utils/test_rich_admin.py` — Python-модуль
  Классы: нет
  Функции: `test_rich_flag_default_is_enabled`, `test_classic_html_to_rich_conversion`, `test_classic_html_emoji_before_bold_becomes_header` — Заголовки вида «🔧 <b>ВКЛЮЧЕНИЕ ТЕХРАБОТ</b>» (эмодзи до тега) тоже выносятся в h6., `test_classic_html_without_bold_header_kept_as_is`, `test_kv_table_escapes_keys_and_keeps_value_html`, `test_traceback_details_escapes_content`, `test_try_send_passes_thread_and_markup`, `test_try_send_disabled_by_setting`, `test_try_send_unsupported_marks_latch`, `test_try_send_render_error_does_not_latch`, `test_try_send_oversized_falls_back`, `test_pre_blocks_survive_conversion` — <pre>-блоки (описание релиза из markdown) сохраняют форматирование —, `test_inline_buttons_move_into_canvas_in_private_admin_chat` — В личке админа Mini App допустим, поэтому переносится вся клавиатура., `test_web_app_button_stays_outside_in_group_admin_chat` — У группы отрицательный id, а Mini App там не откроется — клавиатура остаётся., `test_callback_buttons_move_into_canvas_in_group_admin_chat` — Обычные callback-кнопки в группе переносятся штатно.
- `tests/utils/test_rich_buttons.py` — Python-модуль
  Классы: нет
  Функции: `test_button_types_map_to_spec_tags`, `test_login_url_carries_its_flags`, `test_chosen_chat_flags_are_emitted_as_bare_attributes`, `test_rows_are_preserved_and_align_applied`, `test_long_row_is_split_by_spec_limit` — InputRichBlockButtons: «List of 1-8 buttons». Более длинный ряд сервер отвергнет., `test_unrepresentable_button_keeps_whole_keyboard_outside` — Всё или ничего: половина кнопок внутри — это потерянные кнопки., `test_web_app_is_refused_outside_private_chat` — Mini App открывается только в личке — в группе такая кнопка не сработает., `test_link_style_only_survives_on_callback_buttons` — style="link" спецификация разрешает только callback-кнопкам., `test_unknown_style_is_dropped_not_forwarded`, `test_custom_emoji_icon_moves_into_button_text` — У RichMessageButton нет icon_custom_emoji_id — иконка переносится в текст., `test_text_and_attributes_are_escaped`, `test_nothing_to_move_returns_none`
- `tests/utils/test_rich_logo_url_versioned.py` — Python-модуль
  Классы: нет
  Функции: `logo`, `test_auto_url_carries_the_file_version`, `test_new_logo_file_gets_a_new_address`, `test_explicit_url_is_left_exactly_as_the_operator_wrote_it`
- `tests/utils/test_rich_media.py` — Python-модуль
  Классы: нет
  Функции: `rich_config`, `test_outgoing_rich_images_have_referenced_media`, `bot_api_server`, `test_startup_logo_crosses_real_sdk_http_boundary`, `test_rich_image_attachment_deduplicates_and_avoids_existing_ids`, `test_text_only_and_escaped_image_text_stay_unchanged`
- `tests/utils/test_rich_menu.py` — Python-модуль
  Классы: `DummyTexts` (2 методов), `PremiumEmojiTexts` (2 методов), `HostileTexts` (1 методов)
  Функции: `test_rich_flag_default_is_enabled`, `test_builder_without_subscription`, `test_builder_hints_in_details_and_random_message_sanitized`, `test_builder_without_hints_has_no_details`, `test_input_rich_message_flags`, `test_try_send_disabled_by_setting`, `test_try_send_unsupported_server_marks_unavailable`, `test_try_send_render_error_does_not_disable_rich`, `test_try_edit_text_message_uses_edit_message_text`, `test_try_edit_photo_message_recreates_via_send`, `test_try_edit_not_modified_is_success`, `test_try_edit_unsupported_on_edit_marks_unavailable`, `test_try_edit_build_failure_falls_back`, `test_try_send_happy_path_sends_rich_message` — Успешная отправка: реальный билдер (застабены только источники контента)., `test_try_send_forbidden_is_handled_without_fallback` — Бот заблокирован: True, чтобы классический рендер не долбил тот же чат., `test_try_edit_forbidden_is_handled_without_fallback`, `test_try_edit_transient_edit_error_falls_back_without_disabling` — 'message to edit not found' — не признак старого сервера: rich остаётся включён,, `test_try_edit_photo_delete_failure_falls_back_to_classic` — deleteMessage запрещён для сообщений старше 48ч: rich не отправляется новым, `test_show_main_menu_prefers_rich_and_falls_back` — Поведенческий тест ветвления show_main_menu: rich True — классика не зовётся,, `test_send_passes_message_effect`, `test_rejected_effect_degrades_and_resends` — Отклонённый эффект: повтор без него, эффект отключается до рестарта., `test_logo_included_from_explicit_url`, `test_logo_auto_url_from_webhook`, `test_logo_fetch_failure_degrades_and_resends` — Telegram не скачал логотип: единственный повтор без логотипа, флаг до рестарта., `test_logo_can_be_disabled_explicitly` — Rich-меню должно работать вообще без логотипа., `test_non_http_logo_value_disables_logo_instead_of_breaking_menu` — «Подставлю не-картинку, чтобы не грузилась» не должно ронять rich в классику., `test_unknown_send_error_retries_without_logo` — Незнакомая ошибка при наличии логотипа — повтор без него, а не уход в классику., `test_unknown_send_error_without_logo_falls_back_to_classic` — Без логотипа повторять нечем — незнакомая ошибка честно уходит в классику., `test_trial_offer_free_deeplink` — Новый юзер без триала: ссылка t.me/<bot>?start=trial (бесплатный триал)., `test_trial_offer_absent_when_trial_used`, `test_tg_time_beyond_telegram_date_limit_falls_back_to_text` — Telegram принимает дату сущности только до «сейчас + 1098 дней», `test_strip_tg_time_keeps_inner_text` — Страховка: снимаем теги дат, но текст внутри остаётся., `test_is_rich_date_error_matches_server_code`, `test_send_retries_without_tg_time_on_date_error` — Одна отвергнутая дата не должна ронять меню целиком в классику., `test_tg_time_keeps_past_dates` — Новый лимит не должен задеть обычную истёкшую подписку., `test_tg_time_survives_extreme_datetimes` — datetime.max/min: timestamp() на них падает на части платформ — не роняем меню., `test_try_send_decode_error_falls_back_to_classic` — ClientDecodeError не наследуется от TelegramAPIError и пролетал мимо всех except., `test_try_edit_decode_error_falls_back_to_classic`, `test_inline_buttons_setting_moves_keyboard_into_canvas` — Bot API 10.3: кнопки уезжают в полотно, клавиатуры под сообщением не остаётся., `test_inline_buttons_setting_off_keeps_classic_keyboard`, `test_unmovable_button_keeps_keyboard_outside` — Если перенести можно не всё — клавиатура остаётся под сообщением целиком., `test_edit_clears_old_keyboard_when_buttons_move_inside` — У editMessageText отсутствующий reply_markup означает «не трогать»., `test_happ_connect_without_redirect_never_falls_back_to_raw_url`, `test_happ_connect_with_real_redirect_contains_crypto_only`
- `tests/utils/test_rich_notify.py` — Python-модуль
  Классы: `TestBuildHtml` (11 методов), `TestSend` (8 методов), `TestDeliveryIntegration` (3 методов), `TestLogoAndTimeout` (4 методов), `TestMonitoringIntegration` (4 методов), `TestBroadcastIntegration` (5 методов), `TestUnsupportedServer` (1 методов)
  Функции: нет
- `tests/utils/test_subscription_time.py` — Python-модуль
  Классы: нет
  Функции: `moscow`, `test_complaint_case_is_day_after_tomorrow`, `test_later_today_is_zero`, `test_short_time_across_local_midnight_is_tomorrow`, `test_calendar_day_follows_operator_zone_not_utc`, `test_expired_is_zero`, `test_naive_values_are_utc`, `test_time_left_keeps_partial_day`, `test_time_left_units`, `test_ends_within_days`, `test_expiry_warning`, `test_days_left_rounded_up`
- `tests/utils/test_tag_stripping_is_linear.py` — Python-модуль
  Классы: нет
  Функции: `test_no_quadratic_tag_pattern_remains` — Шаблон `<[^>]+>` не должен вернуться ни в один модуль., `test_stripping_keeps_text_and_bare_angle_brackets`, `test_pathological_input_stays_fast` — Строка из одних «<» — ровно тот вход, на котором старый шаблон вставал., `test_visible_length_uses_the_linear_pattern` — Функция, на которую указал CodeQL, считает длину тем же способом., `test_html_validator_stays_fast_on_unclosed_tags` — Проверка HTML правовых страниц: их длина из кабинета ничем не ограничена., `test_html_validator_verdicts_unchanged` — Ускорение не должно менять вердикты на обычной разметке.
- `tests/utils/test_telegram_delivery.py` — Python-модуль
  Классы: нет
  Функции: `test_expected_delivery_refusals_are_unreachable`, `test_other_errors_are_not_unreachable`, `test_reason_is_plain_russian`
- `tests/utils/test_telegram_html.py` — Python-модуль
  Классы: нет
  Функции: `test_keeps_allowed_inline_tags`, `test_maps_tag_aliases_to_telegram_tags`, `test_strips_unsupported_tags_but_keeps_text`, `test_drops_script_and_iframe_content`, `test_paragraphs_become_blank_lines`, `test_br_becomes_newline`, `test_unordered_list_items_get_bullets`, `test_ordered_list_items_get_numbers`, `test_heading_becomes_bold_block`, `test_link_kept_only_with_http_href`, `test_oversized_href_drops_anchor_but_keeps_text`, `test_misnested_skip_closers_recover`, `test_text_entities_are_escaped`, `test_unclosed_tags_are_closed`, `test_blockquote_and_code_preserved`, `test_split_short_text_single_chunk`, `test_split_empty_returns_empty_list`, `test_split_respects_paragraph_boundaries`, `test_split_hard_splits_oversized_paragraph`, `test_split_closes_open_tags_in_each_chunk`, `test_split_never_exceeds_telegram_hard_limit`, `test_split_link_text_spanning_chunks_stays_within_hard_limit`, `test_hard_split_backs_off_incomplete_entity`, `test_empty_heading_and_paragraphs_leave_no_empty_tags`
- `tests/utils/test_text_search_case_insensitive.py` — Python-модуль
  Классы: нет
  Функции: `test_sqlite_lower_really_is_ascii_only` — Фиксируем причину бага: без наших вариантов ILIKE по кириллице не сработал бы., `test_ascii_term_stays_a_single_pattern` — Для ASCII ILIKE справляется сам — лишние OR только замедлили бы запрос., `test_cyrillic_term_expands_to_case_variants`, `test_variants_are_deduplicated_for_single_case_terms`, `test_search_finds_capitalized_name_in_any_case` — Ровно репорт: имя записано «Позитив», ищут как угодно — находиться должно всегда., `test_search_finds_any_stored_case`, `test_multiword_name_is_found_in_lowercase`, `test_ascii_search_still_works` — Латиница не должна пострадать от изменения., `test_search_still_filters_out_non_matches` — Регистронезависимость не должна превратить поиск в «находит всё»., `test_telegram_id_search_unaffected`
- `tests/utils/test_ticket_media_send.py` — Python-модуль
  Классы: нет
  Функции: `test_albums_by_ten_documents_one_by_one`, `test_failed_chunk_does_not_stop_the_rest`, `test_nothing_sent_returns_none`, `test_delete_notice_removes_media_and_itself`, `test_delete_notice_bad_id_and_telegram_error`
- `tests/utils/test_ticket_text.py` — Python-модуль
  Классы: нет
  Функции: `test_short_ticket_stays_on_one_page`, `test_long_message_is_fully_visible_across_pages`, `test_no_page_exceeds_telegram_limit`, `test_split_never_breaks_html_entities`, `test_long_header_still_leaves_room_for_content`, `test_every_page_repeats_header`, `test_empty_ticket_returns_header_page`, `test_preview_marks_cut_text`
- `tests/utils/test_validators_basic.py` — Python-модуль
  Классы: нет
  Функции: `test_validate_email_handles_expected_patterns` — Проверяем типичные корректные и некорректные адреса., `test_validate_html_tags_rejects_unknown_tags` — Неизвестные HTML теги должны приводить к отказу., `test_validate_html_structure_detects_wrong_nesting` — Неправильная вложенность тегов должна сообщаться пользователю.

### tests/webserver

- `tests/webserver/test_payment_webhook_routes_survive_toggle.py` — Python-модуль
  Классы: нет
  Функции: `test_registration_never_looks_at_the_enable_flag` — Ни один маршрут не должен монтироваться по is_X_enabled()., `test_auto_verification_watchdog_is_not_latched` — Сторож автопроверки обязан смотреть на настройку, а не на первый результат., `platega_configured`, `test_route_is_mounted_while_provider_is_switched_off` — Ровно сценарий из жалобы: перезапуск с выключенной платёжкой., `test_route_is_mounted_when_provider_is_on`, `test_unconfigured_provider_has_no_endpoint` — Без ключа подпись коллбека проверять нечем — маршрута быть не должно.
- `tests/webserver/test_payments.py` — Python-модуль
  Классы: `DummyBot`
  Функции: `test_cryptobot_missing_signature`, `test_cryptobot_invalid_signature`
- `tests/webserver/test_platega_webhook_routing.py` — Python-модуль
  Классы: `DummyBot`
  Функции: `reset_settings`, `test_platega_one_off_payload_routes_to_legacy_handler`, `test_platega_wrong_secret_rejected_before_dispatch`, `test_platega_camel_case_one_off_still_uses_legacy_handler`
- `tests/webserver/test_remnawave_webhook.py` — Python-модуль
  Классы: нет
  Функции: `reset_remnawave_webhook_settings`, `test_remnawave_webhook_accepts_event_without_scope`, `test_remnawave_webhook_rejects_payload_without_event`, `test_intentional_panel_deletion_guard_marks_and_detects` — Verify that mark + is_intentional round-trip works correctly., `test_intentional_panel_deletion_guard_respects_hard_cap` — Verify that the guard stops accepting entries after hitting the cap.
- `tests/webserver/test_scoped_db.py` — Python-модуль
  Классы: нет
  Функции: `test_scoped_db_commits_on_success`, `test_scoped_db_rolls_back_and_reraises`
- `tests/webserver/test_telegram.py` — Python-модуль
  Классы: нет
  Функции: `reset_webhook_settings`, `test_webhook_without_secret` — Без WEBHOOK_SECRET_TOKEN вебхук не принимает апдейты (иначе подделка от любого user_id)., `test_webhook_with_secret`, `test_webhook_secret_mismatch`, `test_webhook_invalid_payload`, `test_webhook_invalid_content_type`, `test_webhook_uses_processor`, `test_webhook_processor_overloaded`, `test_webhook_processor_not_running`, `test_webhook_path_normalization`, `test_health_endpoint`, `test_processor_measures_wait_and_handle` — Очередь меряет ожидание и обработку: медленный update — отдельной строкой, сводка — раз в период, без id людей.
- `tests/webserver/test_unified_app.py` — Python-модуль
  Классы: нет
  Функции: `test_unified_app_health_reports_features`, `test_unified_app_health_path_without_admin`, `test_unified_app_docs_disabled`, `test_unified_app_docs_enabled_with_alias`
