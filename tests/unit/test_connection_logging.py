import logging
from app.infrastructure.connection_logging import CredentialFilter

def test_provider_credentials_are_redacted_from_standard_logs():
    record=logging.LogRecord('httpx',logging.INFO,'test',1,'HTTP %s',('https://api.telegram.org/bot123456:private-token/getMe?access_token=private&client_secret=hidden&code=code-secret&state=state-secret',),None)
    assert CredentialFilter().filter(record)
    msg=record.getMessage()
    for secret in ['private-token','access_token=private','hidden','code-secret','state-secret']:assert secret not in msg
    assert '[REDACTED]' in msg
