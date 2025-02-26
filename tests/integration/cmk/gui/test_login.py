#!/usr/bin/env python3
# Copyright (C) 2019 Checkmk GmbH - License: GNU General Public License v2
# This file is part of Checkmk (https://checkmk.com). It is subject to the terms and
# conditions defined in the file COPYING, which is part of this source code package.

from tests.testlib import CMKWebSession
from tests.testlib.pytest_helpers.marks import skip_if_saas_edition
from tests.testlib.site import Site


@skip_if_saas_edition
def test_login_and_logout(site: Site) -> None:
    web = CMKWebSession(site)

    r = web.get("wato.py?mode=globalvars", allow_redirect_to_login=True)
    assert "Global settings" not in r.text

    web.login()
    site.enforce_non_localized_gui(web)
    r = web.get("wato.py?mode=globalvars")
    assert "Global settings" in r.text

    web.logout()
    r = web.get("wato.py?mode=globalvars", allow_redirect_to_login=True)
    assert "Global settings" not in r.text


@skip_if_saas_edition
def test_session_cookie(site: Site) -> None:
    web = CMKWebSession(site)
    web.login()

    cookie = web.get_auth_cookie()

    assert cookie is not None
    assert cookie.path == f"/{site.id}/"
    # This is ugly but IMHO the only way...
    assert "HttpOnly" in cookie.__dict__.get("_rest", {})
    assert cookie.__dict__.get("_rest", {}).get("SameSite") == "Lax"


@skip_if_saas_edition
def test_automation_user_gui(site: Site) -> None:
    """test authenticated request of an automation user to the gui

    - the HTTP param login must work in Checkmk 2.3
    - a session must not be established
    """
    username = "automation"
    password = site.get_automation_secret()

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        params={
            "_username": username,
            "_secret": password,
        },
    )
    assert "Dashboard" in response.text
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        auth=(username, password),
    )
    assert "Dashboard" in response.text
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        headers={
            "Authorization": f"Bearer {username} {password}",
        },
    )
    assert "Dashboard" in response.text
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None


@skip_if_saas_edition
def test_automation_user_rest_api(site: Site) -> None:
    """test authenticated request of an automation user to the rest api

    - the HTTP param login must work in Checkmk 2.3
    - a session must not be established
    """
    username = "automation"
    password = site.get_automation_secret()

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        params={
            "_username": username,
            "_secret": password,
        },
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        auth=(username, password),
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        headers={
            "Authorization": f"Bearer {username} {password}",
        },
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None


@skip_if_saas_edition
def test_human_user_gui(site: Site) -> None:
    """test authenticated request of a "normal"/"human" user to the gui

    - the HTTP param login must not work
    - a session must be established
    """
    username = "cmkadmin"
    password = site.admin_password

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        params={
            "_username": username,
            "_secret": password,
        },
        allow_redirect_to_login=True,
    )
    assert "Dashboard" not in response.text
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        auth=(username, password),
    )
    assert "Dashboard" in response.text
    assert session.is_logged_in()
    assert session.get_auth_cookie() is not None

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        headers={
            "Authorization": f"Bearer {username} {password}",
        },
    )
    assert "Dashboard" in response.text
    assert session.is_logged_in()
    assert session.get_auth_cookie() is not None


@skip_if_saas_edition
def test_human_user_restapi(site: Site) -> None:
    """test authenticated request of a "normal"/"human" user to the rest api

    - the HTTP param login must not work
    - a session must not be established
    """

    username = "cmkadmin"
    password = site.admin_password

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        params={
            "_username": username,
            "_secret": password,
        },
        expected_code=401,
    )
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        auth=(username, password),
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        headers={
            "Authorization": f"Bearer {username} {password}",
        },
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None


@skip_if_saas_edition
def test_local_secret_no_sessions(site: Site) -> None:
    """test authenticated request with the site internal secret

    - a session must not be established
    """
    b64_token = site.get_site_internal_secret().b64_str
    session = CMKWebSession(site)
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/version",
        headers={
            "Authorization": f"InternalToken {b64_token}",
        },
    )
    assert "site" in response.json()
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None

    session = CMKWebSession(site)
    response = session.get(
        "dashboard.py",
        headers={
            "Authorization": f"InternalToken {b64_token}",
        },
    )
    assert "Dashboard" in response.text
    assert not session.is_logged_in()
    assert session.get_auth_cookie() is None


def test_local_secret_permissions(site: Site) -> None:
    """test if all pages are accessible by the local_secret

    while introducing the secret and refactoring code to this secret we should
    add tests here to make sure the functionallity works..."""

    session = CMKWebSession(site)
    b64_token = site.get_site_internal_secret().b64_str
    response = session.get(
        f"/{site.id}/check_mk/api/1.0/agent_controller_certificates_settings",
        headers={
            "Authorization": f"InternalToken {b64_token}",
        },
    )
    assert response.status_code == 200
    assert isinstance(response.json()["lifetime_in_months"], int)
