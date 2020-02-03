import logging
import pprint
import socket
import subprocess

import click
import docker as dockersdk
import netaddr
import netifaces

_PATH_IPROUTE2_RT_TABLES = "/etc/iproute2/rt_tables"

_logger = logging.getLogger(__name__)
_rtindex = None


def _get_docker():
    return dockersdk.from_env()


def _get_docker_api():
    return dockersdk.APIClient()


def _get_current_container():
    hostname = socket.gethostname()

    _logger.debug("Current hostname: %s", hostname)

    docker = _get_docker()
    docker_api = _get_docker_api()

    hostnames = {
        cont.id: docker_api.inspect_container(cont.id)["Config"]["Hostname"]
        for cont in docker.containers.list()
    }

    _logger.debug("Hostnames map:\n%s", pprint.pformat(hostnames))

    current_id = next(
        (cid for cid, name in hostnames.items() if name == hostname), None)

    if not current_id:
        raise Exception(
            "Couldn't find current container (hostname: {})".format(hostname))

    _logger.debug("Found: %s", current_id)

    return docker.containers.get(current_id)


def _get_wotsim_networks(container, label_net):
    docker = _get_docker()
    docker_api = _get_docker_api()
    config = docker_api.inspect_container(container.id)

    networks = {
        netid: docker_api.inspect_network(netid)
        for netid, attrs in config["NetworkSettings"]["Networks"].items()
    }

    networks = {
        netid: info for netid, info in networks.items()
        if info.get("Labels", {}).get(label_net, None) is not None
    }

    _logger.debug("Simulator networks:\n%s", pprint.pformat(networks))

    return [docker.networks.get(netid) for netid in networks.keys()]


def _get_network_gw_task(network, label_gateway):
    docker_api = _get_docker_api()

    network_info = docker_api.inspect_network(network.id, verbose=True)

    service_infos = {
        net_name: info
        for net_name, info in network_info["Services"].items()
        if len(net_name) > 0
    }

    _logger.debug(
        "Network %s services:\n%s", network.name,
        pprint.pformat(list(service_infos.keys())))

    task_infos = {
        task_info["Name"]: task_info
        for net_name, serv_info in service_infos.items()
        for task_info in serv_info["Tasks"]
    }

    _logger.debug(
        "Network %s tasks:\n%s", network.name,
        pprint.pformat(list(task_infos.keys())))

    task_labels = {
        task_name: docker_api.inspect_task(
            task_name)["Spec"]["ContainerSpec"]["Labels"]
        for task_name in task_infos.keys()
    }

    return next(
        task_infos[task_name]
        for task_name, labels in task_labels.items()
        if labels.get(label_gateway, None) is not None)


def _get_task_netiface(task):
    task_name = task["Name"]
    task_addr = netaddr.IPAddress(task["EndpointIP"])

    iface_addrs = {
        name: netifaces.ifaddresses(name).get(netifaces.AF_INET)
        for name in netifaces.interfaces()
        if netifaces.ifaddresses(name).get(netifaces.AF_INET)
    }

    _logger.debug(
        "Current container interfaces:\n%s",
        pprint.pformat(iface_addrs))

    ret = next(
        (iface_name, addr)
        for iface_name, iface_addrs in iface_addrs.items()
        for addr in iface_addrs
        if task_addr in netaddr.IPNetwork("{}/{}".format(addr["addr"], addr["netmask"])))

    _logger.debug(
        "Output interface for %s:\n%s",
        task_name, pprint.pformat(ret))

    return ret


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


def _raise_if_rtable_exists(rtable_name):
    route_show_res = subprocess.run(
        "ip route show table {}".format(rtable_name),
        shell=True,
        check=False,
        capture_output=True)

    if route_show_res.returncode == 0:
        raise Exception(
            "Cannot update routing configuration - "
            "Table {} is already defined".format(rtable_name))


def _build_routing_commands(gw_task, ports_tcp, ports_udp, rtable_name, rtable_mark):
    cmds = []

    rtindex = _next_rtable_index()

    cmds.append("grep -Fxq \"{idx} {name}\" {path} || echo \"{idx} {name}\" >> {path}".format(
        idx=rtindex,
        name=rtable_name,
        path=_PATH_IPROUTE2_RT_TABLES))

    ifname, ifaddr = _get_task_netiface(gw_task)

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

    def iptable_entry(proto, dport):
        return "iptables -A OUTPUT -t mangle -o {} -p {} --dport {} -j MARK --set-mark {}".format(
            ifname,
            proto,
            dport,
            rtable_mark)

    cmds += [iptable_entry("tcp", port) for port in ports_tcp]
    cmds += [iptable_entry("udp", port) for port in ports_udp]

    return cmds


def _run_commands(cmds):
    for cmd in cmds:
        _logger.debug("# %s", cmd)
        ret = subprocess.run(cmd, shell=True, check=True)
        _logger.debug("%s", ret)


def update_routing(label_net, label_gateway, port_http, port_coap, port_ws, rtable_name, rtable_mark, apply):
    _raise_if_rtable_exists(rtable_name=rtable_name)

    container = _get_current_container()
    networks = _get_wotsim_networks(container, label_net)

    _logger.info(
        "Simulator networks:\n%s",
        pprint.pformat([(net.id, net.name) for net in networks]))

    gw_tasks = {
        net.id: _get_network_gw_task(network=net, label_gateway=label_gateway)
        for net in networks
    }

    _logger.info(
        "Gateway tasks:\n%s",
        pprint.pformat(gw_tasks))

    ports_tcp = [port_http, port_coap, port_ws]
    ports_udp = [port_coap]

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
        _logger.info("Dry run: Skipping configuration update")
        return

    for cmds in gw_commands.values():
        _run_commands(cmds)
