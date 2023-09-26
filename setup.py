#!/usr/bin/python3
"""Setup
"""
from setuptools import find_packages
from distutils.core import setup

version = "0.1.0"

with open("README.rst") as f:
    long_description = f.read()

setup(
    name="ofxstatement-mastercard-de",
    version=version,
    author="Arne Keller",
    author_email="arne.keller@posteo.de",
    url="https://github.com/FliegendeWurst/ofxstatement-mastercard-de",
    description=("OFXStatement plugin for Mastercard statements (Germany)"),
    long_description=long_description,
    license="GPLv3",
    keywords=["ofx", "banking", "statement"],
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Programming Language :: Python :: 3",
        "Natural Language :: English",
        "Topic :: Office/Business :: Financial :: Accounting",
        "Topic :: Utilities",
        "Environment :: Console",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Intended Audience :: End Users/Desktop",
    ],
    packages=find_packages("src"),
    package_dir={"": "src"},
    namespace_packages=["ofxstatement", "ofxstatement.plugins"],
    entry_points={
        "ofxstatement": ["mastercard-de = ofxstatement.plugins.mastercard_de:MastercardPlugin"]
    },
    install_requires=["ofxstatement"],
    include_package_data=True,
    zip_safe=True,
)
