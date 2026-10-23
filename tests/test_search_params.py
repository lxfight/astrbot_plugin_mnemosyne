"""Milvus 默认搜索参数测试。"""

from astrbot_plugin_mnemosyne.core.initialization import _default_search_params


def test_autoindex_does_not_use_ivf_search_params():
    params = _default_search_params({"metric_type": "IP", "index_type": "AUTOINDEX"})

    assert params == {"metric_type": "IP", "params": {}}


def test_hnsw_uses_ef_search_param():
    params = _default_search_params({"metric_type": "L2", "index_type": "HNSW"})

    assert params == {"metric_type": "L2", "params": {"ef": 64}}
