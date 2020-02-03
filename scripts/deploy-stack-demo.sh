#!/usr/bin/env bash

set -e

docker stack deploy --compose-file /vagrant/docker-compose.yml stackdemo