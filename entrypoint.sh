#!/usr/bin/env bash

set -e
set -x

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
    wotsim route --apply
}

run_app () {
    exec wotsim app "$@"
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
    
    exec wotsim chaos "${args[@]}"
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
