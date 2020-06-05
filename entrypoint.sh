#!/usr/bin/env bash

set -e
set -x

: "${WAIT_INIT:?}"
: "${WAIT_GATEWAYS:?}"
: "${WAIT_BROKERS:?}"

print_section () {
    echo
    echo "###" $1
    echo
}

wait_init () {
    print_section "Waiting for initialization (${WAIT_INIT}s)"
    sleep ${WAIT_INIT}
}

wait_gateways () {
    print_section "Waiting for gateways (${WAIT_GATEWAYS}s)"
    sleep ${WAIT_GATEWAYS}
}

wait_brokers () {
    print_section "Waiting for brokers (${WAIT_BROKERS}s)"
    sleep ${WAIT_BROKERS}
}

update_routing () {
    print_section "Updating routing configuration"
    wotemu route --apply
}

run_app () {
    exec wotemu app "$@"
}

run_mqtt_broker () {
    port_mqtt=${PORT_MQTT:-1883}
    exec mosquitto -p ${port_mqtt}
}

run_chaos () {
    args=()
    
    for var in "$@"
    do
        args+=(--netem "${var}")
    done
    
    exec wotemu chaos "${args[@]}"
}

case "$1" in
    app)
        wait_init
        wait_gateways
        update_routing
        wait_brokers
        run_app "${@:2}"
    ;;
    broker)
        wait_init
        wait_gateways
        update_routing
        run_mqtt_broker
    ;;
    gateway)
        wait_init
        run_chaos "${@:2}"
    ;;
    *)
        exec "$@"
    ;;
esac
