#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Mapping, Sequence

import pytest

from cmk.plugins.collection.server_side_calls.kube import special_agent_kube
from cmk.server_side_calls.v1 import (
    HostConfig,
    HTTPProxy,
    IPAddressFamily,
    NetworkAddressConfig,
    PlainTextSecret,
    ResolvedIPAddressFamily,
)

HOST_CONFIG = HostConfig(
    name="host",
    resolved_address="11.211.3.32",
    alias="host_alias",
    resolved_ip_family=ResolvedIPAddressFamily.IPV4,
    address_config=NetworkAddressConfig(ip_family=IPAddressFamily.IPV4),
)

HTTP_PROXIES = {"my_proxy": HTTPProxy("my_proxy", "My Proxy", "proxy.com")}


@pytest.mark.parametrize(
    "params,expected_args",
    [
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "cluster"),
                "kubernetes-api-server": {
                    "endpoint_v2": "https://11.211.3.32",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                    "timeout": {"connect": 5, "read": 8},
                },
                "usage_endpoint": (
                    "cluster-collector",
                    {
                        "endpoint_v2": "https://11.211.3.32:20026",
                        "verify-cert": False,
                        "timeout": {"connect": 10, "read": 12},
                    },
                ),
                "monitored-objects": ["pods"],
            },
            [
                "--cluster",
                "cluster",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="cluster", format="%s"),
                "--monitored-objects",
                "pods",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "https://11.211.3.32",
                "--api-server-proxy",
                "NO_PROXY",
                "--k8s-api-connect-timeout",
                "5",
                "--k8s-api-read-timeout",
                "8",
                "--cluster-collector-endpoint",
                "https://11.211.3.32:20026",
                "--usage-proxy",
                "FROM_ENVIRONMENT",
                "--usage-connect-timeout",
                "10",
                "--usage-read-timeout",
                "12",
            ],
        ),
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "cluster"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://11.211.3.32:8080",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "usage_endpoint": (
                    "cluster-collector",
                    {
                        "endpoint_v2": "https://11.211.3.32:20026",
                        "verify-cert": True,
                    },
                ),
                "monitored-objects": ["pods"],
            },
            [
                "--cluster",
                "cluster",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="cluster", format="%s"),
                "--monitored-objects",
                "pods",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "http://11.211.3.32:8080",
                "--api-server-proxy",
                "NO_PROXY",
                "--cluster-collector-endpoint",
                "https://11.211.3.32:20026",
                "--usage-proxy",
                "FROM_ENVIRONMENT",
                "--usage-verify-cert",
            ],
        ),
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "randomtoken"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://localhost:8080",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "usage_endpoint": (
                    "cluster-collector",
                    {
                        "endpoint_v2": "https://11.211.3.32:20026",
                        "verify-cert": False,
                    },
                ),
                "monitored-objects": ["pods", "namespaces"],
            },
            [
                "--cluster",
                "cluster",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="randomtoken", format="%s"),
                "--monitored-objects",
                "pods",
                "namespaces",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "http://localhost:8080",
                "--api-server-proxy",
                "NO_PROXY",
                "--cluster-collector-endpoint",
                "https://11.211.3.32:20026",
                "--usage-proxy",
                "FROM_ENVIRONMENT",
            ],
        ),
    ],
)
@pytest.mark.usefixtures("fix_register")
def test_parse_arguments(params: Mapping[str, object], expected_args: Sequence[str]) -> None:
    """Tests if all required arguments are present."""
    parsed_params = special_agent_kube.parameter_parser(params)
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == expected_args


def test_parse_arguments_with_no_cluster_endpoint() -> None:
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://127.0.0.1",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods"],
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--api-server-endpoint",
        "https://127.0.0.1",
        "--api-server-proxy",
        "NO_PROXY",
    ]


def test_cronjob_pvcs_piggyback_option() -> None:
    """Test the cronjob and pvc piggyback option"""
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods", "cronjobs_pods", "pvcs"],
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "cronjobs_pods",
        "pvcs",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]


def test_cluster_resource_aggregation() -> None:
    """Test the cluster-resource-aggregation option"""
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods"],
            "cluster-resource-aggregation": (
                "cluster-aggregation-exclude-node-roles",
                ["control*", "worker"],
            ),
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-exclude-node-roles",
        "control*",
        "worker",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]

    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods"],
            "cluster-resource-aggregation": "cluster-aggregation-include-all-nodes",
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-include-all-nodes",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods"],
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]


def test_host_labels_annotation_selection() -> None:
    """Test the import-annotations option"""
    # Option not set -> no annotations imported. This special case is covered
    # by test_parse_arguments. If test_parse_arguments is migrated, this
    # special case needs to be reconsidered.

    # Explicit no filtering
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "import-annotations": "include-annotations-as-host-labels",
            "monitored-objects": ["pods"],
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--include-annotations-as-host-labels",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]

    # Explicit filtering
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "import-annotations": (
                "include-matching-annotations-as-host-labels",
                "checkmk-monitoring$",
            ),
            "monitored-objects": ["pods"],
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--include-matching-annotations-as-host-labels",
        "checkmk-monitoring$",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]


def test_parse_namespace_patterns() -> None:
    parsed_params = special_agent_kube.parameter_parser(
        {
            "cluster-name": "cluster",
            "token": ("password", "token"),
            "kubernetes-api-server": {
                "endpoint_v2": "https://11.211.3.32",
                "verify-cert": False,
                "proxy": ("no_proxy", "no_proxy"),
            },
            "monitored-objects": ["pods"],
            "namespaces": ("namespace-include-patterns", ["default", "kube-system"]),
        }
    )
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == [
        "--cluster",
        "cluster",
        "--kubernetes-cluster-hostname",
        "host",
        "--token",
        PlainTextSecret(value="token", format="%s"),
        "--monitored-objects",
        "pods",
        "--namespace-include-patterns",
        "default",
        "--namespace-include-patterns",
        "kube-system",
        "--cluster-aggregation-exclude-node-roles",
        "control-plane",
        "infra",
        "--api-server-endpoint",
        "https://11.211.3.32",
        "--api-server-proxy",
        "NO_PROXY",
    ]


@pytest.mark.parametrize(
    "params, expected_arguments",
    [
        (
            {
                "cluster-name": "test",
                "token": ("password", "token"),
                "kubernetes-api-server": {
                    "endpoint_v2": "https://127.0.0.1",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "cluster-collector": {
                    "endpoint_v2": "https://127.0.0.1:20026",
                    "verify-cert": False,
                },
                "monitored-objects": ["pods"],
            },
            [
                "--cluster",
                "test",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="token", format="%s"),
                "--monitored-objects",
                "pods",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "https://127.0.0.1",
                "--api-server-proxy",
                "NO_PROXY",
            ],
        ),
        (
            {
                "cluster-name": "test",
                "token": ("password", "token"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://127.0.0.1:8080",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "cluster-collector": {
                    "endpoint_v2": "https://127.0.0.1:20026",
                    "verify-cert": False,
                },
                "monitored-objects": ["pods"],
            },
            [
                "--cluster",
                "test",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="token", format="%s"),
                "--monitored-objects",
                "pods",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "http://127.0.0.1:8080",
                "--api-server-proxy",
                "NO_PROXY",
            ],
        ),
        (
            {
                "cluster-name": "test",
                "token": ("password", "randomtoken"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://localhost:8080",
                    "verify-cert": True,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "cluster-collector": {
                    "endpoint_v2": "https://127.0.0.1:20026",
                    "verify-cert": True,
                },
                "monitored-objects": ["pods"],
            },
            [
                "--cluster",
                "test",
                "--kubernetes-cluster-hostname",
                "host",
                "--token",
                PlainTextSecret(value="randomtoken", format="%s"),
                "--monitored-objects",
                "pods",
                "--cluster-aggregation-exclude-node-roles",
                "control-plane",
                "infra",
                "--api-server-endpoint",
                "http://localhost:8080",
                "--verify-cert-api",
                "--api-server-proxy",
                "NO_PROXY",
            ],
        ),
    ],
)
@pytest.mark.usefixtures("fix_register")
def test_client_configuration_host(
    params: Mapping[str, object], expected_arguments: Sequence[str]
) -> None:
    parsed_params = special_agent_kube.parameter_parser(params)
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    assert commands[0].command_arguments == expected_arguments


@pytest.mark.parametrize(
    "params,expected_proxy_arg",
    [
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "cluster"),
                "kubernetes-api-server": {
                    "endpoint_v2": "https://11.211.3.32",
                    "verify-cert": False,
                    "proxy": ("no_proxy", "no_proxy"),
                },
                "monitored-objects": ["pods"],
            },
            "NO_PROXY",
        ),
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "cluster"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://11.211.3.32:8080",
                    "verify-cert": False,
                    "proxy": ("environment", "environment"),
                },
                "monitored-objects": ["pods"],
            },
            "FROM_ENVIRONMENT",
        ),
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "randomtoken"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://localhost:8001",
                    "verify-cert": False,
                    "proxy": ("url", "http://test:test@127.0.0.1:8080"),
                },
                "monitored-objects": ["pods"],
            },
            "http://test:test@127.0.0.1:8080",
        ),
        (
            {
                "cluster-name": "cluster",
                "token": ("password", "randomtoken"),
                "kubernetes-api-server": {
                    "endpoint_v2": "http://localhost:8001",
                    "verify-cert": False,
                },
                "monitored-objects": ["pods"],
            },
            "FROM_ENVIRONMENT",
        ),
    ],
)
@pytest.mark.usefixtures("fix_register")
def test_proxy_arguments(params: Mapping[str, object], expected_proxy_arg: str) -> None:
    parsed_params = special_agent_kube.parameter_parser(params)
    commands = list(special_agent_kube.commands_function(parsed_params, HOST_CONFIG, HTTP_PROXIES))

    assert len(commands) == 1
    arguments = commands[0].command_arguments

    assert isinstance(arguments, list)
    for argument, argument_after in zip(arguments[:-1], arguments[1:]):
        if argument == "--api-server-proxy":
            assert expected_proxy_arg == argument_after
            return
    assert False, "--api-server-proxy is missing"
