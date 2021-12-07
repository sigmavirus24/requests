"""
requests._internal_utils
~~~~~~~~~~~~~~

Provides utility functions that are consumed internally by Requests
which depend on extremely few external helpers (such as compat)
"""
from .exceptions import ChunkedEncodingError
from .exceptions import ContentDecodingError


def to_native_string(string: t.AnyStr, encoding: str = "ascii") -> str:
    """Given a string object, regardless of type, returns a representation of
    that string in the native string type, encoding and decoding where
    necessary. This assumes ASCII unless told otherwise.
    """
    if isinstance(string, str):
        out = string
    else:
        out = string.decode(encoding)

    return out


def unicode_is_ascii(u_string):
    """Determine if unicode string only contains ASCII characters.

    :param str u_string: unicode string to check. Must be unicode
        and not Python 2 `str`.
    :rtype: bool
    """
    assert isinstance(u_string, str)
    try:
        u_string.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def consume_response(response):
    """Ensure the body is consumed so a socket can be released."""
    try:
        response.content  # Consume socket so it can be released
    except (ChunkedEncodingError, ContentDecodingError, RuntimeError):
        response.raw.read(decode_content=False)

    response.close()
