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


def test_metrics_collector_reports_p99_for_stage_samples():
    collector = MetricsCollector()

    for value in range(1, 101):
        collector.record_operation_time("memory_query", float(value))

    metrics = collector.get_metrics()

    assert metrics.memory_query_p50 == 51.0
    assert metrics.memory_query_p95 == 96.0
    assert metrics.memory_query_p99 == 100.0


def test_metrics_collector_bounds_stage_samples():
    collector = MetricsCollector(max_samples=3)

    for value in (1.0, 2.0, 3.0, 4.0, 5.0):
        collector.record_operation_time("db_operation", value)

    metrics = collector.get_metrics()

    assert len(collector.db_operation_times) == 3
    assert metrics.db_operation_p50 == 4.0
    assert metrics.db_operation_p95 == 5.0
    assert metrics.db_operation_p99 == 5.0


def test_metrics_collector_reports_api_and_request_success_rates():
    collector = MetricsCollector()

    for success in (True, True, True, False):
        collector.record_embedding_api_call(success)
    for success in (True, False):
        collector.record_vector_db_api_call(success)
    for success in (True, True, True, False):
        collector.record_request(success)

    metrics = collector.get_metrics()

    assert metrics.embedding_api_success_rate == 75.0
    assert metrics.milvus_api_success_rate == 50.0
    assert metrics.to_dict()["requests"]["success_rate"] == 75.0


def test_monitoring_service_reuses_plugin_level_collector():
    plugin = SimpleNamespace()

    service = MonitoringService(plugin)

    assert plugin.metrics_collector is service.metrics_collector
    service.record_operation_time("vector_search", 42.0)
    assert service.get_performance_metrics().vector_search_p50 == 42.0
