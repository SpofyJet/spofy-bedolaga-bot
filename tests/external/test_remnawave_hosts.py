"""Разбор ноды панели: активный профиль и uuid его инбаундов."""

from __future__ import annotations

from app.external.remnawave_api import RemnaWaveAPI


NODE_PAYLOAD = {
    'uuid': 'n-1',
    'name': 'DE-1',
    'address': '192.0.2.142',
    'countryCode': 'DE',
    'isConnected': True,
    'isDisabled': False,
    'usersOnline': 0,
    'configProfile': {
        'activeConfigProfileUuid': 'cp-1',
        'activeInbounds': [
            {'uuid': 'in-1', 'profileUuid': 'cp-1', 'tag': 'VLESS_REALITY', 'type': 'vless'},
            {'uuid': 'in-2', 'profileUuid': 'cp-1', 'tag': 'SS', 'type': 'shadowsocks'},
            {'tag': 'без uuid — пропускается'},
        ],
    },
}


def test_parse_node_exposes_active_inbound_uuids_for_host_linking() -> None:
    node = RemnaWaveAPI(base_url='https://panel.example', api_key='k')._parse_node(NODE_PAYLOAD)
    assert (node.active_config_profile_uuid, node.active_inbound_uuids) == ('cp-1', ['in-1', 'in-2'])


def test_parse_node_without_config_profile_has_no_inbounds() -> None:
    payload = {key: value for key, value in NODE_PAYLOAD.items() if key != 'configProfile'}
    node = RemnaWaveAPI(base_url='https://panel.example', api_key='k')._parse_node(payload)
    assert (node.active_config_profile_uuid, node.active_inbound_uuids) == (None, [])
