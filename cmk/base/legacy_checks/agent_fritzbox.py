#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

# {
#     'timeout': 10,
# }


from collections.abc import Mapping, Sequence
from typing import Any

from cmk.base.config import special_agent_info


def agent_fritzbox_arguments(
    params: Mapping[str, Any], hostname: str, ipaddress: str | None
) -> Sequence[str]:
    args = []

    if "timeout" in params:
        args += ["--timeout", "%d" % params["timeout"]]

    args.append(ipaddress or hostname)
    return args


special_agent_info["fritzbox"] = agent_fritzbox_arguments
