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


def _auth_converter(
    v: t.Optional[t.Tuple[str, str]]
) -> t.Optional[_auth.AuthBase]:
    if isinstance(v, tuple) and len(v) == 2:
        return _auth.HTTPBasicAuth(*v)
    return v


@attr.frozen(kw_only=True)
class RequestContext:
    """Context that tracks the per request parameters."""

    allow_redirects: bool = attr.ib(default=True)
    auth: _auth.AuthBase = attr.field(
        validator=attr.validators.optional(
            attr.validators.instance_of(_auth.AuthBase)
        ),
        converter=_auth_converter,
        default=None,
    )
    cert: t.Optional[t.Tuple[str, str]] = attr.field(default=None)
    cookies = attr.field(factory=cookies.RequestsCookieJar)
    headers: t.MutableMapping[str, str] = attr.field(
        factory=structures.CaseInsensitiveDict,
        validator=attr.validators.instance_of(collections.abc.MutableMapping),
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
            default = getattr(self, key, _SENTINEL)
            if default is _SENTINEL:
                return request_options.get(key, _NOT_PROVIDED)
            return request_options.get(key, default)

        return RequestContext(
            # TODO: Handle the rest of the attributes
            headers=_opt("headers"),
            cookies=_opt("cookies"),
            auth=_opt("auth"),
            proxies=_opt("proxies"),
            params=_opt("params"),
        )


@attr.mutable(kw_only=True, getstate_setstate=True)
class SessionContext:
    """Context used to contain the session parameters applied to each request."""

    auth: t.Optional[_auth.AuthBase] = attr.field(
        validator=attr.validators.optional(
            attr.validators.instance_of(_auth.AuthBase)
        ),
        converter=_auth_converter,
        on_setattr=[attr.setters.convert],
        default=None,
    )
    cert: t.Optional[t.Tuple[str, str]] = attr.field(default=None)
    cookies = attr.field(factory=cookies.RequestsCookieJar)
    headers: t.MutableMapping[str, str] = attr.field(
        factory=structures.CaseInsensitiveDict,
        validator=attr.validators.instance_of(collections.abc.MutableMapping),
    )
    hooks: t.Dict[str, t.Any] = attr.ib(factory=dict)
    max_redirects: int = attr.ib(default=models.DEFAULT_REDIRECT_LIMIT)
    params: t.Dict[str, str] = attr.field(factory=dict)
    proxies: t.Dict[str, str] = attr.field(factory=dict)
    stream: bool = attr.field(default=False)
    trust_env: bool = attr.field(default=True)
    verify: t.Union[bool, str] = attr.field(default=True)

    def create_request_context(
        self, request_options: t.Dict[str, t.Any]
    ) -> RequestContext:
        def _opt(key: str, *, merge: bool = False) -> t.Any:
            session_default = getattr(self, key, _SENTINEL)
            if session_default is _SENTINEL:
                return request_options.get(key, _NOT_PROVIDED)

            request_val = request_options.get(key, _SENTINEL)
            if request_val is _SENTINEL:
                return session_default

            if merge:
                return_val = session_default.copy()
                if request_val is not None:
                    return_val.update(request_val)
                return return_val
            return request_val

        return RequestContext(
            # TODO: Handle the rest of the attributes
            headers=_opt("headers", merge=True),
            cookies=_opt("cookies"),
            auth=_opt("auth"),
            proxies=_opt("proxies", merge=True),
            params=_opt("params", merge=True),
        )


T = t.TypeVar("T")


class _ProxyAttribute(t.Generic[T]):
    def __init__(self, *, context_attr: str):
        self.context_attr = context_attr
        self.attr_name = None

    def __set_name__(self, owner: T, name: str):
        self.attr_name = name

    def __get__(self, obj: T, objtype: type = None) -> t.Any:
        ctx = getattr(obj, self.context_attr)
        return getattr(ctx, self.attr_name)

    def __set__(self, obj: T, value: t.Any) -> None:
        ctx = getattr(obj, self.context_attr)
        setattr(ctx, self.attr_name, value)


def proxy_attribute(*, context_attr: str = "_ctx") -> _ProxyAttribute:
    return _ProxyAttribute(context_attr=context_attr)
