"""Context classes for the Session and Request objects."""
import collections
import typing as t

import attr

from . import adapters as _adapters
from . import auth as _auth
from . import cookies
from . import models
from . import structures


_SENTINEL = object()
_NOT_PROVIDED = object()


@attr.define(frozen=True, kw_only=True)
class RequestContext:
    """Context that tracks the per request parameters."""

    allow_redirects: bool = attr.ib(default=True)
    auth: _auth.AuthBase = attr.field(
        validator=attr.validators.optional(
            attr.validators.instance_of(_auth.AuthBase)
        ),
        default=None,
    )
    cert: t.Optional[t.Tuple[str, str]] = attr.field(default=None)
    cookies = attr.field(factory=cookies.RequestsCookieJar)
    headers: structures.CaseInsensitiveDict = attr.field(
        factory=structures.CaseInsensitiveDict,
        converter=structures.CaseInsensitiveDict,
        validator=attr.validators.instance_of(structures.CaseInsensitiveDict),
    )
    params: t.Dict[str, str] = attr.field(factory=dict)
    proxies: t.Dict[str, str] = attr.field(factory=dict)
    stream: bool = attr.field(default=False)
    timeout: t.Union[
        float, int, t.Tuple[t.Union[float, int], t.Union[float, int]]
    ] = attr.ib(default=_adapters.DEFAULT_TIMEOUT)
    trust_env: bool = attr.field(default=True)
    verify: t.Union[bool, str] = attr.field(default=True)

    def copy_with(
        self, request_options: t.Dict[str, t.Any]
    ) -> "RequestContext":
        def _opt(key: str) -> t.Any:
            session_default = getattr(self, key, _SENTINEL)
            if session_default is _SENTINEL:
                return request_options.get(key, _NOT_PROVIDED)
            return request_options.get(key, session_default)

        return RequestContext(
            headers=_opt("headers"),
            cookies=_opt("cookies"),
            auth=_opt("auth"),
            proxies=_opt("proxies"),
            params=_opt("params"),
        )


@attr.mutable(kw_only=True)
class SessionContext:
    """Context used to contain the session parameters applied to each request."""

    adapters: collections.OrderedDict[str, _adapters.BaseAdapter] = attr.field(
        factory=collections.OrderedDict, converter=collections.OrderedDict
    )
    auth: t.Optional[_auth.AuthBase] = attr.field(
        validator=attr.validators.optional(
            attr.validators.instance_of(_auth.AuthBase)
        ),
        default=None,
    )
    cert: t.Optional[t.Tuple[str, str]] = attr.field(default=None)
    cookies = attr.field(factory=cookies.RequestsCookieJar)
    headers: structures.CaseInsensitiveDict = attr.field(
        factory=structures.CaseInsensitiveDict,
        converter=structures.CaseInsensitiveDict,
        validator=attr.validators.instance_of(structures.CaseInsensitiveDict),
    )
    hooks: t.Dict[str, t.Any] = attr.ib(factory=dict)
    max_redirects: int = attr.ib(default=models.DEFAULT_REDIRECT_LIMIT)
    proxies: t.Dict[str, str] = attr.field(factory=dict)
    stream: bool = attr.field(default=False)
    trust_env: bool = attr.field(default=True)
    verify: t.Union[bool, str] = attr.field(default=True)

    @adapters.validator
    def _validate_adapters(self, attribute, value):
        for adapter in value.values():
            if not isinstance(adapter, _adapters.BaseAdapter):
                raise ValueError(
                    "adapters must inherit from requests.adapters.BaseAdapter"
                )

    def create_request_context(
        self, request_options: t.Dict[str, t.Any]
    ) -> RequestContext:
        def _opt(key: str) -> t.Any:
            session_default = getattr(self, key, _SENTINEL)
            if session_default is _SENTINEL:
                return request_options.get(key, _NOT_PROVIDED)
            return request_options.get(key, session_default)

        return RequestContext(
            headers=_opt("headers"),
            cookies=_opt("cookies"),
            auth=_opt("auth"),
            proxies=_opt("proxies"),
            params=_opt("params"),
        )
