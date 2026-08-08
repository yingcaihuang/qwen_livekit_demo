"""SAML 2.0 SP service: handles SAML protocol processing for authentication.

This module provides infrastructure for SAML authentication including:
- Converting FastAPI requests to python3-saml format
- Loading SAML configuration from the database
- Building python3-saml settings dictionaries
- Parsing IdP Metadata from URL or XML content
- Custom exception types for SAML validation errors
"""

import logging
import re

import aiohttp
import aiosqlite
from cryptography.x509 import load_pem_x509_certificate
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from starlette.requests import Request

logger = logging.getLogger(__name__)


class SAMLValidationError(Exception):
    """SAML 验证流程中的错误。

    Attributes:
        message: Human-readable error description.
        error_code: Machine-readable error code for categorization.
    """

    def __init__(self, message: str, error_code: str):
        self.message = message
        self.error_code = error_code
        super().__init__(message)


def prepare_request_from_fastapi(request: Request) -> dict:
    """将 FastAPI Request 转换为 python3-saml 所需的 request dict 格式。

    python3-saml expects a specific dict structure describing the incoming
    HTTP request. This helper bridges FastAPI/Starlette Request objects to
    that format.

    Args:
        request: The incoming FastAPI/Starlette Request object.

    Returns:
        A dict compatible with OneLogin_Saml2_Auth initialization.
        The ``post_data`` field is empty and should be filled by the caller
        when handling POST requests (e.g. ACS).
    """
    return {
        "https": "on" if request.url.scheme == "https" else "off",
        "http_host": request.headers.get("host", ""),
        "script_name": request.url.path,
        "get_data": dict(request.query_params),
        "post_data": {},  # Caller fills this for POST endpoints (ACS)
    }


def build_saml_settings(config: dict, base_url: str) -> dict:
    """构建 python3-saml 所需的完整 settings dict。

    Translates the flat database configuration into the nested structure
    expected by ``OneLogin_Saml2_Auth``.

    Args:
        config: Dict of SAML configuration values loaded from the
            ``saml_config`` database table. Expected keys:
            - idp_entity_id (str)
            - idp_sso_url (str)
            - idp_slo_url (str | None)
            - idp_x509_cert (str)
            - sp_entity_id (str | None)
            - nameid_format (str)
            - sign_algorithm (str)
        base_url: The application's external base URL (scheme + host),
            e.g. ``https://admin.example.com``.

    Returns:
        A dict suitable for passing to ``OneLogin_Saml2_Auth``.
    """
    sp_entity_id = config.get("sp_entity_id") or f"{base_url}/api/saml/metadata"
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": f"{base_url}/api/saml/acs",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "singleLogoutService": {
                "url": f"{base_url}/api/saml/sls",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "NameIDFormat": config.get(
                "nameid_format", "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
            ),
        },
        "idp": {
            "entityId": config.get("idp_entity_id", ""),
            "singleSignOnService": {
                "url": config.get("idp_sso_url", ""),
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "singleLogoutService": {
                "url": config.get("idp_slo_url") or "",
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": config.get("idp_x509_cert", ""),
        },
        "security": {
            "authnRequestsSigned": False,
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "signatureAlgorithm": config.get(
                "sign_algorithm", "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
            ),
            "wantNameId": True,
            "requestedAuthnContext": False,
        },
    }


async def load_saml_settings(db: aiosqlite.Connection, request: Request) -> dict:
    """从数据库加载 SAML 配置并构建 python3-saml settings dict。

    Loads the singleton ``saml_config`` row and combines it with request
    information to produce a complete settings dict for python3-saml.

    Args:
        db: An active aiosqlite connection (with row_factory = aiosqlite.Row).
        request: The incoming FastAPI/Starlette Request, used to derive the
            application's base URL (scheme + host).

    Returns:
        A dict suitable for ``OneLogin_Saml2_Auth`` initialization.

    Raises:
        SAMLValidationError: If no SAML configuration exists in the database
            or if required IdP fields are missing.
    """
    cursor = await db.execute(
        "SELECT idp_entity_id, idp_sso_url, idp_slo_url, idp_x509_cert, "
        "sp_entity_id, groups_attribute, nameid_format, sign_algorithm, "
        "login_button_enabled, idp_metadata_url, clock_skew_seconds "
        "FROM saml_config WHERE id = 1"
    )
    row = await cursor.fetchone()

    if row is None:
        raise SAMLValidationError(
            message="SAML 未配置",
            error_code="saml_not_configured",
        )

    config = dict(row)

    # Validate that required IdP fields are present
    if not config.get("idp_entity_id"):
        raise SAMLValidationError(
            message="SAML 配置缺少 IdP Entity ID",
            error_code="missing_idp_entity_id",
        )
    if not config.get("idp_sso_url"):
        raise SAMLValidationError(
            message="SAML 配置缺少 IdP SSO URL",
            error_code="missing_idp_sso_url",
        )
    if not config.get("idp_x509_cert"):
        raise SAMLValidationError(
            message="SAML 配置缺少 IdP 签名证书",
            error_code="missing_idp_x509_cert",
        )

    # Derive base URL from the request
    scheme = request.url.scheme
    host = request.headers.get("host", request.url.netloc)
    base_url = f"{scheme}://{host}"

    return build_saml_settings(config, base_url)


# Regex pattern to detect XXE indicators in XML content
_XXE_PATTERN = re.compile(r"<!DOCTYPE|<!ENTITY", re.IGNORECASE)


def _check_xxe(xml_content: str) -> None:
    """Reject XML containing DTD declarations or entity references (XXE prevention).

    Args:
        xml_content: Raw XML string to inspect.

    Raises:
        ValueError: If the XML contains ``<!DOCTYPE`` or ``<!ENTITY`` markers.
    """
    if _XXE_PATTERN.search(xml_content):
        raise ValueError("不安全的 XML 内容：检测到 DOCTYPE 或 ENTITY 声明")


def _extract_idp_fields(parsed: dict) -> dict:
    """Extract required IdP fields from python3-saml parsed metadata structure.

    The ``OneLogin_Saml2_IdPMetadataParser`` returns a nested dict with an
    ``idp`` key containing the parsed IdP information. This function extracts
    and validates the required fields.

    Args:
        parsed: The dict returned by ``OneLogin_Saml2_IdPMetadataParser.parse``.

    Returns:
        A flat dict with keys: ``idp_entity_id``, ``idp_sso_url``,
        ``idp_slo_url``, ``idp_x509_cert``.

    Raises:
        ValueError: If required fields (entity ID, SSO URL, or X.509 cert)
            are missing from the parsed metadata.
    """
    idp = parsed.get("idp", {})

    # Extract entity ID
    entity_id = idp.get("entityId", "")
    if not entity_id:
        raise ValueError("IdP Metadata 缺少 entityId")

    # Extract SSO URL (HTTP-Redirect binding)
    sso_service = idp.get("singleSignOnService", {})
    sso_url = sso_service.get("url", "")
    if not sso_url:
        raise ValueError("IdP Metadata 缺少 SingleSignOnService (HTTP-Redirect binding)")

    # Extract SLO URL (optional)
    slo_service = idp.get("singleLogoutService", {})
    slo_url = slo_service.get("url", "") or None

    # Extract X.509 certificate
    x509_cert = idp.get("x509cert", "")
    if not x509_cert:
        # python3-saml may also store certs under x509certMulti
        cert_multi = idp.get("x509certMulti", {})
        signing_certs = cert_multi.get("signing", [])
        if signing_certs:
            x509_cert = signing_certs[0]

    if not x509_cert:
        raise ValueError("IdP Metadata 缺少签名证书 (KeyDescriptor/X509Certificate)")

    return {
        "idp_entity_id": entity_id,
        "idp_sso_url": sso_url,
        "idp_slo_url": slo_url,
        "idp_x509_cert": x509_cert,
    }


async def parse_idp_metadata(url: str | None = None, xml: str | None = None) -> dict:
    """解析 IdP Metadata（从 URL 或 XML 内容）。

    Supports two modes of operation:
    1. Fetch metadata from a URL and parse it.
    2. Parse metadata directly from an XML string.

    At least one of ``url`` or ``xml`` must be provided. If both are provided,
    ``url`` takes precedence (the XML at the URL is fetched and used).

    Args:
        url: URL pointing to the IdP's metadata XML endpoint. If provided,
            the metadata is fetched via HTTP GET.
        xml: Raw IdP Metadata XML string. Used when ``url`` is not provided.

    Returns:
        A dict with keys:
        - ``idp_entity_id`` (str): The IdP's entity ID.
        - ``idp_sso_url`` (str): The IdP's SSO endpoint URL.
        - ``idp_slo_url`` (str | None): The IdP's SLO endpoint URL, or None.
        - ``idp_x509_cert`` (str): The IdP's X.509 signing certificate (PEM body without headers).

    Raises:
        ValueError: If neither ``url`` nor ``xml`` is provided, if the URL is
            unreachable, if the XML is invalid, or if required metadata fields
            are missing.
    """
    if not url and not xml:
        raise ValueError("必须提供 metadata_url 或 metadata_xml 中的至少一个")

    metadata_xml: str

    if url:
        # Fetch metadata from URL
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        raise ValueError(f"无法访问 IdP Metadata URL：HTTP {resp.status}")
                    metadata_xml = await resp.text()
        except aiohttp.ClientError as e:
            raise ValueError(f"无法访问 IdP Metadata URL：{e}") from e
        except ValueError:
            # Re-raise our own ValueErrors
            raise
        except Exception as e:
            raise ValueError(f"获取 IdP Metadata 时发生错误：{e}") from e
    else:
        metadata_xml = xml  # type: ignore[assignment]

    # XXE prevention: reject XML with DOCTYPE or ENTITY declarations
    _check_xxe(metadata_xml)

    # Parse using python3-saml's IdP metadata parser
    try:
        parsed = OneLogin_Saml2_IdPMetadataParser.parse(
            metadata_xml,
            required_sso_binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
        )
    except Exception as e:
        raise ValueError(f"IdP Metadata XML 解析失败：{e}") from e

    # Extract and validate required fields
    return _extract_idp_fields(parsed)


def generate_sp_metadata(settings: dict) -> str:
    """生成 SP Metadata XML 字符串。

    Uses ``OneLogin_Saml2_Settings`` to produce a standards-compliant SAML 2.0
    SP Metadata XML document. The generated metadata includes:
    - EntityDescriptor with the configured SP Entity ID
    - AssertionConsumerService element (HTTP-POST binding)
    - SingleLogoutService element (HTTP-Redirect binding)
    - NameIDFormat declaration

    Args:
        settings: A python3-saml settings dict as returned by
            ``build_saml_settings()``. Must contain at minimum the ``sp``
            and ``idp`` sections with valid configuration.

    Returns:
        A string containing the SP Metadata XML document.

    Raises:
        Exception: If python3-saml encounters invalid settings and cannot
            produce valid metadata.
    """
    from onelogin.saml2.settings import OneLogin_Saml2_Settings

    # OneLogin_Saml2_Settings validates the settings structure on init.
    # We pass sp_validation_only=True because we only need SP metadata
    # and don't want IdP validation to block metadata generation when
    # IdP fields may be placeholders during initial setup.
    saml_settings = OneLogin_Saml2_Settings(
        settings=settings,
        sp_validation_only=True,
    )

    metadata = saml_settings.get_sp_metadata()

    # Validate the generated metadata for well-formedness
    errors = saml_settings.validate_metadata(metadata)
    if errors:
        error_detail = ", ".join(errors)
        raise SAMLValidationError(
            message=f"生成的 SP Metadata 无效: {error_detail}",
            error_code="invalid_sp_metadata",
        )

    # metadata is returned as bytes by python3-saml; decode to string
    if isinstance(metadata, bytes):
        return metadata.decode("utf-8")
    return metadata


# Maximum allowed size for X.509 certificate PEM content (64 KB)
_MAX_CERT_SIZE_BYTES = 65536

# Dangerous URI schemes that must be rejected in RelayState
_DANGEROUS_SCHEMES = re.compile(r"^\s*(javascript|data|vbscript)\s*:", re.IGNORECASE)


def validate_relay_state(relay_state: str | None, allowed_origin: str) -> str | None:
    """验证 RelayState 安全性。

    Only allows relative paths (starting with ``/`` but not ``//``) or
    same-origin URLs (starting with ``allowed_origin``). Rejects external
    URLs, dangerous protocol schemes, and empty/None values.

    Args:
        relay_state: The RelayState value from the SAML flow. May be None
            or empty.
        allowed_origin: The application's base URL (scheme + host), e.g.
            ``https://admin.example.com``. Used to validate same-origin URLs.

    Returns:
        The validated path/URL string if safe, or ``None`` if the input is
        rejected (None, empty, or unsafe).
    """
    if not relay_state:
        return None

    # Strip whitespace
    relay_state = relay_state.strip()
    if not relay_state:
        return None

    # Reject dangerous URI schemes
    if _DANGEROUS_SCHEMES.match(relay_state):
        logger.warning("RelayState rejected: dangerous scheme detected")
        return None

    # Reject protocol-relative URLs (starts with //)
    if relay_state.startswith("//"):
        logger.warning("RelayState rejected: protocol-relative URL")
        return None

    # Allow relative paths starting with /
    if relay_state.startswith("/"):
        return relay_state

    # Allow same-origin absolute URLs
    if relay_state.startswith(allowed_origin):
        # Ensure it's truly the same origin (not just a prefix match on a
        # different domain like allowed_origin="https://a.com" matching
        # "https://a.com.evil.com")
        remainder = relay_state[len(allowed_origin) :]
        if (
            remainder == ""
            or remainder.startswith("/")
            or remainder.startswith("?")
            or remainder.startswith("#")
        ):
            return relay_state

    # Everything else is rejected
    logger.warning("RelayState rejected: external URL")
    return None


def validate_x509_cert(cert_pem: str) -> bool:
    """验证证书为有效 X.509 PEM 格式且 <= 64KB。

    Uses the ``cryptography`` library to parse the PEM-encoded certificate
    and verify it is structurally valid.

    Args:
        cert_pem: The PEM-encoded X.509 certificate string. May or may not
            include ``-----BEGIN CERTIFICATE-----`` headers.

    Returns:
        ``True`` if the certificate is valid PEM X.509 and within the size
        limit. ``False`` otherwise.
    """
    if not cert_pem:
        return False

    # Check size limit
    if len(cert_pem.encode("utf-8")) > _MAX_CERT_SIZE_BYTES:
        return False

    # Ensure PEM headers are present for parsing
    pem_data = cert_pem.strip()
    if not pem_data.startswith("-----BEGIN CERTIFICATE-----"):
        # Wrap bare certificate body with PEM headers
        pem_data = "-----BEGIN CERTIFICATE-----\n" + pem_data + "\n-----END CERTIFICATE-----"

    try:
        load_pem_x509_certificate(pem_data.encode("utf-8"))
        return True
    except (ValueError, Exception):
        return False


def check_xml_xxe(xml_string: str) -> None:
    """XXE 预检：检测 <!DOCTYPE 和 <!ENTITY 声明。

    This function should be called before passing any XML content to
    python3-saml for processing. It raises a ``SAMLValidationError`` if
    XXE indicators are found.

    Args:
        xml_string: Raw XML string to inspect.

    Raises:
        SAMLValidationError: If the XML contains ``<!DOCTYPE`` or
            ``<!ENTITY`` markers, with error_code ``'xxe_detected'``.
    """
    if _XXE_PATTERN.search(xml_string):
        raise SAMLValidationError(
            message="不安全的 XML 内容：检测到 DOCTYPE 或 ENTITY 声明",
            error_code="xxe_detected",
        )


async def initiate_login(
    db: aiosqlite.Connection, request: Request, next_url: str | None = None
) -> str:
    """生成 AuthnRequest 并返回 IdP 重定向 URL。

    Performs the following steps:
    1. Loads SAML settings from the database.
    2. Prepares the python3-saml request dict from the incoming FastAPI request.
    3. Creates a ``OneLogin_Saml2_Auth`` instance and calls ``login()`` to
       generate the redirect URL containing the encoded AuthnRequest.
    4. Extracts the AuthnRequest ID and stores it in ``saml_login_state``
       for later InResponseTo validation (replay prevention).
    5. Returns the IdP redirect URL.

    Args:
        db: An active aiosqlite connection.
        request: The incoming FastAPI/Starlette Request.
        next_url: Optional path to redirect the user to after login completes.
            Stored as ``relay_state`` in the login state table.

    Returns:
        The full IdP redirect URL (with SAMLRequest and RelayState query params).

    Raises:
        SAMLValidationError: If SAML is not configured or settings are invalid.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    # Load settings and prepare request dict
    settings = await load_saml_settings(db, request)
    req_dict = prepare_request_from_fastapi(request)

    # Create auth instance and generate the redirect URL
    # python3-saml's login() returns the redirect URL with the SAMLRequest param
    auth = OneLogin_Saml2_Auth(req_dict, old_settings=settings)
    redirect_url = auth.login(return_to=next_url or "")

    # Extract the AuthnRequest ID from the last generated request
    # OneLogin_Saml2_Auth stores the last request ID after login() is called
    request_id = auth.get_last_request_id()

    # Store request_id in saml_login_state for InResponseTo validation
    await db.execute(
        "INSERT INTO saml_login_state (request_id, relay_state) VALUES (?, ?)",
        (request_id, next_url),
    )
    await db.commit()

    logger.info("SAML AuthnRequest generated, request_id=%s", request_id)
    return redirect_url


async def process_acs(db: aiosqlite.Connection, request: Request, form_data: dict) -> dict:
    """处理 ACS POST 回调：验证 SAMLResponse 并返回用户信息。

    Performs the following steps:
    1. Loads SAML settings (including clock skew tolerance).
    2. Prepares the request dict with ``post_data`` populated from form data.
    3. Creates a ``OneLogin_Saml2_Auth`` instance and processes the response.
    4. Checks for validation errors (signature, time conditions, audience).
    5. For SP-Initiated flows: validates InResponseTo against stored state.
    6. For IdP-Initiated flows: skips InResponseTo check.
    7. Deletes consumed request_id and cleans up expired state records.
    8. Returns extracted user information (NameID, attributes, session index).

    Args:
        db: An active aiosqlite connection.
        request: The incoming FastAPI/Starlette Request.
        form_data: The parsed form data from the POST body, expected to
            contain ``SAMLResponse`` and optionally ``RelayState``.

    Returns:
        A dict with keys:
        - ``nameid`` (str): The authenticated user's NameID value.
        - ``attributes`` (dict): SAML attribute statements.
        - ``session_index`` (str | None): The SAML session index for SLO.
        - ``relay_state`` (str | None): The validated RelayState for redirect.

    Raises:
        SAMLValidationError: If signature verification, time conditions,
            audience check, or InResponseTo validation fails.
    """
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    # Load SAML config to get clock_skew_seconds
    cursor = await db.execute("SELECT clock_skew_seconds FROM saml_config WHERE id = 1")
    row = await cursor.fetchone()
    clock_skew = row[0] if row else 120

    # Load full settings
    settings = await load_saml_settings(db, request)

    # Add clock skew tolerance to the security section
    if "security" not in settings:
        settings["security"] = {}
    settings["security"]["allowedClockDrift"] = clock_skew

    # Prepare request dict with post_data from the ACS form submission
    req_dict = prepare_request_from_fastapi(request)
    req_dict["post_data"] = form_data

    # Create auth instance and process the SAML response
    auth = OneLogin_Saml2_Auth(req_dict, old_settings=settings)
    auth.process_response()

    # Check for errors from python3-saml validation
    errors = auth.get_errors()
    if errors:
        error_reason = auth.get_last_error_reason() or ", ".join(errors)
        logger.warning(
            "SAML ACS validation failed: %s (errors: %s)",
            error_reason,
            errors,
        )
        raise SAMLValidationError(
            message=f"SAML 验证失败: {error_reason}",
            error_code="saml_validation_failed",
        )

    # Extract user info from the validated assertion
    nameid = auth.get_nameid()
    attributes = auth.get_attributes()
    session_index = auth.get_session_index()

    # Determine if this is SP-Initiated or IdP-Initiated
    # python3-saml provides the InResponseTo value from the parsed response
    in_response_to = auth.get_last_response_in_response_to()

    relay_state: str | None = None

    if in_response_to:
        # SP-Initiated flow: validate InResponseTo against stored state
        cursor = await db.execute(
            "SELECT relay_state, created_at FROM saml_login_state WHERE request_id = ?",
            (in_response_to,),
        )
        state_row = await cursor.fetchone()

        if state_row is None:
            logger.warning(
                "SAML InResponseTo validation failed: request_id=%s not found or expired",
                in_response_to,
            )
            raise SAMLValidationError(
                message="SAML 请求匹配失败（可能重放或已超时）",
                error_code="in_response_to_mismatch",
            )

        relay_state = state_row[0]

        # Delete consumed request_id (single-use: prevents replay)
        await db.execute(
            "DELETE FROM saml_login_state WHERE request_id = ?",
            (in_response_to,),
        )
    else:
        # IdP-Initiated flow: no InResponseTo to validate
        # Use RelayState from form_data if present
        relay_state = form_data.get("RelayState")
        logger.info("SAML IdP-Initiated login detected (no InResponseTo)")

    # Clean up expired state records (5-minute TTL)
    await db.execute(
        "DELETE FROM saml_login_state WHERE created_at < datetime('now', '-5 minutes')"
    )
    await db.commit()

    # Validate RelayState for security (prevent open redirect)
    scheme = request.url.scheme
    host = request.headers.get("host", request.url.netloc)
    allowed_origin = f"{scheme}://{host}"
    relay_state = validate_relay_state(relay_state, allowed_origin)

    logger.info(
        "SAML ACS processed successfully: nameid=%s, sp_initiated=%s",
        nameid,
        bool(in_response_to),
    )

    return {
        "nameid": nameid,
        "attributes": attributes,
        "session_index": session_index,
        "relay_state": relay_state,
    }
