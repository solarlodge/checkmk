#!/usr/bin/env python3
# Copyright (C) 2020 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
import os
import typing
import urllib
from typing import Any

import pytest

from tests.testlib.rest_api_client import (
    ClientRegistry,
    Response,
    RestApiClient,
    RuleConditions,
    RuleProperties,
)

from cmk.utils import paths
from cmk.utils.rulesets.definition import RuleGroup
from cmk.utils.store import load_mk_file

import cmk.gui.watolib.check_mk_automations
import cmk.gui.watolib.rulespecs

DEFAULT_VALUE_RAW = """{
    "ignore_fs_types": ["tmpfs", "nfs", "smbfs", "cifs", "iso9660"],
    "never_ignore_mountpoints": ["~.*/omd/sites/[^/]+/tmp$"],
}"""

DEFAULT_CONDITIONS: RuleConditions = {
    "host_tags": [
        {
            "key": "criticality",
            "operator": "is",
            "value": "prod",
        },
        {
            "key": "networking",
            "operator": "is_not",
            "value": "wan",
        },
    ],
    "host_label_groups": [
        {
            "operator": "and",
            "label_group": [
                {
                    "operator": "and",
                    "label": "os:windows",
                }
            ],
        },
    ],
}


@pytest.fixture(scope="function", name="new_rule")
def new_rule_fixture(clients: ClientRegistry) -> tuple[Response, dict[str, Any]]:
    return _create_rule(
        clients,
        folder="/",
        comment="They made me do it!",
        description="This is my title for this very important rule.",
        documentation_url="http://example.com/",
    )


def _create_rule(
    clients: ClientRegistry,
    folder: str,
    comment: str = "",
    description: str = "",
    documentation_url: str = "",
    disabled: bool = False,
    ruleset: str = "inventory_df_rules",
    value: dict[str, Any] | list[Any] | tuple | str | None = None,
    value_raw: str | None = DEFAULT_VALUE_RAW,
    conditions: RuleConditions | None = None,
    expect_ok: bool = True,
) -> tuple[Response, dict[str, Any]]:
    if value is None:
        value = {
            "ignore_fs_types": ["tmpfs", "nfs", "smbfs", "cifs", "iso9660"],
            "never_ignore_mountpoints": ["~.*/omd/sites/[^/]+/tmp$"],
        }
    properties: RuleProperties = {
        "description": description,
        "comment": comment,
        "disabled": disabled,
    }
    if documentation_url:
        properties["documentation_url"] = documentation_url

    if conditions is None:
        conditions = DEFAULT_CONDITIONS

    values = {
        "ruleset": ruleset,
        "folder": folder,
        "properties": properties,
        "value_raw": value_raw,
        "conditions": conditions,
    }
    resp = clients.Rule.create(
        ruleset=ruleset,
        folder=folder,
        properties=properties,
        value_raw=value_raw,
        conditions=conditions,
        expect_ok=expect_ok,
    )
    return resp, values


@pytest.fixture(scope="function", name="test_folders")
def site_with_test_folders(clients: ClientRegistry) -> tuple[str, str]:
    test_folder_name_one = "test_folder_1"
    test_folder_name_two = "test_folder_2"
    clients.Folder.create(
        folder_name=test_folder_name_one,
        title=test_folder_name_one,
        parent="/",
        expect_ok=True,
    )
    clients.Folder.create(
        folder_name=test_folder_name_two,
        title=test_folder_name_two,
        parent="/",
        expect_ok=True,
    )
    return test_folder_name_one, test_folder_name_two


def test_openapi_get_non_existing_rule(clients: ClientRegistry) -> None:
    clients.Rule.get(rule_id="non_existing_rule_id", expect_ok=False).assert_status_code(404)


def test_openapi_create_rule_regression(clients: ClientRegistry) -> None:
    value_raw = '{"inodes_levels": (10.0, 5.0), "levels": [(0, (0, 0)), (0, (0.0, 0.0))], "magic": 0.8, "trend_perfdata": True}'
    r = clients.Rule.create(
        ruleset=RuleGroup.CheckgroupParameters("filesystem"),
        value_raw=value_raw,
        conditions={},
        folder="~",
        properties={"disabled": False, "description": "API2I"},
    )
    print(r)


def test_openapi_value_raw_is_unaltered(clients: ClientRegistry) -> None:
    value_raw = "{'levels': (10.0, 5.0)}"
    resp = clients.Rule.create(
        ruleset=RuleGroup.CheckgroupParameters("memory_percentage_used"),
        value_raw=value_raw,
        conditions={},
        folder="~",
        properties={"disabled": False},
    )
    resp2 = clients.Rule.get(rule_id=resp.json["id"])
    assert value_raw == resp2.json["extensions"]["value_raw"]


def test_openapi_value_active_check_http(clients: ClientRegistry) -> None:
    value_raw = """{
        "name": "Halli-gALLI",
        "host": {"address": "mimi.ch", "virthost": "mimi.ch"},
        "mode": (
            "url",
            {
                "uri": "/lala/misite.html",
                "ssl": "auto",
                "expect_string": "status:UP",
                "urlize": True,
            },
        ),
    }"""
    resp = clients.Rule.create(
        ruleset=RuleGroup.ActiveChecks("http"),
        value_raw=value_raw,
        conditions={},
        folder="~",
        properties={"disabled": False},
    )
    clients.Rule.get(rule_id=resp.json["id"])


def test_openapi_rules_href_escaped(clients: ClientRegistry) -> None:
    resp = clients.Ruleset.list(search_options="?used=0")
    ruleset = next(r for r in resp.json["value"] if RuleGroup.SpecialAgents("gcp") == r["id"])
    assert (
        ruleset["links"][0]["href"]
        == "http://localhost/NO_SITE/check_mk/api/1.0/objects/ruleset/special_agents%253Agcp"
    )


def test_openapi_create_rule_failure(clients: ClientRegistry) -> None:
    resp = clients.Rule.create(
        ruleset="host_groups",
        folder="~",
        properties={
            "description": "This is my title for this very important rule.",
            "comment": "They made me do it!",
            "documentation_url": "http://example.com/",
            "disabled": False,
        },
        value_raw="{}",
        conditions={},
        expect_ok=False,
    )
    resp.assert_status_code(400)
    # Its not really important that this text is in the response, just that this call failed.
    # assert "You have not defined any host group yet" in resp.json["detail"]


def test_openapi_create_rule(
    clients: ClientRegistry,
    new_rule: tuple[Response, dict[str, typing.Any]],
) -> None:
    new_resp, values = new_rule
    resp = clients.Ruleset.get(ruleset_id=values["ruleset"])
    assert resp.json["extensions"]["number_of_rules"] == 1
    # Also fetch the newly created rule and check if it's actually persisted.
    resp2 = clients.Rule.get(new_resp.json["id"])
    ext = resp2.json["extensions"]
    assert ext["ruleset"] == values["ruleset"]
    assert ext["folder"] == values["folder"]
    assert ext["properties"] == values["properties"]
    assert ext["conditions"].items() >= values["conditions"].items()
    # Check that the format on disk is as expected.
    rules_mk = os.path.join(paths.omd_root, "etc", "check_mk", "conf.d", "wato", "rules.mk")
    environ = load_mk_file(rules_mk, default={})
    stored_condition = environ[values["ruleset"]][0]["condition"]  # type: ignore[index]
    expected_condition = {
        "host_tags": {"criticality": "prod", "networking": {"$ne": "wan"}},
        "host_label_groups": [("and", [("and", "os:windows")])],
    }
    assert stored_condition == expected_condition


def test_create_rule_with_string_value(clients: ClientRegistry) -> None:
    resp = clients.Rule.create(
        ruleset=RuleGroup.ExtraHostConf("notification_options"),
        folder="/",
        properties={"description": "Test", "disabled": False},
        value_raw="'d,u,r,f,s'",
        conditions={},
    )
    assert resp.json["extensions"]["value_raw"] == "'d,u,r,f,s'"


def test_openapi_list_rules_with_hyphens(
    clients: ClientRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cmk.gui.watolib.rulespecs.CheckTypeGroupSelection,
        "get_elements",
        lambda x: {"fileinfo_groups": "some title"},
    )
    STATIC_CHECKS_FILEINFO_GROUPS = RuleGroup.StaticChecks("fileinfo-groups")
    _, result = _create_rule(
        clients,
        "/",
        ruleset=STATIC_CHECKS_FILEINFO_GROUPS,
        value_raw="('fileinfo_groups', '', {'group_patterns': []})",
    )
    assert result["ruleset"] == STATIC_CHECKS_FILEINFO_GROUPS
    resp2 = clients.Rule.list(ruleset=STATIC_CHECKS_FILEINFO_GROUPS)
    assert len(resp2.json["value"]) == 1
    assert resp2.json["value"][0]["extensions"]["ruleset"] == STATIC_CHECKS_FILEINFO_GROUPS


def test_openapi_list_rules(
    clients: ClientRegistry,
    new_rule: tuple[Response, dict[str, typing.Any]],
) -> None:
    _, values = new_rule
    rule_set = values["ruleset"]
    resp = clients.Rule.list(ruleset=rule_set)
    for entry in resp.json["value"]:
        assert entry["domainType"] == "rule"
    stored = resp.json["value"][0]["extensions"]
    assert stored["properties"]["disabled"] == values["properties"]["disabled"]
    assert stored["properties"]["comment"] == values["properties"]["comment"]
    # Do the complete round-trip check. Everything stored is also retrieved.
    assert stored["conditions"]["host_label_groups"] == values["conditions"]["host_label_groups"]
    assert stored["conditions"]["host_tags"] == values["conditions"]["host_tags"]


def test_openapi_delete_rule(
    api_client: RestApiClient,
    clients: ClientRegistry,
    new_rule: tuple[Response, dict[str, typing.Any]],
) -> None:
    resp, values = new_rule
    _resp = clients.Ruleset.get(ruleset_id=values["ruleset"])
    assert _resp.json["extensions"]["number_of_rules"] == 1
    api_client.follow_link(
        resp.json,
        ".../delete",
        headers={"If-Match": _resp.headers["ETag"]},
    ).assert_status_code(204)
    list_resp = clients.Ruleset.get(ruleset_id=values["ruleset"])
    assert list_resp.json["extensions"]["number_of_rules"] == 0
    api_client.follow_link(
        resp.json,
        ".../delete",
        expect_ok=False,
    ).assert_status_code(404)


@pytest.mark.parametrize("ruleset", ["host_groups", RuleGroup.SpecialAgents("gcp")])
def test_openapi_show_ruleset(clients: ClientRegistry, ruleset: str) -> None:
    resp = clients.Ruleset.get(ruleset_id=urllib.parse.quote(ruleset))
    assert resp.json["extensions"]["name"] == ruleset


def test_openapi_show_non_existing_ruleset(clients: ClientRegistry) -> None:
    # Request a ruleset that doesn't exist should return a 400 Bad Request.
    resp = clients.Ruleset.get(ruleset_id="non_existing_ruleset", expect_ok=False)
    resp.assert_status_code(404)


def test_openapi_list_rulesets(clients: ClientRegistry) -> None:
    resp = clients.Ruleset.list(search_options="?fulltext=cisco_qos&used=False")
    assert len(resp.json["value"]) == 2


def test_create_rule_old_label_format(
    clients: ClientRegistry,
    new_rule: tuple[Response, dict[str, typing.Any]],
) -> None:
    """This test can be removed when the old "host_labels" field is eventually removed."""

    # Create rule - new format
    _, values = new_rule

    # add field "host_labels" with the old format & remove the new field "host_label_groups"
    conditions: RuleConditions = {
        "host_tags": [
            {
                "key": "criticality",
                "operator": "is",
                "value": "prod",
            },
            {
                "key": "networking",
                "operator": "is_not",
                "value": "wan",
            },
        ],
        "host_labels": [{"key": "os", "operator": "is", "value": "windows"}],
    }

    clients.Rule.create(
        ruleset=values["ruleset"],
        folder=values["folder"],
        properties=values["properties"],
        value_raw=values["value_raw"],
        conditions=conditions,
    )


def test_create_rule_old_and_new_label_formats(
    clients: ClientRegistry,
    new_rule: tuple[Response, dict[str, typing.Any]],
) -> None:
    """This test can be removed when the old "host_labels" field is eventually removed."""
    # Create rule - new format
    _, values = new_rule

    # add field "host_labels" - Sending old format + new format
    conditions: RuleConditions = {
        "host_tags": [
            {
                "key": "criticality",
                "operator": "is",
                "value": "prod",
            },
            {
                "key": "networking",
                "operator": "is_not",
                "value": "wan",
            },
        ],
        "host_labels": [{"key": "os", "operator": "is", "value": "windows"}],
        "host_label_groups": [
            {"operator": "and", "label_group": [{"operator": "and", "label": "os:windows"}]}
        ],
    }

    resp = clients.Rule.create(
        ruleset=values["ruleset"],
        folder=values["folder"],
        properties=values["properties"],
        value_raw=values["value_raw"],
        conditions=conditions,
        expect_ok=False,
    )

    resp.assert_status_code(400)
    assert resp.json["fields"]["conditions"]["_schema"] == [
        "Please provide the field 'host_labels' OR 'host_label_groups', not both."
    ]


def test_create_rule_missing_operator(clients: ClientRegistry) -> None:
    conditions: RuleConditions = {"service_description": {"operator": "one_of"}}
    resp, _ = _create_rule(
        clients=clients,
        folder="/",
        comment="They made me do it!",
        description="This is my title for this very important rule.",
        documentation_url="http://example.com/",
        conditions=conditions,
        expect_ok=False,
    )
    resp.assert_status_code(400)


def test_create_rule_missing_match_on(clients: ClientRegistry) -> None:
    conditions: RuleConditions = {"service_description": {"match_on": []}}
    resp, _ = _create_rule(
        clients=clients,
        folder="/",
        comment="They made me do it!",
        description="This is my title for this very important rule.",
        documentation_url="http://example.com/",
        conditions=conditions,
        expect_ok=False,
    )
    resp.assert_status_code(400)


def test_create_rule_empty_match_on_str(clients: ClientRegistry) -> None:
    conditions: RuleConditions = {
        "host_name": {
            "operator": "one_of",
            "match_on": [""],
        }
    }
    resp, _ = _create_rule(
        clients=clients,
        folder="/",
        comment="They made me do it!",
        description="This is my title for this very important rule.",
        documentation_url="http://example.com/",
        conditions=conditions,
        expect_ok=False,
    )
    resp.assert_status_code(400)


def test_create_rule_no_conditions_nor_properties(clients: ClientRegistry) -> None:
    resp = clients.Rule.create(
        ruleset="active_checks:http",
        folder="/",
        value_raw='{"name": "check_localhost", "host": {"address": ("direct", "localhost")}, "mode": ("url", {})}',
    )

    clients.Rule.get(rule_id=resp.json["id"])


def test_create_rule_no_conditions(clients: ClientRegistry) -> None:
    resp = clients.Rule.create(
        ruleset="active_checks:http",
        folder="/",
        properties={},
        value_raw='{"name": "check_localhost", "host": {"address": ("direct", "localhost")}, "mode": ("url", {})}',
    )

    clients.Rule.get(rule_id=resp.json["id"])


def test_create_rule_no_properties(clients: ClientRegistry) -> None:
    resp = clients.Rule.create(
        ruleset="active_checks:http",
        folder="/",
        conditions={},
        value_raw='{"name": "check_localhost", "host": {"address": ("direct", "localhost")}, "mode": ("url", {})}',
    )

    clients.Rule.get(rule_id=resp.json["id"])
