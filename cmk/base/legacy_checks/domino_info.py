#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.domino import DETECT

# Example SNMP walk:
#
# .1.3.6.1.4.1.334.72.2.2.0 1
# .1.3.6.1.4.1.334.72.1.1.4.8.0 MEDEMA
# .1.3.6.1.4.1.334.72.1.1.6.2.1.0 CN=HH-BK4/OU=SRV/O=MEDEMA/C=DE
# .1.3.6.1.4.1.334.72.1.1.6.2.4.0 Release 8.5.3FP5 HF89


def inventory_domino_info(info):
    if info and len(info[0]) != 0:
        yield None, None


def check_domino_info(_no_item, _no_params, info):
    translate_status = {
        "1": (0, "up"),
        "2": (2, "down"),
        "3": (2, "not-responding"),
        "4": (1, "crashed"),
        "5": (3, "unknown"),
    }
    status, domain, name, release = info[0]

    state, state_readable = translate_status[status]
    yield state, "Server is %s" % state_readable

    if len(domain) > 0:
        yield 0, "Domain: %s" % domain

    yield 0, f"Name: {name}, {release}"


def parse_domino_info(string_table: StringTable) -> StringTable:
    return string_table


check_info["domino_info"] = LegacyCheckDefinition(
    parse_function=parse_domino_info,
    detect=DETECT,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.334.72",
        oids=["2.2", "1.1.4.8", "1.1.6.2.1", "1.1.6.2.4"],
    ),
    service_name="Domino Info",
    discovery_function=inventory_domino_info,
    check_function=check_domino_info,
)
