"""Redirect logic and handling in its own stand-alone class."""
import enum
import typing as t
import urllib.parse

from . import models
from . import utils
from .status_codes import codes

if t.TYPE_CHECKING:
    from . import contexts


class Decision:
    """Represent the final decision around whether to redirect and where to.

    This class will be inspectable and used to represent:
    - Should a consumer of this be following a redirect?
    - Why should it follow the redirect or not?
    - Where should it redirect to (the full URL)
    - Should it remove authentication
    """

    class Reason(enum.Enum):
        """Reasons for the decision instance."""

        NO_REDIRECT_DETECTED = "nrd"
        USER_DISABLED_REDIRECTS = "udr"

        TOO_MANY_REDIRECTS = "tmr"

        REDIRECT_301 = "301"
        REDIRECT_302 = "302"
        REDIRECT_303 = "303"
        REDIRECT_307 = "307"
        REDIRECT_308 = "308"

    def __init__(  # noqa: D107
        self,
        *,
        allow_redirect: bool,
        reason: t.Optional[Reason] = None,
        **kwargs,
    ):
        self.allow_redirect = allow_redirect
        self.reason = reason
        self.redirect_information = kwargs
        self.redirect_information.setdefault("strip_authentication", True)

    def was_a_redirect(self) -> bool:
        """Detect if the response was a redirect."""
        return self.reason in {
            Decision.Reason.TOO_MANY_REDIRECTS,
            Decision.Reason.REDIRECT_301,
            Decision.Reason.REDIRECT_302,
            Decision.Reason.REDIRECT_303,
            Decision.Reason.REDIRECT_307,
            Decision.Reason.REDIRECT_308,
        }

    @property
    def redirect_url(self) -> t.Optional[str]:
        """Redirect to the user to this location."""
        return self.redirect_information.get("redirect_to")

    def should_strip_authentication(self) -> bool:
        """Indicate if the consumer should remove sensitive auth.

        This is to prevent leaking authentication information to a third-party
        that isn't trusted to handle that data.
        """
        return self.redirect_information["strip_authentication"]


# TODO(sigmavirus24): Better name please
class RedirectDecisionEngine:
    """Handle managing logic and decisions around redirects.

    In prior versions of Requests, this logic was built into the Session
    object and almost impossible to extend or override.

    This takes a SessionContext to understand how a session has been
    configured and returns parameters for the next request while deciding when
    to allow a redirect.
    """

    def __init__(self, config: "contexts.SessionContext"):  # noqa: D107
        self._config = config

    def __getstate__(self):
        return {"_config": self._config}

    def __setstate__(self, state):
        self._config = state["_config"]

    @property
    def max_redirect_limit(self) -> int:
        """Describe how many redirects to follow at once."""
        return self._config.max_redirects

    def decision_for(
        self,
        response: models.Response,
        allow_redirects: bool = True,
        *,
        redirects_seen: t.Optional[int] = None,
    ) -> Decision:
        """Make a decision about how to handle a response.

        :param response:
            The response that we're making a decision for
        :type response:
            :class:`~requests.models.Response`
        :param allow_redirects:
            Whether the user has allowed redirects
        :type: allow_redirects:
            bool
        :param redirects_seen:
            Used to influence the decision if a Response's history isn't
            accurate
        :type redirects_seen:
            int
        :returns:
            How to handle this response
        :rtype:
            :class:`~requests.redirects.Decision`
        """
        redirects_disabled = not allow_redirects
        if response.status_code not in models.REDIRECT_STATI:
            # It is not even a redirect, fall out early
            return Decision(
                allow_redirect=False,
                reason=Decision.Reason.NO_REDIRECT_DETECTED,
            )

        if redirects_disabled:
            # The user doesn't want to follow redirects
            return Decision(
                allow_redirect=False,
                reason=Decision.Reason.USER_DISABLED_REDIRECTS,
            )
        if (
            redirects_seen is not None
            and redirects_seen >= self.max_redirect_limit
        ) or (len(response.history) >= self.max_redirect_limit):
            # We've already followed the maximum number of redirects we want
            # to follow
            return Decision(
                allow_redirect=False, reason=Decision.Reason.TOO_MANY_REDIRECTS
            )

        # We're probably firmly in redirect territory here now
        next_url = _build_next_url(response)

        next_method = _rebuild_method(response)

        next_headers = response.request.headers.copy()
        next_body = response.request.body
        # https://github.com/psf/requests/issues/1084
        if response.status_code not in (
            codes.temporary_redirect,  # pylint: disable=no-member
            codes.permanent_redirect,  # pylint: disable=no-member
        ):
            # https://github.com/psf/requests/issues/3490
            purged_headers = (
                "Content-Length",
                "Content-Type",
                "Transfer-Encoding",
            )
            for header in purged_headers:
                next_headers.pop(header, None)
            next_body = None

        next_headers.pop("Cookie", None)

        return Decision(
            allow_redirect=True,
            reason=_redirect_reason_from_status(response),
            redirect_to=next_url,
            next_method=next_method,
            next_headers=next_headers,
            next_body=next_body,
            strip_authentication=_should_strip_auth(
                response.request.url, next_url
            ),
        )


_code_to_reason = {
    301: Decision.Reason.REDIRECT_301,
    302: Decision.Reason.REDIRECT_302,
    303: Decision.Reason.REDIRECT_303,
    307: Decision.Reason.REDIRECT_307,
    308: Decision.Reason.REDIRECT_308,
}


def _redirect_reason_from_status(response: models.Response) -> Decision.Reason:
    return _code_to_reason[response.status_code]


def _build_next_url(response: models.Response) -> str:
    previous_request = response.request
    location_header_value = _get_redirect_target(response)
    previous_fragment = urllib.parse.urlparse(previous_request.url).fragment

    # Handle redirection without scheme (see: RFC 1808 Section 4)
    url = location_header_value
    if location_header_value.startswith("//"):
        parsed_rurl = urllib.parse.urlparse(response.url)
        url = ":".join([parsed_rurl.scheme, url])

    # Normalize url case and attach previous fragment if needed (RFC 7231 7.1.2)
    parsed = urllib.parse.urlparse(url)
    if parsed.fragment == "" and previous_fragment:
        parsed = parsed._replace(fragment=previous_fragment)
    elif parsed.fragment:
        previous_fragment = parsed.fragment
    url = parsed.geturl()

    # Facilitate relative 'location' headers, as allowed by RFC 7231.
    # (e.g. '/path/to/resource' instead of 'http://domain.tld/path/to/resource')
    # Compliant with RFC3986, we percent encode the url.
    if not parsed.netloc:
        url = urllib.parse.urljoin(response.url, utils.requote_uri(url))
    else:
        url = utils.requote_uri(url)

    if isinstance(url, bytes):  # Let's just be safe
        url = url.decode("utf-8")

    return url


def _rebuild_method(response: models.Response) -> "str":
    """Determine what method to use on the redirect.

    When being redirected we may want to change the method of the request
    based on certain specs or browser behavior.
    """
    prepared_request = response.request
    method = prepared_request.method

    # https://tools.ietf.org/html/rfc7231#section-6.4.4
    if (
        response.status_code == codes.see_other  # pylint: disable=no-member
        and method != "HEAD"
    ):
        method = "GET"

    # Do what the browsers do, despite standards...
    # First, turn 302s into GETs.
    if (
        response.status_code == codes.found  # pylint: disable=no-member
        and method != "HEAD"
    ):
        method = "GET"

    # Second, if a POST is responded to with a 301, turn it into a GET.
    # This bizarre behaviour is explained in Issue 1704.
    if (
        response.status_code == codes.moved  # pylint: disable=no-member
        and method == "POST"
    ):
        method = "GET"

    return method


def _get_redirect_target(response: models.Response) -> str:
    location = response.headers["location"]
    # Currently the underlying http module on py3 decode headers
    # in latin1, but empirical evidence suggests that latin1 is very
    # rarely used with non-ASCII characters in HTTP headers.
    # It is more likely to get UTF8 header rather than latin1.
    # This causes incorrect handling of UTF8 encoded location headers.
    # To solve this, we re-encode the location in latin1.
    location = location.encode("latin1")
    return location.decode("utf8")


def _should_strip_auth(old_url: str, new_url: str):
    """Decide whether Authorization header should be removed when redirecting."""
    old_parsed = urllib.parse.urlparse(old_url)
    new_parsed = urllib.parse.urlparse(new_url)
    if old_parsed.hostname != new_parsed.hostname:
        return True
    # Special case: allow http -> https redirect when using the standard
    # ports. This isn't specified by RFC 7235, but is kept to avoid
    # breaking backwards compatibility with older versions of requests
    # that allowed any redirects on the same host.
    if (
        old_parsed.scheme == "http"
        and old_parsed.port in (80, None)
        and new_parsed.scheme == "https"
        and new_parsed.port in (443, None)
    ):
        return False

    # Handle default port usage corresponding to scheme.
    changed_port = old_parsed.port != new_parsed.port
    changed_scheme = old_parsed.scheme != new_parsed.scheme
    default_port = (utils.DEFAULT_PORTS.get(old_parsed.scheme, None), None)
    if (
        not changed_scheme
        and old_parsed.port in default_port
        and new_parsed.port in default_port
    ):
        return False

    # Standard case: root URI must match
    return changed_port or changed_scheme
