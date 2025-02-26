#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import contains, SNMPTree
from cmk.agent_based.v2.type_defs import StringTable


def inventory_bdt_tape_info(info):
    return [(None, None)]


def check_bdt_tape_info(_no_item, _no_params, info):
    for name, value in zip(["Name", "Description", "Vendor", "Agent Version"], info[0]):
        yield 0, f"{name}: {value}"


def parse_bdt_tape_info(string_table: StringTable) -> StringTable | None:
    return string_table or None


check_info["bdt_tape_info"] = LegacyCheckDefinition(
    parse_function=parse_bdt_tape_info,
    detect=contains(".1.3.6.1.2.1.1.2.0", ".1.3.6.1.4.1.20884.10893.2.101"),
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.20884.10893.2.101.1",
        oids=["1", "2", "3", "4"],
    ),
    service_name="Tape Library Info",
    discovery_function=inventory_bdt_tape_info,
    check_function=check_bdt_tape_info,
)
