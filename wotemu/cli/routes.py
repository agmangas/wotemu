import logging
import pprint
import re
import socket
import subprocess

import click
import docker
import netaddr
import netifaces

import wotemu.config
import wotemu.enums
from wotemu.utils import (get_current_task, get_network_gateway_task,
                          get_output_iface_for_task, get_task_networks,
                          ping_docker)

_PATH_IPROUTE2_RT_TABLES = "/etc/iproute2/rt_tables"

_logger = logging.getLogger(__name__)
_rtindex = None


def _next_rtable_index():
    def exists_rtable(rtidx):
        cmd = "grep -q '{}\\s.*' /etc/iproute2/rt_tables".format(rtidx)
        return subprocess.run(cmd, shell=True).returncode == 0

    global _rtindex

    if _rtindex is None:
        _rtindex = next(
            idx for idx in reversed(range(10, 201))
            if not exists_rtable(idx))

    return _rtindex


def _rtable_exists(rtable_name):
    route_show_res = subprocess.run(
        "ip route show table {}".format(rtable_name),
        shell=True,
        check=False,
        capture_output=True)

    return route_show_res.returncode == 0


def _build_routing_commands(gw_task, ports_tcp, ports_udp, rtable_name, rtable_mark):
    cmds = []

    rtindex = _next_rtable_index()

    cmds.append("grep -Fxq \"{idx} {name}\" {path} || echo \"{idx} {name}\" >> {path}".format(
        idx=rtindex,
        name=rtable_name,
        path=_PATH_IPROUTE2_RT_TABLES))

    ifname, ifaddr = get_output_iface_for_task(gw_task)

    ifcidr = netaddr.IPNetwork("{}/{}".format(
        ifaddr["addr"], ifaddr["netmask"])).cidr

    cmds.append("ip route add {} via {} onlink dev {} proto kernel src {} table {}".format(
        ifcidr,
        gw_task["EndpointIP"],
        ifname,
        ifaddr["addr"],
        rtable_name))

    cmds.append("ip rule add fwmark {} table {}".format(
        hex(rtable_mark),
        rtable_name))

    def build_iptables_rules(proto, dport):
        return [
            "iptables -A OUTPUT -t mangle -o {} -p {} --dport {} -j MARK --set-mark {}".format(
                ifname,
                proto,
                dport,
                rtable_mark),
            "iptables -A OUTPUT -t mangle -o {} -p {} --sport {} -j MARK --set-mark {}".format(
                ifname,
                proto,
                dport,
                rtable_mark)
        ]

    cmds += [
        rule
        for port in ports_tcp
        for rule in build_iptables_rules("tcp", port)
    ]

    cmds += [
        rule
        for port in ports_udp
        for rule in build_iptables_rules("udp", port)
    ]

    return cmds


def _run_commands(cmds):
    for cmd in cmds:
        _logger.info("# %s", cmd)
        ret = subprocess.run(cmd, shell=True, check=True)
        _logger.info("%s", ret)


def update_routing(conf, rtable_name, rtable_mark, apply):
    ports_tcp = [
        conf.port_http,
        conf.port_ws,
        conf.port_mqtt,
        conf.port_coap
    ]

    ports_udp = [conf.port_coap]

    _logger.debug("TCP ports: %s", ports_tcp)
    _logger.debug("UDP ports: %s", ports_udp)

    docker_url = conf.docker_proxy_url
    ping_docker(docker_url=docker_url)

    if _rtable_exists(rtable_name=rtable_name):
        _logger.info("Table '%s' exists: Skip configuration", rtable_name)
        return

    task = get_current_task(docker_url=docker_url)
    network_ids = get_task_networks(docker_url=docker_url, task=task)

    gw_tasks = {
        net_id: get_network_gateway_task(
            docker_url=docker_url,
            network_id=net_id)
        for net_id in network_ids
    }

    _logger.debug(
        "Gateway tasks:\n%s",
        pprint.pformat(gw_tasks))

    gw_commands = {
        net_id: _build_routing_commands(
            gw_task=task,
            ports_tcp=ports_tcp,
            ports_udp=ports_udp,
            rtable_name=rtable_name,
            rtable_mark=rtable_mark)
        for net_id, task in gw_tasks.items()
    }

    _logger.info(
        "Routing commands:\n%s",
        pprint.pformat(gw_commands))

    if not apply:
        _logger.warning("Dry run: Skip configuration update")
        return

    for cmds in gw_commands.values():
        _run_commands(cmds)
