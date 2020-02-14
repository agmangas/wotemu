#!/usr/bin/env bash

set -e

: "${PATH_WOTPY:?}"
: "${PATH_WOTSIM:?}"
: "${PORT_CATALOGUE:?}"
: "${PORT_HTTP:?}"
: "${PORT_WS:?}"
: "${PORT_COAP:?}"

print_section () {
    echo
    echo "###" $1
    echo
}

wait_gateways () {
    print_section "Waiting for gateways (10s)"
    sleep 10
}

update_routing () {
    print_section "Updating routing configuration"

    wotsim route \
    --port-http ${PORT_HTTP} \
    --port-ws ${PORT_WS} \
    --port-coap ${PORT_COAP} \
    --apply
}

run_benchmark_server () {
    print_section "Running benchmark server"

    python3 ${PATH_WOTPY}/examples/benchmark/server.py \
    --mqtt-broker= \
    --port-catalogue=${PORT_CATALOGUE} \
    --port-http=${PORT_HTTP} \
    --port-ws=${PORT_WS} \
    --port-coap=${PORT_COAP} \
    --hostname=$(hostname)
}

idle () {
    print_section "Idling indefinitely"
    sleep infinity
}

case "$1" in
    node)
        wait_gateways
        update_routing
        run_benchmark_server
    ;;
    gateway)
        idle
    ;;
    *)
        exec "$@"
    ;;
esac
