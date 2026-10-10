from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlsplit
import re
import pytest
import yaml
from pathlib import Path
from app.core.config import Settings
from app.core import email
from app.modules.auth import service


@pytest.mark.parametrize('base', [None, 'https://career.example.org/', 'http://localhost:8080'])
def test_verification_email_browser_address(monkeypatch, base):
    monkeypatch.delenv('APP_BASE_URL', raising=False)
    settings = Settings(_env_file=None, **({'app_base_url':base} if base else {}))
    monkeypatch.setattr(service, 'get_settings', lambda:settings)
    monkeypatch.setattr(email, 'get_settings', lambda:settings)
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr(email.smtplib, 'SMTP', smtp)
    service._send_verification_email(SimpleNamespace(email='jury@example.com'), 'test+token/value')
    message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
    html = message.get_body(preferencelist=('html',)).get_content()
    text = message.get_body(preferencelist=('plain',)).get_content()
    link = re.search(r'href="([^"]+)"', html).group(1)
    expected = (base or 'http://localhost:8000').rstrip('/')
    assert link.startswith(expected + '/auth/verify?')
    assert link in text
    assert parse_qs(urlsplit(link).query) == {'token':['test+token/value']}
    assert 'http://app:8000' not in html + text


def test_compose_and_example_use_browser_address():
    root = Path(__file__).resolve().parents[2]
    for filename in ['compose.yaml', 'compose.test.yaml']:
        config = yaml.safe_load((root / filename).read_text(encoding='utf-8'))
        assert config['services']['app']['environment']['APP_BASE_URL'] == '${APP_BASE_URL:-http://localhost:8000}'
    override = yaml.safe_load((root / 'compose.override.yaml').read_text(encoding='utf-8'))
    assert 'APP_BASE_URL' not in override['services']['app']['environment']
    assert 'APP_BASE_URL=http://localhost:8000' in (root / '.env.example').read_text(encoding='utf-8')
