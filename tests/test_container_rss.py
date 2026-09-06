import pytest

from fixtures.container_rss import process_rss_bytes, process_rss_details, reviewed_budget_allows, total_rss_bytes


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
    assert process_rss_details(tmp_path, own_pid=3) == [
        {"pid": 1, "name": "unknown", "rss_bytes": 100 * 1024},
        {"pid": 2, "name": "unknown", "rss_bytes": 250 * 1024},
    ]


@pytest.mark.parametrize("override,allowed", [
    ({}, True),
    ({"version": "26.0910"}, False),
    ({"platform": "linux/arm64"}, False),
    ({"baseline_image": "different:baseline"}, False),
    ({"image_delta_bytes": 100_000_001}, False),
    ({"idle_rss_delta_bytes": 120_000_001}, False),
    ({"candidate_idle_rss_bytes": 180_000_001}, False),
])
def test_footprint_review_is_bounded_and_cannot_approve_other_releases(override, allowed):
    report = {
        "version": "26.0906", "platform": "linux/amd64", "baseline_image": "previous:release",
        "image_delta_bytes": 51_435_986, "idle_rss_delta_bytes": 107_057_152,
        "candidate_idle_rss_bytes": 157_036_544,
    }
    review = {
        "version": "26.0906", "platform": "linux/amd64", "baseline_image": "previous:release",
        "max_image_delta_bytes": 100_000_000, "max_idle_rss_delta_bytes": 120_000_000,
        "max_candidate_idle_rss_bytes": 180_000_000,
    }
    assert reviewed_budget_allows({**report, **override}, review) is allowed
