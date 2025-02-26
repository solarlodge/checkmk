#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import os
from collections.abc import Callable, Sequence
from typing import Any, cast, Literal, NewType, NotRequired

from typing_extensions import TypedDict

import cmk.utils.plugin_registry
import cmk.utils.store as store

from cmk.gui.config import active_config
from cmk.gui.hooks import request_memoize

from ._connector import ConnectorType, user_connector_registry, UserConnector


class UserConnectionTypedDictBase(TypedDict):
    id: str
    disabled: bool


class UserConnection(UserConnectionTypedDictBase):
    type: str


class Fixed(TypedDict):
    server: str
    failover_servers: NotRequired[list[str]]


class Discover(TypedDict):
    domain: str


class LDAPConnectionConfigFixed(TypedDict):
    connect_to: tuple[Literal["fixed_list"], Fixed]


class LDAPConnectionConfigDiscover(TypedDict):
    connect_to: tuple[Literal["discover"], Discover]


class SyncAttribute(TypedDict, total=False):
    attr: str


class GroupsToContactGroups(TypedDict, total=False):
    nested: Literal[True]
    other_connections: list[str]


class DisableNotificationsAttribute(TypedDict):
    disable: NotRequired[Literal[True]]
    timerange: NotRequired[tuple[float, float]]


DISABLE_NOTIFICATIONS = tuple[Literal["disable_notifications"], DisableNotificationsAttribute]
ICONS_PER_ITEM = tuple[Literal["icons_per_item"], None | Literal["entry"]]
NAV_HIDE_ICONS_TITLE = tuple[Literal["nav_hide_icons_title"], None | Literal["hide"]]
SHOW_MODE = tuple[
    Literal["show_mode"],
    None | Literal["default_show_less", "default_show_more", "enforce_show_more"],
]
UI_SIDEBAR_POSITIONS = tuple[Literal["ui_sidebar_position"], None | Literal["left"]]
START_URL = tuple[Literal["start_url"], None | str]
TEMP_UNIT = tuple[Literal["temperature_unit"], None | Literal["celsius", "fahrenheit"]]
UI_THEME = tuple[Literal["ui_theme"], None | Literal["facelift", "modern-dark"]]
FORCE_AUTH_USER = tuple[Literal["force_authuser"], bool]

ATTRIBUTE = (
    DISABLE_NOTIFICATIONS
    | ICONS_PER_ITEM
    | NAV_HIDE_ICONS_TITLE
    | SHOW_MODE
    | UI_SIDEBAR_POSITIONS
    | START_URL
    | TEMP_UNIT
    | UI_THEME
    | FORCE_AUTH_USER
)


class GroupsToSync(TypedDict):
    cn: str
    attribute: ATTRIBUTE


class GroupsToAttributes(TypedDict, total=False):
    nested: Literal[True]
    other_connections: list[str]
    groups: list[GroupsToSync]


class ActivePlugins(TypedDict, total=False):
    alias: SyncAttribute
    auth_expire: SyncAttribute
    groups_to_roles: dict[str, list[tuple[str, str | None]]]
    groups_to_contactgroups: GroupsToContactGroups
    groups_to_attributes: GroupsToAttributes
    disable_notifications: SyncAttribute
    email: SyncAttribute
    icons_per_item: SyncAttribute
    nav_hide_icons_title: SyncAttribute
    pager: SyncAttribute
    show_mode: SyncAttribute
    ui_sidebar_position: SyncAttribute
    start_url: SyncAttribute
    temperature_unit: SyncAttribute
    ui_theme: SyncAttribute
    force_authuser: SyncAttribute


DIR_SERVER_389 = tuple[Literal["389directoryserver"], LDAPConnectionConfigFixed]
OPEN_LDAP = tuple[Literal["openldap"], LDAPConnectionConfigFixed]
ACTIVE_DIR = tuple[Literal["ad"], LDAPConnectionConfigFixed | LDAPConnectionConfigDiscover]


class LDAPConnectionTypedDict(UserConnectionTypedDictBase):
    description: str
    comment: str
    docu_url: str
    directory_type: DIR_SERVER_389 | OPEN_LDAP | ACTIVE_DIR
    bind: NotRequired[tuple[str, tuple[Literal["password", "store"], str]]]
    port: NotRequired[int]
    use_ssl: NotRequired[Literal[True]]
    connect_timeout: NotRequired[float]
    version: NotRequired[Literal[2, 3]]
    page_size: NotRequired[int]
    response_timeout: NotRequired[int]
    suffix: NotRequired[str]
    user_dn: str
    user_scope: Literal["sub", "base", "one"]
    user_id_umlauts: Literal["keep", "replace"]
    user_filter: NotRequired[str]
    user_filter_group: NotRequired[str]
    user_id: NotRequired[str]
    lower_user_ids: NotRequired[Literal[True]]
    create_only_on_login: NotRequired[Literal[True]]
    group_dn: str
    group_scope: Literal["sub", "base", "one"]
    group_filter: NotRequired[str]
    group_member: NotRequired[str]
    active_plugins: ActivePlugins
    cache_livetime: int
    customer: NotRequired[str]
    type: Literal["ldap"]


class UserRoleMapping(TypedDict, total=False):
    user: list[str]
    admin: list[str]
    guest: list[str]
    agent_registration: list[str]


PrivateKeyPath = NewType(
    "PrivateKeyPath", str
)  # this needs to be written to a .mk file, so a more complex type like Path will lead to problems
PublicKeyPath = NewType(
    "PublicKeyPath", str
)  # this needs to be written to a .mk file, so a more complex type like Path will lead to problems


class SAMLConnectionTypedDict(UserConnectionTypedDictBase):
    name: str
    description: str
    comment: str
    docu_url: str
    idp_metadata: Any
    checkmk_entity_id: str
    checkmk_metadata_endpoint: str
    checkmk_assertion_consumer_service_endpoint: str
    checkmk_server_url: str
    connection_timeout: tuple[int, int]
    signature_certificate: Literal["builtin"] | tuple[
        Literal["custom"], tuple[PrivateKeyPath, PublicKeyPath]
    ]
    encryption_certificate: NotRequired[
        Literal["builtin"] | tuple[Literal["custom"], tuple[PrivateKeyPath, PublicKeyPath]]
    ]
    user_id_attribute_name: str
    user_alias_attribute_name: str
    email_attribute_name: str
    contactgroups_mapping: str
    role_membership_mapping: Literal[False] | tuple[Literal[True], tuple[str, UserRoleMapping]]
    type: Literal["saml2"]
    version: Literal["1.0.0"]
    owned_by_site: str
    customer: NotRequired[str]


UserConnectionSpec = LDAPConnectionTypedDict | SAMLConnectionTypedDict


@request_memoize(maxsize=None)
def get_connection(connection_id: str | None) -> UserConnector | None:
    """Returns the connection object of the requested connection id

    This function maintains a cache that for a single connection_id only one object per request is
    created."""
    connections_with_id = [c for cid, c in _all_connections() if cid == connection_id]
    return connections_with_id[0] if connections_with_id else None


def active_connections_by_type(connection_type: str) -> list[dict[str, Any]]:
    return [c for c in connections_by_type(connection_type) if not c["disabled"]]


def connections_by_type(connection_type: str) -> list[dict[str, Any]]:
    return [c for c in _get_connection_configs() if c["type"] == connection_type]


def clear_user_connection_cache() -> None:
    get_connection.cache_clear()  # type: ignore[attr-defined]


def active_connections() -> list[tuple[str, UserConnector]]:
    enabled_configs = [cfg for cfg in _get_connection_configs() if not cfg["disabled"]]  #
    return [
        (connection_id, connection)  #
        for connection_id, connection in _get_connections_for(enabled_configs)
        if connection.is_enabled()
    ]


def connection_choices() -> list[tuple[str, str]]:
    return sorted(
        [
            (connection_id, f"{connection_id} ({connection.type()})")
            for connection_id, connection in _all_connections()
            if connection.type() == ConnectorType.LDAP
        ],
        key=lambda id_and_description: id_and_description[1],
    )


def _all_connections() -> list[tuple[str, UserConnector]]:
    return _get_connections_for(_get_connection_configs())


def _get_connections_for(configs: list[dict[str, Any]]) -> list[tuple[str, UserConnector]]:
    return [(cfg["id"], user_connector_registry[cfg["type"]](cfg)) for cfg in configs]


def _get_connection_configs() -> list[dict[str, Any]]:
    return builtin_connections + active_config.user_connections


_HTPASSWD_CONNECTION: UserConnection = {
    "type": "htpasswd",
    "id": "htpasswd",
    "disabled": False,
}
# The htpasswd connector is enabled by default and always executed first.
# NOTE: This list may be appended to in edition specific registration functions.
builtin_connections: list[UserConnection] = [_HTPASSWD_CONNECTION]


def get_ldap_connections() -> dict[str, LDAPConnectionTypedDict]:
    ldap_connections = cast(
        dict[str, LDAPConnectionTypedDict],
        {c["id"]: c for c in active_config.user_connections if c["type"] == "ldap"},
    )
    return ldap_connections


def get_active_ldap_connections() -> dict[str, LDAPConnectionTypedDict]:
    return {
        ldap_id: ldap_connection
        for ldap_id, ldap_connection in get_ldap_connections().items()
        if not ldap_connection["disabled"]
    }


def get_saml_connections() -> dict[str, SAMLConnectionTypedDict]:
    saml_connections = cast(
        dict[str, SAMLConnectionTypedDict],
        {c["id"]: c for c in active_config.user_connections if c["type"] == "saml2"},
    )
    return saml_connections


def get_active_saml_connections() -> dict[str, SAMLConnectionTypedDict]:
    return {
        saml_id: saml_connection
        for saml_id, saml_connection in get_saml_connections().items()
        if not saml_connection["disabled"]
    }


# The saved configuration for user connections is a bit inconsistent, let's fix
# this here once and for all.
def fix_user_connections() -> None:
    for cfg in active_config.user_connections:
        # Although our current configuration always seems to have a 'disabled'
        # entry, this might not have always been the case.
        cfg.setdefault("disabled", False)
        # Only migrated configurations have a 'type' entry, all others are
        # implictly LDAP connections.
        cfg.setdefault("type", "ldap")


def locked_attributes(connection_id: str | None) -> Sequence[str]:
    """Returns a list of connection specific locked attributes"""
    return _get_attributes(connection_id, lambda c: c.locked_attributes())


def multisite_attributes(connection_id: str | None) -> Sequence[str]:
    """Returns a list of connection specific multisite attributes"""
    return _get_attributes(connection_id, lambda c: c.multisite_attributes())


def non_contact_attributes(connection_id: str | None) -> Sequence[str]:
    """Returns a list of connection specific non contact attributes"""
    return _get_attributes(connection_id, lambda c: c.non_contact_attributes())


def _get_attributes(
    connection_id: str | None, selector: Callable[[UserConnector], Sequence[str]]
) -> Sequence[str]:
    connection = get_connection(connection_id)
    return selector(connection) if connection else []


def _multisite_dir() -> str:
    return cmk.utils.paths.default_config_dir + "/multisite.d/wato/"


def load_connection_config(lock: bool = False) -> list[UserConnectionSpec]:
    """Load the configured connections for the Setup

    Note:
        This function should only be used in the Setup context, when configuring
        the connections. During UI rendering, `active_config.user_connections` must
        be used.
    """
    filename = os.path.join(_multisite_dir(), "user_connections.mk")
    return store.load_from_mk_file(filename, "user_connections", default=[], lock=lock)


def save_connection_config(
    connections: list[UserConnectionSpec], base_dir: str | None = None
) -> None:
    """Save the connections for the Setup

    Note:
        This function should only be used in the Setup context, when configuring
        the connections. During UI rendering, `active_config.user_connections` must
        be used.
    """
    if not base_dir:
        base_dir = _multisite_dir()
    store.mkdir(base_dir)
    store.save_to_mk_file(
        os.path.join(base_dir, "user_connections.mk"), "user_connections", connections
    )

    for connector_class in user_connector_registry.values():
        connector_class.config_changed()

    clear_user_connection_cache()
