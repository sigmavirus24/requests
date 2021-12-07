"""
requests.compat
~~~~~~~~~~~~~~~

This module handles import compatibility issues between Python 2 and
Python 3.
"""

try:
    import chardet
except ImportError:
    import charset_normalizer as chardet
