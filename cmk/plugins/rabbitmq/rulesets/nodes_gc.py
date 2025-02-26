#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.
from collections.abc import Mapping

from cmk.rulesets.v1 import Localizable
from cmk.rulesets.v1.form_specs import InputHint
from cmk.rulesets.v1.form_specs.basic import DataSize, Float, IECMagnitude, Integer
from cmk.rulesets.v1.form_specs.composed import DictElement, Dictionary
from cmk.rulesets.v1.form_specs.levels import LevelDirection, Levels
from cmk.rulesets.v1.rule_specs import CheckParameters, HostAndItemCondition, Topic

MAGNITUDES = tuple(IECMagnitude)[:5]


def _migrate_levels(
    value: object,
) -> Mapping[str, tuple[str, tuple[int, int] | tuple[float, float] | None]]:
    if not isinstance(value, dict):
        raise TypeError(value)

    migrated = {}

    for key, levels in value.items():
        if not isinstance(levels, tuple):
            raise TypeError(value)

        if levels[0] not in ("no_levels", "fixed"):
            migrated[key] = ("fixed", levels)
        else:
            migrated[key] = levels

    return migrated


def _parameter_form_rabbitmq_nodes_gc() -> Dictionary:
    return Dictionary(
        elements={
            "gc_num_upper": DictElement(
                parameter_form=Levels(
                    form_spec_template=Integer(unit=Localizable("runs")),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Upper level for total number of GC runs"),
                )
            ),
            "gc_num_rate_upper": DictElement(
                parameter_form=Levels(
                    form_spec_template=Float(unit=Localizable("1/s")),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=InputHint((0.0, 0.0)),
                    predictive=None,
                    title=Localizable("Upper level for GC run rate"),
                )
            ),
            "gc_num_rate_lower": DictElement(
                parameter_form=Levels(
                    form_spec_template=Float(unit=Localizable("1/s")),
                    level_direction=LevelDirection.LOWER,
                    prefill_fixed_levels=InputHint((0.0, 0.0)),
                    predictive=None,
                    title=Localizable("Lower level for GC run rate"),
                )
            ),
            "gc_bytes_reclaimed_upper": DictElement(
                parameter_form=Levels(
                    form_spec_template=DataSize(displayed_magnitudes=MAGNITUDES),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Absolute levels for memory reclaimed by GC"),
                )
            ),
            "gc_bytes_reclaimed_rate_upper": DictElement(
                parameter_form=Levels(
                    form_spec_template=DataSize(displayed_magnitudes=MAGNITUDES),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Upper level for rate of memory reclaimed by GC"),
                )
            ),
            "gc_bytes_reclaimed_rate_lower": DictElement(
                parameter_form=Levels(
                    form_spec_template=DataSize(displayed_magnitudes=MAGNITUDES),
                    level_direction=LevelDirection.LOWER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Lower level for rate of memory reclaimed by GC"),
                )
            ),
            "runqueue_upper": DictElement(
                parameter_form=Levels(
                    form_spec_template=Integer(),
                    level_direction=LevelDirection.UPPER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Upper level for runtime run queue"),
                )
            ),
            "runqueue_lower": DictElement(
                parameter_form=Levels(
                    form_spec_template=Integer(),
                    level_direction=LevelDirection.LOWER,
                    prefill_fixed_levels=InputHint((0, 0)),
                    predictive=None,
                    title=Localizable("Lower level for runtime run queue"),
                )
            ),
        },
        migrate=_migrate_levels,
    )


rule_spec_rabbitmq_nodes_gc = CheckParameters(
    name="rabbitmq_nodes_gc",
    topic=Topic.APPLICATIONS,
    parameter_form=_parameter_form_rabbitmq_nodes_gc,
    title=Localizable("RabbitMQ nodes GC"),
    condition=HostAndItemCondition(item_title=Localizable("Node name")),
)
