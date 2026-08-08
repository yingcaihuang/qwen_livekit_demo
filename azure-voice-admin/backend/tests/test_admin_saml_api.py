"""Integration tests for the Admin SAML configuration API endpoints."""

import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

# Set temp DB path before imports
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(_tmpdir, "test.db")

import app.database as db_mod  # noqa: E402
from app.main import app  # noqa: E402


# Generate a valid self-signed test certificate at module load time
def _generate_test_cert() -> str:
    import datetime

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test.example.com")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime(2023, 1, 1))
        .not_valid_after(datetime.datetime(2025, 12, 31))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


TEST_CERT = _generate_test_cert()


@pytest.fixture(autouse=True)
async def setup_db(tmp_path):
    """Use a fresh temp database for each test."""
    test_db = str(tmp_path / "test.db")
    db_mod.DB_PATH = test_db
    from app.database import init_db

    await init_db()
    yield
    if Path(test_db).exists():
        Path(test_db).unlink()


@pytest.fixture
async def client():
    """Provide an async HTTP client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestGetSamlConfig:
    """Tests for GET /api/admin/saml-config."""

    async def test_returns_defaults_when_no_config(self, client):
        """Returns default values when saml_config table has no row."""
        resp = await client.get("/api/admin/saml-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["idp_entity_id"] is None
        assert data["idp_sso_url"] is None
        assert data["idp_x509_cert"] is None
        assert data["groups_attribute"] == "groups"
        assert data["login_button_enabled"] is False

    async def test_returns_saved_config(self, client):
        """Returns previously saved configuration."""
        # First save a config
        await client.put(
            "/api/admin/saml-config",
            json={
                "idp_entity_id": "https://idp.example.com",
                "idp_sso_url": "https://idp.example.com/sso",
                "idp_x509_cert": TEST_CERT,
                "sp_entity_id": "https://sp.example.com",
                "groups_attribute": "memberOf",
                "login_button_enabled": True,
            },
        )
        # Then GET
        resp = await client.get("/api/admin/saml-config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["idp_entity_id"] == "https://idp.example.com"
        assert data["idp_sso_url"] == "https://idp.example.com/sso"
        assert data["idp_x509_cert"] == TEST_CERT
        assert data["sp_entity_id"] == "https://sp.example.com"
        assert data["groups_attribute"] == "memberOf"
        assert data["login_button_enabled"] is True


class TestUpdateSamlConfig:
    """Tests for PUT /api/admin/saml-config."""

    async def test_saves_valid_config(self, client):
        """Saves valid config and returns it."""
        resp = await client.put(
            "/api/admin/saml-config",
            json={
                "idp_entity_id": "https://idp.example.com",
                "idp_sso_url": "https://idp.example.com/sso",
                "idp_x509_cert": TEST_CERT,
                "login_button_enabled": False,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["idp_entity_id"] == "https://idp.example.com"
        assert data["idp_sso_url"] == "https://idp.example.com/sso"
        assert data["login_button_enabled"] is False

    async def test_rejects_missing_idp_entity_id(self, client):
        """Returns 422 when idp_entity_id is missing."""
        resp = await client.put(
            "/api/admin/saml-config",
            json={
                "idp_sso_url": "https://idp.example.com/sso",
                "idp_x509_cert": TEST_CERT,
            },
        )
        assert resp.status_code == 422
        assert "idp_entity_id" in resp.json()["detail"]

    async def test_rejects_missing_idp_sso_url(self, client):
        """Returns 422 when idp_sso_url is missing."""
        resp = await client.put(
            "/api/admin/saml-config",
            json={
                "idp_entity_id": "https://idp.example.com",
                "idp_x509_cert": TEST_CERT,
            },
        )
        assert resp.status_code == 422
        assert "idp_sso_url" in resp.json()["detail"]

    async def test_rejects_missing_idp_x509_cert(self, client):
        """Returns 422 when idp_x509_cert is missing."""
        resp = await client.put(
            "/api/admin/saml-config",
            json={
                "idp_entity_id": "https://idp.example.com",
                "idp_sso_url": "https://idp.example.com/sso",
            },
        )
        assert resp.status_code == 422
        assert "idp_x509_cert" in resp.json()["detail"]

    async def test_rejects_invalid_cert_format(self, client):
        """Returns 422 when certificate is not valid PEM X.509."""
        resp = await client.put(
            "/api/admin/saml-config",
            json={
                "idp_entity_id": "https://idp.example.com",
                "idp_sso_url": "https://idp.example.com/sso",
                "idp_x509_cert": "not-a-valid-certificate",
            },
        )
        assert resp.status_code == 422
        assert "证书格式无效" in resp.json()["detail"]

    async def test_upsert_updates_existing_config(self, client):
        """Calling PUT twice updates the existing record (not duplicates)."""
        payload = {
            "idp_entity_id": "https://idp1.example.com",
            "idp_sso_url": "https://idp1.example.com/sso",
            "idp_x509_cert": TEST_CERT,
        }
        await client.put("/api/admin/saml-config", json=payload)

        # Update with new entity_id
        payload["idp_entity_id"] = "https://idp2.example.com"
        resp = await client.put("/api/admin/saml-config", json=payload)
        assert resp.status_code == 200
        assert resp.json()["idp_entity_id"] == "https://idp2.example.com"


class TestParseMetadata:
    """Tests for POST /api/admin/saml-config/parse-metadata."""

    async def test_rejects_no_input(self, client):
        """Returns 400 when neither URL nor XML is provided."""
        resp = await client.post(
            "/api/admin/saml-config/parse-metadata",
            json={},
        )
        assert resp.status_code == 400
        assert "metadata_url 或 metadata_xml" in resp.json()["detail"]

    async def test_parses_valid_xml(self, client):
        """Parses valid IdP metadata XML and returns extracted fields."""
        metadata_xml = """\
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
    <md:SingleLogoutService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example.com/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>
"""
        resp = await client.post(
            "/api/admin/saml-config/parse-metadata",
            json={"metadata_xml": metadata_xml},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["idp_entity_id"] == "https://idp.example.com/entity"
        assert data["idp_sso_url"] == "https://idp.example.com/sso"
        assert data["idp_slo_url"] == "https://idp.example.com/slo"
        assert data["idp_x509_cert"]

    async def test_rejects_invalid_xml(self, client):
        """Returns 400 for invalid XML content."""
        resp = await client.post(
            "/api/admin/saml-config/parse-metadata",
            json={"metadata_xml": "not valid xml"},
        )
        assert resp.status_code == 400

    async def test_rejects_xxe_xml(self, client):
        """Returns 400 for XML with DOCTYPE declarations (XXE prevention)."""
        xxe_xml = '<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe "test">]><root/>'
        resp = await client.post(
            "/api/admin/saml-config/parse-metadata",
            json={"metadata_xml": xxe_xml},
        )
        assert resp.status_code == 400
        assert "DOCTYPE" in resp.json()["detail"]
