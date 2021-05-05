#!/usr/bin/env bash

set -e
set -x

REGEX_PKGS='"(.+)(>=?)(.+),(<=?)(.+)"'
REGEX_BASE='install_requires=[^\]]+'
REGEX_APPS='"apps":[^\]]+'

REQUIREMENTS_BASE=$(grep -ozP ${REGEX_BASE} setup.py | grep -aoP ${REGEX_PKGS})
REQUIREMENTS_APPS=$(grep -ozP ${REGEX_APPS} setup.py | grep -aoP ${REGEX_PKGS})

echo ${REQUIREMENTS_BASE} | xargs -n1 pip3 install -U
echo ${REQUIREMENTS_APPS} | xargs -n1 pip3 install -U
