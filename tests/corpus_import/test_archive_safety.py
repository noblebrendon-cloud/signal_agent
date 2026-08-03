from __future__ import annotations

import stat
import struct
import zipfile
from pathlib import Path

import pytest

from signal_agent.corpus_import.archive_safety import normalize_member_path, scan_archive
from signal_agent.corpus_import.errors import (
    ArchiveMemberCollisionError,
    ArchivePolicyError,
    InsufficientDiskSpaceError,
    UnreadableArchiveError,
    UnsafeArchivePathError,
    UnsupportedArchiveMemberError,
)
from signal_agent.corpus_import.models import ArchivePolicy


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.txt",
        "nested/../../escape.txt",
        "nested\\..\\escape.txt",
        "/absolute.txt",
        "C:/drive.txt",
        "\\root-relative.txt",
        "//server/share.txt",
        "bad\x00name.txt",
        "bad\x1fname.txt",
        "CON.txt",
        "nested/LPT1.json",
        "name:stream",
        "trailing-dot.",
        "trailing-space ",
        "invalid?.txt",
    ],
)
def test_unsafe_member_names_are_rejected(member_name: str) -> None:
    with pytest.raises(UnsafeArchivePathError):
        normalize_member_path(member_name)


def test_paths_are_normalized_to_nfc_posix_form() -> None:
    normalized, is_directory = normalize_member_path("nested//cafe\u0301/file.json")

    assert normalized == "nested/café/file.json"
    assert is_directory is False


def test_exact_duplicate_members_are_rejected(synthetic_run_factory) -> None:
    def writer(archive: zipfile.ZipFile) -> None:
        archive.writestr("conversations.json", "[]")
        archive.writestr("duplicate.txt", "one")
        archive.writestr("duplicate.txt", "two")

    with pytest.warns(UserWarning):
        run_root = synthetic_run_factory.create_with_writer(writer)

    with pytest.raises(ArchiveMemberCollisionError) as caught:
        scan_archive(
            run_root / "00_original" / "export.zip",
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )
    assert caught.value.context["collision_type"] == "exact_duplicate"


@pytest.mark.parametrize(
    ("members", "collision_type"),
    [
        (
            [
                ("conversations.json", "[]"),
                ("nested//file.txt", "one"),
                ("nested/file.txt", "two"),
            ],
            "normalized_duplicate",
        ),
        (
            [
                ("conversations.json", "[]"),
                ("Folder/one.txt", "one"),
                ("folder/two.txt", "two"),
            ],
            "casefold_collision",
        ),
        (
            [
                ("conversations.json", "[]"),
                ("cafe\u0301.txt", "one"),
                ("café.txt", "two"),
            ],
            "unicode_normalization_collision",
        ),
        (
            [
                ("conversations.json", "[]"),
                ("cafe\u0301/one.txt", "one"),
                ("café/two.txt", "two"),
            ],
            "unicode_normalization_collision",
        ),
        (
            [
                ("conversations.json", "[]"),
                ("folder", "file"),
                ("folder/child.txt", "child"),
            ],
            "file_directory_conflict",
        ),
    ],
)
def test_output_path_collisions_are_rejected(
    synthetic_run_factory,
    members: list[tuple[str, str]],
    collision_type: str,
) -> None:
    run_root = synthetic_run_factory.create(members)

    with pytest.raises(ArchiveMemberCollisionError) as caught:
        scan_archive(
            run_root / "00_original" / "export.zip",
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )
    assert caught.value.context["collision_type"] == collision_type


@pytest.mark.parametrize(
    ("filesystem_type", "member_type"),
    [
        (stat.S_IFLNK, "symlink"),
        (stat.S_IFCHR, "character_device"),
        (stat.S_IFBLK, "block_device"),
        (stat.S_IFIFO, "fifo"),
        (stat.S_IFSOCK, "socket"),
    ],
)
def test_nonregular_members_are_rejected(
    synthetic_run_factory,
    filesystem_type: int,
    member_type: str,
) -> None:
    def writer(archive: zipfile.ZipFile) -> None:
        archive.writestr("conversations.json", "[]")
        info = zipfile.ZipInfo("unsafe-member")
        info.create_system = 3
        info.external_attr = (filesystem_type | 0o777) << 16
        archive.writestr(info, "target")

    run_root = synthetic_run_factory.create_with_writer(writer)

    with pytest.raises(UnsupportedArchiveMemberError) as caught:
        scan_archive(
            run_root / "00_original" / "export.zip",
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )
    assert caught.value.context["member_type"] == member_type


def _patch_central_u16(source: Path, offset: int, value: int) -> None:
    payload = bytearray(source.read_bytes())
    central = payload.index(b"PK\x01\x02")
    struct.pack_into("<H", payload, central + offset, value)
    source.write_bytes(payload)


def test_encrypted_entry_is_rejected_before_extraction(tmp_path: Path) -> None:
    source = tmp_path / "encrypted-flag.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("conversations.json", "[]")
    _patch_central_u16(source, 8, 0x1)

    with pytest.raises(UnsupportedArchiveMemberError) as caught:
        scan_archive(
            source,
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )
    assert caught.value.context["member_type"] == "encrypted"


def test_unsupported_compression_method_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "unsupported-method.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("conversations.json", "[]")
    _patch_central_u16(source, 10, 99)

    with pytest.raises(UnsupportedArchiveMemberError):
        scan_archive(
            source,
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )


@pytest.mark.parametrize(
    "policy",
    [
        ArchivePolicy(max_archive_members=1),
        ArchivePolicy(max_declared_total_bytes=10),
        ArchivePolicy(max_member_bytes=10),
        ArchivePolicy(max_expansion_ratio=2),
    ],
)
def test_declared_decompression_limits_are_enforced(
    synthetic_run_factory,
    policy: ArchivePolicy,
) -> None:
    run_root = synthetic_run_factory.create(
        [
            ("conversations.json", b"0" * 100),
            ("other.txt", b"1" * 100),
        ]
    )

    with pytest.raises(ArchivePolicyError):
        scan_archive(
            run_root / "00_original" / "export.zip",
            policy=policy,
            available_free_bytes=10 * 1024**3,
        )


def test_path_and_component_length_limits_are_enforced(synthetic_run_factory) -> None:
    run_root = synthetic_run_factory.create(
        [
            ("conversations.json", "[]"),
            ("nested/" + ("a" * 20) + ".txt", "content"),
        ]
    )
    source = run_root / "00_original" / "export.zip"

    with pytest.raises(ArchivePolicyError) as component_error:
        scan_archive(
            source,
            policy=ArchivePolicy(max_component_length=10),
            available_free_bytes=10 * 1024**3,
        )
    assert component_error.value.context["policy_field"] == "max_component_length"

    with pytest.raises(ArchivePolicyError) as path_error:
        scan_archive(
            source,
            policy=ArchivePolicy(max_path_length=20),
            available_free_bytes=10 * 1024**3,
        )
    assert path_error.value.context["policy_field"] == "max_path_length"


def test_insufficient_disk_space_is_refused(synthetic_run_factory) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])

    with pytest.raises(InsufficientDiskSpaceError):
        scan_archive(
            run_root / "00_original" / "export.zip",
            policy=ArchivePolicy(),
            available_free_bytes=1,
        )


def test_truncated_archive_is_typed_as_unreadable(tmp_path: Path) -> None:
    source = tmp_path / "truncated.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("conversations.json", "[]")
    source.write_bytes(source.read_bytes()[:-12])

    with pytest.raises(UnreadableArchiveError):
        scan_archive(
            source,
            policy=ArchivePolicy(),
            available_free_bytes=10 * 1024**3,
        )
