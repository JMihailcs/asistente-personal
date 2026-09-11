from asistente_mikha.tools.diagnostics import (
    get_ram_usage,
    get_disk_usage,
    list_processes,
    get_gpu_status,
    diagnostics,
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


def test_get_gpu_status_reports_unavailable_when_no_device_in_sysfs(monkeypatch):
    from asistente_mikha.tools import diagnostics as diagnostics_module

    monkeypatch.setattr(diagnostics_module, "DRM_DEVICES_GLOB", "/sys/class/drm/no-existe*/device")

    result = get_gpu_status()

    assert result["available"] is False
    assert "reason" in result


def test_diagnostics_router_dispatches_to_each_check():
    assert set(diagnostics(check="ram").keys()) == set(get_ram_usage().keys())
    assert diagnostics(check="disk", path="/")["path"] == "/"
    assert len(diagnostics(check="processes", limit=3)) <= 3
    assert "available" in diagnostics(check="gpu")
