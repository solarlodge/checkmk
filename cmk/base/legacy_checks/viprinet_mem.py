#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition, saveint
from cmk.base.config import check_info

from cmk.agent_based.v2 import render, Service, SNMPTree
from cmk.agent_based.v2.type_defs import DiscoveryResult, StringTable
from cmk.plugins.lib.viprinet import DETECT_VIPRINET


def parse_viprinet_mem(string_table: StringTable) -> StringTable:
    return string_table


def discover_viprinet_mem(section: StringTable) -> DiscoveryResult:
    if section:
        yield Service()


def check_viprinet_mem(_no_item, _no_params, info):
    return (
        0,
        "Memory used: %s" % render.bytes(saveint(info[0][0])),
    )


check_info["viprinet_mem"] = LegacyCheckDefinition(
    parse_function=parse_viprinet_mem,
    detect=DETECT_VIPRINET,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.35424.1.2",
        oids=["2"],
    ),
    service_name="Memory",
    discovery_function=discover_viprinet_mem,
    check_function=check_viprinet_mem,
)
