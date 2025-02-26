#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

#
# Example Output:
# .1.3.6.1.4.1.5951.4.1.1.23.3.0  1
# .1.3.6.1.4.1.5951.4.1.1.23.23.0  1
# .1.3.6.1.4.1.5951.4.1.1.23.24.0  3


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.netscaler import SNMP_DETECT

netscaler_ha_cur_states = {
    0: ("unknown", 1),
    # 1 Indicates that the node is in the process of becoming part of the high
    #   availability configuration.
    1: ("initializing", 1),
    2: ("down", 2),  # undocumented
    # 3 Indicates that the node is accessible and can function as either
    #   a primary or secondary node.
    3: ("functional", 0),
    # 4 Indicates that one of the high availability monitored interfaces
    #   has failed because of a card or link failure. # This state triggers a
    #   failover.
    4: ("some HA monitored interfaces failed", 2),
    5: ("monitorFail", 1),  # undocumented
    6: ("monitorOK", 1),  # undocumented
    # 7 Indicates that all the interfaces of the node are
    #   unusable because the interfaces on which high
    #   availability monitoring is enabled are not connected
    #   or are manually disabled. This state triggers a failover.
    7: ("all HA monitored interfaces failed", 2),
    # 8 Indicates that the node is in listening mode. It does not
    #   participate in high availability transitions or transfer
    #   configuration from the peer node. This is a configured
    #   value, not a statistic.
    8: ("configured to listening mode (dumb)", 1),
    # 9 Indicates that the high availability status of the node has been
    #   manually disabled. Synchronization and propagation cannot take
    #   place between the peer nodes.
    9: ("HA status manually disabled", 1),
    # 10 Indicates that the SSL card has failed. This state triggers a failover.
    10: ("SSL card failed", 2),
    # 11 Indicates that the route monitor has failed. This state triggers
    #    a failover.
    11: ("route monitor has failed", 2),
}

netscaler_ha_peer_mode = {
    0: ("standalone", 0),
    1: ("primary", 0),
    2: ("secondary", 0),
    3: ("unknown", 1),
}


def inventory_netscaler_ha(info):
    if info:
        return [(None, None)]
    return []


def check_netscaler_ha(_no_item, _no_params, info):
    if info:
        state = 0
        peer_state, cur_status, cur_state = map(int, info[0])
        if cur_status == 0:
            infotext = "System not setup for HA"
        else:
            infotext = "State: {}, Neighbour: {}".format(
                netscaler_ha_cur_states[cur_state][0],
                netscaler_ha_peer_mode[peer_state][0],
            )
            state = max(
                netscaler_ha_cur_states[cur_state][1], netscaler_ha_peer_mode[peer_state][1]
            )

        return state, infotext
    return None


def parse_netscaler_ha(string_table: StringTable) -> StringTable:
    return string_table


check_info["netscaler_ha"] = LegacyCheckDefinition(
    parse_function=parse_netscaler_ha,
    detect=SNMP_DETECT,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.5951.4.1.1.23",
        oids=["3", "23", "24"],
    ),
    service_name="HA Node Status",
    discovery_function=inventory_netscaler_ha,
    check_function=check_netscaler_ha,
)
