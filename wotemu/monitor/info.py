import logging
import platform
import socket

import psutil

_logger = logging.getLogger(__name__)


def get_node_info():
    net_addrs = {
        key: [item._asdict() for item in val]
        for key, val in psutil.net_if_addrs().items()
    }

    disks = [
        item._asdict()
        for item in psutil.disk_partitions(all=False)
    ]

    return {
        "cpu_count": psutil.cpu_count(),
        "mem_total": psutil.virtual_memory().total,
        "net": net_addrs,
        "disks": disks,
        "python_version": platform.python_version(),
        "uname": platform.uname()._asdict()
    }
