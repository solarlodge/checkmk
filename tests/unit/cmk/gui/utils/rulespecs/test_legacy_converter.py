#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from collections.abc import Sequence
from functools import partial
from typing import TypeVar

import pytest

from cmk.utils.rulesets.definition import RuleGroup
from cmk.utils.version import Edition

import cmk.gui.graphing._valuespecs as legacy_graphing_valuespecs
import cmk.gui.valuespec as legacy_valuespecs
from cmk.gui import inventory as legacy_inventory_groups
from cmk.gui import wato as legacy_wato
from cmk.gui.exceptions import MKUserError
from cmk.gui.i18n import _
from cmk.gui.utils.autocompleter_config import ContextAutocompleterConfig
from cmk.gui.utils.rule_specs.legacy_converter import (
    _convert_to_custom_group,
    _convert_to_legacy_levels,
    _convert_to_legacy_rulespec_group,
    _convert_to_legacy_valuespec,
    _to_generated_builtin_sub_group,
    convert_to_legacy_rulespec,
)
from cmk.gui.utils.rule_specs.loader import RuleSpec as APIV1RuleSpec
from cmk.gui.valuespec import LegacyBinaryUnit, LegacyDataSize
from cmk.gui.wato import _check_mk_configuration as legacy_cmk_config_groups
from cmk.gui.wato import _rulespec_groups as legacy_wato_groups
from cmk.gui.wato import pages as legacy_page_groups
from cmk.gui.watolib import rulespec_groups as legacy_rulespec_groups
from cmk.gui.watolib import rulespecs as legacy_rulespecs
from cmk.gui.watolib import timeperiods as legacy_timeperiods

import cmk.rulesets.v1 as api_v1
from cmk.rulesets.v1.form_specs import FormSpec


def _v1_custom_text_validate(value: str) -> None:
    api_v1.validators.DisallowEmpty(error_msg=api_v1.Localizable("Fill this"))(value)
    api_v1.validators.MatchRegex(
        regex=r"^[^.\r\n]+$", error_msg=api_v1.Localizable("No dot allowed")
    )(value)

    if value == "admin":
        raise api_v1.validators.ValidationError(api_v1.Localizable("Forbidden"))


def _legacy_custom_text_validate(value: str, varprefix: str) -> None:
    if value == "admin":
        raise MKUserError(varprefix, _("Forbidden"))


@pytest.mark.parametrize(
    ["new_valuespec", "expected"],
    [
        pytest.param(
            api_v1.form_specs.basic.HostState(),
            legacy_valuespecs.DropdownChoice(
                choices=[
                    (0, _("Up")),
                    (1, _("Down")),
                    (2, _("Unreachable")),
                ],
                sorted=False,
                default_value=0,
            ),
            id="minimal HostState",
        ),
        pytest.param(
            api_v1.form_specs.basic.HostState(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help text"),
                prefill=api_v1.form_specs.DefaultValue(1),
            ),
            legacy_valuespecs.DropdownChoice(
                choices=[
                    (0, _("Up")),
                    (1, _("Down")),
                    (2, _("Unreachable")),
                ],
                sorted=False,
                title=_("title"),
                help=_("help text"),
                default_value=1,
            ),
            id="MonitoringState",
        ),
        pytest.param(
            api_v1.form_specs.basic.ServiceState(),
            legacy_valuespecs.MonitoringState(),
            id="minimal MonitoringState",
        ),
        pytest.param(
            api_v1.form_specs.basic.ServiceState(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_valuespecs.MonitoringState(
                title=_("title"),
                help=_("help text"),
                default_value=0,
            ),
            id="MonitoringState",
        ),
        pytest.param(
            api_v1.form_specs.composed.Dictionary(elements={}),
            legacy_valuespecs.Dictionary(elements=[]),
            id="minimal Dictionary",
        ),
        pytest.param(
            api_v1.form_specs.composed.Dictionary(
                elements={
                    "key_req": api_v1.form_specs.composed.DictElement(
                        parameter_form=api_v1.form_specs.basic.ServiceState(
                            title=api_v1.Localizable("title")
                        ),
                        required=True,
                    ),
                    "key_read_only": api_v1.form_specs.composed.DictElement(
                        parameter_form=api_v1.form_specs.basic.ServiceState(
                            title=api_v1.Localizable("title")
                        ),
                        read_only=True,
                    ),
                },
                title=api_v1.Localizable("Configuration title"),
                help_text=api_v1.Localizable("Helpful description"),
                deprecated_elements=("old_key", "another_old_key"),
                no_elements_text=api_v1.Localizable("No elements specified"),
            ),
            legacy_valuespecs.Dictionary(
                elements=[
                    ("key_req", legacy_valuespecs.MonitoringState(title=_("title"))),
                    ("key_read_only", legacy_valuespecs.MonitoringState(title=_("title"))),
                ],
                title=_("Configuration title"),
                help=_("Helpful description"),
                empty_text=_("No elements specified"),
                required_keys=["key_req"],
                show_more_keys=[],
                hidden_keys=["key_read_only"],
                ignored_keys=["old_key", "another_old_key"],
            ),
            id="Dictionary",
        ),
        pytest.param(
            api_v1.form_specs.basic.Integer(),
            legacy_valuespecs.Integer(),
            id="minimal Integer",
        ),
        pytest.param(
            api_v1.form_specs.basic.Integer(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help"),
                label=api_v1.Localizable("label"),
                unit=api_v1.Localizable("days"),
                prefill=api_v1.form_specs.DefaultValue(-1),
                custom_validate=lambda x: None,
            ),
            legacy_valuespecs.Integer(
                title=_("title"),
                help=_("help"),
                label=_("label"),
                unit=_("days"),
                default_value=-1,
                validate=lambda x, y: None,
            ),
            id="Integer",
        ),
        pytest.param(
            api_v1.form_specs.basic.Float(),
            legacy_valuespecs.Float(display_format="%r"),
            id="minimal Float",
        ),
        pytest.param(
            api_v1.form_specs.basic.Float(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help"),
                label=api_v1.Localizable("label"),
                unit=api_v1.Localizable("1/s"),
                prefill=api_v1.form_specs.DefaultValue(-1.0),
                custom_validate=lambda x: None,
            ),
            legacy_valuespecs.Float(
                title=_("title"),
                help=_("help"),
                label=_("label"),
                display_format="%r",
                unit=_("1/s"),
                default_value=-1.0,
                validate=lambda x, y: None,
            ),
            id="Float",
        ),
        pytest.param(
            api_v1.form_specs.basic.DataSize(
                displayed_magnitudes=tuple(api_v1.form_specs.basic.SIMagnitude)[:5]
            ),
            LegacyDataSize(
                units=[
                    LegacyBinaryUnit.Byte,
                    LegacyBinaryUnit.KB,
                    LegacyBinaryUnit.MB,
                    LegacyBinaryUnit.GB,
                    LegacyBinaryUnit.TB,
                ],
            ),
            id="minimal DataSize",
        ),
        pytest.param(
            api_v1.form_specs.basic.DataSize(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help"),
                label=api_v1.Localizable("label"),
                displayed_magnitudes=(
                    api_v1.form_specs.basic.SIMagnitude.KILO,
                    api_v1.form_specs.basic.SIMagnitude.EXA,
                ),
                prefill=api_v1.form_specs.DefaultValue(-1),
                custom_validate=lambda x: None,
            ),
            LegacyDataSize(
                title=_("title"),
                help=_("help"),
                label=_("label"),
                units=[
                    LegacyBinaryUnit.KB,
                    LegacyBinaryUnit.EB,
                ],
                default_value=-1,
                validate=lambda x, y: None,
            ),
            id="DataSize",
        ),
        pytest.param(
            api_v1.form_specs.basic.Percentage(),
            legacy_valuespecs.Percentage(display_format="%r"),
            id="minimal Percentage",
        ),
        pytest.param(
            api_v1.form_specs.basic.Percentage(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help"),
                label=api_v1.Localizable("label"),
                prefill=api_v1.form_specs.DefaultValue(-1.0),
                custom_validate=lambda x: None,
            ),
            legacy_valuespecs.Percentage(
                title=_("title"),
                help=_("help"),
                label=_("label"),
                display_format="%r",
                default_value=-1.0,
                validate=lambda x, y: None,
            ),
            id="Percentage",
        ),
        pytest.param(
            api_v1.form_specs.basic.Text(),
            legacy_valuespecs.TextInput(placeholder=""),
            id="minimal TextInput",
        ),
        pytest.param(
            api_v1.form_specs.basic.Text(custom_validate=api_v1.validators.DisallowEmpty()),
            legacy_valuespecs.TextInput(
                placeholder="",
                allow_empty=False,
                validate=lambda _x, _y: None,  # ignored by test
            ),
            id="TextInput empty disallowed",
        ),
        pytest.param(
            api_v1.form_specs.basic.Text(
                title=api_v1.Localizable("spec title"),
                label=api_v1.Localizable("spec label"),
                macro_support=True,
                help_text=api_v1.Localizable("help text"),
                prefill=api_v1.form_specs.InputHint("myname"),
                custom_validate=_v1_custom_text_validate,
            ),
            legacy_valuespecs.TextInput(
                title=_("spec title"),
                label=_("spec label"),
                placeholder="myname",
                help=_(
                    "help text This field supports the use of macros. The corresponding plugin replaces the macros with the actual values."
                ),
                validate=_legacy_custom_text_validate,
            ),
            id="TextInput",
        ),
        pytest.param(
            api_v1.form_specs.basic.RegularExpression(
                predefined_help_text=api_v1.form_specs.basic.MatchingScope.INFIX,
            ),
            legacy_valuespecs.RegExp(
                mode=legacy_valuespecs.RegExp.infix, case_sensitive=True, placeholder=""
            ),
            id="minimal RegularExpression",
        ),
        pytest.param(
            api_v1.form_specs.basic.RegularExpression(
                predefined_help_text=api_v1.form_specs.basic.MatchingScope.PREFIX,
                title=api_v1.Localizable("spec title"),
                label=api_v1.Localizable("spec label"),
                help_text=api_v1.Localizable("help text"),
                prefill=api_v1.form_specs.DefaultValue("mypattern$"),
                custom_validate=_v1_custom_text_validate,
            ),
            legacy_valuespecs.RegExp(
                mode=legacy_valuespecs.RegExp.prefix,
                case_sensitive=True,
                title=_("spec title"),
                label=_("spec label"),
                help=_("help text"),
                default_value="mypattern$",
                validate=_legacy_custom_text_validate,
            ),
            id="RegularExpression",
        ),
        pytest.param(
            api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(elements=[]),
            legacy_valuespecs.Tuple(elements=[]),
            id="minimal Tuple",
        ),
        pytest.param(
            api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(
                elements=[
                    api_v1.form_specs.basic.Text(title=api_v1.Localizable("child title 1")),
                    api_v1.form_specs.basic.Text(title=api_v1.Localizable("child title 2")),
                ],
                title=api_v1.Localizable("parent title"),
                help_text=api_v1.Localizable("parent help"),
            ),
            legacy_valuespecs.Tuple(
                elements=[
                    legacy_valuespecs.TextInput(title=_("child title 1"), placeholder=""),
                    legacy_valuespecs.TextInput(title=_("child title 2"), placeholder=""),
                ],
                title=_("parent title"),
                help=_("parent help"),
            ),
            id="Tuple",
        ),
        pytest.param(
            api_v1.form_specs.basic.SingleChoice(elements=[]),
            legacy_valuespecs.DropdownChoice(
                choices=[], invalid_choice="complain", no_preselect_title="Please choose"
            ),
            id="minimal DropdownChoice",
        ),
        pytest.param(
            api_v1.form_specs.basic.SingleChoice(
                elements=[
                    api_v1.form_specs.basic.SingleChoiceElement(
                        name="true", title=api_v1.Localizable("Enabled")
                    ),
                    api_v1.form_specs.basic.SingleChoiceElement(
                        name="false", title=api_v1.Localizable("Disabled")
                    ),
                ],
                no_elements_text=api_v1.Localizable("No elements"),
                deprecated_elements=(),
                frozen=True,
                title=api_v1.Localizable("title"),
                label=api_v1.Localizable("label"),
                help_text=api_v1.Localizable("help text"),
                prefill=api_v1.form_specs.DefaultValue("true"),
                invalid_element_validation=api_v1.form_specs.basic.InvalidElementValidator(
                    mode=api_v1.form_specs.basic.InvalidElementMode.KEEP,
                    display=api_v1.Localizable("invalid choice title"),
                    error_msg=api_v1.Localizable("invalid choice msg"),
                ),
            ),
            legacy_valuespecs.DropdownChoice(
                choices=[("true", _("Enabled")), ("false", _("Disabled"))],
                empty_text=_("No elements"),
                deprecated_choices=[],
                read_only=True,
                title=_("title"),
                label=_("label"),
                help=_("help text"),
                default_value="true",
                invalid_choice=None,
                invalid_choice_title=_("invalid choice title"),
                invalid_choice_error=_("invalid choice msg"),
            ),
            id="DropdownChoice",
        ),
        pytest.param(
            api_v1.form_specs.composed.CascadingSingleChoice(elements=[]),
            legacy_valuespecs.CascadingDropdown(choices=[], no_preselect_title="Please choose"),
            id="minimal CascadingDropdown",
        ),
        pytest.param(
            api_v1.form_specs.composed.CascadingSingleChoice(
                elements=[
                    api_v1.form_specs.composed.CascadingSingleChoiceElement(
                        name="first",
                        title=api_v1.Localizable("Spec title"),
                        parameter_form=api_v1.form_specs.basic.Text(),
                    )
                ],
                title=api_v1.Localizable("parent title"),
                help_text=api_v1.Localizable("parent help"),
                label=api_v1.Localizable("parent label"),
                prefill=api_v1.form_specs.DefaultValue("first"),
            ),
            legacy_valuespecs.CascadingDropdown(
                choices=[("first", _("Spec title"), legacy_valuespecs.TextInput(placeholder=""))],
                title=_("parent title"),
                help=_("parent help"),
                label=_("parent label"),
                default_value=("first", ""),
            ),
            id="CascadingDropdown",
        ),
        pytest.param(
            api_v1.form_specs.composed.List(
                element_template=api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(elements=[])
            ),
            legacy_valuespecs.ListOf(
                valuespec=legacy_valuespecs.Tuple(elements=[]),
                add_label="Add new entry",
                del_label="Remove this entry",
                text_if_empty="No entries",
            ),
            id="minimal ListOf",
        ),
        pytest.param(
            api_v1.form_specs.composed.List(
                element_template=api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(
                    elements=[
                        api_v1.form_specs.basic.Text(),
                        api_v1.form_specs.basic.Integer(unit=api_v1.Localizable("km")),
                    ]
                ),
                title=api_v1.Localizable("list title"),
                help_text=api_v1.Localizable("list help"),
                editable_order=False,
                add_element_label=api_v1.Localizable("Add item"),
                remove_element_label=api_v1.Localizable("Remove item"),
                no_element_label=api_v1.Localizable("No items"),
            ),
            legacy_valuespecs.ListOf(
                valuespec=legacy_valuespecs.Tuple(
                    elements=[
                        legacy_valuespecs.TextInput(placeholder=""),
                        legacy_valuespecs.Integer(unit="km"),
                    ]
                ),
                title="list title",
                help="list help",
                add_label="Add item",
                del_label="Remove item",
                movable=False,
                text_if_empty="No items",
            ),
            id="ListOf",
        ),
        pytest.param(
            api_v1.form_specs.basic.FixedValue(value=True),
            legacy_valuespecs.FixedValue(value=True, totext=""),
            id="minimal FixedValue",
        ),
        pytest.param(
            api_v1.form_specs.basic.FixedValue(
                value="enabled",
                title=api_v1.Localizable("Enable the option"),
                label=api_v1.Localizable("The option is enabled"),
                help_text=api_v1.Localizable("Help text"),
            ),
            legacy_valuespecs.FixedValue(
                value="enabled",
                title=_("Enable the option"),
                totext=_("The option is enabled"),
                help=_("Help text"),
            ),
            id="FixedValue",
        ),
        pytest.param(
            api_v1.form_specs.basic.TimeSpan(
                # reverse just to keep the test simple
                displayed_magnitudes=tuple(reversed(api_v1.form_specs.basic.TimeMagnitude))
            ),
            legacy_valuespecs.TimeSpan(),
            id="minimal TimeSpan",
        ),
        pytest.param(
            api_v1.form_specs.basic.TimeSpan(
                title=api_v1.Localizable("age title"),
                label=api_v1.Localizable("age label"),
                help_text=api_v1.Localizable("help text"),
                displayed_magnitudes=[
                    api_v1.form_specs.basic.TimeMagnitude.DAY,
                    api_v1.form_specs.basic.TimeMagnitude.HOUR,
                    api_v1.form_specs.basic.TimeMagnitude.MINUTE,
                    api_v1.form_specs.basic.TimeMagnitude.SECOND,
                ],
                prefill=api_v1.form_specs.DefaultValue(100),
            ),
            legacy_valuespecs.TimeSpan(
                title=_("age title"),
                label=_("age label"),
                help=_("help text"),
                display=["days", "hours", "minutes", "seconds"],
                default_value=100,
            ),
            id="TimeSpan",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Proxy(),
            legacy_valuespecs.CascadingDropdown(
                title=_("HTTP proxy"),
                default_value=("environment", "environment"),
                choices=[
                    (
                        "environment",
                        _("Use from environment"),
                        legacy_valuespecs.FixedValue(
                            value="environment",
                            help=_(
                                "Use the proxy settings from the environment variables. The variables <tt>NO_PROXY</tt>, "
                                "<tt>HTTP_PROXY</tt> and <tt>HTTPS_PROXY</tt> are taken into account during execution. "
                                "Have a look at the python requests module documentation for further information. Note "
                                "that these variables must be defined as a site-user in ~/etc/environment and that "
                                "this might affect other notification methods which also use the requests module."
                            ),
                            totext=_(
                                "Use proxy settings from the process environment. This is the default."
                            ),
                        ),
                    ),
                    (
                        "no_proxy",
                        _("Connect without proxy"),
                        legacy_valuespecs.FixedValue(
                            value=None,
                            totext=_(
                                "Connect directly to the destination instead of using a proxy."
                            ),
                        ),
                    ),
                    (
                        "global",
                        _("Use globally configured proxy"),
                        legacy_valuespecs.DropdownChoice(
                            choices=lambda: [],
                            sorted=True,
                        ),
                    ),
                    (
                        "url",
                        _("Use explicit proxy settings"),
                        legacy_valuespecs.Url(
                            title=_("Proxy URL"),
                            default_scheme="http",
                            allowed_schemes=frozenset(
                                {"http", "https", "socks4", "socks4a", "socks5", "socks5h"}
                            ),
                        ),
                    ),
                ],
                sorted=False,
            ),
            id="minimal HTTPProxy",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Proxy(
                allowed_schemas=frozenset(
                    {
                        api_v1.form_specs.preconfigured.ProxySchema.HTTP,
                        api_v1.form_specs.preconfigured.ProxySchema.HTTPS,
                    }
                ),
                title=api_v1.Localizable("age title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_valuespecs.CascadingDropdown(
                title=_("HTTP proxy"),
                default_value=("environment", "environment"),
                choices=[
                    (
                        "environment",
                        _("Use from environment"),
                        legacy_valuespecs.FixedValue(
                            value="environment",
                            help=_(
                                "Use the proxy settings from the environment variables. The variables <tt>NO_PROXY</tt>, "
                                "<tt>HTTP_PROXY</tt> and <tt>HTTPS_PROXY</tt> are taken into account during execution. "
                                "Have a look at the python requests module documentation for further information. Note "
                                "that these variables must be defined as a site-user in ~/etc/environment and that "
                                "this might affect other notification methods which also use the requests module."
                            ),
                            totext=_(
                                "Use proxy settings from the process environment. This is the default."
                            ),
                        ),
                    ),
                    (
                        "no_proxy",
                        _("Connect without proxy"),
                        legacy_valuespecs.FixedValue(
                            value=None,
                            totext=_(
                                "Connect directly to the destination instead of using a proxy."
                            ),
                        ),
                    ),
                    (
                        "global",
                        _("Use globally configured proxy"),
                        legacy_valuespecs.DropdownChoice(
                            choices=lambda: [],
                            sorted=True,
                        ),
                    ),
                    (
                        "url",
                        _("Use explicit proxy settings"),
                        legacy_valuespecs.Url(
                            title=_("Proxy URL"),
                            default_scheme="http",
                            allowed_schemes=frozenset({"http", "https"}),
                        ),
                    ),
                ],
                sorted=False,
            ),
            id="HTTPProxy",
        ),
        pytest.param(
            api_v1.form_specs.basic.BooleanChoice(),
            legacy_valuespecs.Checkbox(default_value=False),
            id="minimal BooleanChoice",
        ),
        pytest.param(
            api_v1.form_specs.basic.BooleanChoice(
                title=api_v1.Localizable("boolean choice title"),
                label=api_v1.Localizable("boolean choice label"),
                help_text=api_v1.Localizable("help text"),
                prefill=api_v1.form_specs.DefaultValue(True),
            ),
            legacy_valuespecs.Checkbox(
                title=_("boolean choice title"),
                label=_("boolean choice label"),
                help=_("help text"),
                default_value=True,
            ),
            id="BooleanChoice",
        ),
        pytest.param(
            api_v1.form_specs.basic.FileUpload(),
            legacy_valuespecs.FileUpload(allow_empty=True),
            id="minimal FileUpload",
        ),
        pytest.param(
            api_v1.form_specs.basic.FileUpload(
                title=api_v1.Localizable("my title"),
                help_text=api_v1.Localizable("help text"),
                extensions=("txt", "rst"),
                mime_types=("text/plain",),
            ),
            legacy_valuespecs.FileUpload(
                title=_("my title"),
                help=_("help text"),
                allowed_extensions=("txt", "rst"),
                mime_types=("text/plain",),
                allow_empty=True,
            ),
            id="FileUpload",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Metric(),
            legacy_graphing_valuespecs.MetricName(
                title=_("Metric"),
                help=_("Select from a list of metrics known to Checkmk"),
            ),
            id="minimal Metric",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Metric(
                title=api_v1.Localizable("metric title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_graphing_valuespecs.MetricName(
                title=_("metric title"),
                help=_("help text"),
            ),
            id="Metric",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.MonitoredHost(),
            legacy_valuespecs.MonitoredHostname(
                title=_("Host name"),
                help=_("Select from a list of host names known to Checkmk"),
                autocompleter=ContextAutocompleterConfig(
                    ident=legacy_valuespecs.MonitoredHostname.ident,
                    strict=True,
                    show_independent_of_context=True,
                ),
            ),
            id="minimal MonitoredHost",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.MonitoredHost(
                title=api_v1.Localizable("host title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_valuespecs.MonitoredHostname(
                title=_("host title"),
                help=_("help text"),
                autocompleter=ContextAutocompleterConfig(
                    ident=legacy_valuespecs.MonitoredHostname.ident,
                    strict=True,
                    show_independent_of_context=True,
                ),
            ),
            id="MonitoredHost",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.MonitoredService(),
            legacy_valuespecs.MonitoredServiceDescription(
                title=_("Service description"),
                help=_("Select from a list of service descriptions known to Checkmk"),
                autocompleter=ContextAutocompleterConfig(
                    ident=legacy_valuespecs.MonitoredServiceDescription.ident,
                    strict=True,
                    show_independent_of_context=True,
                ),
            ),
            id="minimal MonitoredService",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.MonitoredService(
                title=api_v1.Localizable("service title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_valuespecs.MonitoredServiceDescription(
                title=_("service title"),
                help=_("help text"),
                autocompleter=ContextAutocompleterConfig(
                    ident=legacy_valuespecs.MonitoredServiceDescription.ident,
                    strict=True,
                    show_independent_of_context=True,
                ),
            ),
            id="MonitoredService",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Password(),
            legacy_page_groups.IndividualOrStoredPassword(allow_empty=False),
            id="minimal Password",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.Password(
                title=api_v1.Localizable("password title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_page_groups.IndividualOrStoredPassword(
                title=_("password title"),
                help=_("help text"),
                allow_empty=False,
            ),
            id="Password",
        ),
        pytest.param(
            api_v1.form_specs.composed.MultipleChoice(
                elements=[
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="first", title=api_v1.Localizable("First")
                    )
                ]
            ),
            legacy_valuespecs.ListChoice(choices=[("first", _("First"))], default_value=()),
            id="minimal MultipleChoice",
        ),
        pytest.param(
            api_v1.form_specs.composed.MultipleChoice(
                title=api_v1.Localizable("my title"),
                help_text=api_v1.Localizable("help text"),
                elements=[
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="first", title=api_v1.Localizable("First")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="second", title=api_v1.Localizable("Second")
                    ),
                ],
                show_toggle_all=True,
                prefill=api_v1.form_specs.DefaultValue(("first", "second")),
            ),
            legacy_valuespecs.ListChoice(
                choices=[("first", _("First")), ("second", _("Second"))],
                toggle_all=True,
                title=_("my title"),
                help=_("help text"),
                default_value=["first", "second"],
            ),
            id="MultipleChoice",
        ),
        pytest.param(
            api_v1.form_specs.composed.MultipleChoice(
                title=api_v1.Localizable("my title"),
                help_text=api_v1.Localizable("help text"),
                elements=[
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="first", title=api_v1.Localizable("First")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="second", title=api_v1.Localizable("Second")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="third", title=api_v1.Localizable("Third")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="fourth", title=api_v1.Localizable("Fourth")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="fifth", title=api_v1.Localizable("Fifth")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="sixth", title=api_v1.Localizable("Sixth")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="seventh", title=api_v1.Localizable("Seventh")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="eight", title=api_v1.Localizable("Eight")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="ninth", title=api_v1.Localizable("Ninth")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="tenth", title=api_v1.Localizable("Tenth")
                    ),
                    api_v1.form_specs.composed.MultipleChoiceElement(
                        name="eleventh", title=api_v1.Localizable("Eleventh")
                    ),
                ],
                show_toggle_all=True,
                prefill=api_v1.form_specs.DefaultValue(("first", "third")),
            ),
            legacy_valuespecs.DualListChoice(
                choices=[
                    ("first", _("First")),
                    ("second", _("Second")),
                    ("third", _("Third")),
                    ("fourth", _("Fourth")),
                    ("fifth", _("Fifth")),
                    ("sixth", _("Sixth")),
                    ("seventh", _("Seventh")),
                    ("eight", _("Eight")),
                    ("ninth", _("Ninth")),
                    ("tenth", _("Tenth")),
                    ("eleventh", _("Eleventh")),
                ],
                toggle_all=True,
                title=_("my title"),
                help=_("help text"),
                default_value=["first", "third"],
            ),
            id="large MultipleChoice",
        ),
        pytest.param(
            api_v1.form_specs.basic.MultilineText(),
            legacy_valuespecs.TextAreaUnicode(),
            id="minimal MultilineText",
        ),
        pytest.param(
            api_v1.form_specs.basic.MultilineText(
                monospaced=True,
                title=api_v1.Localizable("my title"),
                help_text=api_v1.Localizable("help text"),
                label=api_v1.Localizable("label"),
                prefill=api_v1.form_specs.DefaultValue("default text"),
                macro_support=True,
            ),
            legacy_valuespecs.TextAreaUnicode(
                monospaced=True,
                title=_("my title"),
                help=_(
                    "help text This field supports the use of macros. The corresponding plugin replaces the macros with the actual values."
                ),
                label=_("label"),
                default_value="default text",
            ),
            id="MultilineText",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.TimePeriod(),
            legacy_timeperiods.TimeperiodSelection(),
            id="minimal TimePeriod",
        ),
        pytest.param(
            api_v1.form_specs.preconfigured.TimePeriod(
                title=api_v1.Localizable("title"),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_timeperiods.TimeperiodSelection(
                title="title",
                help="help text",
            ),
            id="TimePeriod",
        ),
    ],
)
def test_convert_to_legacy_valuespec(
    new_valuespec: FormSpec, expected: legacy_valuespecs.ValueSpec
) -> None:
    _compare_specs(_convert_to_legacy_valuespec(new_valuespec, _), expected)


def _get_cascading_single_choice_with_prefill_selection(
    prefill_selection: str,
) -> api_v1.form_specs.composed.CascadingSingleChoice:
    return api_v1.form_specs.composed.CascadingSingleChoice(
        elements=[
            api_v1.form_specs.composed.CascadingSingleChoiceElement(
                name="no_prefill",
                title=api_v1.Localizable("no prefill"),
                parameter_form=api_v1.form_specs.basic.Integer(),
            ),
            api_v1.form_specs.composed.CascadingSingleChoiceElement(
                name="simple_prefill",
                title=api_v1.Localizable("simple prefill"),
                parameter_form=api_v1.form_specs.basic.Text(
                    prefill=api_v1.form_specs.DefaultValue("prefill_text")
                ),
            ),
            api_v1.form_specs.composed.CascadingSingleChoiceElement(
                name="nested",
                title=api_v1.Localizable("nested"),
                parameter_form=api_v1.form_specs.composed.Dictionary(
                    elements={
                        "key1": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.Integer()
                        ),
                        "key2": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.Integer()
                        ),
                    }
                ),
            ),
            api_v1.form_specs.composed.CascadingSingleChoiceElement(
                name="nested_prefill",
                title=api_v1.Localizable("nested prefill"),
                parameter_form=api_v1.form_specs.composed.Dictionary(
                    elements={
                        "key1": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.Integer(
                                prefill=api_v1.form_specs.DefaultValue(1)
                            ),
                            required=True,
                        ),
                        "key2": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.Integer(
                                prefill=api_v1.form_specs.DefaultValue(2)
                            ),
                            required=True,
                        ),
                    }
                ),
            ),
        ],
        prefill=api_v1.form_specs.DefaultValue(prefill_selection),
    )


@pytest.mark.parametrize(
    ["prefilled_spec", "expected_default_value"],
    [
        pytest.param(
            _get_cascading_single_choice_with_prefill_selection("no_prefill"),
            ("no_prefill", 0),
            id="no_prefill",
        ),
        pytest.param(
            _get_cascading_single_choice_with_prefill_selection("simple_prefill"),
            ("simple_prefill", "prefill_text"),
            id="simple_prefill",
        ),
        pytest.param(
            _get_cascading_single_choice_with_prefill_selection("nested"),
            ("nested", {}),
            id="nested",
        ),
        pytest.param(
            _get_cascading_single_choice_with_prefill_selection("nested_prefill"),
            ("nested_prefill", {"key1": 1, "key2": 2}),
            id="nested_prefill",
        ),
    ],
)
def test_cascading_singe_choice_prefill_selection_conversion(
    prefilled_spec: api_v1.form_specs.composed.CascadingSingleChoice, expected_default_value: tuple
) -> None:
    converted_prefilled_spec = _convert_to_legacy_valuespec(prefilled_spec, lambda x: x)
    assert expected_default_value == converted_prefilled_spec.default_value()


@pytest.mark.parametrize(
    ["legacy_main_group", "new_topic", "expected"],
    [
        pytest.param(
            legacy_rulespec_groups.RulespecGroupMonitoringConfiguration,
            api_v1.rule_specs.Topic.APPLICATIONS,
            legacy_wato_groups.RulespecGroupCheckParametersApplications,
            id="CheckParametersApplications",
        ),
    ],
)
def test_convert_to_legacy_rulespec_group(
    legacy_main_group: type[legacy_rulespecs.RulespecGroup],
    new_topic: api_v1.rule_specs.Topic,
    expected: type[legacy_rulespecs.RulespecSubGroup],
) -> None:
    assert _convert_to_legacy_rulespec_group(legacy_main_group, new_topic, _) == expected


@pytest.mark.parametrize(
    ["new_rulespec", "expected"],
    [
        pytest.param(
            api_v1.rule_specs.CheckParameters(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=partial(
                    api_v1.form_specs.composed.Dictionary,
                    elements={
                        "key": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.ServiceState(
                                title=api_v1.Localizable("valuespec title")
                            )
                        ),
                    },
                ),
                condition=api_v1.rule_specs.HostAndItemCondition(
                    item_title=api_v1.Localizable("item title")
                ),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.CheckParameterRulespecWithItem(
                check_group_name="test_rulespec",
                group=legacy_wato_groups.RulespecGroupCheckParametersApplications,
                title=lambda: _("rulespec title"),
                item_spec=lambda: legacy_valuespecs.TextInput(title=_("item title")),
                parameter_valuespec=lambda: legacy_valuespecs.Dictionary(
                    elements=[
                        ("key", legacy_valuespecs.MonitoringState(title=_("valuespec title")))
                    ],
                ),
                match_type="dict",
                create_manual_check=False,
            ),
            id="CheckParameterRuleSpec with HostAndItemCondition",
        ),
        pytest.param(
            api_v1.rule_specs.CheckParameters(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=partial(
                    api_v1.form_specs.composed.Dictionary,
                    elements={
                        "key": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.ServiceState(
                                title=api_v1.Localizable("valuespec title")
                            )
                        ),
                    },
                ),
                condition=api_v1.rule_specs.HostCondition(),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.CheckParameterRulespecWithoutItem(
                check_group_name="test_rulespec",
                group=legacy_wato_groups.RulespecGroupCheckParametersApplications,
                title=lambda: _("rulespec title"),
                parameter_valuespec=lambda: legacy_valuespecs.Dictionary(
                    elements=[
                        ("key", legacy_valuespecs.MonitoringState(title=_("valuespec title")))
                    ],
                ),
                match_type="dict",
                create_manual_check=False,
            ),
            id="CheckParameterRuleSpec with HostCondition",
        ),
        pytest.param(
            api_v1.rule_specs.EnforcedService(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=partial(
                    api_v1.form_specs.composed.Dictionary,
                    elements={
                        "key": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.ServiceState(
                                title=api_v1.Localizable("valuespec title")
                            )
                        ),
                    },
                ),
                condition=api_v1.rule_specs.HostAndItemCondition(
                    item_title=api_v1.Localizable("item title")
                ),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.ManualCheckParameterRulespec(
                check_group_name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupEnforcedServicesApplications,
                title=lambda: _("rulespec title"),
                item_spec=lambda: legacy_valuespecs.TextInput(
                    title=_("item title"),
                    placeholder="",
                    allow_empty=False,
                    validate=lambda x, y: None,  # text only checks it's not None.
                ),
                parameter_valuespec=lambda: legacy_valuespecs.Dictionary(
                    elements=[
                        ("key", legacy_valuespecs.MonitoringState(title=_("valuespec title")))
                    ],
                ),
                match_type="dict",
            ),
            id="EnforcedServiceRuleSpec with HostAndItemCondition",
        ),
        pytest.param(
            api_v1.rule_specs.EnforcedService(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=None,
                condition=api_v1.rule_specs.HostAndItemCondition(
                    item_title=api_v1.Localizable("item title")
                ),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.ManualCheckParameterRulespec(
                check_group_name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupEnforcedServicesApplications,
                title=lambda: _("rulespec title"),
                item_spec=lambda: legacy_valuespecs.TextInput(
                    title=_("item title"),
                    placeholder="",
                    allow_empty=False,
                    validate=lambda x, y: None,  # text only checks it's not None.
                ),
                parameter_valuespec=None,
                match_type="dict",
            ),
            id="EnforcedServiceRuleSpec with HostAndItemCondition no parameters",
        ),
        pytest.param(
            api_v1.rule_specs.EnforcedService(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=partial(
                    api_v1.form_specs.composed.Dictionary,
                    elements={
                        "key": api_v1.form_specs.composed.DictElement(
                            parameter_form=api_v1.form_specs.basic.ServiceState(
                                title=api_v1.Localizable("valuespec title")
                            )
                        ),
                    },
                ),
                condition=api_v1.rule_specs.HostCondition(),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.ManualCheckParameterRulespec(
                check_group_name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupEnforcedServicesApplications,
                title=lambda: _("rulespec title"),
                parameter_valuespec=lambda: legacy_valuespecs.Dictionary(
                    elements=[
                        ("key", legacy_valuespecs.MonitoringState(title=_("valuespec title")))
                    ],
                ),
                match_type="dict",
            ),
            id="EnforcedServiceRuleSpec with HostCondition",
        ),
        pytest.param(
            api_v1.rule_specs.EnforcedService(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                parameter_form=None,
                condition=api_v1.rule_specs.HostCondition(),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.ManualCheckParameterRulespec(
                check_group_name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupEnforcedServicesApplications,
                title=lambda: _("rulespec title"),
                parameter_valuespec=None,
                match_type="dict",
            ),
            id="EnforcedServiceRuleSpec with HostCondition no parameters",
        ),
        pytest.param(
            api_v1.rule_specs.ActiveCheck(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name=RuleGroup.ActiveChecks("test_rulespec"),
                group=_to_generated_builtin_sub_group(
                    legacy_wato_groups.RulespecGroupActiveChecks,
                    "Applications",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="ActiveCheckRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.AgentAccess(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name="test_rulespec",
                group=_to_generated_builtin_sub_group(
                    legacy_cmk_config_groups.RulespecGroupAgent,
                    "Applications",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="AgentAccessRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.AgentConfig(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.AGENT_PLUGINS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name=RuleGroup.AgentConfig("test_rulespec"),
                group=_to_generated_builtin_sub_group(
                    legacy_rulespec_groups.RulespecGroupMonitoringAgents,
                    "Agent plug-ins",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="AgentConfigRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.Host(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.NOTIFICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupHostsMonitoringRulesNotifications,
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="HostRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.InventoryParameters(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name=RuleGroup.InvParameters("test_rulespec"),
                group=_to_generated_builtin_sub_group(
                    legacy_inventory_groups.RulespecGroupInventory,
                    "Applications",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="InventoryParameterRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.NotificationParameters(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.NOTIFICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name=RuleGroup.NotificationParameters("test_rulespec"),
                group=legacy_rulespec_groups.RulespecGroupMonitoringConfigurationNotifications,
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="NotificationParametersRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.DiscoveryParameters(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.APPLICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name="test_rulespec",
                group=_to_generated_builtin_sub_group(
                    legacy_wato.RulespecGroupDiscoveryCheckParameters,
                    "Applications",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="ServiceDiscoveryRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.Service(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.NOTIFICATIONS,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                condition=api_v1.rule_specs.HostCondition(),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name="test_rulespec",
                group=legacy_rulespec_groups.RulespecGroupMonitoringConfigurationNotifications,
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="ServiceRuleSpec with HostCondition",
        ),
        pytest.param(
            api_v1.rule_specs.Service(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.VIRTUALIZATION,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                condition=api_v1.rule_specs.HostAndServiceCondition(),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.ServiceRulespec(
                name="test_rulespec",
                item_type="service",
                group=legacy_wato_groups.RulespecGroupCheckParametersVirtualization,
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="ServiceRuleSpec with HostAndServiceCondition",
        ),
        pytest.param(
            api_v1.rule_specs.SNMP(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.SERVER_HARDWARE,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name="test_rulespec",
                group=_to_generated_builtin_sub_group(
                    legacy_rulespec_groups.RulespecGroupAgentSNMP,
                    "Server hardware",
                    lambda x: x,
                ),
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="SNMPRuleSpec",
        ),
        pytest.param(
            api_v1.rule_specs.SpecialAgent(
                name="test_rulespec",
                title=api_v1.Localizable("rulespec title"),
                topic=api_v1.rule_specs.Topic.CLOUD,
                eval_type=api_v1.rule_specs.EvalType.MERGE,
                parameter_form=lambda: api_v1.form_specs.composed.Dictionary(elements={}),
                help_text=api_v1.Localizable("help text"),
            ),
            legacy_rulespecs.HostRulespec(
                name=RuleGroup.SpecialAgents("test_rulespec"),
                group=legacy_wato_groups.RulespecGroupDatasourceProgramsCloud,
                title=lambda: _("rulespec title"),
                valuespec=partial(legacy_valuespecs.TextInput),
                match_type="dict",
            ),
            id="SpecialAgentRuleSpec",
        ),
    ],
)
def test_convert_to_legacy_rulespec(
    new_rulespec: APIV1RuleSpec, expected: legacy_rulespecs.Rulespec
) -> None:
    _compare_specs(convert_to_legacy_rulespec(new_rulespec, Edition.CRE, _), expected)


def _compare_specs(actual: object, expected: object) -> None:
    ignored_attrs = {"__orig_class__"}

    if isinstance(expected, Sequence) and not isinstance(expected, str):
        assert isinstance(actual, Sequence) and not isinstance(actual, str)
        assert len(actual) == len(expected)
        for actual_elem, expected_elem in zip(actual, expected):
            _compare_specs(actual_elem, expected_elem)
        return

    if not hasattr(expected, "__dict__"):
        assert actual == expected
        return

    expected_keys = expected.__dict__.keys() - ignored_attrs
    actual_keys = actual.__dict__.keys() - ignored_attrs
    assert expected_keys == actual_keys

    if isinstance(expected, legacy_rulespecs.RulespecBaseGroup):
        _compare_rulespec_groups(actual, expected)

    for attr, expected_value in expected.__dict__.items():
        if attr in ignored_attrs:
            continue
        actual_value = getattr(actual, attr)
        if attr in [
            "_custom_validate",
            "_validate",
            "_render_function",
            "to_valuespec",
            "from_valuespec",
        ]:
            # testing the equality of the validation in a generic way seems very difficult
            #  check that the field was set during conversion and test behavior separately
            assert (actual_value is not None) is (expected_value is not None)
            continue
        if not callable(expected_value):
            _compare_specs(actual_value, expected_value)
            continue

        # cached access to the password store
        if "functools._lru_cache_wrapper" in str(actual_value):
            continue

        try:
            _compare_specs(actual_value(), expected_value())
        except TypeError:  # deal with valuespec constructors
            assert actual_value == expected_value


def _compare_rulespec_groups(actual: object, expected: legacy_rulespecs.RulespecBaseGroup) -> None:
    if isinstance(expected, legacy_rulespecs.RulespecSubGroup):
        assert isinstance(actual, legacy_rulespecs.RulespecSubGroup)
        assert expected.choice_title == actual.choice_title
        assert expected.help == actual.help
        assert expected.main_group == actual.main_group
        assert expected.name == actual.name
        assert expected.sub_group_name == actual.sub_group_name
        assert expected.title == actual.title
    else:
        raise NotImplementedError()


def test_generated_rulespec_group_single_registration():
    first_group = _convert_to_custom_group(
        legacy_rulespec_groups.RulespecGroupMonitoringConfiguration,
        api_v1.Localizable("test"),
        lambda x: x,
    )
    second_group = _convert_to_custom_group(
        legacy_rulespec_groups.RulespecGroupMonitoringConfiguration,
        api_v1.Localizable("test"),
        lambda x: x,
    )
    assert first_group == second_group


@pytest.mark.parametrize(
    "input_value",
    [
        pytest.param("admin", id="custom validation"),
        pytest.param("", id="empty validation"),
        pytest.param(".", id="regex validation"),
    ],
)
def test_convert_validation(input_value: str) -> None:
    converted_spec = _convert_to_legacy_valuespec(
        api_v1.form_specs.basic.Text(custom_validate=_v1_custom_text_validate), _
    )

    expected_spec = legacy_valuespecs.TextInput(
        validate=_legacy_custom_text_validate,
        regex=r"^[^.\r\n]+$",
        regex_error=_("No dot allowed"),
        allow_empty=False,
        empty_text=_("Fill this"),
    )

    test_args = (input_value, "var_prefix")
    with pytest.raises(MKUserError) as expected_error:
        expected_spec.validate_value(*test_args)

    with pytest.raises(MKUserError) as actual_error:
        converted_spec.validate_value(*test_args)

    assert actual_error.value.args == expected_error.value.args
    assert actual_error.value.message == expected_error.value.message
    assert actual_error.value.varname == expected_error.value.varname


@pytest.mark.parametrize(
    "input_value, expected_error",
    [
        pytest.param(
            ["first", "second", "third"], "Max number of elements exceeded", id="max elements"
        ),
        pytest.param([], "Empty list", id="empty validation"),
        pytest.param(["first", "first"], "Duplicate elements", id="custom validation"),
    ],
)
def test_list_custom_validate(input_value: Sequence[str], expected_error: str) -> None:
    def _v1_custom_list_validate(value: Sequence[object]) -> None:
        api_v1.validators.DisallowEmpty(error_msg=api_v1.Localizable("Empty list"))(value)

        if len(value) > 2:
            raise api_v1.validators.ValidationError(
                api_v1.Localizable("Max number of elements exceeded")
            )

        if len(set(value)) != len(value):
            raise api_v1.validators.ValidationError(api_v1.Localizable("Duplicate elements"))

    v1_api_list = api_v1.form_specs.composed.List(
        element_template=api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(
            elements=[api_v1.form_specs.basic.Text()]
        ),
        custom_validate=_v1_custom_list_validate,
    )

    legacy_list = _convert_to_legacy_valuespec(v1_api_list, _)

    with pytest.raises(MKUserError, match=expected_error):
        legacy_list.validate_value(input_value, "var_prefix")


T = TypeVar("T")


def _narrow_type(x: object, narrow_to: type[T]) -> T:
    if isinstance(x, narrow_to):
        return x
    raise ValueError(x)


@pytest.mark.parametrize(
    ["parameter_form", "old_value", "expected_transformed_value"],
    [
        pytest.param(
            api_v1.form_specs.basic.Integer(migrate=lambda x: _narrow_type(x, int) * 2),
            2,
            4,
            id="integer migration",
        ),
        pytest.param(
            api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(
                elements=[
                    api_v1.form_specs.basic.Integer(migrate=lambda x: _narrow_type(x, int) * 2),
                    api_v1.form_specs.basic.Percentage(
                        migrate=lambda x: _narrow_type(x, float) * 2
                    ),
                ]
            ),
            (2, 2.0),
            (4, 4.0),
            id="migrate nested element",
        ),
        pytest.param(
            api_v1.form_specs.composed.Dictionary(
                elements={
                    "key2": api_v1.form_specs.composed.DictElement(
                        parameter_form=api_v1.form_specs.basic.Integer()
                    )
                },
                migrate=lambda x: {"key2": _narrow_type(x, dict)["key"]},
            ),
            {"key": 2},
            {"key2": 2},
            id="migrate top level element",
        ),
        pytest.param(
            api_v1.form_specs.composed.CascadingSingleChoice(
                elements=[
                    api_v1.form_specs.composed.CascadingSingleChoiceElement(
                        name="key_new",
                        title=api_v1.Localizable("Spec title"),
                        parameter_form=api_v1.form_specs.basic.Text(migrate=lambda x: f"{x}_new"),
                    )
                ],
                migrate=lambda x: (
                    f"{_narrow_type(x, tuple)[0]}_new",
                    _narrow_type(x, tuple)[1],
                ),
            ),
            ("key", "value"),
            ("key_new", "value_new"),
            id="migrate nested and top level element",
        ),
    ],
)
def test_migrate(
    parameter_form: FormSpec,
    old_value: object,
    expected_transformed_value: object,
) -> None:
    legacy_valuespec = _convert_to_legacy_valuespec(parameter_form, localizer=lambda x: x)
    actual_transformed_value = legacy_valuespec.transform_value(value=old_value)
    assert expected_transformed_value == actual_transformed_value


def _exposed_form_specs() -> Sequence[FormSpec]:
    return [
        api_v1.form_specs.basic.Integer(),
        api_v1.form_specs.basic.Float(),
        api_v1.form_specs.basic.DataSize(
            displayed_magnitudes=tuple(api_v1.form_specs.basic.IECMagnitude)
        ),
        api_v1.form_specs.basic.Percentage(),
        api_v1.form_specs.basic.Text(),
        api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved(elements=[]),
        api_v1.form_specs.composed.Dictionary(elements={}),
        api_v1.form_specs.basic.SingleChoice(
            elements=[
                api_v1.form_specs.basic.SingleChoiceElement(
                    name="foo",
                    title=api_v1.Localizable("Whatever"),
                ),
            ],
            prefill=api_v1.form_specs.DefaultValue("foo"),
        ),
        api_v1.form_specs.composed.CascadingSingleChoice(elements=[]),
        api_v1.form_specs.basic.ServiceState(),
        api_v1.form_specs.basic.HostState(),
        api_v1.form_specs.composed.List(element_template=api_v1.form_specs.basic.Integer()),
        api_v1.form_specs.basic.FixedValue(value=None),
        api_v1.form_specs.basic.TimeSpan(
            displayed_magnitudes=tuple(api_v1.form_specs.basic.TimeMagnitude)
        ),
        api_v1.form_specs.levels.Levels(
            level_direction=api_v1.form_specs.levels.LevelDirection.UPPER,
            predictive=None,
            form_spec_template=api_v1.form_specs.basic.Integer(),
            prefill_fixed_levels=api_v1.form_specs.DefaultValue((23.0, 42.0)),
        ),
        api_v1.form_specs.basic.BooleanChoice(),
        api_v1.form_specs.basic.FileUpload(),
        api_v1.form_specs.preconfigured.Proxy(),
        api_v1.form_specs.preconfigured.Metric(),
        api_v1.form_specs.preconfigured.MonitoredHost(),
        api_v1.form_specs.preconfigured.MonitoredService(),
        api_v1.form_specs.preconfigured.Password(),
        api_v1.form_specs.basic.RegularExpression(
            predefined_help_text=api_v1.form_specs.basic.MatchingScope.FULL
        ),
    ]


@pytest.mark.parametrize("form_spec", _exposed_form_specs())
def test_form_spec_transform(form_spec: FormSpec) -> None:
    if isinstance(
        form_spec,
        (
            api_v1.form_specs.basic.Integer,
            api_v1.form_specs.basic.Float,
            api_v1.form_specs.basic.DataSize,
            api_v1.form_specs.basic.Percentage,
            api_v1.form_specs.basic.Text,
            api_v1.form_specs.basic.RegularExpression,
            api_v1.form_specs.composed.TupleDoNotUseWillbeRemoved,
            api_v1.form_specs.composed.Dictionary,
            api_v1.form_specs.basic.SingleChoice,
            api_v1.form_specs.composed.CascadingSingleChoice,
            api_v1.form_specs.basic.ServiceState,
            api_v1.form_specs.basic.HostState,
            api_v1.form_specs.composed.List,
            api_v1.form_specs.basic.FixedValue,
            api_v1.form_specs.basic.TimeSpan,
            api_v1.form_specs.levels.Levels,
            api_v1.form_specs.basic.BooleanChoice,
            api_v1.form_specs.composed.MultipleChoice,
            api_v1.form_specs.basic.MultilineText,
        ),
    ):
        try:
            _ = form_spec.migrate
        except AttributeError:
            assert False
    elif isinstance(
        form_spec,
        (
            api_v1.form_specs.basic.FileUpload,
            api_v1.form_specs.preconfigured.Metric,
            api_v1.form_specs.preconfigured.MonitoredHost,
            api_v1.form_specs.preconfigured.MonitoredService,
            api_v1.form_specs.preconfigured.Password,
            api_v1.form_specs.preconfigured.Proxy,
        ),
    ):
        # these don't have a transform
        assert True
    else:
        raise NotImplementedError(form_spec)


def _get_legacy_no_levels_choice() -> tuple[str, str, legacy_valuespecs.FixedValue]:
    return (
        "no_levels",
        _("No levels"),
        legacy_valuespecs.FixedValue(
            value=None, title=_("No levels"), totext=_("Do not impose levels, always be OK")
        ),
    )


def _get_legacy_fixed_levels_choice(at_or_below: str) -> tuple[str, str, legacy_valuespecs.Tuple]:
    return (
        "fixed",
        _("Fixed levels"),
        legacy_valuespecs.Tuple(
            elements=[
                legacy_valuespecs.Integer(title=_("Warning %s") % at_or_below, default_value=1),
                legacy_valuespecs.Integer(title=_("Critical %s") % at_or_below, default_value=2),
            ]
        ),
    )


@pytest.mark.parametrize(
    ["api_levels", "legacy_levels"],
    [
        pytest.param(
            api_v1.form_specs.levels.Levels(
                title=api_v1.Localizable("Lower levels"),
                form_spec_template=api_v1.form_specs.basic.Integer(),
                level_direction=api_v1.form_specs.levels.LevelDirection.LOWER,
                prefill_fixed_levels=api_v1.form_specs.DefaultValue((1, 2)),
                predictive=None,
            ),
            legacy_valuespecs.CascadingDropdown(
                title=_("Lower levels"),
                choices=[
                    _get_legacy_no_levels_choice(),
                    _get_legacy_fixed_levels_choice("below"),
                ],
                default_value=("fixed", (1, 2)),
            ),
            id="lower fixed",
        ),
        pytest.param(
            api_v1.form_specs.levels.Levels(
                form_spec_template=api_v1.form_specs.basic.Integer(),
                level_direction=api_v1.form_specs.levels.LevelDirection.UPPER,
                prefill_fixed_levels=api_v1.form_specs.DefaultValue((1, 2)),
                predictive=None,
            ),
            legacy_valuespecs.CascadingDropdown(
                choices=[
                    _get_legacy_no_levels_choice(),
                    _get_legacy_fixed_levels_choice("at"),
                ],
                default_value=("fixed", (1, 2)),
            ),
            id="upper fixed",
        ),
        pytest.param(
            api_v1.form_specs.levels.Levels[float](
                title=api_v1.Localizable("Cast to super type float"),
                form_spec_template=api_v1.form_specs.basic.TimeSpan(
                    displayed_magnitudes=[api_v1.form_specs.basic.TimeMagnitude.SECOND]
                ),
                level_direction=api_v1.form_specs.levels.LevelDirection.LOWER,
                prefill_fixed_levels=api_v1.form_specs.DefaultValue((1, 2)),
                predictive=None,
            ),
            legacy_valuespecs.CascadingDropdown(
                title=_("Cast to super type float"),
                choices=(
                    _get_legacy_no_levels_choice(),
                    (
                        "fixed",
                        _("Fixed levels"),
                        legacy_valuespecs.Tuple(
                            elements=[
                                legacy_valuespecs.TimeSpan(
                                    title=_("Warning below"),
                                    default_value=1,
                                    display=["seconds"],
                                ),
                                legacy_valuespecs.TimeSpan(
                                    title=_("Critical below"),
                                    default_value=2,
                                    display=["seconds"],
                                ),
                            ],
                        ),
                    ),
                ),
                default_value=("fixed", (1.0, 2.0)),
            ),
            # mypy allows passing integers where a float is expected. We cast these to float, "
            # so that CascadingDropdown does not complain.",
            id="cast_to_float",
        ),
        pytest.param(
            api_v1.form_specs.levels.Levels[int](
                title=api_v1.Localizable("Upper levels"),
                form_spec_template=api_v1.form_specs.basic.Integer(unit=api_v1.Localizable("GiB")),
                level_direction=api_v1.form_specs.levels.LevelDirection.UPPER,
                prefill_fixed_levels=api_v1.form_specs.DefaultValue((1, 2)),
                predictive=api_v1.form_specs.levels.PredictiveLevels(
                    reference_metric="my_metric",
                    prefill_abs_diff=api_v1.form_specs.DefaultValue((5, 10)),
                    prefill_rel_diff=api_v1.form_specs.DefaultValue((50.0, 80.0)),
                    prefill_stddev_diff=api_v1.form_specs.DefaultValue((2.0, 3.0)),
                ),
            ),
            legacy_valuespecs.CascadingDropdown(
                title=_("Upper levels"),
                choices=(
                    _get_legacy_no_levels_choice(),
                    (
                        "fixed",
                        _("Fixed levels"),
                        legacy_valuespecs.Tuple(
                            elements=[
                                legacy_valuespecs.Integer(
                                    title=_("Warning at"),
                                    default_value=1,
                                    unit="GiB",
                                ),
                                legacy_valuespecs.Integer(
                                    title=_("Critical at"),
                                    default_value=2,
                                    unit="GiB",
                                ),
                            ],
                        ),
                    ),
                    (
                        "predictive",
                        _("Predictive levels (only on CMC)"),
                        legacy_valuespecs.Transform(
                            valuespec=legacy_valuespecs.Dictionary(
                                elements=[
                                    (
                                        "period",
                                        legacy_valuespecs.DropdownChoice(
                                            choices=[
                                                ("wday", _("Day of the week")),
                                                ("day", _("Day of the month")),
                                                ("hour", _("Hour of the day")),
                                                ("minute", _("Minute of the hour")),
                                            ],
                                            title=_("Base prediction on"),
                                            help=_(
                                                "Define the periodicity in which the repetition of the measured data is expected (monthly, weekly, daily or hourly)"
                                            ),
                                        ),
                                    ),
                                    (
                                        "horizon",
                                        legacy_valuespecs.Integer(
                                            title=_("Length of historic data to consider"),
                                            help=_(
                                                "How many days in the past Checkmk should evaluate the measurement data"
                                            ),
                                            unit=_("days"),
                                            minvalue=1,
                                            default_value=90,
                                        ),
                                    ),
                                    (
                                        "levels",
                                        legacy_valuespecs.CascadingDropdown(
                                            title=_(
                                                "Level definition in relation to the predicted value"
                                            ),
                                            choices=[
                                                (
                                                    "absolute",
                                                    _("Absolute difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.Integer(
                                                                title=_("Warning above"),
                                                                unit="GiB",
                                                                default_value=5,
                                                            ),
                                                            legacy_valuespecs.Integer(
                                                                title=_("Critical above"),
                                                                unit="GiB",
                                                                default_value=10,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a fixed absolute value"
                                                        ),
                                                    ),
                                                ),
                                                (
                                                    "relative",
                                                    _("Relative difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.Percentage(
                                                                title=_("Warning above"),
                                                                unit="%",
                                                                default_value=50.0,
                                                            ),
                                                            legacy_valuespecs.Percentage(
                                                                title=_("Critical above"),
                                                                unit="%",
                                                                default_value=80.0,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a percentage"
                                                        ),
                                                    ),
                                                ),
                                                (
                                                    "stddev",
                                                    _("Standard deviation difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.Float(
                                                                title=_("Warning above"),
                                                                unit=_(
                                                                    "times the standard deviation"
                                                                ),
                                                                default_value=2.0,
                                                            ),
                                                            legacy_valuespecs.Float(
                                                                title=_("Critical above"),
                                                                unit=_(
                                                                    "times the standard deviation"
                                                                ),
                                                                default_value=3.0,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a multiple of the standard deviation"
                                                        ),
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ),
                                    (
                                        "bound",
                                        legacy_valuespecs.Optional(
                                            title=_("Fixed limits"),
                                            label=_("Set fixed limits"),
                                            valuespec=legacy_valuespecs.Tuple(
                                                help=_(
                                                    "Regardless of how the dynamic levels are computed according to the prediction: they will never be set below the following limits. This avoids false alarms during times where the predicted levels would be very low."
                                                ),
                                                elements=[
                                                    legacy_valuespecs.Integer(
                                                        title="Warning level is at least",
                                                        unit="GiB",
                                                    ),
                                                    legacy_valuespecs.Integer(
                                                        title="Critical level is at least",
                                                        unit="GiB",
                                                    ),
                                                ],
                                            ),
                                        ),
                                    ),
                                ],
                                required_keys=["period", "horizon", "levels", "bound"],
                            ),
                            to_valuespec=lambda x: x,
                            from_valuespec=lambda x: x,
                        ),
                    ),
                ),
                default_value=("fixed", (1, 2)),
            ),
            id="fixed+predictive Integer",
        ),
        pytest.param(
            api_v1.form_specs.levels.Levels(
                form_spec_template=api_v1.form_specs.basic.TimeSpan(
                    displayed_magnitudes=[
                        api_v1.form_specs.basic.TimeMagnitude.SECOND,
                        api_v1.form_specs.basic.TimeMagnitude.MINUTE,
                    ]
                ),
                level_direction=api_v1.form_specs.levels.LevelDirection.LOWER,
                prefill_fixed_levels=api_v1.form_specs.DefaultValue((1.0, 2.0)),
                predictive=api_v1.form_specs.levels.PredictiveLevels(
                    reference_metric="my_metric",
                    prefill_abs_diff=api_v1.form_specs.DefaultValue((5.0, 10.0)),
                    prefill_rel_diff=api_v1.form_specs.DefaultValue((50.0, 80.0)),
                    prefill_stddev_diff=api_v1.form_specs.DefaultValue((2.0, 3.0)),
                ),
                title=api_v1.Localizable("Lower levels"),
            ),
            legacy_valuespecs.CascadingDropdown(
                title=_("Lower levels"),
                choices=(
                    _get_legacy_no_levels_choice(),
                    (
                        "fixed",
                        _("Fixed levels"),
                        legacy_valuespecs.Tuple(
                            elements=[
                                legacy_valuespecs.TimeSpan(
                                    title=_("Warning below"),
                                    default_value=1,
                                    display=["seconds", "minutes"],
                                ),
                                legacy_valuespecs.TimeSpan(
                                    title=_("Critical below"),
                                    default_value=2,
                                    display=["seconds", "minutes"],
                                ),
                            ],
                        ),
                    ),
                    (
                        "predictive",
                        _("Predictive levels (only on CMC)"),
                        legacy_valuespecs.Transform(
                            valuespec=legacy_valuespecs.Dictionary(
                                elements=[
                                    (
                                        "period",
                                        legacy_valuespecs.DropdownChoice(
                                            choices=[
                                                ("wday", _("Day of the week")),
                                                ("day", _("Day of the month")),
                                                ("hour", _("Hour of the day")),
                                                ("minute", _("Minute of the hour")),
                                            ],
                                            title=_("Base prediction on"),
                                            help=_(
                                                "Define the periodicity in which the repetition of the measured data is expected (monthly, weekly, daily or hourly)"
                                            ),
                                        ),
                                    ),
                                    (
                                        "horizon",
                                        legacy_valuespecs.Integer(
                                            title=_("Length of historic data to consider"),
                                            help=_(
                                                "How many days in the past Checkmk should evaluate the measurement data"
                                            ),
                                            unit=_("days"),
                                            minvalue=1,
                                            default_value=90,
                                        ),
                                    ),
                                    (
                                        "levels",
                                        legacy_valuespecs.CascadingDropdown(
                                            title=_(
                                                "Level definition in relation to the predicted value"
                                            ),
                                            choices=[
                                                (
                                                    "absolute",
                                                    _("Absolute difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.TimeSpan(
                                                                title=_("Warning below"),
                                                                display=["seconds", "minutes"],
                                                                default_value=5,
                                                            ),
                                                            legacy_valuespecs.TimeSpan(
                                                                title=_("Critical below"),
                                                                display=["seconds", "minutes"],
                                                                default_value=10,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a fixed absolute value"
                                                        ),
                                                    ),
                                                ),
                                                (
                                                    "relative",
                                                    _("Relative difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.Percentage(
                                                                title=_("Warning below"),
                                                                unit="%",
                                                                default_value=50.0,
                                                            ),
                                                            legacy_valuespecs.Percentage(
                                                                title=_("Critical below"),
                                                                unit="%",
                                                                default_value=80.0,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a percentage"
                                                        ),
                                                    ),
                                                ),
                                                (
                                                    "stddev",
                                                    _("Standard deviation difference"),
                                                    legacy_valuespecs.Tuple(
                                                        elements=[
                                                            legacy_valuespecs.Float(
                                                                title=_("Warning below"),
                                                                unit=_(
                                                                    "times the standard deviation"
                                                                ),
                                                                default_value=2.0,
                                                            ),
                                                            legacy_valuespecs.Float(
                                                                title=_("Critical below"),
                                                                unit=_(
                                                                    "times the standard deviation"
                                                                ),
                                                                default_value=3.0,
                                                            ),
                                                        ],
                                                        help=_(
                                                            "The thresholds are calculated by increasing or decreasing the predicted value by a multiple of the standard deviation"
                                                        ),
                                                    ),
                                                ),
                                            ],
                                        ),
                                    ),
                                    (
                                        "bound",
                                        legacy_valuespecs.Optional(
                                            title=_("Fixed limits"),
                                            label=_("Set fixed limits"),
                                            valuespec=legacy_valuespecs.Tuple(
                                                help=_(
                                                    "Regardless of how the dynamic levels are computed according to the prediction: they will never be set above the following limits. This avoids false alarms during times where the predicted levels would be very high."
                                                ),
                                                elements=[
                                                    legacy_valuespecs.TimeSpan(
                                                        title="Warning level is at most",
                                                        display=["seconds", "minutes"],
                                                    ),
                                                    legacy_valuespecs.TimeSpan(
                                                        title="Critical level is at most",
                                                        display=["seconds", "minutes"],
                                                    ),
                                                ],
                                            ),
                                        ),
                                    ),
                                ],
                                required_keys=["period", "horizon", "levels", "bound"],
                            ),
                            to_valuespec=lambda x: x,
                            from_valuespec=lambda x: x,
                        ),
                    ),
                ),
                default_value=("fixed", (1, 2)),
            ),
            id="fixed+predictive TimeSpan",
        ),
    ],
)
def test_level_conversion(
    api_levels: api_v1.form_specs.levels.Levels,
    legacy_levels: legacy_valuespecs.Dictionary,
) -> None:
    _compare_specs(_convert_to_legacy_levels(api_levels, _), legacy_levels)
