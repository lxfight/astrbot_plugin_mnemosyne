(function enableDemoBridge() {
    const params = new URLSearchParams(window.location.search);
    if (window.AstrBotPluginView || params.get('demo') !== '1') return;

    const now = Date.now();
    const day = 86400000;
    const sessionIds = [
        'design-review-07',
        'release-planning',
        'vector-research',
        'daily-dialogue',
        'product-notes',
    ];
    const memoryTexts = [
        '用户偏好简洁而有层次的界面，希望关键信息在第一屏就可以完成扫描。',
        '下一个版本将聚焦记忆工作台、检索效率与管理面板的交互反馈。',
        '向量检索需要同时呈现相似度、来源会话与记录时间，便于判断结果质量。',
        '系统在晚间对长会话执行摘要，并保留原始消息的可追溯引用。',
        '发布前需要完成桌面端与移动端的视觉回归，并检查深色主题。',
        '会话筛选应支持键盘操作，批量动作只在存在选中项时出现。',
        '用户希望导出的记忆文件保持稳定字段，以便进入后续分析流程。',
        '监控页面应突出系统健康度，性能数据保持低噪声并适合快速扫描。',
    ];

    const memories = Array.from({ length: 42 }, (_, index) => ({
        memory_id: `memory-${String(index + 1).padStart(3, '0')}`,
        session_id: sessionIds[index % sessionIds.length],
        persona_id: index % 3 === 0 ? 'researcher' : 'default',
        content: memoryTexts[index % memoryTexts.length],
        create_time: new Date(now - index * 14400000).toISOString(),
        memory_type: index % 5 === 0 ? 'summary' : 'long_term',
        similarity_score: Math.max(0.71, 0.982 - index * 0.006),
    }));

    const sessions = sessionIds.map((sessionId, index) => ({
        session_id: sessionId,
        memory_count: memories.filter(memory => memory.session_id === sessionId).length,
        first_memory_time: new Date(now - (index + 12) * day).toISOString(),
        last_memory_time: new Date(now - index * 7200000).toISOString(),
    }));

    const memoriesByDate = Object.fromEntries(
        Array.from({ length: 18 }, (_, index) => {
            const date = new Date(now - (17 - index) * day).toISOString().slice(0, 10);
            return [date, 5 + ((index * 7) % 13)];
        }),
    );

    function filterMemories(query = {}) {
        const keyword = String(query.keyword || '').toLowerCase();
        const filtered = memories.filter(memory => (
            (!keyword || memory.content.toLowerCase().includes(keyword))
            && (!query.session_id || memory.session_id === query.session_id)
            && (!query.persona_id || memory.persona_id === query.persona_id)
        ));
        const offset = Number(query.offset || 0);
        const limit = Number(query.limit || 20);
        return {
            records: filtered.slice(offset, offset + limit),
            total_count: filtered.length,
            pagination: {
                page: Math.floor(offset / limit) + 1,
                page_size: limit,
                total: filtered.length,
                total_pages: Math.max(1, Math.ceil(filtered.length / limit)),
            },
        };
    }

    window.AstrBotPluginView = {
        ready: async () => ({ plugin: 'mnemosyne', mode: 'demo' }),
        apiGet: async (endpoint, query = {}) => {
            if (endpoint === 'monitoring/dashboard') {
                return {
                    status: {
                        overall_status: 'healthy',
                        components: {
                            milvus: { status: 'healthy', message: '索引与连接状态正常' },
                            embedding_api: { status: 'healthy', message: '平均响应 186 ms' },
                            message_counter: { status: 'healthy', message: '事件流持续同步' },
                            background_task: { status: 'degraded', message: '一个摘要任务等待重试' },
                        },
                    },
                    resources: {
                        vector_database: { total_records: 12842 },
                        sessions: { active: 18, total: 326 },
                        memory: { usage_percent: 43.7, used_mb: 716 },
                    },
                    metrics: {
                        memory_query: { p95: 48.2 },
                        vector_search: { p95: 112.6 },
                        db_operation: { p95: 18.4 },
                        api_success_rate: { embedding: 99.8, milvus: 99.9 },
                        requests: { total: 284612, success_rate: 99.7 },
                    },
                };
            }
            if (endpoint === 'memories/search') return filterMemories(query);
            if (endpoint === 'memories/sessions') return sessions;
            if (endpoint === 'memories/statistics') {
                return {
                    total_memories: 12842,
                    total_sessions: 326,
                    memories_by_date: memoriesByDate,
                    most_active_sessions: sessions.map(session => [session.session_id, session.memory_count * 11]),
                };
            }
            if (endpoint === 'config') {
                return {
                    vector_db_type: 'milvus',
                    embedding_model: 'text-embedding-3-large',
                    enable_memory: true,
                    summary_threshold: 32,
                    similarity_threshold: 0.78,
                    memory_prompt: '提取稳定、可复用且有明确上下文的长期记忆。',
                    retrieval: { top_k: 8, rerank: true, hybrid_search: true },
                };
            }
            throw new Error(`未知演示接口: ${endpoint}`);
        },
        apiPost: async (endpoint, body = {}) => {
            if (endpoint === 'memories/vector-search') {
                const records = memories.slice(0, Number(body.limit || 20));
                return { records, total_count: records.length };
            }
            const updateMatch = endpoint.match(/^memories\/([^/]+)\/update$/);
            if (updateMatch) {
                const memory = memories.find(item => item.memory_id === updateMatch[1]);
                if (!memory) return { status: 'error', message: '记忆记录不存在' };
                memory.content = String(body.content || '').trim();
                return {
                    updated: true,
                    record: {
                        ...memory,
                        previous_memory_id: memory.memory_id,
                        id_changed: false,
                        embedding_regenerated: true,
                    },
                };
            }
            return { success: true };
        },
        download: async () => true,
    };
}());
