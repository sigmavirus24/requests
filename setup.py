#!/usr/bin/env python
# Learn more: https://github.com/kennethreitz/setup.py
import os
from codecs import open

from setuptools import setup

here = os.path.abspath(os.path.dirname(__file__))

packages = ["requests"]

requires = [
    'charset_normalizer~=2.0.0; python_version >= "3"',
    'idna>=2.5,<3; python_version < "3"',
    'idna>=2.5,<4; python_version >= "3"',
    "urllib3>=1.21.1,<1.27",
    "certifi>=2017.4.17",
    "attrs>=21.2.0",
]

about = {}
with open(os.path.join(here, "requests", "__version__.py"), "r", "utf-8") as f:
    exec(f.read(), about)

with open("README.md", "r", "utf-8") as f:
    readme = f.read()

setup(
    name=about["__title__"],
    version=about["__version__"],
    description=about["__description__"],
    long_description=readme,
    long_description_content_type="text/markdown",
    author=about["__author__"],
    author_email=about["__author_email__"],
    url=about["__url__"],
    packages=packages,
    package_data={"": ["LICENSE"]},
    package_dir={"requests": "requests"},
    include_package_data=True,
    python_requires=">=3.7",
    install_requires=requires,
    license=about["__license__"],
    zip_safe=False,
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Natural Language :: English",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: Implementation :: CPython",
        "Programming Language :: Python :: Implementation :: PyPy",
    ],
    extras_require={
        "security": [],
        "socks": ["PySocks>=1.5.6, !=1.5.7"],
    },
    project_urls={
        "Documentation": "https://requests.readthedocs.io",
        "Source": "https://github.com/psf/requests",
    },
)
