#!/usr/bin/env python3
# Copyright (C) 2020 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.gui.openapi.endpoints import (
    acknowledgement,
    activate_changes,
    agent,
    audit_log,
    autocomplete,
    aux_tags,
    cert,
    comment,
    contact_group_config,
    downtime,
    folder_config,
    host,
    host_config,
    host_group_config,
    host_internal,
    host_tag_group,
    metric,
    notification_rules,
    password,
    rule,
    ruleset,
    service,
    service_discovery,
    service_group_config,
    site_management,
    time_periods,
    user_config,
    user_role,
    version,
)
from cmk.gui.openapi.restful_objects.registry import EndpointRegistry


def register(endpoint_registry: EndpointRegistry) -> None:
    acknowledgement.register(endpoint_registry)
    activate_changes.register(endpoint_registry)
    agent.register(endpoint_registry)
    audit_log.register(endpoint_registry)
    autocomplete.register(endpoint_registry)
    aux_tags.register(endpoint_registry)
    cert.register(endpoint_registry)
    comment.register(endpoint_registry)
    contact_group_config.register(endpoint_registry)
    downtime.register(endpoint_registry)
    folder_config.register(endpoint_registry)
    host.register(endpoint_registry)
    host_config.register(endpoint_registry)
    host_group_config.register(endpoint_registry)
    host_internal.register(endpoint_registry)
    host_tag_group.register(endpoint_registry)
    metric.register(endpoint_registry)
    notification_rules.register(endpoint_registry)
    password.register(endpoint_registry)
    rule.register(endpoint_registry)
    ruleset.register(endpoint_registry)
    service.register(endpoint_registry)
    service_discovery.register(endpoint_registry)
    service_group_config.register(endpoint_registry)
    site_management.register(endpoint_registry)
    time_periods.register(endpoint_registry)
    user_config.register(endpoint_registry)
    user_role.register(endpoint_registry)
    version.register(endpoint_registry)
