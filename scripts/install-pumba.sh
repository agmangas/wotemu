#!/usr/bin/env bash

set -e

cd /usr/bin
wget --quiet https://github.com/alexei-led/pumba/releases/download/0.7.2/pumba_linux_amd64
mv pumba_linux_amd64 pumba
chmod +x pumba