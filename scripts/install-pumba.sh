#!/usr/bin/env bash

set -e
set -x

VERSION_PUMBA=${VERSION_PUMBA:-0.7.7}

cd /usr/bin
wget --quiet https://github.com/alexei-led/pumba/releases/download/${VERSION_PUMBA}/pumba_linux_amd64
mv pumba_linux_amd64 pumba
chmod +x pumba