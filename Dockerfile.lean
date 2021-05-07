FROM ubuntu:20.04

ENV PATH_WOTEMU /root/wotemu
ENV WAIT_GATEWAYS 10

WORKDIR ${PATH_WOTEMU}
COPY ./scripts ./scripts
RUN ./scripts/install-image-deps.sh
RUN ./scripts/install-pumba.sh
COPY . .
RUN pip3 install -U .

ENTRYPOINT ["/root/wotemu/entrypoint.sh"]