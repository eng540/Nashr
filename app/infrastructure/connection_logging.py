"""Redact credentials in HTTP diagnostics before formatting handlers."""
import logging,re
class CredentialFilter(logging.Filter):
    def filter(self,record):
        message=record.getMessage()
        message=re.sub(r'(api\.telegram\.org/bot)[^/\s]+',r'\1[REDACTED]',message)
        message=re.sub(r'([?&](?:access_token|input_token|client_secret|code|state|upload_id)=)[^&\s"\']+',r'\1[REDACTED]',message)
        record.msg=message;record.args=()
        return True

def install():
    for name in ('httpx','httpcore','uvicorn.access'):
        logger=logging.getLogger(name)
        logger.addFilter(CredentialFilter())
    # httpcore children emit their own records. Avoid their low-level request
    # and response bodies/headers altogether on credential-bearing requests.
    logging.getLogger('httpcore').setLevel(logging.CRITICAL)
