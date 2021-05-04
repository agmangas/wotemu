#!/usr/bin/env bash

set -e
set -x

VERSION_DOCKER=${VERSION_DOCKER:-20.10.6}
VERSION_COMPOSE=${VERSION_COMPOSE:-1.29.1}

apt-get update -y
apt-get install -y curl
curl -fsSL https://get.docker.com -o get-docker.sh
export VERSION=${VERSION_DOCKER}
sh get-docker.sh
usermod -aG docker vagrant
curl -L https://github.com/docker/compose/releases/download/${VERSION_COMPOSE}/docker-compose-`uname -s`-`uname -m` -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
docker-compose --version