import io as StringIO

try:
    from cStringIO import StringIO as cStringIO
except ImportError:
    cStringIO = None


def u(s):
    return s.decode("unicode-escape")
