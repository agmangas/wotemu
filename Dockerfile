FROM ubuntu:19.04

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

COPY . /root/wotsim
RUN pip3 install -U /root/wotsim/

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