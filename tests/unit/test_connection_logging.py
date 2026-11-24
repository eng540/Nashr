import logging
from app.infrastructure.connection_logging import CredentialFilter

def test_provider_credentials_are_redacted_from_standard_logs():
    record=logging.LogRecord('httpx',logging.INFO,'test',1,'HTTP %s',('https://api.telegram.org/bot123456:private-token/getMe?access_token=private&client_secret=hidden&code=code-secret&state=state-secret',),None)
    assert CredentialFilter().filter(record)
    msg=record.getMessage()
    for secret in ['private-token','access_token=private','hidden','code-secret','state-secret']:assert secret not in msg
    assert '[REDACTED]' in msg


def test_instagram_debug_input_token_is_redacted():
    record=logging.LogRecord('httpx',logging.INFO,'test',1,'HTTP %s',('https://graph.facebook.com/v27.0/debug_token?input_token=synthetic-private&fields=id',),None)
    assert CredentialFilter().filter(record)
    assert 'synthetic-private' not in record.getMessage()
    assert 'input_token=[REDACTED]' in record.getMessage()


def test_uvicorn_access_formatter_keeps_structured_arguments_and_redacts():
    from uvicorn.logging import AccessFormatter
    record=logging.LogRecord('uvicorn.access',logging.INFO,'test',1,'%s - "%s %s HTTP/%s" %d',('127.0.0.1:123','GET','/callback?code=synthetic-code&state=synthetic-state','1.1',400),None)
    CredentialFilter().filter(record)
    assert len(record.args)==5
    output=AccessFormatter('%(request_line)s %(status_code)s',use_colors=False).format(record)
    assert 'synthetic-code' not in output and 'synthetic-state' not in output
    assert '[REDACTED]' in output and '400' in output
