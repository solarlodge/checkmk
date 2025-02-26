#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import all_of, contains, OIDEnd, SNMPTree

DEVICE_TYPE_MAP = {
    "1": "Power",
    "2": "Cooling",
    "3": "Control",
    "4": "Connectivity",
    "5": "Robotics",
    "6": "Media",
    "7": "Drive",
    "8": "Operator action request",
}

RAS_STATUS_MAP = {
    "1": (0, "good"),
    "2": (2, "failed"),
    "3": (2, "degraded"),
    "4": (1, "warning"),
    "5": (0, "informational"),
    "6": (3, "unknown"),
    "7": (3, "invalid"),
}

OPNEED_STATUS_MAP = {
    "0": (0, "no"),
    "1": (2, "yes"),
    "2": (0, "no"),
}


def parse_quantum_libsmall_status(string_table):
    parsed = []
    for line in string_table:
        for oidend, dev_state in line:
            dev_type = DEVICE_TYPE_MAP.get(oidend.split(".")[0])
            if not (dev_type or dev_state):
                continue
            parsed.append((dev_type, dev_state))
    return parsed


def inventory_quantum_libsmall_status(parsed):
    if parsed:
        return [(None, None)]
    return []


def check_quantum_libsmall_status(_no_item, _no_params, parsed):
    for dev_type, dev_state in parsed:
        if dev_type == "Operator action request":
            state, state_readable = OPNEED_STATUS_MAP.get(dev_state, (3, "unknown[%s]" % dev_state))
        else:
            state, state_readable = RAS_STATUS_MAP.get(dev_state, (3, "unknown[%s]" % dev_state))
        yield state, f"{dev_type}: {state_readable}"


check_info["quantum_libsmall_status"] = LegacyCheckDefinition(
    detect=all_of(
        contains(".1.3.6.1.2.1.1.1.0", "linux"), contains(".1.3.6.1.2.1.1.6.0", "library")
    ),
    fetch=[
        SNMPTree(
            base=".1.3.6.1.4.1.3697.1.10.10.1.15",
            oids=[OIDEnd(), "10"],
        ),
        SNMPTree(
            base=".1.3.6.1.4.1.3764.1.10.10",
            oids=[OIDEnd(), "12"],
        ),
    ],
    parse_function=parse_quantum_libsmall_status,
    service_name="Tape library status",
    discovery_function=inventory_quantum_libsmall_status,
    check_function=check_quantum_libsmall_status,
)
