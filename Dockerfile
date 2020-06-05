FROM ubuntu:19.10

ENV PATH_WOTEMU /root/wotemu
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

COPY . ${PATH_WOTEMU}
RUN ${PATH_WOTEMU}/scripts/install-pumba.sh
RUN pip3 install ${PATH_WOTEMU}

ENTRYPOINT ["/root/wotemu/entrypoint.sh"]