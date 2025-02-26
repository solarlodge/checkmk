#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Iterator, Mapping
from typing import Literal

from pydantic import BaseModel

from cmk.server_side_calls.v1 import (
    HostConfig,
    parse_secret,
    replace_macros,
    Secret,
    SpecialAgentCommand,
    SpecialAgentConfig,
)


class Params(BaseModel, frozen=True):
    timeout: int | None = None
    ssl: tuple[str, str | None] = ("hostname", None)
    api_token: tuple[Literal["password", "store"], str]


def commands_function(
    params: Params,
    host_config: HostConfig,
    _http_proxies: Mapping[str, object],
) -> Iterator[SpecialAgentCommand]:
    command_arguments: list[str | Secret] = (
        ["--timeout", str(params.timeout)] if params.timeout else []
    )

    ssl_config_ident, ssl_config_value = params.ssl
    if ssl_config_ident == "deactivated":
        command_arguments.append("--no-cert-check")
    elif ssl_config_ident == "hostname":
        command_arguments += ["--cert-server-name", host_config.name]
    else:
        ssl_server = replace_macros(str(ssl_config_value), host_config.macros)
        command_arguments += ["--cert-server-name", ssl_server]

    command_arguments += ["--api-token", parse_secret(params.api_token)]

    yield SpecialAgentCommand(
        command_arguments=[*command_arguments, host_config.resolved_address or host_config.name]
    )


special_agent_pure_storage_fa = SpecialAgentConfig(
    name="pure_storage_fa",
    parameter_parser=Params.model_validate,
    commands_function=commands_function,
)
