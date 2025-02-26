#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# In cooperation with Thorsten Bruhns from OPITZ Consulting


from cmk.base.check_api import check_levels, LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import IgnoreResultsError, render

# <<<oracle_dataguard_stats:sep(124)>>>
# TESTDB|TESTDBU2|PHYSICAL STANDBY|apply finish time|+00 00:00:00.000|NOT ALLOWED|ENABLED|MAXIMUM PERFORMANCE|DISABLED||||APPLYING_LOG
# TESTDB|TESTDBU2|PHYSICAL STANDBY|apply lag|+00 00:00:00|NOT ALLOWED|ENABLED|MAXIMUM PERFORMANCE|DISABLED||||APPLYING_LOG
#
# TUX12C|TUXSTDB|PHYSICAL STANDBY|transport lag|+00 00:00:00
# TUX12C|TUXSTDB|PHYSICAL STANDBY|apply lag|+00 00:28:57
# TUX12C|TUXSTDB|PHYSICAL STANDBY|apply finish time|+00 00:00:17.180
# TUX12C|TUXSTDB|PHYSICAL STANDBY|estimated startup time|20


def inventory_oracle_dataguard_stats(parsed):
    for instance in parsed:
        yield instance, {}


def _get_seconds(timestamp: str) -> int | None:
    if not timestamp or timestamp[0] != "+":
        return None

    days = int(timestamp[1:3])
    h = int(timestamp[4:6])
    min_ = int(timestamp[7:9])
    sec = int(timestamp[10:12])

    return sec + 60 * min_ + 3600 * h + 86400 * days


def check_oracle_dataguard_stats(item, params, parsed):  # pylint: disable=too-many-branches
    try:
        dgdata = parsed[item]
    except KeyError:
        # In case of missing information we assume that the login into
        # the database has failed and we simply skip this check. It won't
        # switch to UNKNOWN, but will get stale.
        raise IgnoreResultsError("Dataguard disabled or Instance not running")

    yield 0, "Database Role %s" % (dgdata["database_role"].lower())

    if "protection_mode" in dgdata:
        yield 0, "Protection Mode %s" % (dgdata["protection_mode"].lower())

    if "broker_state" in dgdata:
        yield 0, "Broker %s" % (dgdata["broker_state"].lower())

        # Observer is only usable with enabled Fast Start Failover!
        if "fs_failover_status" in dgdata and dgdata["fs_failover_status"] != "DISABLED":
            if dgdata["fs_failover_observer_present"] != "YES":
                yield 2, "Observer not connected"
            else:
                yield 0, "Observer connected {} from host {}".format(
                    dgdata["fs_failover_observer_present"].lower(),
                    dgdata["fs_failover_observer_host"],
                )

                if (
                    dgdata["protection_mode"] == "MAXIMUM PERFORMANCE"
                    and dgdata["fs_failover_status"] == "TARGET UNDER LAG LIMIT"
                ) or (
                    dgdata["protection_mode"] == "MAXIMUM AVAILABILITY"
                    and dgdata["fs_failover_status"] == "SYNCHRONIZED"
                ):
                    state = 0
                else:
                    state = 1
                yield state, "Fast Start Failover %s" % (dgdata["fs_failover_status"].lower())

    # switchover_status is important for non broker environemnts as well.
    if "switchover_status" in dgdata:
        if dgdata["database_role"] == "PRIMARY":
            if dgdata["switchover_status"] in (
                "TO STANDBY",
                "SESSIONS ACTIVE",
                "RESOLVABLE GAP",
                "LOG SWITCH GAP",
            ):
                yield 0, "Switchover to standby possible"
            else:
                primary_broker_state = params.get("primary_broker_state")
                if primary_broker_state or dgdata["broker_state"].lower() == "enabled":
                    # We need primary_broker_state False for Data-Guards without Broker
                    yield 2, "Switchover to standby not possible! reason: %s" % dgdata[
                        "switchover_status"
                    ].lower()
                else:
                    yield 0, "Switchoverstate ignored "

        elif dgdata["database_role"] == "PHYSICAL STANDBY":
            # don't show the ok state, due to distracting 'NOT ALLOWED' state!
            if dgdata["switchover_status"] in ("SYNCHRONIZED", "NOT ALLOWED", "SESSIONS ACTIVE"):
                yield 0, "Switchover to primary possible"
            else:
                yield 2, "Switchover to primary not possible! reason: %s" % dgdata[
                    "switchover_status"
                ]

    if dgdata["database_role"] != "PHYSICAL STANDBY":
        return

    if mrp_status := dgdata.get("mrp_status"):
        yield 0, "Managed Recovery Process state %s" % mrp_status.lower()

        if dgdata.get("open_mode", "") == "READ ONLY WITH APPLY":
            yield params.get("active_dataguard_option"), "Active Data-Guard found"

    elif mrp_status is not None:
        yield 0, "Managed Recovery Process not started"

    for dgstat_param in ("apply finish time", "apply lag", "transport lag"):
        raw_value = dgdata["dgstat"][dgstat_param]
        seconds = _get_seconds(raw_value)
        pkey = dgstat_param.replace(" ", "_")
        label = dgstat_param.capitalize()
        # NOTE: not all of these metrics have params implemented, that's why we have to use 'get'

        if seconds is None:
            yield params.get(f"missing_{pkey}_state", 0), f"{label}: {raw_value or 'no value'}"
            continue

        levels_upper = params.get(pkey) or (None, None)
        levels_lower = params.get(f"{pkey}_min") or (None, None)

        yield check_levels(
            seconds,
            pkey,
            levels_upper + levels_lower,
            human_readable_func=render.time_offset,
            infoname=label,
        )

    if (
        dgdata["database_role"] == "PHYSICAL STANDBY"
        and "broker_state" not in dgdata
        and "apply lag" in dgdata["dgstat"]
        and dgdata["dgstat"]["apply lag"] == ""
    ):
        # old sql cannot detect a started standby database without running media recovery
        # => add an information for old plugin with possible wrong result
        yield 0, "old plugin data found, recovery active?"


check_info["oracle_dataguard_stats"] = LegacyCheckDefinition(
    # section is already migrated!
    service_name="ORA %s Dataguard-Stats",
    discovery_function=inventory_oracle_dataguard_stats,
    check_function=check_oracle_dataguard_stats,
    check_ruleset_name="oracle_dataguard_stats",
    check_default_parameters={
        "apply_lag": (3600, 14400),
        "missing_apply_lag_state": 1,
        "active_dataguard_option": 1,
        "primary_broker_state": False,
    },
)
