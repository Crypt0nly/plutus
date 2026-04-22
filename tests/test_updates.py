from packaging.tags import Tag

from plutus.gateway.routes import (
    _latest_compatible_release_version,
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
