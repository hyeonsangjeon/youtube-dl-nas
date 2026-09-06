import pytest

from fixtures.container_rss import process_rss_bytes, total_rss_bytes


def test_rss_parser_counts_resident_memory_not_virtual_size():
    assert process_rss_bytes("VmSize: 999999 kB\nVmRSS: 1234 kB\n") == 1234 * 1024
    assert process_rss_bytes("Name: kernel-thread\n") == 0


def test_rss_parser_rejects_an_unknown_unit():
    with pytest.raises(ValueError):
        process_rss_bytes("VmRSS: 123 MB\n")


def test_rss_total_excludes_probe_and_ignores_exited_processes(tmp_path):
    for pid, rss in ((1, 100), (2, 250), (3, 4000)):
        process = tmp_path / str(pid)
        process.mkdir()
        (process / "status").write_text(f"VmRSS: {rss} kB\n")
    (tmp_path / "4").mkdir()
    (tmp_path / "sys").mkdir()
    assert total_rss_bytes(tmp_path, own_pid=3) == 350 * 1024
