#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="codecomprehender",
    version="0.1.0",
    description="Add AI-generated comments to Java code",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Your Name",
    url="https://github.com/yourusername/codecomprehender",

    packages=find_packages(where="src"),
    package_dir={"": "src"},

    python_requires=">=3.8",
    install_requires=[
        "click>=8.0.0",
        "openai>=1.0.0",
        "javalang>=0.13.0",
        "python-dotenv>=0.19.0",
        "graphviz>=0.20.0",
        "tqdm>=4.60.0",
    ],

    entry_points={
        "console_scripts": [
            "codecomprehender=codecomprehender.main:main",
        ],
    },

    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)