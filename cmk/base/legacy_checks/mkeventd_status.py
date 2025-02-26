#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# Example output from agent:
# <<<mkeventd_status:sep(0)>>>
# ["heute"]
# [["status_config_load_time", "status_num_open_events", "status_messages", "status_message_rate", "status_average_message_rate", "status_connects", "status_connect_rate", "status_average_connect_rate", "status_rule_tries", "status_rule_trie_rate", "status_average_rule_trie_rate", "status_drops", "status_drop_rate", "status_average_drop_rate", "status_events", "status_event_rate", "status_average_event_rate", "status_rule_hits", "status_rule_hit_rate", "status_average_rule_hit_rate", "status_average_processing_time", "status_average_request_time", "status_average_sync_time", "status_replication_slavemode", "status_replication_last_sync", "status_replication_success", "status_event_limit_host", "status_event_limit_rule", "status_event_limit_overall", "status_event_limit_active_hosts", "status_event_limit_active_rules", "status_event_limit_active_overall"], [1474040901.678517, 19, 0, 0.0, 0.0, 2, 0.1998879393337847, 0.1998879393337847, 0, 0.0, 0.0, 0, 0.0, 0.0, 0, 0.0, 0.0, 0, 0.0, 0.0, 0.0, 0.002389192581176758, 0.0, "master", 0.0, false, 10, 5, 20, [], ["catch_w", "catch_y", "catch_x"], false]]


# mypy: disable-error-code="var-annotated"

import time

from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import get_rate, get_value_store, render


def parse_mkeventd_status(string_table):
    import json

    parsed, site = {}, None
    for line in string_table:
        try:
            data = json.loads(line[0])
        except ValueError:
            # The agent plugin asks the event console for json OutputFormat, but
            # older versions always provide python format - even when other format
            # was requested. Skipping the site. Won't eval data from other systems.
            continue

        if len(data) == 1:
            site = data[0]
            parsed[site] = None  # Site is marked as down until overwritten later
        elif site:
            # strip "status_" from the column names
            keys = [col[7:] for col in data[0]]
            parsed[site] = dict(zip(keys, data[1]))

    return parsed


def inventory_mkeventd_status(parsed):
    return [(site, {}) for (site, status) in parsed.items() if status is not None]


def check_mkeventd_status(item, params, parsed):  # pylint: disable=too-many-branches
    if item not in parsed:
        return

    status = parsed[item]

    # Ignore down sites. This happens on a regular basis due to restarts
    # of the core. The availability of a site is monitored with 'omd_status'.
    if status is None:
        yield 0, "Currently not running"
        return

    yield 0, "Current events: %d" % status["num_open_events"], [
        ("num_open_events", status["num_open_events"])
    ]

    yield 0, "Virtual memory: %s" % render.bytes(status["virtual_memory_size"]), [
        ("process_virtual_size", status["virtual_memory_size"])
    ]

    # Event limits
    if status["event_limit_active_overall"]:
        yield 2, "Overall event limit active"
    else:
        yield 0, "Overall event limit inactive"

    for ty in ["hosts", "rules"]:
        limited = status["event_limit_active_%s" % ty]
        if limited:
            yield 1, "Event limit active for %d %s (%s)" % (len(limited), ty, ", ".join(limited))
        else:
            yield 0, "No %s event limit active" % ty

    # Rates
    columns = [
        ("Received messages", "message", "%.2f/s"),
        ("Rule hits", "rule_hit", "%.2f/s"),
        ("Rule tries", "rule_trie", "%.2f/s"),
        ("Message drops", "drop", "%.2f/s"),
        ("Created events", "event", "%.2f/s"),
        ("Client connects", "connect", "%.2f/s"),
    ]
    rates = {}
    this_time = time.time()
    for title, col, fmt in columns:
        counter_value = status[col + "s"]
        rate = get_rate(get_value_store(), col, this_time, counter_value, raise_overflow=True)
        rates[col] = rate
        yield 0, ("%s: " + fmt) % (title, rate), [("average_%s_rate" % col, rate)]

    # Hit rate
    if rates["rule_trie"] == 0.0:
        hit_rate_txt = "-"
    else:
        value = rates["rule_hit"] / rates["rule_trie"] * 100
        hit_rate_txt = "%.2f%%" % value
        yield 0, "", [("average_rule_hit_ratio", value)]
    yield 0, "{}: {}".format("Rule hit ratio", hit_rate_txt)

    # Time columns
    time_columns = [
        ("Processing time per message", "processing"),
        ("Time per client request", "request"),
        ("Replication synchronization", "sync"),
    ]
    for title, name in time_columns:
        value = status.get("average_%s_time" % name)
        if value:
            txt = "%.2f ms" % (value * 1000)
            yield 0, "", [("average_%s_time" % name, value)]
        else:
            if name == "sync":
                continue  # skip if not available
            txt = "-"
        yield 0, f"{title}: {txt}"


check_info["mkeventd_status"] = LegacyCheckDefinition(
    parse_function=parse_mkeventd_status,
    service_name="OMD %s Event Console",
    discovery_function=inventory_mkeventd_status,
    check_function=check_mkeventd_status,
)
