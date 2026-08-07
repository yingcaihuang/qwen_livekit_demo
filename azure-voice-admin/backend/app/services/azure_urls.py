"""Robust Azure OpenAI request-URL resolution (v1-only / OpenAI-compatible).

Azure OpenAI has moved to the ``/openai/v1`` surface (the OpenAI-compatible
"v1" API) and no longer uses the classic ``api-version`` query parameter or the
``/openai/deployments/{deployment}/...`` path shape. Endpoints are configured as
one of:

    - a plain base host, e.g. ``https://x.services.ai.azure.com`` or
      ``https://x.openai.azure.com``
    - a v1 base, e.g. ``https://x.services.ai.azure.com/openai/v1``
    - a full v1 operation URL, e.g.
      ``https://x.services.ai.azure.com/openai/v1/images/generations``

``resolve_azure_url`` normalizes all of these into a single final URL for the
requested operation. The v1 surface expects ``model`` in the request body, so
callers always include it; no ``api-version`` query is ever appended.
"""

from __future__ import annotations

# Operations understood by the resolver. ``operation`` is the trailing path the
# v1 surface appends after the ``/openai/v1`` segment.
_OPERATIONS = ("images/generations", "images/edits", "chat/completions")

# Marker identifying the Azure "v1" (OpenAI-compatible) surface.
_V1_MARKER = "/openai/v1"

# Trailing verbs that indicate the user pasted a full operation URL.
_OPERATION_VERBS = ("generations", "edits", "completions")


def resolve_azure_url(endpoint: str, operation: str) -> str:
    """Resolve the final Azure v1 request URL for ``operation``.

    Args:
        endpoint: The instance endpoint. May be a plain base
            (``https://x.openai.azure.com``), a v1 base
            (``https://x.services.ai.azure.com/openai/v1``), or a full v1
            operation URL of either shape.
        operation: One of ``"images/generations"``, ``"images/edits"`` or
            ``"chat/completions"``.

    Returns:
        The resolved v1 request URL. Never contains an ``api-version`` query.
    """
    base = (endpoint or "").rstrip("/")
    lower = base.lower()
    # The trailing verb of the requested operation (generations/edits/completions).
    verb = operation.rsplit("/", 1)[-1]

    # Rule 1: the Azure "v1" (OpenAI-compatible) surface.
    # Handles BOTH a v1 base ("…/openai/v1") and a full v1 operation URL
    # ("…/openai/v1/images/generations", "…/images/edits", "…/chat/completions").
    # Slicing at "/openai/v1" and re-appending the requested operation naturally
    # drops any trailing operation the user typed, so an edits request against an
    # endpoint that ends in /images/generations correctly targets /images/edits.
    marker_idx = lower.find(_V1_MARKER)
    if marker_idx != -1:
        v1_base = base[: marker_idx + len(_V1_MARKER)]
        return f"{v1_base}/{operation}"

    # Split off any existing query string for the full-URL detection.
    path_part = base.partition("?")[0]
    path_lower = path_part.lower()

    # Rule 2: a full operation URL without "/openai/v1" (the path already ends in
    # a known operation verb). Replace the trailing verb with the requested
    # operation's verb. No api-version query is appended.
    if any(path_lower.endswith(f"/{v}") for v in _OPERATION_VERBS):
        return f"{path_part.rsplit('/', 1)[0]}/{verb}"

    # Rule 3: a plain base host -> append the v1 operation path.
    return f"{base}/openai/v1/{operation}"
