#!/usr/bin/env bash

set -e

cd /usr/bin
wget --quiet https://github.com/alexei-led/pumba/releases/download/0.6.8/pumba_linux_amd64
mv pumba_linux_amd64 pumba
chmod +x pumba