FROM ubuntu:19.04

ENV PATH_WOTPY /root/wot-py
ENV PATH_WOTSIM /root/wotsim
ENV PORT_CATALOGUE 9090
ENV PORT_HTTP 80
ENV PORT_WS 81
ENV PORT_COAP 5683

# Install dependencies

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

RUN pip3 install wotpy

# Clone Wotpy repository

RUN git clone https://github.com/agmangas/wot-py.git ${PATH_WOTPY}
RUN pip3 install -r ${PATH_WOTPY}/examples/benchmark/requirements.txt

# Copy sources and install Wotsim

COPY . ${PATH_WOTSIM}
RUN pip3 install ${PATH_WOTSIM}

# Expose ports and set entrypoint

EXPOSE ${PORT_CATALOGUE}
EXPOSE ${PORT_HTTP}
EXPOSE ${PORT_WS}
EXPOSE ${PORT_COAP}/tcp
EXPOSE ${PORT_COAP}/udp

ENTRYPOINT ["/root/wotsim/entrypoint.sh"]
CMD ["idle"]