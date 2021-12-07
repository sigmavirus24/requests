import io as StringIO

try:
    from cStringIO import StringIO as cStringIO
except ImportError:
    cStringIO = None


def u(s):
    if isinstance(s, str):
        return s
    return s.decode("unicode-escape")
