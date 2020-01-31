#!/usr/bin/env bash

set -e

docker service create --replicas 2 --name helloworld -p 9999:80 nginxdemos/hello:plain-text