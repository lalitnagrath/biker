"""Single source of truth for Amazon CreatorsAPI credentials.

Every Amazon API consumer in this project must load credentials through this
module — never duplicate the secret values or the resolution logic:

    * bike.py
    * honda-cb350.py
    * db/amazon_search_service.py (Control Center Amazon Import)

Resolution order (first value wins):

    1. explicit argument
    2. AMAZON_CREATOR_CREDENTIAL_ID / AMAZON_CREATOR_CREDENTIAL_SECRET env vars
    3. built-in defaults below

No new environment variables are required: the built-in defaults keep scripts
and the Control Center working out of the box, exactly like bike.py did.
"""

import os

DEFAULT_CREDENTIAL_ID = "amzn1.application-oa2-client.b9b4e4acd8b145de93d67e30964552f6"
DEFAULT_CREDENTIAL_SECRET = "amzn1.oa2-cs.v1.c54ce65e63d4bc8d44bf9ec5dbb7a368aa943b0cc84bb89a32eb77afbb0ca028"
DEFAULT_PARTNER_TAG = "helpfulsurfer-21"

_CREDENTIAL_ID_ENV = "AMAZON_CREATOR_CREDENTIAL_ID"
_CREDENTIAL_SECRET_ENV = "AMAZON_CREATOR_CREDENTIAL_SECRET"
_PARTNER_TAG_ENV = "AMAZON_PARTNER_TAG"


def get_credentials(credential_id: str | None = None,
                    credential_secret: str | None = None) -> tuple[str, str]:
    """Resolve CreatorsAPI credentials.

    Returns (credential_id, credential_secret) using explicit args, then the
    standard environment variables, then the built-in defaults. Raises
    RuntimeError if nothing can be resolved.
    """
    cid = credential_id or os.environ.get(_CREDENTIAL_ID_ENV) or DEFAULT_CREDENTIAL_ID
    csecret = credential_secret or os.environ.get(_CREDENTIAL_SECRET_ENV) or DEFAULT_CREDENTIAL_SECRET
    if not cid or not csecret:
        raise RuntimeError(
            f"Amazon credentials not configured. Set {_CREDENTIAL_ID_ENV} and "
            f"{_CREDENTIAL_SECRET_ENV} environment variables, or provide them "
            "explicitly."
        )
    return cid, csecret


def get_partner_tag(partner_tag: str | None = None) -> str:
    """Resolve the affiliate partner tag.

    Uses an explicit tag, then the AMAZON_PARTNER_TAG environment variable,
    then the built-in default.
    """
    tag = partner_tag or os.environ.get(_PARTNER_TAG_ENV) or DEFAULT_PARTNER_TAG
    if not tag or not tag.strip():
        raise RuntimeError(
            f"Amazon partner tag not configured. Set {_PARTNER_TAG_ENV} or "
            "provide one explicitly."
        )
    return tag.strip()
