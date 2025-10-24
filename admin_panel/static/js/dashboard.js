// 仪表板相关功能

// 加载仪表板数据
async function loadDashboard() {
    console.log('加载仪表板数据...');
    showLoading(true);
    
    try {
        // 调用仪表板 API
        const data = await apiCall('/monitoring/dashboard');
        AppState.dashboardData = data;
        
        // 渲染各个部分
        renderSystemStatus(data.status);
        renderResourceSummary(data.resources);
        renderComponentsHealth(data.status.components);
        renderPerformanceMetrics(data.metrics);
        
        showToast('仪表板数据加载成功', 'success');
    } catch (error) {
        console.error('加载仪表板失败:', error);
        showError('仪表板数据加载失败');
    } finally {
        showLoading(false);
    }
}

// 刷新仪表板
async function refreshDashboard() {
    await loadDashboard();
}

// 渲染系统状态
function renderSystemStatus(statusData) {
    const statusCard = document.getElementById('overall-status');
    if (!statusCard) return;
    
    const indicator = getStatusIndicator(statusData.overall_status);
    
    statusCard.querySelector('.card-icon').textContent = indicator.icon;
    statusCard.querySelector('.status-text').textContent = indicator.text;
    statusCard.querySelector('.status-text').className = `status-text ${indicator.class}`;
}

// 渲染资源摘要
function renderResourceSummary(resourcesData) {
    // 记忆总数
    const totalMemoriesEl = document.getElementById('total-memories');
    if (totalMemoriesEl && resourcesData.vector_database) {
        totalMemoriesEl.textContent = formatNumber(resourcesData.vector_database.total_records);
    }
    
    // 活跃会话
    const activeSessionsEl = document.getElementById('active-sessions');
    if (activeSessionsEl && resourcesData.sessions) {
        activeSessionsEl.textContent = `${resourcesData.sessions.active} / ${resourcesData.sessions.total}`;
    }
    
    // 内存使用
    const memoryUsageEl = document.getElementById('memory-usage');
    if (memoryUsageEl && resourcesData.memory) {
        const percent = resourcesData.memory.usage_percent;
        if (percent !== null) {
            memoryUsageEl.textContent = `${percent.toFixed(1)}%`;
        } else {
            memoryUsageEl.textContent = `${resourcesData.memory.used_mb.toFixed(0)} MB`;
        }
    }
}

// 渲染组件健康状态
function renderComponentsHealth(componentsData) {
    const container = document.getElementById('components-health');
    if (!container) return;
    
    container.innerHTML = '';
    
    for (const [name, component] of Object.entries(componentsData)) {
        const indicator = getStatusIndicator(component.status);
        
        const componentEl = document.createElement('div');
        componentEl.className = 'component-item';
        componentEl.innerHTML = `
            <div class="component-status ${indicator.class}"></div>
            <div class="component-info">
                <h4>${getComponentDisplayName(name)}</h4>
                <p>${component.message || indicator.text}</p>
            </div>
        `;
        
        container.appendChild(componentEl);
    }
}

// 渲染性能指标
function renderPerformanceMetrics(metricsData) {
    const container = document.getElementById('performance-metrics');
    if (!container) return;
    
    container.innerHTML = '';
    
    // 记忆查询性能
    if (metricsData.memory_query) {
        addMetricItem(container, '记忆查询 (P95)', 
            `${metricsData.memory_query.p95.toFixed(1)} ms`, 
            '95百分位延迟');
    }
    
    // 向量搜索性能
    if (metricsData.vector_search) {
        addMetricItem(container, '向量搜索 (P95)', 
            `${metricsData.vector_search.p95.toFixed(1)} ms`, 
            '95百分位延迟');
    }
    
    // 数据库操作性能
    if (metricsData.db_operation) {
        addMetricItem(container, '数据库操作 (P95)', 
            `${metricsData.db_operation.p95.toFixed(1)} ms`, 
            '95百分位延迟');
    }
    
    // API 成功率
    if (metricsData.api_success_rate) {
        addMetricItem(container, 'Embedding API', 
            `${metricsData.api_success_rate.embedding.toFixed(1)}%`, 
            '成功率');
        
        addMetricItem(container, 'Milvus API', 
            `${metricsData.api_success_rate.milvus.toFixed(1)}%`, 
            '成功率');
    }
    
    // 请求统计
    if (metricsData.requests) {
        addMetricItem(container, '请求总数', 
            formatNumber(metricsData.requests.total), 
            `成功率: ${metricsData.requests.success_rate.toFixed(1)}%`);
    }
}

// 添加指标项
function addMetricItem(container, title, value, label) {
    const metricEl = document.createElement('div');
    metricEl.className = 'metric-item';
    metricEl.innerHTML = `
        <h4>${title}</h4>
        <div class="metric-value">${value}</div>
        <div class="metric-label">${label}</div>
    `;
    container.appendChild(metricEl);
}

// 获取组件显示名称
function getComponentDisplayName(name) {
    const names = {
        'milvus': 'Milvus 向量库',
        'embedding_api': 'Embedding API',
        'message_counter': '消息计数器',
        'background_task': '后台任务'
    };
    return names[name] || name;
}

// 显示错误
function showError(message) {
    const container = document.getElementById('components-health');
    if (container) {
        container.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: var(--danger-color);">
                <p>❌ ${message}</p>
                <button class="btn btn-primary" onclick="refreshDashboard()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 导出函数
window.loadDashboard = loadDashboard;
window.refreshDashboard = refreshDashboard;