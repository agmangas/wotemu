import setuptools

from wotsim.__version__ import __version__

setuptools.setup(
    name="wotsim",
    version=__version__,
    keywords='wot iot fog w3c simulator',
    author='Andres Garcia Mangas',
    author_email='andres.garcia@fundacionctic.org',
    description="Real time fog layer simulator based on the W3C Web of Things",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License"
    ],
    entry_points={
        "console_scripts": [
            "wotsim=wotsim.cli.main:cli"
        ]
    },
    python_requires='>=3.6',
    install_requires=[
        "docker>=4.1.0,<5.0",
        "coloredlogs>=14.0,<15.0",
        "netaddr>=0.7.19,<0.8.0",
        "netifaces>=0.10.9,<0.11.0",
        "Click>=7.0,<8.0",
        "sh>=1.12.14,<2.0"
    ],
    extras_require={
        "dev": [
            "autopep8",
            "pylint",
            "rope"
        ]
    }
)
