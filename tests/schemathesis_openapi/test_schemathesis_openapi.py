#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
import logging

import pytest
from hypothesis import given, strategies

from tests.schemathesis_openapi import settings
from tests.schemathesis_openapi.runners import run_crud_test, run_state_machine_test
from tests.schemathesis_openapi.schema import get_schema, parametrize_crud_endpoints

logger = logging.getLogger(__name__)
schema = get_schema()


@pytest.mark.type("schemathesis_openapi")
@schema.parametrize(endpoint="")
def test_openapi_stateless(case):
    """Run default, stateless schemathesis testing."""
    if case.path == "/domain-types/notification_rule/collections/all" and case.method in (
        "GET",
        "POST",
    ):
        pytest.skip(reason="Currently fails due to CMK-14375.")
    case.call_and_validate(allow_redirects=settings.allow_redirects)


@pytest.mark.skip(reason="Currently fails due to recursive schema references")
@pytest.mark.type("schemathesis_openapi")
def test_openapi_stateful():
    """Run stateful schemathesis testing."""
    run_state_machine_test(schema)


@pytest.mark.type("schemathesis_openapi")
@given(data=strategies.data())
@pytest.mark.parametrize(
    "endpoint", **parametrize_crud_endpoints(schema, ignore="site_connection|rule")
)
def test_openapi_crud(
    data: strategies.SearchStrategy,
    endpoint: dict[str, str],
) -> None:
    """Run schemathesis based CRUD testing."""
    run_crud_test(
        schema,
        data,
        endpoint["target"],
        endpoint["source"],
    )
