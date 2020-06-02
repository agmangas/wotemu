FROM ubuntu:19.10

ENV PATH_WOTSIM /root/wotsim
ENV WAIT_INIT 20
ENV WAIT_GATEWAYS 20
ENV WAIT_BROKERS 20

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

COPY . ${PATH_WOTSIM}
RUN ${PATH_WOTSIM}/scripts/install-pumba.sh
RUN pip3 install ${PATH_WOTSIM}

ENTRYPOINT ["/root/wotsim/entrypoint.sh"]