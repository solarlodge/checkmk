#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Iterator, Mapping, Sequence
from typing import Literal

from pydantic import BaseModel

from cmk.server_side_calls.v1 import (
    HostConfig,
    HTTPProxy,
    IPAddressFamily,
    NetworkAddressConfig,
    parse_secret,
    PlainTextSecret,
    ResolvedIPAddressFamily,
    Secret,
    SpecialAgentCommand,
    SpecialAgentConfig,
)


class ExampleParams(BaseModel):
    protocol: str
    user: str
    password: tuple[Literal["store", "password"], str]


def parse_example_params(params: Mapping[str, object]) -> ExampleParams:
    return ExampleParams.model_validate(params)


def generate_example_commands(
    params: ExampleParams,
    _host_config: HostConfig,
    _http_proxies: Mapping[str, HTTPProxy],
) -> Iterator[SpecialAgentCommand]:
    args: Sequence[str | Secret] = [
        "-p",
        params.protocol,
        "-u",
        params.user,
        "-s",
        parse_secret(params.password),
    ]
    yield SpecialAgentCommand(command_arguments=args)


special_agent_example = SpecialAgentConfig(
    name="example",
    parameter_parser=parse_example_params,
    commands_function=generate_example_commands,
)


def test_active_check_config() -> None:
    host_config = HostConfig(
        name="hostname",
        resolved_address="0.0.0.1",
        alias="host_alias",
        resolved_ip_family=ResolvedIPAddressFamily.IPV4,
        address_config=NetworkAddressConfig(
            ip_family=IPAddressFamily.DUAL_STACK,
            ipv4_address="0.0.0.1",
            ipv6_address=None,
            additional_ipv4_addresses=["0.0.0.4", "0.0.0.5"],
            additional_ipv6_addresses=[
                "fe80::241",
                "fe80::242",
                "fe80::243",
            ],
        ),
    )
    params = {
        "protocol": "HTTP",
        "user": "example_user",
        "password": ("password", "password1234"),
    }

    parsed_params = special_agent_example.parameter_parser(params)
    commands = list(special_agent_example.commands_function(parsed_params, host_config, {}))

    assert len(commands) == 1
    assert commands[0] == SpecialAgentCommand(
        command_arguments=[
            "-p",
            "HTTP",
            "-u",
            "example_user",
            "-s",
            PlainTextSecret(value="password1234", format="%s"),
        ],
    )
