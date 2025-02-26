#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.cmctc import DETECT_CMCTC

# .1.3.6.1.4.1.2606.4.3.1.1.0 1
# .1.3.6.1.4.1.2606.4.3.1.2.0 1
# .1.3.6.1.4.1.2606.4.3.1.3.0 1
# .1.3.6.1.4.1.2606.4.3.1.4.0 2
# .1.3.6.1.4.1.2606.4.3.1.5.0 2


def inventory_cmctc_config(info):
    return [(None, {})]


def check_cmctc_config(_no_item, _no_params, info):
    temp_unit_map = {
        "1": "celsius",
        "2": "fahrenheit",
    }

    beeper_map = {
        "1": "on",
        "2": "off",
    }

    acknowledge_map = {
        "1": "disabled",
        "2": "enabled",
    }

    alarm_relay_map = {
        "1": "pick up",
        "2": "release",
        "3": "off",
    }

    web_access_map = {
        "1": "view only",
        "2": "full",
        "3": "disables",
    }

    temp_id, beeper_id, ack_id, relay_logic_id, web_access_id = info[0]

    temperature_unit = temp_unit_map.get(temp_id)
    beeper = beeper_map.get(beeper_id)
    acknowledging = acknowledge_map.get(ack_id)
    relay_logic = alarm_relay_map.get(relay_logic_id)
    web_access = web_access_map.get(web_access_id)

    infotext = (
        "Web access: %s, Beeper: %s, Acknowledging: %s, "
        "Alarm relay logic in case of alarm: %s, Temperature unit: %s"
    ) % (web_access, beeper, acknowledging, relay_logic, temperature_unit)

    return 0, infotext


def parse_cmctc_config(string_table: StringTable) -> StringTable | None:
    return string_table or None


check_info["cmctc_config"] = LegacyCheckDefinition(
    parse_function=parse_cmctc_config,
    detect=DETECT_CMCTC,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.2606.4.3.1",
        oids=["1", "2", "3", "4", "5"],
    ),
    service_name="TC configuration",
    discovery_function=inventory_cmctc_config,
    check_function=check_cmctc_config,
)
