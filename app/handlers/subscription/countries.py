from .common import logger


async def _get_available_countries(promo_group_id: int | None = None):
    from app.database.crud.server_squad import get_available_server_squads
    from app.database.database import AsyncSessionLocal
    from app.utils.cache import cache, cache_key

    cache_key_value = cache_key('available_countries', promo_group_id or 'all')
    cached_countries = await cache.get(cache_key_value)
    if cached_countries:
        return cached_countries

    try:
        async with AsyncSessionLocal() as db:
            available_servers = await get_available_server_squads(db, promo_group_id=promo_group_id)

        if promo_group_id is not None and not available_servers:
            logger.info(
                'Промогруппа не имеет доступных серверов, возврат пустого списка', promo_group_id=promo_group_id
            )
            await cache.set(cache_key_value, [], 60)
            return []

        countries = []
        for server in available_servers:
            countries.append(
                {
                    'uuid': server.squad_uuid,
                    'name': server.display_name,
                    'price_kopeks': server.price_kopeks,
                    'country_code': server.country_code,
                    'is_available': server.is_available and not server.is_full,
                    'description': server.description or '',
                }
            )

        if not countries:
            logger.info('🔄 Серверов в БД нет, получаем из RemnaWave...')
            from app.services.remnawave_service import RemnaWaveService

            service = RemnaWaveService()
            squads = await service.get_all_squads()

            for squad in squads:
                squad_name = squad['name']

                if not any(
                    flag in squad_name for flag in ['🇳🇱', '🇩🇪', '🇺🇸', '🇫🇷', '🇬🇧', '🇮🇹', '🇪🇸', '🇨🇦', '🇯🇵', '🇸🇬', '🇦🇺']
                ):
                    name_lower = squad_name.lower()
                    if 'netherlands' in name_lower or 'нидерланды' in name_lower or 'nl' in name_lower:
                        squad_name = f'🇳🇱 {squad_name}'
                    elif 'germany' in name_lower or 'германия' in name_lower or 'de' in name_lower:
                        squad_name = f'🇩🇪 {squad_name}'
                    elif 'usa' in name_lower or 'сша' in name_lower or 'america' in name_lower or 'us' in name_lower:
                        squad_name = f'🇺🇸 {squad_name}'
                    else:
                        squad_name = f'🌐 {squad_name}'

                countries.append(
                    {
                        'uuid': squad['uuid'],
                        'name': squad_name,
                        'price_kopeks': 0,
                        'is_available': True,
                        'description': '',
                    }
                )

        await cache.set(cache_key_value, countries, 300)
        return countries

    except Exception as e:
        logger.error('Ошибка получения списка стран', error=e)
        fallback_countries = [
            {
                'uuid': 'default-free',
                'name': '🆓 Бесплатный сервер',
                'price_kopeks': 0,
                'is_available': True,
                'description': '',
            },
        ]

        await cache.set(cache_key_value, fallback_countries, 60)
        return fallback_countries
