FROM ubuntu:19.04

ENV DOCKER_CLI_VERSION 19.03.5

RUN apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential \
    python3 \
    python3-pip \
    iproute2 \
    inetutils-ping \
    iptables \
    tshark \
    wget \
    curl \
    tcpdump \
    git

WORKDIR /root

RUN git clone https://github.com/agmangas/wot-py.git
RUN pip3 install wotpy
RUN pip3 install -r ./wot-py/examples/benchmark/requirements.txt

RUN wget -O docker.tgz https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_CLI_VERSION}.tgz
RUN tar xvfz docker.tgz
RUN mv ./docker/docker /usr/bin/docker
RUN rm -fr docker docker.tgz

EXPOSE 9090
EXPOSE 9191
EXPOSE 9292
EXPOSE 9393/tcp
EXPOSE 9393/udp

CMD python3 /root/wot-py/examples/benchmark/server.py \
    --mqtt-broker= \
    --port-catalogue=9090 \
    --port-http=9191 \
    --port-ws=9292 \
    --port-coap=9393 \
    --hostname=$(hostname)