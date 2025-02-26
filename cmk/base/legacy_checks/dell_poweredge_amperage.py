#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.check_legacy_includes.dell_poweredge import check_dell_poweredge_amperage
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.dell import DETECT_IDRAC_POWEREDGE


def inventory_dell_poweredge_amperage_power(info):
    inventory = []
    for line in info:
        if line[6] != "" and line[5] in ("24", "26"):
            inventory.append((line[6], None))
    return inventory


def inventory_dell_poweredge_amperage_current(info):
    inventory = []
    for line in info:
        if line[6] != "" and line[5] in ("23", "25"):
            inventory.append((line[6], None))
    return inventory


def parse_dell_poweredge_amperage(string_table: StringTable) -> StringTable:
    return string_table


check_info["dell_poweredge_amperage"] = LegacyCheckDefinition(
    parse_function=parse_dell_poweredge_amperage,
    detect=DETECT_IDRAC_POWEREDGE,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.674.10892.5.4.600.30.1",
        oids=["1", "2", "4", "5", "6", "7", "8", "10", "11"],
    ),
)

check_info["dell_poweredge_amperage.power"] = LegacyCheckDefinition(
    service_name="%s",
    sections=["dell_poweredge_amperage"],
    discovery_function=inventory_dell_poweredge_amperage_power,
    check_function=check_dell_poweredge_amperage,
)

check_info["dell_poweredge_amperage.current"] = LegacyCheckDefinition(
    service_name="%s",
    sections=["dell_poweredge_amperage"],
    discovery_function=inventory_dell_poweredge_amperage_current,
    check_function=check_dell_poweredge_amperage,
)
