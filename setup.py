from setuptools import setup, find_packages

setup(
    name="termstory",
    version="0.2.0",
    author="TermStory Contributors",
    description="Local shell history parser, session grouper, and daily summary display",
    long_description=open("README.md").read() if open("README.md") else "",
    long_description_content_type="text/markdown",
    url="https://github.com/atuinsh/termstory",
    packages=find_packages(),
    install_requires=[
        "typer>=0.9.0",
        "python-dateutil>=2.8.2",
    ],
    entry_points={
        "console_scripts": [
            "termstory=termstory.cli:app",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",
)
