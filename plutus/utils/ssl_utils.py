"""Shared SSL utilities for Plutus network clients.

On macOS, Python does not use the system keychain by default.  The bundled
``ssl`` module ships without the Apple root CA certificates, which causes
``CERTIFICATE_VERIFY_FAILED`` errors when connecting to any HTTPS host
(including api.telegram.org, discord.com, api.github.com, etc.).

The standard fix is to use the ``certifi`` CA bundle, which ships with every
Python installation and contains the Mozilla root CA store.  This module
provides helper functions that return properly configured SSL contexts and
connector objects for ``aiohttp`` and ``httpx`` so every network client in
Plutus automatically gets the correct certificates on all platforms.

Usage
-----
aiohttp::

    from plutus.utils.ssl_utils import make_aiohttp_connector
    session = aiohttp.ClientSession(connector=make_aiohttp_connector(), ...)

httpx::

    from plutus.utils.ssl_utils import make_httpx_ssl_context
    async with httpx.AsyncClient(verify=make_httpx_ssl_context()) as client:
        ...
"""

from __future__ import annotations

import ssl

import certifi


def make_ssl_context() -> ssl.SSLContext:
    """Return an SSL context that trusts the certifi CA bundle.

    This is the correct fix for macOS where Python's bundled ``ssl`` module
    does not automatically use the system keychain.  Using certifi's CA bundle
    works identically on macOS, Windows, and Linux.
    """
    ctx = ssl.create_default_context(cafile=certifi.where())
    return ctx


def make_aiohttp_connector() -> "aiohttp.TCPConnector":  # type: ignore[name-defined]
    """Return an ``aiohttp.TCPConnector`` using the certifi CA bundle.

    Import is deferred so this module can be imported even when aiohttp is not
    installed (e.g. in minimal environments).
    """
    import aiohttp  # noqa: PLC0415

    return aiohttp.TCPConnector(ssl=make_ssl_context())


def make_httpx_ssl_context() -> ssl.SSLContext:
    """Return an SSL context suitable for use as ``httpx.AsyncClient(verify=...)``.

    httpx accepts an ``ssl.SSLContext`` directly for the ``verify`` parameter.
    """
    return make_ssl_context()
