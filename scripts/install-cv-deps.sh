#!/usr/bin/env bash

apt-get update -y

DEBIAN_FRONTEND=noninteractive apt-get install -y \
libsm6 \
libxext6 \
ffmpeg \
libfontconfig1 \
libxrender1 \
libgl1-mesa-glx