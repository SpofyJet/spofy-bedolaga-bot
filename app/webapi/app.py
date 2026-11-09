from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.cabinet.apple_iap import apple_iap_only_router
from app.config import settings
from app.webapi.docs import add_redoc_endpoint

from .middleware import RequestLoggingMiddleware, RequestPathContextMiddleware, pool_exhausted_handler
from .routes import (
    backups,
    ban_notifications,
    broadcasts,
    campaigns,
    config,
    contests,
    health,
    logs,
    main_menu_buttons,
    media,
    menu_layout,
    miniapp,
    pages,
    partners,
    pinned_messages,
    polls,
    promo_groups,
    promo_offers,
    promocodes,
    remnawave,
    servers,
    stats,
    subscription_events,
    subscriptions,
    tickets,
    tokens,
    transactions,
    user_messages,
    users,
    webhooks,
    websocket,
    welcome_texts,
)


def create_web_api_app(lifespan: Any = None) -> FastAPI:
    docs_config = settings.get_web_api_docs_config()

    # Убираем openapi_tags для предотвращения ошибок при генерации openapi.json
    app = FastAPI(
        title=settings.WEB_API_TITLE,
        version=settings.WEB_API_VERSION,
        docs_url=docs_config.get('docs_url'),
        redoc_url=None,
        openapi_url=docs_config.get('openapi_url'),
        swagger_ui_parameters={'persistAuthorization': True},
        redirect_slashes=False,
        lifespan=lifespan,
    )

    add_redoc_endpoint(
        app,
        redoc_url=docs_config.get('redoc_url'),
        openapi_url=docs_config.get('openapi_url'),
        title=settings.WEB_API_TITLE,
    )

    allowed_origins = settings.get_web_api_allowed_origins()
    cabinet_origins = settings.get_cabinet_allowed_origins()
    all_origins = list(set(allowed_origins + cabinet_origins))

    if '*' in all_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_credentials=False,
            allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
            allow_headers=['Authorization', 'Content-Type', 'X-CSRF-Token', 'X-Telegram-Init-Data'],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=all_origins,
            allow_credentials=True,
            allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
            allow_headers=['Authorization', 'Content-Type', 'X-CSRF-Token', 'X-Telegram-Init-Data'],
        )

    app.add_exception_handler(SQLAlchemyTimeoutError, pool_exhausted_handler)

    if settings.WEB_API_REQUEST_LOGGING:
        app.add_middleware(RequestLoggingMiddleware)

    # Всегда: путь запроса нужен логу действий пользователя (таймлайн активности).
    app.add_middleware(RequestPathContextMiddleware)

    app.include_router(health.router)
    app.include_router(stats.router, prefix='/stats', tags=['stats'])
    app.include_router(config.router, prefix='/settings', tags=['settings'])
    app.include_router(users.router, prefix='/users', tags=['users'])
    app.include_router(subscriptions.router, prefix='/subscriptions', tags=['subscriptions'])
    app.include_router(tickets.router, prefix='/tickets', tags=['support'])
    app.include_router(transactions.router, prefix='/transactions', tags=['transactions'])
    app.include_router(promo_groups.router, prefix='/promo-groups', tags=['promo-groups'])
    app.include_router(promo_offers.router, prefix='/promo-offers', tags=['promo-offers'])
    app.include_router(servers.router, prefix='/servers', tags=['servers'])
    app.include_router(contests.router, prefix='/contests', tags=['contests'])
    app.include_router(
        main_menu_buttons.router,
        prefix='/main-menu/buttons',
        tags=['main-menu'],
    )
    app.include_router(
        menu_layout.router,
        prefix='/menu-layout',
        tags=['menu-layout'],
    )
    app.include_router(
        user_messages.router,
        prefix='/main-menu/messages',
        tags=['main-menu'],
    )
    app.include_router(
        welcome_texts.router,
        prefix='/welcome-texts',
        tags=['welcome-texts'],
    )
    app.include_router(pages.router, prefix='/pages', tags=['pages'])
    app.include_router(promocodes.router, prefix='/promo-codes', tags=['promo-codes'])
    app.include_router(broadcasts.router, prefix='/broadcasts', tags=['broadcasts'])
    app.include_router(backups.router, prefix='/backups', tags=['backups'])
    app.include_router(campaigns.router, prefix='/campaigns', tags=['campaigns'])
    app.include_router(tokens.router, prefix='/tokens', tags=['auth'])
    app.include_router(remnawave.router, prefix='/remnawave', tags=['remnawave'])
    app.include_router(media.router, tags=['media'])
    app.include_router(miniapp.router, prefix='/miniapp', tags=['miniapp'])
    app.include_router(partners.router, prefix='/partners', tags=['partners'])
    app.include_router(polls.router, prefix='/polls', tags=['polls'])
    app.include_router(logs.router, prefix='/logs', tags=['logs'])
    app.include_router(
        pinned_messages.router,
        prefix='/pinned-messages',
        tags=['pinned-messages'],
    )
    app.include_router(
        subscription_events.router,
        prefix='/notifications/subscriptions',
        tags=['notifications'],
    )
    app.include_router(webhooks.router, prefix='/webhooks', tags=['webhooks'])
    app.include_router(websocket.router, tags=['websocket'])
    app.include_router(
        ban_notifications.router,
        prefix='/ban-notifications',
        tags=['ban-notifications'],
    )

    # Cabinet (Personal Account) routes
    if settings.is_cabinet_enabled():
        from app.cabinet.routes import router as cabinet_router

        app.include_router(cabinet_router)
    elif settings.is_apple_iap_enabled():
        app.include_router(apple_iap_only_router)

    return app
