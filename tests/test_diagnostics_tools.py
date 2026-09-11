from asistente_mikha.tools.diagnostics import (
    get_ram_usage,
    get_disk_usage,
    list_processes,
    get_gpu_status,
)


def test_get_ram_usage_returns_expected_keys():
    result = get_ram_usage()
    assert set(result.keys()) == {"total_gb", "used_gb", "available_gb", "percent_used"}
    assert result["total_gb"] > 0
    assert 0 <= result["percent_used"] <= 100


def test_get_disk_usage_default_path():
    result = get_disk_usage()
    assert result["path"] == "/"
    assert result["total_gb"] > 0
    assert 0 <= result["percent_used"] <= 100


def test_list_processes_respects_limit_and_sorts_desc():
    result = list_processes(limit=5)
    assert len(result) <= 5
    rss_values = [p["rss_mb"] for p in result]
    assert rss_values == sorted(rss_values, reverse=True)
    for entry in result:
        assert set(entry.keys()) == {"pid", "name", "rss_mb"}


def test_get_gpu_status_returns_structured_result():
    result = get_gpu_status()
    assert "available" in result
    if result["available"]:
        assert "vram_total_bytes" in result
        assert result["vram_total_bytes"] > 0
