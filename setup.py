from os import path

import setuptools

from wotemu.__version__ import __version__


def _get_readme():
    curr_dir = path.abspath(path.dirname(__file__))

    with open(path.join(curr_dir, "README.md")) as fh:
        return fh.read()


setuptools.setup(
    name="wotemu",
    version=__version__,
    keywords='wot iot edge emulator',
    author='Andres Garcia Mangas',
    author_email='andres.garcia@fundacionctic.org',
    description="An emulator for Python applications to help in the design of IoT deployments based on the edge computing model",
    long_description=_get_readme(),
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Development Status :: 4 - Beta",
        "Operating System :: POSIX :: Linux"
    ],
    entry_points={
        "console_scripts": [
            "wotemu=wotemu.cli.main:cli"
        ]
    },
    python_requires='>=3.6',
    install_requires=[
        "docker>=4.1.0,<5.0",
        "coloredlogs>=14.0,<15.0",
        "netaddr>=0.7.19,<0.8.0",
        "netifaces>=0.10.9,<0.11.0",
        "Click>=7.0,<8.0",
        "sh>=1.12.14,<2.0",
        "wotpy==0.14.5",
        "aioredis>=1.3,<2.0",
        "tornado>=5.1,<6.0",
        "PyYAML>=5.3,<6.0",
        "inflection>=0.4.0,<0.5.0",
        "numpy>=1.15.0,<2.0",
        "deepmerge>=0.1.0,<0.2.0",
        "pyshark>=0.4.2,<0.5.0",
        "psutil>=5.6.0,<6.0",
        "plotly>=4.11,<5.0",
        "pandas>=1.1,<2.0",
        "lxml>=4.5,<5.0",
        "websockets>=8.0,<9.0"
    ],
    extras_require={
        "dev": [
            "autopep8>=1.5,<2.0",
            "pylint>=2.0,<3.0",
            "rope>=0.16.0,<1.0",
            "pytest>=5.0,<6.0",
            "pytest-asyncio>=0.10.0,<1.0",
            "docker>=4.0,<5.0",
            "html5lib>=1.1,<2.0",
            "bumpversion>=0.5.3,<0.6.0"
        ],
        "apps": [
            "motor>=2.3,<3.0",
            "opencv-python>=4.5,<4.6",
            "face-recognition>=1.3,<1.4"
        ]
    }
)
