#!/usr/bin/env bash

# Patch docker and dockerd to the latest master version to enable privileged support on stacks
# https://github.com/moby/moby/issues/25885#issuecomment-557790402

set -e

echo "Stopping Docker service"

/etc/init.d/docker stop

cd /usr/bin

echo "Patching Docker to enable privileged support on stacks"

mv docker docker.bak
mv dockerd dockerd.bak
mv docker-init docker-init.bak
mv docker-proxy docker-proxy.bak

wget --quiet -O docker https://github.com/olljanat/cli/releases/download/beta1/docker
wget --quiet -O dockerd https://master.dockerproject.org/linux/x86_64/dockerd
wget --quiet -O docker-init https://master.dockerproject.org/linux/x86_64/docker-init
wget --quiet -O docker-proxy https://master.dockerproject.org/linux/x86_64/docker-proxy

chmod 755 docker dockerd docker-init docker-proxy

echo "Starting Docker service"

/etc/init.d/docker start