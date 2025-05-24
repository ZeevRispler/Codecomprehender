from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="codecomprehender",
    version="1.0.0",
    author="CodeComprehender Team",
    description="An intelligent tool to analyze and annotate Java codebases with meaningful comments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/codecomprehender",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Documentation",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "click>=8.1.0",
        "openai>=1.0.0",
        "javalang>=0.13.0",
        "graphviz>=0.20.0",
        "pyyaml>=6.0",
        "tqdm>=4.65.0",
        "colorama>=0.4.6",
        "python-dotenv>=1.0.0",
    ],
    entry_points={
        "console_scripts": [
            "codecomprehender=codecomprehender.src.main:main",
        ],
    },
)