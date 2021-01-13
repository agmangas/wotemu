FROM ubuntu:20.04

ENV PATH_WOTEMU /root/wotemu
ENV WAIT_GATEWAYS 10
ENV VERSION_PUMBA 0.7.7

RUN apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3 \
    python3-pip \
    iproute2 \
    iptables \
    tshark \
    wget \
    curl \
    mosquitto \
    dnsutils \
    cgroup-tools 

COPY . ${PATH_WOTEMU}
RUN ${PATH_WOTEMU}/scripts/install-pumba.sh
RUN pip3 install ${PATH_WOTEMU}

ENTRYPOINT ["/root/wotemu/entrypoint.sh"]