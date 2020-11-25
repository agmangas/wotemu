#!/usr/bin/env bash

set -e
set -x

sed -i -E "s/GRUB_CMDLINE_LINUX=\"(.*)\"/GRUB_CMDLINE_LINUX=\"\1 cgroup_enable=memory swapaccount=1\"/g" /etc/default/grub
cat /etc/default/grub
update-grub