"""Tests for SAML service — specifically the parse_idp_metadata function."""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.saml_service import (
    _check_xxe,
    _extract_idp_fields,
    parse_idp_metadata,
)

# A minimal but valid IdP Metadata XML with HTTP-Redirect SSO binding and X.509 cert
VALID_IDP_METADATA = """\
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
  <md:IDPSSODescriptor
      WantAuthnRequestsSigned="false"
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>MIICpDCCAYwCCQDMe4rsFOQhGDANBgkqhkiG9w0BAQsFADAUMRIwEAYDVQQDDAls
b2NhbGhvc3QwHhcNMjMwMTAxMDAwMDAwWhcNMjQwMTAxMDAwMDAwWjAUMRIwEAYD
VQQDDAlsb2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC7
7TnvaOdazM8EYnJGN3UPlqiotkD2MMA9J2y/hPDGxGMkKKMHrqSLUCIhjnIm5bDD
QcaBngCm0sTqp1m3Mudm3jYmusB0rlqbH5YHpHsKb4CjE8K7jmQCLfPl0YWMNU09
J4V1F6EB1Rv+2cVftn8VDKMHOGKjpCj/JLTRzwPvfmOSvPjPBx20ZBMPIQbpCl4u
+w0MDx3eDQo6TFCcYVNt4bP3ytT3imSypmAs+5OvYBkz3Kb1mOW3KxMjC62dBp/u
4RQcd7BcleWp3aPHuBsaMXJdjRKMpPBhQ0W15GG0puLiW8VQNEQYG4I7pxJkJITM
x3eFAAGE/IeVxn0lhz3BAgMBAAEwDQYJKoZIhvcNAQELBQADggEBAA==</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/sso"/>
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""

# Metadata missing the SingleSignOnService element
METADATA_NO_SSO = """\
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>MIICpDCCAYwCCQDMe4rsFOQhGDANBg==</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""

# Metadata missing the KeyDescriptor/X509Certificate
METADATA_NO_CERT = """\
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""

# Metadata with no IDPSSODescriptor at all
METADATA_NO_IDP_DESCRIPTOR = """\
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
  <md:SPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
  </md:SPSSODescriptor>
</md:EntityDescriptor>
"""

# XML with XXE DOCTYPE declaration
XXE_METADATA = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
</md:EntityDescriptor>
"""


class TestCheckXxe:
    """Tests for the _check_xxe helper."""

    def test_accepts_safe_xml(self):
        """Normal XML without DOCTYPE/ENTITY passes."""
        _check_xxe(VALID_IDP_METADATA)  # Should not raise

    def test_rejects_doctype(self):
        """XML with <!DOCTYPE is rejected."""
        with pytest.raises(ValueError, match="DOCTYPE"):
            _check_xxe(XXE_METADATA)

    def test_rejects_entity_declaration(self):
        """XML with <!ENTITY is rejected."""
        xml = '<root><!ENTITY test "value"></root>'
        with pytest.raises(ValueError, match="ENTITY"):
            _check_xxe(xml)

    def test_case_insensitive(self):
        """Detection is case-insensitive."""
        with pytest.raises(ValueError):
            _check_xxe("<root><!doctype foo></root>")


class TestExtractIdpFields:
    """Tests for the _extract_idp_fields helper."""

    def test_extracts_all_fields(self):
        """All fields are correctly extracted from a well-structured parsed dict."""
        parsed = {
            "idp": {
                "entityId": "https://idp.test.com",
                "singleSignOnService": {
                    "url": "https://idp.test.com/sso",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": "https://idp.test.com/slo",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": "MIIC...",
            }
        }
        result = _extract_idp_fields(parsed)
        assert result["idp_entity_id"] == "https://idp.test.com"
        assert result["idp_sso_url"] == "https://idp.test.com/sso"
        assert result["idp_slo_url"] == "https://idp.test.com/slo"
        assert result["idp_x509_cert"] == "MIIC..."

    def test_slo_url_optional(self):
        """SLO URL can be absent (returns None)."""
        parsed = {
            "idp": {
                "entityId": "https://idp.test.com",
                "singleSignOnService": {"url": "https://idp.test.com/sso"},
                "x509cert": "MIIC...",
            }
        }
        result = _extract_idp_fields(parsed)
        assert result["idp_slo_url"] is None

    def test_missing_entity_id_raises(self):
        """Missing entityId raises ValueError."""
        parsed = {
            "idp": {
                "singleSignOnService": {"url": "https://idp.test.com/sso"},
                "x509cert": "MIIC...",
            }
        }
        with pytest.raises(ValueError, match="entityId"):
            _extract_idp_fields(parsed)

    def test_missing_sso_url_raises(self):
        """Missing SSO URL raises ValueError."""
        parsed = {
            "idp": {
                "entityId": "https://idp.test.com",
                "singleSignOnService": {"url": ""},
                "x509cert": "MIIC...",
            }
        }
        with pytest.raises(ValueError, match="SingleSignOnService"):
            _extract_idp_fields(parsed)

    def test_missing_cert_raises(self):
        """Missing X.509 cert raises ValueError."""
        parsed = {
            "idp": {
                "entityId": "https://idp.test.com",
                "singleSignOnService": {"url": "https://idp.test.com/sso"},
            }
        }
        with pytest.raises(ValueError, match="签名证书"):
            _extract_idp_fields(parsed)

    def test_falls_back_to_x509cert_multi(self):
        """If x509cert is empty, falls back to x509certMulti.signing[0]."""
        parsed = {
            "idp": {
                "entityId": "https://idp.test.com",
                "singleSignOnService": {"url": "https://idp.test.com/sso"},
                "x509cert": "",
                "x509certMulti": {"signing": ["CERT_A", "CERT_B"]},
            }
        }
        result = _extract_idp_fields(parsed)
        assert result["idp_x509_cert"] == "CERT_A"


class TestParseIdpMetadata:
    """Tests for the parse_idp_metadata async function."""

    async def test_parses_valid_xml_directly(self):
        """Parsing valid metadata XML returns expected fields."""
        result = await parse_idp_metadata(xml=VALID_IDP_METADATA)
        assert result["idp_entity_id"] == "https://idp.example.com/entity"
        assert result["idp_sso_url"] == "https://idp.example.com/sso"
        assert result["idp_slo_url"] == "https://idp.example.com/slo"
        assert result["idp_x509_cert"]  # Non-empty cert

    async def test_raises_when_no_input(self):
        """Raises ValueError when neither url nor xml is provided."""
        with pytest.raises(ValueError, match="metadata_url 或 metadata_xml"):
            await parse_idp_metadata()

    async def test_raises_for_empty_strings(self):
        """Raises ValueError when both url and xml are empty strings."""
        with pytest.raises(ValueError, match="metadata_url 或 metadata_xml"):
            await parse_idp_metadata(url="", xml="")

    async def test_rejects_xxe_xml(self):
        """Raises ValueError for XML containing DOCTYPE declarations."""
        with pytest.raises(ValueError, match="DOCTYPE"):
            await parse_idp_metadata(xml=XXE_METADATA)

    async def test_rejects_invalid_xml(self):
        """Raises ValueError for non-XML content."""
        with pytest.raises(ValueError, match="解析失败"):
            await parse_idp_metadata(xml="this is not xml at all")

    async def test_rejects_metadata_missing_sso(self):
        """Raises ValueError when metadata lacks SSO binding."""
        with pytest.raises(ValueError):
            await parse_idp_metadata(xml=METADATA_NO_SSO)

    async def test_rejects_metadata_missing_cert(self):
        """Raises ValueError when metadata lacks signing certificate."""
        with pytest.raises(ValueError, match="签名证书"):
            await parse_idp_metadata(xml=METADATA_NO_CERT)

    async def test_rejects_metadata_no_idp_descriptor(self):
        """Raises ValueError when metadata has no IDPSSODescriptor."""
        with pytest.raises(ValueError):
            await parse_idp_metadata(xml=METADATA_NO_IDP_DESCRIPTOR)

    async def test_url_fetch_success(self):
        """Fetching from URL delegates to aiohttp and parses result."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=VALID_IDP_METADATA)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = lambda *args, **kwargs: mock_session_ctx

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.saml_service.aiohttp.ClientSession", return_value=mock_client_ctx):
            result = await parse_idp_metadata(url="https://idp.example.com/metadata")
            assert result["idp_entity_id"] == "https://idp.example.com/entity"
            assert result["idp_sso_url"] == "https://idp.example.com/sso"

    async def test_url_fetch_non_200(self):
        """Raises ValueError when URL returns non-200 status."""
        mock_resp = AsyncMock()
        mock_resp.status = 404
        mock_resp.text = AsyncMock(return_value="Not Found")

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = lambda *args, **kwargs: mock_session_ctx

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.saml_service.aiohttp.ClientSession", return_value=mock_client_ctx):
            with pytest.raises(ValueError, match="HTTP 404"):
                await parse_idp_metadata(url="https://idp.example.com/metadata")

    async def test_url_fetch_network_error(self):
        """Raises ValueError when URL fetch encounters network error."""
        import aiohttp as _aiohttp

        class _FailingGet:
            """Context manager that raises ClientError on __aenter__."""

            async def __aenter__(self):
                raise _aiohttp.ClientError("Connection refused")

            async def __aexit__(self, *args):
                pass

        mock_session = AsyncMock()
        mock_session.get = lambda *args, **kwargs: _FailingGet()

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.saml_service.aiohttp.ClientSession", return_value=mock_client_ctx):
            with pytest.raises(ValueError, match="无法访问"):
                await parse_idp_metadata(url="https://unreachable.example.com/metadata")

    async def test_url_takes_precedence_over_xml(self):
        """When both url and xml are provided, url is fetched (xml param ignored)."""
        mock_resp = AsyncMock()
        mock_resp.status = 200
        mock_resp.text = AsyncMock(return_value=VALID_IDP_METADATA)

        mock_session_ctx = AsyncMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = lambda *args, **kwargs: mock_session_ctx

        mock_client_ctx = AsyncMock()
        mock_client_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.saml_service.aiohttp.ClientSession", return_value=mock_client_ctx):
            # Pass invalid xml param — it should be ignored since url is set
            result = await parse_idp_metadata(
                url="https://idp.example.com/metadata", xml="<invalid"
            )
            assert result["idp_entity_id"] == "https://idp.example.com/entity"

    async def test_metadata_without_slo_returns_none(self):
        """Metadata without SLO service sets idp_slo_url to None."""
        metadata_no_slo = """\
<?xml version="1.0" encoding="UTF-8"?>
<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata"
    entityID="https://idp.example.com/entity">
  <md:IDPSSODescriptor
      protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:X509Data>
          <ds:X509Certificate>MIICpDCCAYwCCQDMe4rsFOQhGDANBgkqhkiG9w0BAQsFADAUMRIwEAYDVQQDDAls
b2NhbGhvc3QwHhcNMjMwMTAxMDAwMDAwWhcNMjQwMTAxMDAwMDAwWjAUMRIwEAYD
VQQDDAlsb2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC7
7TnvaOdazM8EYnJGN3UPlqiotkD2MMA9J2y/hPDGxGMkKKMHrqSLUCIhjnIm5bDD
QcaBngCm0sTqp1m3Mudm3jYmusB0rlqbH5YHpHsKb4CjE8K7jmQCLfPl0YWMNU09
J4V1F6EB1Rv+2cVftn8VDKMHOGKjpCj/JLTRzwPvfmOSvPjPBx20ZBMPIQbpCl4u
+w0MDx3eDQo6TFCcYVNt4bP3ytT3imSypmAs+5OvYBkz3Kb1mOW3KxMjC62dBp/u
4RQcd7BcleWp3aPHuBsaMXJdjRKMpPBhQ0W15GG0puLiW8VQNEQYG4I7pxJkJITM
x3eFAAGE/IeVxn0lhz3BAgMBAAEwDQYJKoZIhvcNAQELBQADggEBAA==</ds:X509Certificate>
        </ds:X509Data>
      </ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""
        result = await parse_idp_metadata(xml=metadata_no_slo)
        assert result["idp_entity_id"] == "https://idp.example.com/entity"
        assert result["idp_sso_url"] == "https://idp.example.com/sso"
        assert result["idp_slo_url"] is None
        assert result["idp_x509_cert"]
