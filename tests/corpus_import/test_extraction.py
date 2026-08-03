from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import pytest

from signal_agent.corpus_import.archive_safety import scan_archive
from signal_agent.corpus_import.errors import ArchivePolicyError, ExtractionError
from signal_agent.corpus_import.extraction import (
    MAX_STREAM_CHUNK_SIZE,
    extract_archive_to_staging,
)
from signal_agent.corpus_import.models import ArchivePolicy


def _plan(run_root: Path, policy: ArchivePolicy | None = None):
    return scan_archive(
        run_root / "00_original" / "export.zip",
        policy=policy or ArchivePolicy(),
        available_free_bytes=10 * 1024**3,
    )


def test_streamed_extraction_writes_exact_member_bytes(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    expected = {
        "conversations.json": b'[{"id":"one"}]',
        "nested/binary.dat": bytes(range(256)) * 8,
        "empty.txt": b"",
    }
    run_root = synthetic_run_factory.create(list(expected.items()))
    source = run_root / "00_original" / "export.zip"

    result = extract_archive_to_staging(
        source,
        _plan(run_root),
        tmp_path / "staged-extract",
        policy=ArchivePolicy(),
        chunk_size=17,
    )

    assert result.actual_bytes_written == sum(map(len, expected.values()))
    assert {item.path for item in result.files} == set(expected)
    for relative_path, content in expected.items():
        assert (tmp_path / "staged-extract").joinpath(*relative_path.split("/")).read_bytes() == content


def test_extraction_reads_in_bounded_chunks(
    synthetic_run_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_root = synthetic_run_factory.create(
        [
            ("conversations.json", b"x" * (3 * 1024 * 1024)),
        ],
        compression=zipfile.ZIP_STORED,
    )
    observed_read_sizes: list[int] = []
    original_read = zipfile.ZipExtFile.read

    def bounded_read(handle, size=-1):
        observed_read_sizes.append(size)
        return original_read(handle, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded_read)
    extract_archive_to_staging(
        run_root / "00_original" / "export.zip",
        _plan(run_root),
        tmp_path / "bounded",
        policy=ArchivePolicy(),
        chunk_size=1024 * 1024,
    )

    assert observed_read_sizes
    assert -1 not in observed_read_sizes
    assert max(observed_read_sizes) <= MAX_STREAM_CHUNK_SIZE


def test_chunk_size_above_one_mib_is_refused(synthetic_run_factory, tmp_path: Path) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", "[]")])

    with pytest.raises(ValueError):
        extract_archive_to_staging(
            run_root / "00_original" / "export.zip",
            _plan(run_root),
            tmp_path / "too-large-chunk",
            policy=ArchivePolicy(),
            chunk_size=MAX_STREAM_CHUNK_SIZE + 1,
        )


def test_actual_streamed_total_limit_is_enforced(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    policy = ArchivePolicy(max_actual_total_bytes=10)
    run_root = synthetic_run_factory.create([("conversations.json", b"x" * 20)])
    plan = _plan(run_root, policy)

    with pytest.raises(ArchivePolicyError) as caught:
        extract_archive_to_staging(
            run_root / "00_original" / "export.zip",
            plan,
            tmp_path / "limited",
            policy=policy,
            chunk_size=4,
        )
    assert caught.value.context["policy_field"] == "max_actual_total_bytes"


def _corrupt_first_member_payload(source: Path) -> None:
    payload = bytearray(source.read_bytes())
    with zipfile.ZipFile(source) as archive:
        info = archive.infolist()[0]
    header = info.header_offset
    filename_length, extra_length = struct.unpack_from("<HH", payload, header + 26)
    data_offset = header + 30 + filename_length + extra_length
    payload[data_offset] ^= 0xFF
    source.write_bytes(payload)


def test_corrupted_crc_is_rejected_during_streaming(
    synthetic_run_factory,
    tmp_path: Path,
) -> None:
    run_root = synthetic_run_factory.create(
        [("conversations.json", b"uncorrupted content")],
        compression=zipfile.ZIP_STORED,
    )
    source = run_root / "00_original" / "export.zip"
    plan = _plan(run_root)
    _corrupt_first_member_payload(source)

    with pytest.raises(ExtractionError):
        extract_archive_to_staging(
            source,
            plan,
            tmp_path / "corrupt",
            policy=ArchivePolicy(),
        )


def test_injected_archive_read_failure_is_typed(
    synthetic_run_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", b"content")])
    original_read = zipfile.ZipExtFile.read
    calls = 0

    def failing_read(handle, size=-1):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise OSError("injected read failure")
        return original_read(handle, min(size, 2))

    monkeypatch.setattr(zipfile.ZipExtFile, "read", failing_read)

    with pytest.raises(ExtractionError):
        extract_archive_to_staging(
            run_root / "00_original" / "export.zip",
            _plan(run_root),
            tmp_path / "read-failure",
            policy=ArchivePolicy(),
            chunk_size=2,
        )


def test_injected_destination_open_failure_is_typed(
    synthetic_run_factory,
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_root = synthetic_run_factory.create([("conversations.json", b"content")])
    destination_root = tmp_path / "write-failure"
    original_open = Path.open

    def failing_open(path: Path, mode="r", *args, **kwargs):
        if mode == "xb" and destination_root in path.parents:
            raise OSError("injected destination failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)

    with pytest.raises(ExtractionError):
        extract_archive_to_staging(
            run_root / "00_original" / "export.zip",
            _plan(run_root),
            destination_root,
            policy=ArchivePolicy(),
        )
