# WoTemu

[![Docker Cloud Build](https://img.shields.io/docker/cloud/build/agmangas/wotemu)](https://hub.docker.com/r/agmangas/wotemu) &nbsp; [![Build Status](https://travis-ci.com/agmangas/wotemu.svg?branch=master)](https://travis-ci.com/agmangas/wotemu)

An emulator for Python applications to help in the design of **IoT deployments** based on the **edge computing** model. It is focused on the [Web of Things](https://www.w3.org/WoT/) paradigm by offering extended support for applications programmed with [WoTPy](https://pypi.org/project/wotpy/).

As an emulator, WoTemu demands significantly higher computation resources than other design tools in the same domain, it is, however, able to run the real production code, which simplifies the design process and provides more meaningful insights into the architecture.

The main output of an emulation experiment is an HTML report describing the observed behaviour of the stack. Please see a [demo report here](https://agmangas.github.io/demo-wotemu-report/).

## Design

WoTemu leverages [Docker Swarm Mode](https://docs.docker.com/engine/swarm/) to offer simple horizontal scaling across heterogeneous nodes; this enables the emulation of scenarios with hundreds of actors.

The following image shows a high-level view of a simple emulation stack. This serves to illustrate the main design choices behind WoTemu.

![Design diagram](diagram.png "Design diagram")

* All communications for the supported protocols (HTTP, CoAP, Websockets and MQTT) go through the network **gateways**; these use NetEm to shape the traffic and emulate real network conditions. This redirection is based on iptables and is invisible to the application.
* All **nodes** report their metrics (e.g. system resources, packets, interactions) to a central Redis store in a periodic fashion. This will be later used to build the final HTML report.
* A **Docker API proxy** instance is always deployed in a _manager_ node to enable **nodes** to access stack metadata (e.g. container IDs of other nodes in the same network).

## Quickstart

Write a Python file that exposes a `topology` function that takes no arguments and returns an instance of `wotemu.topology.models.Topology`. The Compose file that describes the emulation stack can be generated with the following command:

```
wotemu compose --path /examples/simple.py
```

The emulation stack is deployed using the regular Docker interface:

```
docker stack deploy -c /examples/simple.py simple
```

The emulation stack may be stopped when you consider that enough time has passed to gather a significant amount of data:

```
wotemu stop --compose-file /examples/simple.yml --stack simple
```

An HTML report containing useful insights into the behaviour of the emulation stack may be generated with the following command.

```
wotemu report --out /report/ --stack simple
```