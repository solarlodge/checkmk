#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.check_legacy_includes.temperature import check_temperature
from cmk.base.config import check_info

from cmk.agent_based.v2 import Service, SNMPTree
from cmk.agent_based.v2.type_defs import DiscoveryResult, StringTable
from cmk.plugins.lib.viprinet import DETECT_VIPRINET


def check_viprinet_temp(item, params, info):
    reading = int(info[0][item == "System"])
    return check_temperature(reading, params, "viprinet_temp_%s" % item)


def parse_viprinet_temp(string_table: StringTable) -> StringTable:
    return string_table


def discover_viprinet_temp(section: StringTable) -> DiscoveryResult:
    if section:
        yield Service(item="CPU")
        yield Service(item="System")


check_info["viprinet_temp"] = LegacyCheckDefinition(
    parse_function=parse_viprinet_temp,
    detect=DETECT_VIPRINET,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.35424.1.2",
        oids=["3", "4"],
    ),
    service_name="Temperature %s",
    discovery_function=discover_viprinet_temp,
    check_function=check_viprinet_temp,
    check_ruleset_name="temperature",
)
