#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.infoblox import DETECT_INFOBLOX

# .1.3.6.1.4.1.7779.3.1.1.2.1.15.0 X.X.X.X --> IB-PLATFORMONE-MIB::ibGridMasterVIP.0
# .1.3.6.1.4.1.7779.3.1.1.2.1.16.0 ONLINE --> IB-PLATFORMONE-MIB::ibGridReplicationState.0


def inventory_infoblox_grid_status(info):
    return [(None, None)]


def check_infoblox_grid_status(_no_item, _no_params, info):
    master_vip, status = info[0]
    status_readable = status.lower()
    if status_readable == "online":
        state = 0
    else:
        state = 2

    return state, f"Status: {status_readable}, Master virtual IP: {master_vip}"


def parse_infoblox_grid_status(string_table: StringTable) -> StringTable | None:
    return string_table or None


check_info["infoblox_grid_status"] = LegacyCheckDefinition(
    parse_function=parse_infoblox_grid_status,
    detect=DETECT_INFOBLOX,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.7779.3.1.1.2.1",
        oids=["15", "16"],
    ),
    service_name="Grid replication",
    discovery_function=inventory_infoblox_grid_status,
    check_function=check_infoblox_grid_status,
)
