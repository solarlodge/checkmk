#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Sequence

import pytest

from cmk.base.plugins.agent_based.agent_based_api.v1 import HostLabel
from cmk.base.plugins.agent_based.check_mk import host_label_function_labels, parse_checkmk_labels

from cmk.agent_based.v1.type_defs import StringTable


@pytest.mark.parametrize(
    "string_table,expected_parsed_data",
    [
        (
            [
                ["Version:", "1.7.0i1"],
                ["AgentOS:", "linux"],
                ["Hostname:", "klappclub"],
                ["AgentDirectory:", "/etc/check_mk"],
                ["DataDirectory:", "/var/lib/check_mk_agent"],
                ["SpoolDirectory:", "/var/lib/check_mk_agent/spool"],
                ["PluginsDirectory:", "/usr/lib/check_mk_agent/plugins"],
                ["LocalDirectory:", "/usr/lib/check_mk_agent/local"],
                ["OSType:", "linux"],
                ["OSPlatform:", "ubuntu"],
                ["OSName:", "Ubuntu"],
                ["OSVersion:", "20.04"],
            ],
            [
                HostLabel("cmk/os_family", "linux"),
                HostLabel("cmk/os_type", "linux"),
                HostLabel("cmk/os_platform", "ubuntu"),
                HostLabel("cmk/os_name", "Ubuntu"),
                HostLabel("cmk/os_version", "20.04"),
            ],
        ),
    ],
)
def test_checkmk_labels(
    string_table: StringTable, expected_parsed_data: Sequence[HostLabel]
) -> None:
    result = list(host_label_function_labels(parse_checkmk_labels(string_table)))
    assert isinstance(result[0], HostLabel)
    assert expected_parsed_data == result
