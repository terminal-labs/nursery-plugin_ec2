import ast
import io
import re
from pathlib import Path

from setuptools import find_packages
from setuptools import setup

with io.open("README.md", "rt", encoding="utf8") as f:
    readme = f.read()

_description_re = re.compile(r"description\s+=\s+(?P<description>.*)")

with open(Path("nursery_ec2") / "plugin.py", "rb") as f:
    description = str(
        ast.literal_eval(_description_re.search(f.read().decode("utf-8")).group(1))
    )


install_requires = ["beautifulsoup4", "lxml", "Nursery"]
dev_require = ["black", "ipdb", "pre-commit"]

setup(
    author="Terminal Labs",
    author_email="solutions@terminallabs.com",
    description=description,
    extras_require={"dev": dev_require},
    install_requires=install_requires,
    keywords="nursery plugin virtualbox ec2",
    license="BSD-3-Clause",
    long_description=readme,
    long_description_content_type="text/markdown",
    name="nursery-ec2",
    packages=find_packages(),
    url="https://github.com/terminal-labs/nursery-ec2",
    version="0.0.1",
    classifiers=[
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.8",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    entry_points={"nursery.plugins": ["nursery-ec2 = nursery_ec2.plugin:ec2Target"]},
)
