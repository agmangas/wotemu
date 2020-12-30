# WoTemu

[![Docker Cloud Build](https://img.shields.io/docker/cloud/build/agmangas/wotemu)](https://hub.docker.com/r/agmangas/wotemu) &nbsp; [![Build Status](https://travis-ci.com/agmangas/wotemu.svg?branch=master)](https://travis-ci.com/agmangas/wotemu)

An emulator for [Web of Things](https://www.w3.org/WoT/) applications programmed on top of [WoTPy](https://pypi.org/project/wotpy/) that is based on [Docker Swarm Mode](https://docs.docker.com/engine/swarm/).

## Usage

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

An HTML report containing useful insights into the behaviour of the emulation stack may be generated with the following command. There is a [publicly available demo here](https://agmangas.github.io/demo-wotemu-report/).

```
wotemu report --out /report/ --stack simple
```