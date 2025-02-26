#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import SNMPTree
from cmk.agent_based.v2.type_defs import StringTable
from cmk.plugins.lib.mcafee_gateway import DETECT_EMAIL_GATEWAY


def parse_mcafee_emailgateway_av_mcafee(string_table: StringTable) -> StringTable | None:
    return string_table or None


def inventory_mcafee_gateway_generic(info):
    return [(None, {})]


def check_mcafee_emailgateway_av_mcafee(item, params, info):
    eng_version, dat_version, extra_dat_version = info[0]
    return 0, "Engine version: {}, DAT version: {} ({})".format(
        eng_version,
        dat_version,
        extra_dat_version,
    )


check_info["mcafee_emailgateway_av_mcafee"] = LegacyCheckDefinition(
    parse_function=parse_mcafee_emailgateway_av_mcafee,
    detect=DETECT_EMAIL_GATEWAY,
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.1230.2.4.1.2.3.6",
        oids=["1", "2", "3"],
    ),
    service_name="AV McAfee",
    discovery_function=inventory_mcafee_gateway_generic,
    check_function=check_mcafee_emailgateway_av_mcafee,
)
