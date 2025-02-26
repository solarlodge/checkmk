#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


from cmk.rulesets.v1 import Localizable
from cmk.rulesets.v1.form_specs import DefaultValue, InputHint
from cmk.rulesets.v1.form_specs.basic import Integer, TimeMagnitude, TimeSpan
from cmk.rulesets.v1.form_specs.composed import DictElement, Dictionary
from cmk.rulesets.v1.form_specs.levels import LevelDirection, Levels, LevelsConfigModel
from cmk.rulesets.v1.migrations import (
    migrate_to_upper_float_levels,
    migrate_to_upper_integer_levels,
)
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, Topic

_DAY = 24 * 3600


def _parameter_form_wlan_controllers_clients() -> Dictionary:
    return Dictionary(
        elements={
            "clients": DictElement[LevelsConfigModel[int]](
                parameter_form=Levels[int](
                    title=Localizable("Maximum number of clients"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Integer(),
                    predictive=None,
                    migrate=migrate_to_upper_integer_levels,
                    prefill_fixed_levels=InputHint(value=(0, 0)),
                ),
            )
        },
    )


rule_spec_cisco_prime_wlan_controller_clients = CheckParameters(
    name="cisco_prime_wlan_controller_clients",
    topic=Topic.OPERATING_SYSTEM,
    condition=HostAndItemCondition(item_title=Localizable("Clients")),
    parameter_form=_parameter_form_wlan_controllers_clients,
    title=Localizable("Cisco Prime WLAN Controller Clients"),
)


def _parameter_form_wlan_controllers_access_points() -> Dictionary:
    return Dictionary(
        elements={
            "access_points": DictElement[LevelsConfigModel[int]](
                parameter_form=Levels[int](
                    title=Localizable("Maximum number of access points"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=Integer(),
                    predictive=None,
                    migrate=migrate_to_upper_integer_levels,
                    prefill_fixed_levels=InputHint(value=(0, 0)),
                ),
            ),
        },
    )


rule_spec_cisco_prime_wlan_controller_access_points = CheckParameters(
    name="cisco_prime_wlan_controller_access_points",
    topic=Topic.OPERATING_SYSTEM,
    condition=HostAndItemCondition(item_title=Localizable("Access points")),
    parameter_form=_parameter_form_wlan_controllers_access_points,
    title=Localizable("Cisco Prime WLAN Controller Access Points"),
)


def _parameter_form_wlan_controllers_last_backup() -> Dictionary:
    return Dictionary(
        elements={
            "last_backup": DictElement[LevelsConfigModel[float]](
                parameter_form=Levels[float](
                    title=Localizable("Time since last backup"),
                    level_direction=LevelDirection.UPPER,
                    form_spec_template=TimeSpan(
                        displayed_magnitudes=[
                            TimeMagnitude.DAY,
                            TimeMagnitude.HOUR,
                            TimeMagnitude.MINUTE,
                        ],
                    ),
                    prefill_fixed_levels=DefaultValue((7 * _DAY, 30 * _DAY)),
                    predictive=None,
                    migrate=migrate_to_upper_float_levels,
                ),
            )
        },
    )


rule_spec_cisco_prime_wlan_controller_last_backup = CheckParameters(
    name="cisco_prime_wlan_controller_last_backup",
    topic=Topic.OPERATING_SYSTEM,
    condition=HostAndItemCondition(item_title=Localizable("Last backup")),
    parameter_form=_parameter_form_wlan_controllers_last_backup,
    title=Localizable("Cisco Prime WLAN Controller Last Backup"),
)
