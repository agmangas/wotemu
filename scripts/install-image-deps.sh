#!/usr/bin/env bash

apt-get update -y

DEBIAN_FRONTEND=noninteractive apt-get install -y \
python3 \
python3-pip \
iproute2 \
iptables \
tshark \
wget \
curl \
mosquitto \
dnsutils \
cgroup-tools