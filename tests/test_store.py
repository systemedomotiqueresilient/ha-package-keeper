"""Fichiers : noms sûrs, détection des packages, sauvegardes."""

from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.package_keeper import store
from custom_components.package_keeper.store import PackageError


@pytest.mark.parametrize(
    ("name", "parts"),
    [
        ("derivee_wc", ("derivee_wc",)),
        ("derivee_wc.yaml", ("derivee_wc",)),
        ("chauffage/derivee_wc", ("chauffage", "derivee_wc")),
    ],
)
def test_valid_names(name: str, parts: tuple[str, ...]) -> None:
    assert store.validate_name(name) == parts


@pytest.mark.parametrize(
    "name",
    ["", "../configuration", "/etc/passwd", "Derivee", "a b", "x/../y", "a/b/c/d/e", "é", None],
)
def test_invalid_names(name) -> None:
    with pytest.raises(PackageError) as err:
        store.validate_name(name)
    assert err.value.code == "invalid_name"


def test_detect_setup(tmp_path: Path) -> None:
    cfg = tmp_path
    assert not store.detect_setup(str(cfg)).enabled  # pas de configuration.yaml

    (cfg / "configuration.yaml").write_text("default_config:\n", encoding="utf-8")
    assert not store.detect_setup(str(cfg)).enabled

    (cfg / "configuration.yaml").write_text(
        "homeassistant:\n  # packages: !include_dir_named ancien\n"
        "  packages: !include_dir_merge_named mes_packages\n",
        encoding="utf-8",
    )
    setup = store.detect_setup(str(cfg))
    assert setup.enabled
    assert setup.mode == "include_dir_merge_named"
    assert setup.directory == (cfg / "mes_packages").resolve()


def test_symlink_refused(tmp_path: Path) -> None:
    pkg = tmp_path / "packages"
    pkg.mkdir()
    outside = tmp_path / "ailleurs"
    outside.mkdir()
    (pkg / "lien").symlink_to(outside, target_is_directory=True)
    setup = store.PackagesSetup(True, "include_dir_named", pkg)
    with pytest.raises(PackageError):
        store.package_path(setup, "lien/x")


def test_description() -> None:
    assert store.description("# packages/x.yaml\n# Chauffage mobile\nclimate:\n") == "Chauffage mobile"
    assert store.description("# =====\n# sensor:\n# =====\nsensor:\n") is None
    assert store.description("sensor:\n# Commentaire tardif\n") is None


def test_check_text() -> None:
    assert store.check_text("a: 1") == b"a: 1\n"
    assert store.check_text("a: 1\r\nb: 2\r\n") == b"a: 1\nb: 2\n"
    for bad, code in (("   ", "empty"), ("x" * (store.MAX_PACKAGE_BYTES + 1), "too_large")):
        with pytest.raises(PackageError) as err:
            store.check_text(bad)
        assert err.value.code == code


def test_backups_pruned_and_listed(tmp_path: Path) -> None:
    pkg = tmp_path / "packages"
    pkg.mkdir()
    setup = store.PackagesSetup(True, "include_dir_named", pkg)
    assert store.backup(str(tmp_path), setup, "x", 2, "before_saved") is None  # rien à sauver

    (pkg / "x.yaml").write_text("v: 1\n", encoding="utf-8")
    ids = [store.backup(str(tmp_path), setup, "x", 2, "before_saved") for _ in range(3)]
    backups = store.list_backups(str(tmp_path), "x")
    assert len(backups) == 2
    assert ids[0] not in {b["id"] for b in backups}
    assert store.read_backup(str(tmp_path), "x", backups[0]["id"]) == "v: 1\n"
    with pytest.raises(PackageError):
        store.read_backup(str(tmp_path), "x", "../../secrets.yaml")


def test_list_packages_skips_unmanaged_names(tmp_path: Path) -> None:
    pkg = tmp_path / "packages"
    (pkg / "sous").mkdir(parents=True)
    (pkg / "ok.yaml").write_text("# Mon package\nsensor:\n", encoding="utf-8")
    (pkg / "sous" / "imbrique.yaml").write_text("sensor:\n", encoding="utf-8")
    (pkg / "Majuscule.yaml").write_text("sensor:\n", encoding="utf-8")
    setup = store.PackagesSetup(True, "include_dir_named", pkg)
    names = {p["name"]: p for p in store.list_packages(setup)}
    assert set(names) == {"ok", "sous/imbrique"}
    assert names["ok"]["description"] == "Mon package"
