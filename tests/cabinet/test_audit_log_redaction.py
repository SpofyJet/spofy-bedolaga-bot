"""Regression: RBAC audit logs must not persist credentials from requests."""

from app.cabinet.dependencies import _AUDIT_REDACTED, _sanitize_audit_payload


def test_sensitive_fields_are_redacted_recursively():
    payload = {
        'password': 'plain-password',
        'nested': {
            'api_key': 'payment-key',
            'refresh_token': 'refresh-token',
            'safe': 'visible',
        },
        'items': [{'clientSecret': 'oauth-secret', 'name': 'visible-name'}],
    }

    result = _sanitize_audit_payload(payload)

    assert result['password'] == _AUDIT_REDACTED
    assert result['nested']['api_key'] == _AUDIT_REDACTED
    assert result['nested']['refresh_token'] == _AUDIT_REDACTED
    assert result['nested']['safe'] == 'visible'
    assert result['items'][0]['clientSecret'] == _AUDIT_REDACTED
    assert result['items'][0]['name'] == 'visible-name'
    # Redaction must not mutate the request-derived object in place.
    assert payload['password'] == 'plain-password'


def test_secret_setting_value_is_redacted_using_url_key():
    result = _sanitize_audit_payload(
        {'value': 'smtp-password'},
        request_path='/cabinet/admin/settings/SMTP_PASSWORD',
    )

    assert result == {'value': _AUDIT_REDACTED}


def test_non_secret_setting_value_remains_visible():
    result = _sanitize_audit_payload(
        {'value': 30},
        request_path='/cabinet/admin/settings/TRIAL_DURATION_DAYS',
    )

    assert result == {'value': 30}
