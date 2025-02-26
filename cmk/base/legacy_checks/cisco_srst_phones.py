#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2 import all_of, contains, equals, SNMPTree
from cmk.agent_based.v2.type_defs import StringTable


def inventory_cisco_srst_phones(info):
    return [(None, {})]


def check_cisco_srst_phones(_no_item, _no_params, info):
    phones = int(info[0][0])
    yield 0, "%d phones registered" % phones, [("registered_phones", phones)]


def parse_cisco_srst_phones(string_table: StringTable) -> StringTable | None:
    return string_table or None


check_info["cisco_srst_phones"] = LegacyCheckDefinition(
    parse_function=parse_cisco_srst_phones,
    detect=all_of(
        contains(".1.3.6.1.2.1.1.1.0", "cisco"), equals(".1.3.6.1.4.1.9.9.441.1.2.1.0", "1")
    ),
    fetch=SNMPTree(
        base=".1.3.6.1.4.1.9.9.441.1.3",
        oids=["2"],
    ),
    service_name="SRST Phones",
    discovery_function=inventory_cisco_srst_phones,
    check_function=check_cisco_srst_phones,
)
