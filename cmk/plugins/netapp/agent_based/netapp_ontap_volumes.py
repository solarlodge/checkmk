#!/usr/bin/env python3
# Copyright (C) 2024 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

import time
from collections.abc import Iterable, Mapping, MutableMapping, Sequence
from typing import Any

from cmk.agent_based.v2 import (
    AgentSection,
    CheckPlugin,
    get_value_store,
    Metric,
    Result,
    RuleSetType,
    State,
)
from cmk.agent_based.v2.type_defs import CheckResult, DiscoveryResult, StringTable
from cmk.plugins.lib.df import (
    df_check_filesystem_single,
    df_discovery,
    FILESYSTEM_DEFAULT_LEVELS,
    INODES_DEFAULT_PARAMS,
    MAGIC_FACTOR_DEFAULT_PARAMS,
    mountpoints_in_group,
    TREND_DEFAULT_PARAMS,
)
from cmk.plugins.lib.netapp_api import combine_netapp_api_volumes, single_volume_metrics
from cmk.plugins.netapp import models

VolumesSection = Mapping[str, models.VolumeModel]
VolumesCountersSection = Mapping[str, models.VolumeCountersModel]


# <<<netapp_ontap_volumes:sep(0)>>>
# {
#     "files": {"maximum": 21251126, "used": 97},
#     "msid": 2147484705,
#     "name": "Test_300T",
#     "space": {
#         "afs_total": 329853488332800,
#         "available": 12804446535680,
#         "logical_space": {"enforcement": false, "used": 1433600},
#     },
#     "state": "online",
#     "svm": {"name": "FlexPodXCS_NFS_Frank", "uuid": "208cfe14-c334-11ed-afdc-00a098c50e5b"},
#     "uuid": "00b3e6b1-5781-11ee-b0c8-00a098c54c0b",
# }
# {
#     "files": {"maximum": 31122, "used": 101},
#     "msid": 2147484684,
#     "name": "svm_ansible_01_jl_root",
#     "space": {
#         "afs_total": 1020055552,
#         "available": 1019604992,
#         "logical_space": {"enforcement": false, "used": 450560},
#     },
#     "state": "online",
#     "svm": {"name": "svm_ansible_01_jl", "uuid": "00bd0f4e-27ac-11ee-8516-00a098c50e5b"},
#     "uuid": "0125d89f-27ac-11ee-8516-00a098c50e5b",
# }

# <<<netapp_ontap_volumes_counters:sep(0)>>>
# {
#     "counters": [
#         {"name": "bytes_read", "value": 495499},
#         {"name": "bytes_written", "value": 0},
#         {"name": "total_read_ops", "value": 605},
#         {"name": "total_write_ops", "value": 0},
#         {"name": "read_latency", "value": 10659},
#         {"name": "write_latency", "value": 0},
#         {"name": "cifs.read_data", "value": 0},
#         {"name": "cifs.read_latency", "value": 0},
#         {"name": "cifs.read_ops", "value": 0},
#         {"name": "cifs.write_data", "value": 0},
#         {"name": "cifs.write_latency", "value": 0},
#         {"name": "cifs.write_ops", "value": 0},
#         {"name": "nfs.read_data", "value": 0},
#         {"name": "nfs.read_latency", "value": 0},
#         {"name": "nfs.read_ops", "value": 0},
#         {"name": "nfs.write_data", "value": 0},
#         {"name": "nfs.write_latency", "value": 0},
#         {"name": "nfs.write_ops", "value": 0},
#         {"name": "iscsi.read_data", "value": 0},
#         {"name": "iscsi.read_latency", "value": 0},
#         {"name": "iscsi.read_ops", "value": 0},
#         {"name": "iscsi.write_data", "value": 0},
#         {"name": "iscsi.write_latency", "value": 0},
#         {"name": "iscsi.write_ops", "value": 0},
#         {"name": "fcp.read_data", "value": 0},
#         {"name": "fcp.read_latency", "value": 0},
#         {"name": "fcp.read_ops", "value": 0},
#         {"name": "fcp.write_data", "value": 0},
#         {"name": "fcp.write_latency", "value": 0},
#         {"name": "fcp.write_ops", "value": 0},
#     ],
#     "id": "mcc_darz_a-01:FlexPodXCS_NFS_Frank:Test_300T:00b3e6b1-5781-11ee-b0c8-00a098c54c0b",
# }


def parse_netapp_ontap_volumes(
    string_table: StringTable,
) -> VolumesSection:
    return {
        vol_obj.item_name(): vol_obj
        for vol in string_table
        if (vol_obj := models.VolumeModel.model_validate_json(vol[0]))
    }


agent_section_netapp_ontap_volumes = AgentSection(
    name="netapp_ontap_volumes",
    parse_function=parse_netapp_ontap_volumes,
)


def parse_netapp_ontap_volumes_counters(
    string_table: StringTable,
) -> VolumesCountersSection:
    return {
        counter_obj.item_name(): counter_obj
        for line in string_table
        if (counter_obj := models.VolumeCountersModel.model_validate_json(line[0]))
    }


agent_section_netapp_ontap_volumes_counters = AgentSection(
    name="netapp_ontap_volumes_counters",
    parse_function=parse_netapp_ontap_volumes_counters,
)


def _get_volume_counters_key(volume: models.VolumeModel) -> str:
    return f"{volume.svm_name}:{volume.name}:{volume.uuid}"


def discover_netapp_ontap_volumes(
    params: Sequence[Mapping[str, Any]],
    section_netapp_ontap_volumes: VolumesSection | None,
    section_netapp_ontap_volumes_counters: VolumesCountersSection | None,
) -> DiscoveryResult:
    if section_netapp_ontap_volumes:
        yield from df_discovery(params, section_netapp_ontap_volumes)


def _check_single_netapp_volume(
    item: str,
    params: Mapping[str, Any],
    volume: models.VolumeModel,
    volume_counter: models.VolumeCountersModel,
) -> CheckResult:
    if volume.incomplete():
        return

    value_store = get_value_store()

    assert volume.files_used is not None  # to avoid my-py complaining about this being None
    assert volume.files_maximum is not None  # to avoid my-py complaining about this being None
    inodes_total = volume.files_maximum
    yield from df_check_filesystem_single(
        value_store,
        item,
        volume.size_total(),
        volume.size_available(),
        0,
        inodes_total,
        inodes_total - volume.files_used,
        params,
    )

    assert volume.space_total is not None  # to avoid my-py complaining about this being None
    assert volume.logical_used is not None  # to avoid my-py complaining about this being None
    assert volume.space_available is not None  # to avoid my-py complaining about this being None
    yield from _generate_volume_metrics(value_store, params, volume_counter)
    if not volume.logical_enforcement:
        logical_available = volume.space_total - volume.logical_used
        yield Metric(
            name="logical_used",
            value=volume.logical_used,
            boundaries=(0.0, volume.space_total),
        )
        yield Metric(
            name="space_savings",
            value=volume.space_available - logical_available,
            boundaries=(0.0, volume.space_total),
        )


def _generate_volume_metrics(
    value_store: MutableMapping[str, Any],
    params: Mapping[str, Any],
    volume_counter: models.VolumeCountersModel,
) -> Iterable[Metric]:
    now = time.time()

    for protocol in params.get("perfdata", []):
        # build the actual keys
        # tuple format: (protocol, mode, field)
        if not protocol:  # if it is an empty string, keys should be build differently
            counters_keys = [
                ("", "total_read", "ops"),  # was: read_ops
                ("", "bytes", "written"),  # was: write_data
                ("", "bytes", "read"),  # was: read_data
                ("", "total_write", "ops"),  # was: write_ops
                ("", "write", "latency"),  # was: write_latency
                ("", "read", "latency"),  # was: read_latency
            ]
        else:
            counters_keys = [
                (protocol, mode, field)
                for mode in ["read", "write", "other"]
                for field in ["data", "ops", "latency"]
            ]

        yield from single_volume_metrics(
            counters_keys, volume_counter.model_dump(), value_store, now
        )


def _serialize_volumes(
    section_netapp_ontap_volumes: VolumesSection,
    section_netapp_ontap_volumes_counters: VolumesCountersSection,
) -> Mapping[str, Mapping[str, int | str]]:
    merged_section = {}

    for key, volume in section_netapp_ontap_volumes.items():
        volume_counter = section_netapp_ontap_volumes_counters.get(
            _get_volume_counters_key(volume), None
        )

        merged_section[key] = volume.model_dump() | (
            volume_counter.model_dump() if volume_counter is not None else {}
        )

    return merged_section


def _deserialize_volume(
    combined_volumes: Mapping[str, float]
) -> tuple[models.VolumeModel, models.VolumeCountersModel | None]:
    # if the dictionary contains "id" it means it has counters values
    if combined_volumes.get("id", None) is not None:
        return models.VolumeModel.model_validate(
            combined_volumes
        ), models.VolumeCountersModel.model_validate(combined_volumes)

    return models.VolumeModel.model_validate(combined_volumes), None


def check_netapp_ontap_volumes(
    item: str,
    params: Mapping[str, Any],
    section_netapp_ontap_volumes: VolumesSection | None,
    section_netapp_ontap_volumes_counters: VolumesCountersSection | None,
) -> CheckResult:
    """
    The API is responding with no counters for some online volumes.
    """

    if not section_netapp_ontap_volumes or not section_netapp_ontap_volumes_counters:
        return

    if "patterns" in params:
        volumes_in_group = mountpoints_in_group(section_netapp_ontap_volumes, *params["patterns"])

        if not volumes_in_group:
            yield Result(
                state=State.UNKNOWN,
                summary="No volumes matching the patterns of this group",
            )
            return

        volumes = _serialize_volumes(
            section_netapp_ontap_volumes, section_netapp_ontap_volumes_counters
        )

        combined_volumes_data, volumes_not_online = combine_netapp_api_volumes(
            volumes_in_group, volumes
        )

        for vol, state in volumes_not_online.items():
            yield Result(state=State.WARN, summary=f"Volume {vol} is {state or 'Unknown'}")

        combined_volumes, combined_volumes_counters = _deserialize_volume(combined_volumes_data)

        if combined_volumes and combined_volumes_counters:
            yield from _check_single_netapp_volume(
                item, params, combined_volumes, combined_volumes_counters
            )
            yield Result(state=State.OK, notice="%d volume(s) in group" % len(volumes_in_group))

        return

    if not (volume := section_netapp_ontap_volumes.get(item)):
        return

    if not volume.state or volume.state != "online":
        # There are volumes with state to None... are they offline? - waiting for discord reponse
        yield Result(state=State.WARN, summary=f"Volume state {volume.state or 'Unknown'}")
        return

    if not section_netapp_ontap_volumes_counters:
        return

    if (
        volume_counter := section_netapp_ontap_volumes_counters.get(
            _get_volume_counters_key(volume)
        )
    ) is None:
        return
    yield from _check_single_netapp_volume(item, params, volume, volume_counter)


check_plugin_netapp_ontap_volumes = CheckPlugin(
    name="netapp_ontap_volumes",
    service_name="Volume %s",
    discovery_function=discover_netapp_ontap_volumes,
    discovery_default_parameters={
        "groups": [],
    },
    discovery_ruleset_name="filesystem_groups",
    discovery_ruleset_type=RuleSetType.ALL,
    check_function=check_netapp_ontap_volumes,
    sections=["netapp_ontap_volumes", "netapp_ontap_volumes_counters"],
    check_default_parameters={
        **FILESYSTEM_DEFAULT_LEVELS,
        **MAGIC_FACTOR_DEFAULT_PARAMS,
        **INODES_DEFAULT_PARAMS,
        **TREND_DEFAULT_PARAMS,
    },
    check_ruleset_name="netapp_volumes",
)
