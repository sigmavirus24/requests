#   __
#  /__)  _  _     _   _ _/   _
# / (   (- (/ (/ (- _)  /  _)
#          /
"""
Requests HTTP Library
~~~~~~~~~~~~~~~~~~~~~

Requests is an HTTP library, written in Python, for human beings.
Basic GET usage:

   >>> import requests
   >>> r = requests.get('https://www.python.org')
   >>> r.status_code
   200
   >>> b'Python is a programming language' in r.content
   True

... or POST:

   >>> payload = dict(key1='value1', key2='value2')
   >>> r = requests.post('https://httpbin.org/post', data=payload)
   >>> print(r.text)
   {
     ...
     "form": {
       "key1": "value1",
       "key2": "value2"
     },
     ...
   }

The other HTTP methods are supported - see :mod:`requests.api`. Full documentation
is at <https://requests.readthedocs.io>.

:copyright: (c) 2017 by Kenneth Reitz.
:license: Apache 2.0, see LICENSE for more details.
"""
import logging
import warnings

import urllib3.exceptions

from . import utils  # noqa: F401
from .__version__ import __author__  # noqa: F401
from .__version__ import __author_email__  # noqa: F401
from .__version__ import __build__  # noqa: F401
from .__version__ import __cake__  # noqa: F401
from .__version__ import __copyright__  # noqa: F401
from .__version__ import __description__  # noqa: F401
from .__version__ import __license__  # noqa: F401
from .__version__ import __title__  # noqa: F401
from .__version__ import __url__  # noqa: F401
from .__version__ import __version__  # noqa: F401
from .api import delete
from .api import get
from .api import head
from .api import options
from .api import patch
from .api import post
from .api import put
from .api import request
from .exceptions import ConnectionError  # noqa: F401
from .exceptions import ConnectTimeout  # noqa: F401
from .exceptions import FileModeWarning
from .exceptions import HTTPError  # noqa: F401
from .exceptions import ReadTimeout  # noqa: F401
from .exceptions import RequestException  # noqa: F401
from .exceptions import RequestsDependencyWarning
from .exceptions import Timeout  # noqa: F401
from .exceptions import TooManyRedirects  # noqa: F401
from .exceptions import URLRequired  # noqa: F401
from .models import PreparedRequest
from .models import Request
from .models import Response
from .sessions import Session
from .sessions import session
from .status_codes import codes

__all__ = (
    "Request",
    "Response",
    "PreparedRequest",
    "request",
    "get",
    "head",
    "post",
    "patch",
    "put",
    "delete",
    "options",
    "session",
    "Session",
    "codes",
)


def check_compatibility(urllib3_version):
    urllib3_version = urllib3_version.split(".")
    assert urllib3_version != [
        "dev"
    ]  # Verify urllib3 isn't installed from git.

    # Sometimes, urllib3 only reports its version as 16.1.
    if len(urllib3_version) == 2:
        urllib3_version.append("0")

    # Check urllib3 for compatibility.
    major, minor, patch = urllib3_version  # noqa: F811
    major, minor, patch = int(major), int(minor), int(patch)
    # urllib3 >= 1.21.1, <= 1.26
    assert major == 1
    assert minor >= 21
    assert minor <= 26


# Check imported dependencies for compatibility.
try:
    check_compatibility(urllib3.__version__)
except (AssertionError, ValueError):
    warnings.warn(
        f"urllib3 ({urllib3.__version__}) doesn't match a supported version!",
        RequestsDependencyWarning,
    )

# Set default logging handler to avoid "No handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())

# Turn off urllib3's DependencyWarning
warnings.simplefilter("ignore", urllib3.exceptions.DependencyWarning)
# FileModeWarnings go off per the default.
warnings.simplefilter("default", FileModeWarning, append=True)
