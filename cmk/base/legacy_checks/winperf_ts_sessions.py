#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# Example output from agent:
# <<<winperf_ts_sessions>>>
# 1385714515.93 2102
# 2 20 rawcount
# 4 18 rawcount
# 6 2 rawcount

# Counters, relative to the base ID (e.g. 2102)
# 2 Total number of Terminal Services sessions.
# 4 Number of active Terminal Services sessions.
# 6 Number of inactive Terminal Services sessions.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2.type_defs import StringTable


def inventory_winperf_ts_sessions(info):
    if len(info) > 1:
        return [(None, {})]
    return []


def check_winperf_ts_sessions(_unused, params, info):
    if not info or len(info) == 1:
        return 3, "Performance counters not available"
    total, active, inactive = (int(l[1]) for l in info[1:4])

    # Tom Moore said, that the order of the columns has recently changed
    # in newer Windows versions (hooray!) and is now active, inactive, total.
    # We try to accommodate for that.
    if active + inactive != total:
        active, inactive, total = total, active, inactive

    state = 0
    state_txt = []
    for val, key, title in [(active, "active", "Active"), (inactive, "inactive", "Inactive")]:
        txt = "%d %s" % (val, title)
        if key in params:
            if val > params[key][0]:
                state = 2
                txt += "(!!)"
            elif val > params[key][1]:
                state = max(state, 1)
                txt += "(!)"
        state_txt.append(txt)

    perfdata = [("active", active), ("inactive", inactive)]
    return state, ", ".join(state_txt), perfdata


def parse_winperf_ts_sessions(string_table: StringTable) -> StringTable:
    return string_table


check_info["winperf_ts_sessions"] = LegacyCheckDefinition(
    parse_function=parse_winperf_ts_sessions,
    service_name="Sessions",
    discovery_function=inventory_winperf_ts_sessions,
    check_function=check_winperf_ts_sessions,
    check_ruleset_name="winperf_ts_sessions",
)
