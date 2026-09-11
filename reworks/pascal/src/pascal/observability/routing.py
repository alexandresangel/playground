"""Successful low-noise endpoints declare their access-log policy themselves."""


def quiet_access(endpoint):
    endpoint.__quiet_access__ = True
    return endpoint


def is_quiet_request(request) -> bool:
    # Routing has completed when the response is logged. This works with prefixes
    # and included routers without reproducing the framework's matching logic.
    endpoint = request.scope.get("endpoint")
    return bool(getattr(endpoint, "__quiet_access__", False))
