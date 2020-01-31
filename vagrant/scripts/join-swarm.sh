#!/usr/bin/env bash

set -e

VAGRANT_USER="vagrant"
VAGRANT_PASS="vagrant"
SWARM_CMD="docker swarm join-token worker | grep \"docker\" | xargs"
SSH_CMD="sshpass -p ${VAGRANT_PASS} ssh -o StrictHostKeyChecking=no ${VAGRANT_USER}@${IP_MANAGER1} ${SWARM_CMD}"
echo "## Fetching join: ${SSH_CMD}"
JOIN_CMD=$(${SSH_CMD})
echo "## Joining: ${JOIN_CMD}"
${JOIN_CMD}