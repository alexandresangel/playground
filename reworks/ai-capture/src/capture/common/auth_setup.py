"""Wire m2m JWKS auth from CHAT_CONFIG."""

from __future__ import annotations

from typing import Any, Callable, Dict, Tuple

from auth_m2m import M2MAuth, configure_auth as _configure_m2m


def configure_auth(
    _base_dir=None,
    config: Dict[str, Any] | None = None,
    *,
    warmup: bool = True,
) -> Tuple[M2MAuth, Callable, Callable, Callable]:
    """Return (auth, get_identity, require_refresh, require_capture).

    ``_base_dir`` is accepted for call-site compatibility and ignored.
    """
    if config is None:
        from settings import load_config

        config = load_config()
    return _configure_m2m(config, warmup=warmup)
