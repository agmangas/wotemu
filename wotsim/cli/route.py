import logging
import pprint
import socket
import subprocess

import click
import docker
import netaddr
import netifaces
import wotsim.constants

_PATH_IPROUTE2_RT_TABLES = "/etc/iproute2/rt_tables"

_logger = logging.getLogger(__name__)
_rtindex = None


def _ping_docker(docker_url):
    docker_client = docker.DockerClient(base_url=docker_url)
    docker_client.ping()


def _get_current_container_id():
    res = subprocess.run(
        "head -1 /proc/self/cgroup | cut -d/ -f3",
        shell=True, check=True, capture_output=True)

    cid = res.stdout.strip().decode()

    _logger.debug("Current container ID: %s", cid)

    return cid


def _get_current_task(docker_url):
    docker_api_client = docker.APIClient(base_url=docker_url)

    cid = _get_current_container_id()

    task = next((
        task for task in docker_api_client.tasks()
        if task.get("Status", {}).get("ContainerStatus", {}).get("ContainerID", None) == cid), None)

    if task is None:
        raise Exception("Could not find task for container: {}".format(cid))

    _logger.debug("Current task:\n%s", pprint.pformat(task))

    return task


def _get_current_wotsim_networks(docker_url):
    docker_api_client = docker.APIClient(base_url=docker_url)

    task = _get_current_task(docker_url=docker_url)

    network_ids = [
        net["Network"]["ID"]
        for net in task["NetworksAttachments"]
    ]

    networks = {
        net_id: docker_api_client.inspect_network(net_id)
        for net_id in network_ids
    }

    networks = {
        net_id: net_info for net_id, net_info in networks.items()
        if net_info.get("Labels", {}).get(wotsim.constants.LABEL_WOTSIM_NETWORK, None) is not None
    }

    _logger.debug("Simulator networks:\n%s", pprint.pformat(networks))

    return list(networks.keys())


def _get_network_gw_task(docker_url, network_id):
    docker_api_client = docker.APIClient(base_url=docker_url)

    network_info = docker_api_client.inspect_network(network_id, verbose=True)

    service_infos = {
        net_name: info
        for net_name, info in network_info["Services"].items()
        if len(net_name) > 0
    }

    _logger.debug(
        "Network %s services:\n%s", network_id,
        pprint.pformat(list(service_infos.keys())))

    task_infos = {
        task_info["Name"]: task_info
        for net_name, serv_info in service_infos.items()
        for task_info in serv_info["Tasks"]
    }

    _logger.debug(
        "Network %s tasks:\n%s", network_id,
        pprint.pformat(list(task_infos.keys())))

    task_labels = {
        task_name: docker_api_client.inspect_task(
            task_name)["Spec"]["ContainerSpec"]["Labels"]
        for task_name in task_infos.keys()
    }

    return next(
        task_infos[task_name]
        for task_name, labels in task_labels.items()
        if labels.get(wotsim.constants.LABEL_WOTSIM_GATEWAY, None) is not None)


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
        _logger.info("# %s", cmd)
        ret = subprocess.run(cmd, shell=True, check=True)
        _logger.info("%s", ret)


def update_routing(docker_url, port_http, port_coap, port_ws, rtable_name, rtable_mark, apply):
    _ping_docker(docker_url=docker_url)
    _raise_if_rtable_exists(rtable_name=rtable_name)

    network_ids = _get_current_wotsim_networks(docker_url=docker_url)

    gw_tasks = {
        net_id: _get_network_gw_task(docker_url=docker_url, network_id=net_id)
        for net_id in network_ids
    }

    _logger.debug(
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
        _logger.warning("Dry run: Skipping configuration update")
        return

    for cmds in gw_commands.values():
        _run_commands(cmds)
