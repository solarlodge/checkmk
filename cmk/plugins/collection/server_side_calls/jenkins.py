#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from typing import Iterator, Mapping, Sequence

from pydantic import BaseModel

from cmk.server_side_calls.v1 import (
    HostConfig,
    HTTPProxy,
    parse_secret,
    replace_macros,
    Secret,
    SpecialAgentCommand,
    SpecialAgentConfig,
)

from .utils import SecretType


class JenkinsParams(BaseModel):
    user: str
    password: tuple[SecretType, str]
    protocol: str
    instance: str
    port: int | None = None
    sections: Sequence[str] = []


def parse_jenkins_params(raw_params: Mapping[str, object]) -> JenkinsParams:
    return JenkinsParams.model_validate(raw_params)


def agent_jenkins_config(
    params: JenkinsParams,
    host_config: HostConfig,
    _http_proxies: Mapping[str, HTTPProxy],
) -> Iterator[SpecialAgentCommand]:
    args: list[str | Secret] = [
        "-P",
        params.protocol,
        "-u",
        params.user,
        "-s",
        parse_secret(params.password),
    ]

    if params.sections:
        args += ["-m", " ".join(params.sections)]

    if params.port:
        args += ["-p", str(params.port)]

    args.append(replace_macros(params.instance, host_config.macros))

    yield SpecialAgentCommand(command_arguments=args)


special_agent_jenkins = SpecialAgentConfig(
    name="jenkins", parameter_parser=parse_jenkins_params, commands_function=agent_jenkins_config
)
