#!/usr/bin/env bash

set -e

apt-get update
apt-get install -y curl
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
usermod -aG docker vagrant
curl -L https://github.com/docker/compose/releases/download/1.25.1/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose