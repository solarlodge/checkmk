#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import check_levels, LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib import fireeye


def discover_fireeye_active_vms(string_table):
    if string_table:
        yield None, {}


def check_fireeye_active_vms(_no_item, params, info):
    value = int(info[0][0])
    return check_levels(
        value,
        "active_vms",
        params["vms"],
        human_readable_func=str,
        infoname="Active VMs",
    )


def parse_fireeye_active_vms(string_table: StringTable) -> StringTable:
    return string_table


check_info["fireeye_active_vms"] = LegacyCheckDefinition(
    parse_function=parse_fireeye_active_vms,
    detect=fireeye.DETECT,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.25597.11.5.1.9",
        oids=["0"],
    ),
    service_name="Active VMs",
    discovery_function=discover_fireeye_active_vms,
    check_function=check_fireeye_active_vms,
    check_ruleset_name="fireeye_active_vms",
    check_default_parameters={"vms": (100, 120)},
)
