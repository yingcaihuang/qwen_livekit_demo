"""Unit tests for Azure v1 request-URL resolution (``resolve_azure_url``).

Azure OpenAI uses the ``/openai/v1`` (OpenAI-compatible) surface, so the
resolver is v1-only and never appends an ``api-version`` query. It normalizes
three endpoint shapes into a single final URL:
  1. A full v1 operation URL (``…/openai/v1/images/generations``): the requested
     operation is (re)appended, so an edits request against a generations
     endpoint targets ``…/openai/v1/images/edits``.
  2. A v1 base (``…/openai/v1``): the requested operation is appended.
  3. A plain base host (``https://x.services.ai.azure.com`` or
     ``https://x.openai.azure.com``): ``/openai/v1/{operation}`` is appended.
"""

from app.services.azure_urls import resolve_azure_url


class TestV1FullOperationUrl:
    """A full v1 operation URL is normalized to the requested operation."""

    def test_v1_full_generations_url_is_preserved(self):
        endpoint = "https://x.services.ai.azure.com/openai/v1/images/generations"
        url = resolve_azure_url(endpoint, "images/generations")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/generations"
        assert "api-version" not in url

    def test_v1_full_generations_endpoint_edits_request_targets_edits(self):
        """An edits request against a generations endpoint must target /images/edits."""
        endpoint = "https://x.services.ai.azure.com/openai/v1/images/generations"
        url = resolve_azure_url(endpoint, "images/edits")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/edits"
        assert "api-version" not in url

    def test_v1_chat_full_url(self):
        endpoint = "https://x.services.ai.azure.com/openai/v1/chat/completions"
        url = resolve_azure_url(endpoint, "chat/completions")
        assert url == "https://x.services.ai.azure.com/openai/v1/chat/completions"
        assert "api-version" not in url


class TestV1Base:
    """A v1 base endpoint has the requested operation appended."""

    def test_v1_base_appends_operation(self):
        endpoint = "https://x.services.ai.azure.com/openai/v1"
        url = resolve_azure_url(endpoint, "images/generations")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/generations"
        assert "api-version" not in url

    def test_v1_base_trailing_slash_normalized(self):
        endpoint = "https://x.services.ai.azure.com/openai/v1/"
        url = resolve_azure_url(endpoint, "images/edits")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/edits"
        assert "api-version" not in url


class TestPlainBase:
    """A plain base host gets /openai/v1/{operation} appended."""

    def test_plain_base_services_generations(self):
        url = resolve_azure_url("https://x.services.ai.azure.com", "images/generations")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/generations"
        assert "api-version" not in url

    def test_plain_base_trailing_slash(self):
        url = resolve_azure_url("https://x.services.ai.azure.com/", "images/generations")
        assert url == "https://x.services.ai.azure.com/openai/v1/images/generations"
        assert "api-version" not in url

    def test_plain_base_openai_azure_chat(self):
        url = resolve_azure_url("https://x.openai.azure.com", "chat/completions")
        assert url == "https://x.openai.azure.com/openai/v1/chat/completions"
        assert "api-version" not in url

    def test_plain_base_openai_azure_edits(self):
        url = resolve_azure_url("https://x.openai.azure.com", "images/edits")
        assert url == "https://x.openai.azure.com/openai/v1/images/edits"
        assert "api-version" not in url
