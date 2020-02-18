FROM ubuntu:19.04

ENV PATH_WOTPY /root/wot-py
ENV PATH_WOTSIM /root/wotsim
ENV PORT_CATALOGUE 9090
ENV PORT_HTTP 80
ENV PORT_WS 81
ENV PORT_COAP 5683
ENV PORT_MQTT 1883

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
    git \
    mosquitto

RUN pip3 install wotpy
RUN git clone https://github.com/agmangas/wot-py.git ${PATH_WOTPY}
RUN pip3 install -r ${PATH_WOTPY}/examples/benchmark/requirements.txt

COPY . ${PATH_WOTSIM}

RUN ${PATH_WOTSIM}/scripts/install-pumba.sh

RUN pip3 install ${PATH_WOTSIM}

EXPOSE ${PORT_CATALOGUE}
EXPOSE ${PORT_HTTP}
EXPOSE ${PORT_WS}
EXPOSE ${PORT_COAP}/tcp
EXPOSE ${PORT_COAP}/udp
EXPOSE ${PORT_MQTT}

ENTRYPOINT ["/root/wotsim/entrypoint.sh"]