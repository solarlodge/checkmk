#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


# check_mk plugin to monitor Fujitsu storage systems supporting FJDARY-E60.MIB or FJDARY-E100.MIB
# Copyright (c) 2012 FuH Entwicklungsgesellschaft mbH, Umkirch, Germany. All rights reserved.
# Author: Philipp Hoefflin, 2012, hoefflin+cmk@fuh-e.de

# generic data structure widely used in the FJDARY-Mibs:
# <oid>
# <oid>.1: Index
# <oid>.3: Status
# the latter can be one of the following:


from cmk.plugins.lib.fjdarye import check_fjdarye_item, discover_fjdarye_item, parse_fjdarye_item

from .agent_based_api.v1 import any_of, equals, register, SNMPTree

FJDARYE_CHANNEL_ADAPTERS = {
    ".1.3.6.1.4.1.211.1.21.1.60": ".2.2.2.1",  # fjdarye60
    ".1.3.6.1.4.1.211.1.21.1.100": ".2.3.2.1",  # fjdarye100
    ".1.3.6.1.4.1.211.1.21.1.101": ".2.3.2.1",  # fjdarye101
    ".1.3.6.1.4.1.211.1.21.1.150": ".2.3.2.1",  # fjdarye500
    ".1.3.6.1.4.1.211.1.21.1.153": ".2.3.2.1",  # fjdarye600
}


register.snmp_section(
    name="fjdarye_channel_adapters",
    parse_function=parse_fjdarye_item,
    fetch=[
        SNMPTree(base=f"{device_oid}{channel_adapter_oid}", oids=["1", "3"])
        for device_oid, channel_adapter_oid in FJDARYE_CHANNEL_ADAPTERS.items()
    ],
    detect=any_of(
        *[equals(".1.3.6.1.2.1.1.2.0", device_oid) for device_oid in FJDARYE_CHANNEL_ADAPTERS]
    ),
)

register.check_plugin(
    name="fjdarye_channel_adapters",
    service_name="Channel Adapter %s",
    discovery_function=discover_fjdarye_item,
    check_function=check_fjdarye_item,
)
