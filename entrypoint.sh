#!/usr/bin/env bash

set -e
set -x

: "${WAIT_GATEWAYS:?}"

print_section () {
    echo
    echo "###" $1
    echo
}

wait_init () {
    print_section "Waiting for base services"
    wotemu wait --waiter-base
}

wait_gateways () {
    print_section "Waiting for gateways (${WAIT_GATEWAYS}s)"
    sleep ${WAIT_GATEWAYS}
}

wait_brokers () {
    print_section "Waiting for MQTT brokers"
    wotemu wait --waiter-mqtt
}

update_routing () {
    print_section "Updating routing configuration"
    wotemu route --apply
}

update_cpu_limits() {
    if [ -z "$TARGET_CPU_SPEED" ]
    then
        print_section "Ignoring CPU limits due to undefined speed variable"
        return
    fi
    
    print_section "Updating CPU limits to match speed: ${TARGET_CPU_SPEED}"
    wotemu limits --speed ${TARGET_CPU_SPEED}
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
        update_cpu_limits
        run_app "${@:2}"
    ;;
    broker)
        wait_init
        wait_gateways
        update_routing
        update_cpu_limits
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
