#!/usr/bin/env bash

set -e
set -x

: "${PORT_CATALOGUE:?}"
: "${PORT_HTTP:?}"
: "${PORT_WS:?}"
: "${PORT_COAP:?}"
: "${PORT_MQTT:?}"
: "${REDIS_URL:?}"

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
    --tcp ${PORT_HTTP} \
    --tcp ${PORT_WS} \
    --tcp ${PORT_COAP} \
    --tcp ${PORT_MQTT} \
    --udp ${PORT_COAP} \
    --apply
}

run_app () {
    exec wotsim app "$@"
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
    app)
        wait_gateways
        update_routing
        wait_brokers
        run_app "${@:2}"
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
