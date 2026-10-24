"""性能指标采集与分阶段延迟测试。"""

from types import SimpleNamespace

from admin_panel.services.monitoring_service import MetricsCollector, MonitoringService


def test_metrics_collector_tracks_rag_stage_percentiles():
    collector = MetricsCollector()

    for value in range(10, 101, 10):
        collector.record_operation_time("embedding", value)
    collector.record_operation_time("postprocess", 12.5)
    collector.record_operation_time("injection", 3.0)

    metrics = collector.get_metrics()

    assert metrics.rag_embedding_p50 == 60.0
    assert metrics.rag_embedding_p95 == 100.0
    assert metrics.rag_postprocess_p95 == 12.5
    assert metrics.rag_injection_p95 == 3.0

    payload = metrics.to_dict()
    assert payload["rag_stages"]["embedding"]["p95"] == 100.0
    assert payload["rag_stages"]["postprocess"]["p50"] == 12.5
    assert payload["rag_stages"]["injection"]["p50"] == 3.0


def test_monitoring_service_reuses_plugin_level_collector():
    plugin = SimpleNamespace()

    service = MonitoringService(plugin)

    assert plugin.metrics_collector is service.metrics_collector
    service.record_operation_time("vector_search", 42.0)
    assert service.get_performance_metrics().vector_search_p50 == 42.0
