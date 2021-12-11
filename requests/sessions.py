"""
requests.sessions
~~~~~~~~~~~~~~~~~

This module provides a Session object to manage and persist settings across
requests (cookies, auth, proxies).
"""
import os
import sys
import time
import typing as t
import warnings
from collections import OrderedDict
from collections.abc import Mapping
from datetime import timedelta
from http import cookiejar as cookielib
from urllib.parse import urlparse

from . import adapters as _adapters
from . import auth as _auth
from . import contexts
from . import redirects
from . import structures
from ._internal_utils import consume_response
from .cookies import cookiejar_from_dict
from .cookies import extract_cookies_to_jar
from .cookies import merge_cookies
from .cookies import RequestsCookieJar
from .exceptions import InvalidScheme
from .exceptions import TooManyRedirects
from .hooks import default_hooks
from .hooks import dispatch_hook
from .models import PreparedRequest
from .models import Request
from .utils import default_headers
from .utils import get_auth_from_url
from .utils import get_environ_proxies
from .utils import get_netrc_auth
from .utils import rewind_body
from .utils import should_bypass_proxies
from .utils import to_key_val_list

if t.TYPE_CHECKING:
    from .auth import AuthBase
    from .models import Response

# formerly defined here, reexposed here for backward compatibility

# Preferred clock, based on which one is more accurate on a given system.
if sys.platform == "win32":
    try:  # Python 3.4+
        preferred_clock = time.perf_counter
    except AttributeError:  # Earlier than Python 3.
        preferred_clock = time.clock
else:
    preferred_clock = time.time


def merge_setting(request_setting, session_setting, dict_class=OrderedDict):
    """Determines appropriate setting for a given request, taking into account
    the explicit setting on that request, and the setting in the session. If a
    setting is a dictionary, they will be merged together using `dict_class`
    """

    if session_setting is None:
        return request_setting

    if request_setting is None:
        return session_setting

    # Bypass if not a dictionary (e.g. verify)
    if not (
        isinstance(session_setting, Mapping)
        and isinstance(request_setting, Mapping)
    ):
        return request_setting

    merged_setting = dict_class(to_key_val_list(session_setting))
    merged_setting.update(to_key_val_list(request_setting))

    # Remove keys that are set to None. Extract keys first to avoid altering
    # the dictionary during iteration.
    none_keys = [k for (k, v) in merged_setting.items() if v is None]
    for key in none_keys:
        del merged_setting[key]

    return merged_setting


def merge_hooks(request_hooks, session_hooks, dict_class=OrderedDict):
    """Properly merges both requests and session hooks.

    This is necessary because when request_hooks == {'response': []}, the
    merge breaks Session hooks entirely.
    """
    if session_hooks is None or session_hooks.get("response") == []:
        return request_hooks

    if request_hooks is None or request_hooks.get("response") == []:
        return session_hooks

    return merge_setting(request_hooks, session_hooks, dict_class)


class Session:
    """A Requests session.

    Provides cookie persistence, connection-pooling, and configuration.

    Basic Usage::

      >>> import requests
      >>> s = requests.Session()
      >>> s.get('https://httpbin.org/get')
      <Response [200]>

    Or as a context manager::

      >>> with requests.Session() as s:
      ...     s.get('https://httpbin.org/get')
      <Response [200]>
    """

    __attrs__ = [
        "_ctx",
        "_adapter_mgr",
    ]

    headers = contexts.proxy_attribute()
    auth = contexts.proxy_attribute()
    proxies = contexts.proxy_attribute()
    hooks = contexts.proxy_attribute()
    params = contexts.proxy_attribute()
    stream = contexts.proxy_attribute()
    #: SSL Verification default.
    #: Defaults to `True`, requiring requests to verify the TLS certificate at the
    #: remote end.
    #: If verify is set to `False`, requests will accept any TLS certificate
    #: presented by the server, and will ignore hostname mismatches and/or
    #: expired certificates, which will make your application vulnerable to
    #: man-in-the-middle (MitM) attacks.
    #: Only set this to `False` for testing.
    verify = contexts.proxy_attribute()
    #: SSL client certificate default, if String, path to ssl client
    #: cert file (.pem). If Tuple, ('cert', 'key') pair.
    cert = contexts.proxy_attribute()
    #: Maximum number of redirects allowed. If the request exceeds this
    #: limit, a :class:`TooManyRedirects` exception is raised.
    #: This defaults to requests.models.DEFAULT_REDIRECT_LIMIT, which is
    #: 30.
    max_redirects = contexts.proxy_attribute()
    #: Trust environment settings for proxy configuration, default
    #: authentication and similar.
    trust_env = contexts.proxy_attribute()
    #: A CookieJar containing all currently outstanding cookies set on this
    #: session. By default it is a
    #: :class:`RequestsCookieJar <requests.cookies.RequestsCookieJar>`, but
    #: may be any other ``cookielib.CookieJar`` compatible object.
    cookies = contexts.proxy_attribute()

    def __init__(self):
        self._ctx = contexts.SessionContext(
            headers=default_headers(),
            hooks=default_hooks(),
        )
        self._adapter_mgr = _adapters.Manager()
        self._adapter_mgr.register("https://", _adapters.HTTPAdapter())
        self._adapter_mgr.register("http://", _adapters.HTTPAdapter())

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def adapters(self) -> t.MutableMapping[str, _adapters.BaseAdapter]:
        warnings.warn(
            "Session.adapters is deprecated for removal in 2023",
            DeprecationWarning,
        )
        return self._adapter_mgr.adapters

    def prepare_request(self, request):
        """Constructs a :class:`PreparedRequest <PreparedRequest>` for
        transmission and returns it. The :class:`PreparedRequest` has settings
        merged from the :class:`Request <Request>` instance and those of the
        :class:`Session`.

        :param request: :class:`Request` instance to prepare with this
            session's settings.
        :rtype: requests.PreparedRequest
        """
        cookies = request.cookies or {}

        # Bootstrap CookieJar.
        if not isinstance(cookies, cookielib.CookieJar):
            cookies = cookiejar_from_dict(cookies)

        # Merge with session cookies
        merged_cookies = merge_cookies(
            merge_cookies(RequestsCookieJar(), self.cookies), cookies
        )

        # Set environment's basic authentication if not explicitly set.
        auth = request.auth
        if self.trust_env and not auth and not self.auth:
            auth = get_netrc_auth(request.url)

        p = PreparedRequest()
        p.prepare(
            method=request.method.upper(),
            url=request.url,
            files=request.files,
            data=request.data,
            json=request.json,
            headers=merge_setting(
                request.headers,
                self.headers,
                dict_class=structures.CaseInsensitiveDict,
            ),
            params=merge_setting(request.params, self.params),
            auth=merge_setting(auth, self.auth),
            cookies=merged_cookies,
            hooks=merge_hooks(request.hooks, self.hooks),
        )
        return p

    def request(
        self,
        method,
        url,
        params=None,
        data=None,
        headers=None,
        cookies=None,
        files=None,
        auth=None,
        timeout=_adapters.DEFAULT_TIMEOUT,
        allow_redirects=True,
        proxies=None,
        hooks=None,
        stream=None,
        verify=None,
        cert=None,
        json=None,
    ):
        """Constructs a :class:`Request <Request>`, prepares it and sends it.
        Returns :class:`Response <Response>` object.

        :param method: method for the new :class:`Request` object.
        :param url: URL for the new :class:`Request` object.
        :param params: (optional) Dictionary or bytes to be sent in the query
            string for the :class:`Request`.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json to send in the body of the
            :class:`Request`.
        :param headers: (optional) Dictionary of HTTP Headers to send with the
            :class:`Request`.
        :param cookies: (optional) Dict or CookieJar object to send with the
            :class:`Request`.
        :param files: (optional) Dictionary of ``'filename': file-like-objects``
            for multipart encoding upload.
        :param auth: (optional) Auth tuple or callable to enable
            Basic/Digest/Custom HTTP Auth.
        :param timeout: (optional) How long to wait for the server to send
            data before giving up, as a float, or a :ref:`(connect timeout,
            read timeout) <timeouts>` tuple.
        :type timeout: float or tuple
        :param allow_redirects: (optional) Set to True by default.
        :type allow_redirects: bool
        :param proxies: (optional) Dictionary mapping protocol or protocol and
            hostname to the URL of the proxy.
        :param stream: (optional) whether to immediately download the response
            content. Defaults to ``False``.
        :param verify: (optional) Either a boolean, in which case it controls whether we verify
            the server's TLS certificate, or a string, in which case it must be a path
            to a CA bundle to use. Defaults to ``True``. When set to
            ``False``, requests will accept any TLS certificate presented by
            the server, and will ignore hostname mismatches and/or expired
            certificates, which will make your application vulnerable to
            man-in-the-middle (MitM) attacks. Setting verify to ``False``
            may be useful during local development or testing.
        :param cert: (optional) if String, path to ssl client cert file (.pem).
            If Tuple, ('cert', 'key') pair.
        :rtype: requests.Response
        """
        request_ctx = self._ctx.create_request_context(
            {
                "allow_redirects": allow_redirects,
                "auth": auth,
                "cert": cert,
                "cookies": cookies,
                "headers": headers,
                "hooks": hooks,
                "params": params,
                "proxies": proxies,
                "stream": stream,
                "timeout": timeout,
            }
        )
        request_ctx.copy_with({})  # TODO: Use for real with Request object
        # Create the Request.
        req = Request(
            method=method.upper(),
            url=url,
            headers=headers,
            files=files,
            data=data or {},
            json=json,
            params=params or {},
            auth=auth,
            cookies=cookies,
            hooks=hooks,
        )
        prep = self.prepare_request(req)

        proxies = proxies or {}

        settings = self.merge_environment_settings(
            prep.url, proxies, stream, verify, cert
        )

        # Send the request.
        send_kwargs = {
            "timeout": timeout,
            "allow_redirects": allow_redirects,
        }
        send_kwargs.update(settings)
        resp = self.send(prep, **send_kwargs)

        return resp

    def get(self, url, **kwargs):
        r"""Sends a GET request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        kwargs.setdefault("allow_redirects", True)
        return self.request("GET", url, **kwargs)

    def options(self, url, **kwargs):
        r"""Sends a OPTIONS request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        kwargs.setdefault("allow_redirects", True)
        return self.request("OPTIONS", url, **kwargs)

    def head(self, url, **kwargs):
        r"""Sends a HEAD request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        kwargs.setdefault("allow_redirects", False)
        return self.request("HEAD", url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        r"""Sends a POST request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param json: (optional) json to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        return self.request("POST", url, data=data, json=json, **kwargs)

    def put(self, url, data=None, **kwargs):
        r"""Sends a PUT request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        return self.request("PUT", url, data=data, **kwargs)

    def patch(self, url, data=None, **kwargs):
        r"""Sends a PATCH request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param data: (optional) Dictionary, list of tuples, bytes, or file-like
            object to send in the body of the :class:`Request`.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        return self.request("PATCH", url, data=data, **kwargs)

    def delete(self, url, **kwargs):
        r"""Sends a DELETE request. Returns :class:`Response` object.

        :param url: URL for the new :class:`Request` object.
        :param \*\*kwargs: Optional arguments that ``request`` takes.
        :rtype: requests.Response
        """

        return self.request("DELETE", url, **kwargs)

    def send(self, request, **kwargs):
        """Send a given PreparedRequest.

        :rtype: requests.Response
        """
        # Set defaults that the hooks can utilize to ensure they always have
        # the correct parameters to reproduce the previous request.
        kwargs.setdefault("stream", self.stream)
        kwargs.setdefault("verify", self.verify)
        kwargs.setdefault("cert", self.cert)
        kwargs.setdefault(
            "proxies", self.rebuild_proxies(request, self.proxies)
        )

        # It's possible that users might accidentally send a Request object.
        # Guard against that specific failure case.
        if isinstance(request, Request):
            raise ValueError("You can only send PreparedRequests.")

        # Set up variables needed for resolve_redirects and dispatching of hooks
        allow_redirects = kwargs.pop("allow_redirects", True)
        stream = kwargs.get("stream")
        hooks = request.hooks

        # Get the appropriate adapter to use
        adapter = self.get_adapter(url=request.url)

        # Start time (approximately) of the request
        start = preferred_clock()

        # Send the request
        r = adapter.send(request, **kwargs)

        # Total elapsed time of the request (approximately)
        elapsed = preferred_clock() - start
        r.elapsed = timedelta(seconds=elapsed)

        # Response manipulation hooks
        r = dispatch_hook("response", hooks, r, **kwargs)

        # Persist cookies
        if r.history:

            # If the hooks create history then we want those cookies too
            for resp in r.history:
                extract_cookies_to_jar(self.cookies, resp.request, resp.raw)

        extract_cookies_to_jar(self.cookies, request, r.raw)

        # Resolve redirects if allowed.
        if allow_redirects:
            # Redirect resolving generator.
            gen = self.resolve_redirects(r, request, **kwargs)
            history = [resp for resp in gen]
        else:
            history = []

        # Shuffle things around if there's history.
        if history:
            # Insert the first (original) request at the start
            history.insert(0, r)
            # Get the last request made
            r = history.pop()
            r.history = history

        if not stream:
            r.content

        return r

    def merge_environment_settings(self, url, proxies, stream, verify, cert):
        """
        Check the environment and merge it with some settings.

        :rtype: dict
        """
        # Gather clues from the surrounding environment.
        if self.trust_env:
            # Set environment's proxies.
            no_proxy = proxies.get("no_proxy") if proxies is not None else None
            env_proxies = get_environ_proxies(url, no_proxy=no_proxy)
            for (k, v) in env_proxies.items():
                proxies.setdefault(k, v)

            # Look for requests environment configuration and be compatible
            # with cURL.
            if verify is True or verify is None:
                verify = os.environ.get(
                    "REQUESTS_CA_BUNDLE"
                ) or os.environ.get("CURL_CA_BUNDLE")

        # Merge all the kwargs.
        proxies = merge_setting(proxies, self.proxies)
        stream = merge_setting(stream, self.stream)
        verify = merge_setting(verify, self.verify)
        cert = merge_setting(cert, self.cert)

        return {
            "verify": verify,
            "proxies": proxies,
            "stream": stream,
            "cert": cert,
        }

    def get_adapter(self, url):
        """
        Returns the appropriate connection adapter for the given URL.

        :rtype: requests.adapters.BaseAdapter
        """
        try:
            adapter = self._adapter_mgr.find(url)
        except _adapters._NoMatchingAdapterError:
            # Nothing matches :-/
            raise InvalidScheme(
                f"No connection adapters were found for {url!r}"
            )
        return adapter

    def close(self):
        """Closes all adapters and as such the session"""
        self._adapter_mgr.close()

    def mount(self, prefix: str, adapter: _adapters.BaseAdapter) -> None:
        """Registers a transport adapter to a prefix.

        :raises ValueError:
            If the adapter does not inherit from requests.adapters.BaseAdapter
        """
        self._adapter_mgr.register(prefix, adapter)

    def unmount(self, prefix: str) -> None:
        """Removes a registered transport adapter at the given prefix."""
        self._adapter_mgr.remove(prefix)

    def __getstate__(self):
        state = {attr: getattr(self, attr, None) for attr in self.__attrs__}
        return state

    def __setstate__(self, state):
        for attr, value in state.items():
            setattr(self, attr, value)

    def resolve_redirects(
        self,
        resp: "Response",
        req: PreparedRequest,
        stream: bool = False,
        timeout: t.Optional[t.Union[float, t.Tuple[float, float]]] = None,
        verify: t.Union[bool, str] = True,
        cert: t.Optional[str] = None,
        proxies: t.Optional[t.Dict[str, str]] = None,
        **adapter_kwargs,
    ) -> t.Generator["Response", None, None]:
        """Generate responses as part of processing redirects.

        This method will take the initial response, initial prepared request,
        and other arguments and continuously follow redirects until a stop
        condition is met.
        """
        logic = redirects.RedirectDecisionEngine(
            config={
                "allow_redirects": True,
                "max_redirects": self.max_redirects,
            }
        )
        decision = logic.decision_for(resp)

        history = []
        while decision.was_a_redirect():
            next_request = req.copy()

            consume_response(resp)
            history.append(resp)

            if decision.reason is decision.Reason.TOO_MANY_REDIRECTS:
                raise TooManyRedirects(
                    f"Exceeded {self.max_redirects} redirects.",
                    response=resp,
                )

            next_url = decision.redirect_url
            info = decision.redirect_information
            next_request.url = next_url
            next_request.method = info["next_method"]
            next_request.headers = info["next_headers"]
            next_request.body = info["next_body"]

            # Extract any cookies sent on the response to the cookiejar
            # in the new request. Because we've mutated our copied prepared
            # request, use the old one that we haven't yet touched.
            extract_cookies_to_jar(next_request._cookies, req, resp.raw)
            merge_cookies(next_request._cookies, self.cookies)
            next_request.prepare_cookies(next_request._cookies)

            # Rebuild auth and proxy information.
            proxies = self.rebuild_proxies(next_request, proxies)
            self.rebuild_auth(next_request, resp, decision)

            # A failed tell() sets `_body_position` to `object()`. This non-None
            # value ensures `rewindable` will be True, allowing us to raise an
            # UnrewindableBodyError, instead of hanging the connection.
            rewindable = next_request._body_position is not None and (
                "Content-Length" in req.headers
                or "Transfer-Encoding" in req.headers
            )

            # Attempt to rewind consumed file-like object.
            if rewindable:
                rewind_body(next_request)

            resp = self.send(
                next_request,
                stream=stream,
                timeout=timeout,
                verify=verify,
                cert=cert,
                proxies=proxies,
                allow_redirects=False,
                **adapter_kwargs,
            )

            extract_cookies_to_jar(self.cookies, next_request, resp.raw)
            resp.history = history[:]

            # extract redirect url, if any, for the next loop
            yield resp

            decision = logic.decision_for(resp)
            req = next_request

    def rebuild_auth(
        self,
        prepared_request: PreparedRequest,
        response: "Response",
        redirect_decision: redirects.Decision,
    ) -> None:
        """When being redirected we may want to strip authentication from the
        request to avoid leaking credentials. This method intelligently removes
        and reapplies authentication where possible to avoid credential loss.
        """
        headers = prepared_request.headers
        url = prepared_request.url

        if (
            "Authorization" in headers
            and redirect_decision.should_strip_authentication()
        ):
            # If we get redirected to a new host, we should strip out any
            # authentication headers.
            del headers["Authorization"]

        # .netrc might have more auth for us on our new host.
        new_auth = get_netrc_auth(url) if self.trust_env else None
        if new_auth is not None:
            prepared_request.prepare_auth(new_auth)

    def rebuild_proxies(self, prepared_request, proxies):
        """This method re-evaluates the proxy configuration by considering the
        environment variables. If we are redirected to a URL covered by
        NO_PROXY, we strip the proxy configuration. Otherwise, we set missing
        proxy keys for this URL (in case they were stripped by a previous
        redirect).

        This method also replaces the Proxy-Authorization header where
        necessary.

        :rtype: dict
        """
        proxies = proxies if proxies is not None else {}
        headers = prepared_request.headers
        url = prepared_request.url
        scheme = urlparse(url).scheme
        new_proxies = proxies.copy()
        no_proxy = proxies.get("no_proxy")

        bypass_proxy = should_bypass_proxies(url, no_proxy=no_proxy)
        if self.trust_env and not bypass_proxy:
            environ_proxies = get_environ_proxies(url, no_proxy=no_proxy)

            proxy = environ_proxies.get(scheme, environ_proxies.get("all"))

            if proxy:
                new_proxies.setdefault(scheme, proxy)

        if "Proxy-Authorization" in headers:
            del headers["Proxy-Authorization"]

        try:
            username, password = get_auth_from_url(new_proxies[scheme])
        except KeyError:
            username, password = None, None

        if username and password:
            headers["Proxy-Authorization"] = _auth._basic_auth_str(
                username, password
            )

        return new_proxies


def session():
    """
    Returns a :class:`Session` for context-management.

    .. deprecated:: 1.0.0

        This method has been deprecated since version 1.0.0 and is only kept for
        backwards compatibility. New code should use :class:`~requests.sessions.Session`
        to create a session. This may be removed at a future date.

    :rtype: Session
    """
    return Session()
