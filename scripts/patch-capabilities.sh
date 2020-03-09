#!/usr/bin/env bash

set -e
set -u

echo "## Adding runc proxy to enable privileged support"

cp /vagrant/scripts/runc-proxy /root/runc-proxy
cp /etc/docker/daemon.json /etc/docker/daemon.json.bak || true

if [ -f /etc/docker/daemon.json ];
    then cat /etc/docker/daemon.json
    else echo "{}"
fi \
    | jq '.+ {"runtimes": {"runc-proxy": {"path": "/root/runc-proxy"}}, "default-runtime": "runc-proxy"}' \
    | tee /etc/docker/daemon.json.new

mv /etc/docker/daemon.json.new /etc/docker/daemon.json

echo "## Restarting Docker service"

systemctl daemon-reload
systemctl restart docker
