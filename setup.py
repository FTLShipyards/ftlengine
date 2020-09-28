from setuptools import setup, find_packages
from src import __version__

with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name="ftlengine",
    version=__version__,
    author="Jakob Daugherty",
    author_email="jakob.daugherty@quarkworks.co",
    description="A Docker based development and deployment engine",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Jakob-Daugherty/ftlengine",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
