from packaging.tags import Tag

from plutus.gateway.routes import (
    _github_asset_compatible_wheel_url,
    _latest_compatible_release_version,
    _latest_github_release_version,
    _release_has_compatible_wheel,
)


def test_release_has_compatible_wheel_matches_supported_tags():
    supported_tags = {Tag("cp311", "cp311", "manylinux_2_28_x86_64")}
    release_files = [
        {
            "filename": "plutus_ai-0.3.245-cp311-cp311-win_amd64.whl",
            "packagetype": "bdist_wheel",
            "requires_python": ">=3.11",
            "yanked": False,
        },
        {
            "filename": "plutus_ai-0.3.245-cp311-cp311-manylinux_2_28_x86_64.whl",
            "packagetype": "bdist_wheel",
            "requires_python": ">=3.11",
            "yanked": False,
        },
    ]

    assert _release_has_compatible_wheel(
        release_files,
        supported_tags=supported_tags,
        python_version="3.11.9",
    ) is True


def test_release_has_compatible_wheel_respects_requires_python():
    supported_tags = {Tag("cp311", "cp311", "manylinux_2_28_x86_64")}
    release_files = [
        {
            "filename": "plutus_ai-0.3.245-cp311-cp311-manylinux_2_28_x86_64.whl",
            "packagetype": "bdist_wheel",
            "requires_python": ">=3.12",
            "yanked": False,
        },
    ]

    assert _release_has_compatible_wheel(
        release_files,
        supported_tags=supported_tags,
        python_version="3.11.9",
    ) is False


def test_latest_compatible_release_version_skips_newer_incompatible_release():
    supported_tags = {Tag("cp311", "cp311", "manylinux_2_28_x86_64")}
    pypi_data = {
        "info": {"version": "0.3.246"},
        "releases": {
            "0.3.245": [
                {
                    "filename": "plutus_ai-0.3.245-cp311-cp311-manylinux_2_28_x86_64.whl",
                    "packagetype": "bdist_wheel",
                    "requires_python": ">=3.11",
                    "yanked": False,
                },
            ],
            "0.3.246": [
                {
                    "filename": "plutus_ai-0.3.246-cp311-cp311-win_amd64.whl",
                    "packagetype": "bdist_wheel",
                    "requires_python": ">=3.11",
                    "yanked": False,
                },
            ],
        },
    }

    assert _latest_compatible_release_version(
        pypi_data,
        supported_tags=supported_tags,
        python_version="3.11.9",
    ) == "0.3.245"


def test_github_asset_compatible_wheel_url_matches_supported_tags():
    supported_tags = {Tag("cp311", "cp311", "manylinux_2_28_x86_64")}
    assets = [
        {
            "name": "plutus_ai-0.3.280-cp311-cp311-win_amd64.whl",
            "browser_download_url": "https://example.test/win.whl",
        },
        {
            "name": "plutus_ai-0.3.280-cp311-cp311-manylinux_2_28_x86_64.whl",
            "browser_download_url": "https://example.test/linux.whl",
        },
    ]

    assert _github_asset_compatible_wheel_url(
        assets,
        supported_tags=supported_tags,
    ) == "https://example.test/linux.whl"


def test_latest_github_release_version_skips_drafts_prereleases_and_incompatible_assets():
    supported_tags = {Tag("cp311", "cp311", "manylinux_2_28_x86_64")}
    releases = [
        {
            "tag_name": "v0.3.282",
            "draft": False,
            "prerelease": True,
            "html_url": "https://example.test/pre",
            "assets": [
                {
                    "name": "plutus_ai-0.3.282-cp311-cp311-manylinux_2_28_x86_64.whl",
                    "browser_download_url": "https://example.test/pre.whl",
                }
            ],
        },
        {
            "tag_name": "v0.3.281",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.test/incompatible",
            "assets": [
                {
                    "name": "plutus_ai-0.3.281-cp311-cp311-win_amd64.whl",
                    "browser_download_url": "https://example.test/win.whl",
                }
            ],
        },
        {
            "tag_name": "v0.3.280",
            "draft": False,
            "prerelease": False,
            "html_url": "https://example.test/release",
            "assets": [
                {
                    "name": "plutus_ai-0.3.280-cp311-cp311-manylinux_2_28_x86_64.whl",
                    "browser_download_url": "https://example.test/linux.whl",
                }
            ],
        },
    ]

    assert _latest_github_release_version(
        releases,
        supported_tags=supported_tags,
    ) == (
        "0.3.280",
        "https://example.test/linux.whl",
        "https://example.test/release",
    )
