#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# Possible output:
# # tw_cli show
#
# Ctl   Model        (V)Ports  Drives   Units   NotOpt  RRate   VRate  BBU
# ------------------------------------------------------------------------
# c0    9550SXU-4LP  4         3        2       0       1       1      -
# c1    9550SXU-8LP  8         7        3       0       1       1      -
#
# tw_cli version: 2.01.09.004

# Another version produces this output:
# <<<3ware_info>>>
# /c0 Model = 9550SXU-8LP
# /c0 Firmware Version = FE9X 3.08.00.029
# /c0 Serial Number = L320809A6450122
# Port   Status           Unit   Size        Blocks        Serial

# This version of the check currently only handles output of the first type


from cmk.base.check_api import LegacyCheckDefinition
from cmk.base.config import check_info

from cmk.agent_based.v2.type_defs import StringTable


def inventory_3ware_info(info):
    inventory = []
    for line in info:
        if len(line) == 8:
            controller = line[0]
            inventory.append((controller, None))
    return inventory


def check_3ware_info(item, _no_params, info):
    infotext = ""
    for line in info:
        line = " ".join(line[1:])
        infotext = infotext + line + ";"
    return (0, infotext)


def parse_3ware_info(string_table: StringTable) -> StringTable:
    return string_table


check_info["3ware_info"] = LegacyCheckDefinition(
    parse_function=parse_3ware_info,
    service_name="RAID 3ware controller %s",
    discovery_function=inventory_3ware_info,
    check_function=check_3ware_info,
)
