#!/usr/bin/env bash

set -e

: "${PATH_WOTPY:?}"
: "${PATH_WOTSIM:?}"
: "${PORT_CATALOGUE:?}"
: "${PORT_HTTP:?}"
: "${PORT_WS:?}"
: "${PORT_COAP:?}"
: "${PORT_MQTT:?}"

print_section () {
    echo
    echo "###" $1
    echo
}

wait_gateways () {
    print_section "Waiting for gateways (20s)"
    sleep 20
}

wait_brokers () {
    print_section "Waiting for brokers (10s)"
    sleep 10
}

update_routing () {
    print_section "Updating routing configuration"
    
    wotsim route \
    --port-http ${PORT_HTTP} \
    --port-ws ${PORT_WS} \
    --port-coap ${PORT_COAP} \
    --port-mqtt ${PORT_MQTT} \
    --apply
}

run_benchmark_server () {
    print_section "Running benchmark server"
    
    exec python3 ${PATH_WOTPY}/examples/benchmark/server.py \
    --mqtt-broker=${MQTT_BROKER} \
    --port-catalogue=${PORT_CATALOGUE} \
    --port-http=${PORT_HTTP} \
    --port-ws=${PORT_WS} \
    --port-coap=${PORT_COAP} \
    --hostname=$(hostname)
}

run_mqtt_broker () {
    exec mosquitto -p ${PORT_MQTT}
}

run_chaos () {
    args=()
    
    for var in "$@"
    do
        args+=(--netem "${var}")
    done
    
    exec wotsim chaos "${args[@]}"
}

idle () {
    print_section "Idling indefinitely"
    exec sleep infinity
}

case "$1" in
    node)
        wait_gateways
        update_routing
        wait_brokers
        run_benchmark_server
    ;;
    broker)
        wait_gateways
        update_routing
        run_mqtt_broker
    ;;
    gateway)
        run_chaos "${@:2}"
    ;;
    *)
        exec "$@"
    ;;
esac
