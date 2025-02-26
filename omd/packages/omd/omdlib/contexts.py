#!/usr/bin/env python3
# Copyright (C) 2023 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.


import abc
import os
import sys
from pathlib import Path
from typing import cast

import omdlib
import omdlib.utils
from omdlib.init_scripts import check_status
from omdlib.skel_permissions import (
    load_skel_permissions_from,
    Permissions,
    skel_permissions_file_path,
)
from omdlib.type_defs import Config, Replacements
from omdlib.utils import is_containerized

from cmk.utils.exceptions import MKTerminate
from cmk.utils.version import Edition


class AbstractSiteContext(abc.ABC):
    """Object wrapping site specific information"""

    def __init__(self, sitename: str | None) -> None:
        super().__init__()
        self._sitename = sitename
        self._config_loaded = False
        self._config: Config = {}

    @property
    def name(self) -> str | None:
        return self._sitename

    @property
    @abc.abstractmethod
    def version(self) -> str | None:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def dir(self) -> str:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def tmp_dir(self) -> str:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def real_dir(self) -> str:
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def real_tmp_dir(self) -> str:
        raise NotImplementedError()

    @property
    def version_meta_dir(self) -> str:
        return "%s/.version_meta" % self.dir

    @property
    def conf(self) -> Config:
        """{ "CORE" : "nagios", ... } (contents of etc/omd/site.conf plus defaults from hooks)"""
        if not self._config_loaded:
            raise Exception("Config not loaded yet")
        return self._config

    @abc.abstractmethod
    def load_config(self, defaults: dict[str, str]) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def exists(self) -> bool:
        raise NotImplementedError()

    @abc.abstractmethod
    def is_empty(self) -> bool:
        raise NotImplementedError()

    @staticmethod
    @abc.abstractmethod
    def is_site_context() -> bool:
        raise NotImplementedError()


class SiteContext(AbstractSiteContext):
    @property
    def name(self) -> str:
        return cast(str, self._sitename)

    @property
    def dir(self) -> str:
        return os.path.join(omdlib.utils.omd_base_path(), "omd/sites", cast(str, self._sitename))

    @property
    def tmp_dir(self) -> str:
        return "%s/tmp" % self.dir

    @property
    def real_dir(self) -> str:
        return "/opt/" + self.dir.lstrip("/")

    @property
    def real_tmp_dir(self) -> str:
        return "%s/tmp" % self.real_dir

    @property
    def version(self) -> str | None:
        """The version of a site is solely determined by the link ~SITE/version
        In case the version of a site can not be determined, it reports None."""
        version_link = self.dir + "/version"
        try:
            return os.readlink(version_link).split("/")[-1]
        except Exception:
            return None

    @property
    def hook_dir(self) -> str | None:
        if self.version is None:
            return None
        return "/omd/versions/%s/lib/omd/hooks/" % self.version

    @property
    def replacements(self) -> Replacements:
        """Dictionary of key/value for replacing macros in skel files"""
        version = self.version
        if version is None:
            raise RuntimeError("Failed to determine site version")
        return {
            "###SITE###": self.name,
            "###ROOT###": self.dir,
            "###EDITION###": Edition[version.split(".")[-1].upper()].long,
        }

    def load_config(self, defaults: dict[str, str]) -> None:
        """Load all variables from omd/sites.conf. These variables always begin with
        CONFIG_. The reason is that this file can be sources with the shell.

        Puts these variables into the config dict without the CONFIG_. Also
        puts the variables into the process environment."""
        self._config = {**defaults, **self.read_site_config()}
        self._config_loaded = True

    def read_site_config(self) -> Config:
        """Read and parse the file site.conf of a site into a dictionary and returns it"""
        config: Config = {}
        if not (confpath := Path(self.dir, "etc/omd/site.conf")).exists():
            return {}

        with confpath.open() as conf_file:
            for line in conf_file:
                line = line.strip()
                if line == "" or line[0] == "#":
                    continue
                var, value = line.split("=", 1)
                if not var.startswith("CONFIG_"):
                    sys.stderr.write("Ignoring invalid variable %s.\n" % var)
                else:
                    config[var[7:].strip()] = value.strip().strip("'")

        return config

    def exists(self) -> bool:
        # In container environments the tmpfs may be managed by the container runtime (when
        # using the --tmpfs option).  In this case the site directory is
        # created as parent of the tmp directory to mount the tmpfs during
        # container initialization. Detect this situation and don't treat the
        # site as existing in that case.
        if is_containerized():
            if not os.path.exists(self.dir):
                return False
            if os.listdir(self.dir) == ["tmp"]:
                return False
            return True

        return os.path.exists(self.dir)

    def is_empty(self) -> bool:
        for entry in os.listdir(self.dir):
            if entry not in [".", ".."]:
                return False
        return True

    def is_autostart(self) -> bool:
        """Determines whether a specific site is set to autostart."""
        return self.conf.get("AUTOSTART", "on") == "on"

    def is_disabled(self) -> bool:
        """Whether or not this site has been disabled with 'omd disable'"""
        apache_conf = os.path.join(omdlib.utils.omd_base_path(), "omd/apache/%s.conf" % self.name)
        return not os.path.exists(apache_conf)

    def is_stopped(self) -> bool:
        """Check if site is completely stopped"""
        return check_status(self.dir, display=False) == 1

    @staticmethod
    def is_site_context() -> bool:
        return True

    @property
    def skel_permissions(self) -> Permissions:
        """Returns the skeleton permissions. Load either from version meta directory
        or from the original version skel.permissions file"""
        if not self._has_version_meta_data():
            if self.version is None:
                raise MKTerminate("Failed to determine site version")
            return load_skel_permissions_from(skel_permissions_file_path(self.version))

        return load_skel_permissions_from(self.version_meta_dir + "/skel.permissions")

    @property
    def version_skel_dir(self) -> str:
        """Returns the current version skel directory. In case the meta data is
        available and fits the sites version use that one instead of the version
        skel directory."""
        if not self._has_version_meta_data():
            return "/omd/versions/%s/skel" % self.version
        return self.version_meta_dir + "/skel"

    def _has_version_meta_data(self) -> bool:
        if not os.path.exists(self.version_meta_dir):
            return False

        if self._version_meta_data_version() != self.version:
            return False

        return True

    def _version_meta_data_version(self) -> str:
        with open(self.version_meta_dir + "/version") as f:
            return f.read().strip()


class RootContext(AbstractSiteContext):
    def __init__(self) -> None:
        super().__init__(sitename=None)

    @property
    def dir(self) -> str:
        """Absolute base path (without trailing slash)"""
        return "/"

    @property
    def tmp_dir(self) -> str:
        return "/tmp"  # nosec B108 # BNS:13b2c8

    @property
    def real_dir(self) -> str:
        """Absolute base path (without trailing slash)"""
        return "/" + self.dir.lstrip("/")

    @property
    def real_tmp_dir(self) -> str:
        return "%s/tmp" % self.real_dir

    @property
    def version(self) -> str:
        return omdlib.__version__

    def load_config(self, defaults: dict[str, str]) -> None:
        pass

    def exists(self) -> bool:
        return False

    def is_empty(self) -> bool:
        return False

    @staticmethod
    def is_site_context() -> bool:
        return False
