// Mnemosyne 管理面板 — AstrBot Plugin Pages
// 通过 Bridge SDK 与仪表盘通信

const bridge = window.AstrBotPluginPage;

// ==================== 全局状态 ====================
const AppState = {
    currentPage: 'dashboard',
    loading: false,
    dashboardData: null,
    memoriesData: null,
    sessionsData: null,
};

// ==================== Bridge API 封装 ====================
// Dashboard 自动提取 response.data 字段，bridge 收到的已是最终数据

async function apiGet(endpoint, params) {
    try {
        return await bridge.apiGet(endpoint, params);
    } catch (error) {
        console.error('API GET 失败:', endpoint, error);
        throw error;
    }
}

async function apiPost(endpoint, body) {
    try {
        return await bridge.apiPost(endpoint, body);
    } catch (error) {
        console.error('API POST 失败:', endpoint, error);
        throw error;
    }
}

// ==================== 安全函数 ====================

function escapeHtml(unsafe) {
    if (typeof unsafe !== 'string') return String(unsafe);
    return unsafe
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function formatTime(timestamp) {
    if (!timestamp) return '-';
    try {
        const date = new Date(timestamp);
        if (isNaN(date.getTime())) return escapeHtml(String(timestamp));
        return date.toLocaleString('zh-CN', {
            year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
    } catch {
        return escapeHtml(String(timestamp));
    }
}

// ==================== 存储工具（兼容沙箱 iframe） ====================

function safeGetItem(key, fallback) {
    try { return localStorage.getItem(key); } catch { return fallback; }
}

function safeSetItem(key, value) {
    try { localStorage.setItem(key, value); } catch { /* 沙箱无 localStorage */ }
}

// ==================== 应用初始化 ====================

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Mnemosyne 管理面板初始化...');

    // 等待 bridge 就绪
    const context = await bridge.ready();
    console.log('Bridge 就绪:', context);

    // 初始化主题（沙箱兼容）
    initTheme();

    // 设置导航
    setupNavigation();

    // 加载初始页面
    loadPage('dashboard');
});

// ==================== 主题管理 ====================

function initTheme() {
    const savedTheme = safeGetItem('theme', 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeToggleUI(savedTheme);

    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (toggleBtn) {
        toggleBtn.addEventListener('click', toggleTheme);
    }
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', newTheme);
    safeSetItem('theme', newTheme);
    updateThemeToggleUI(newTheme);
}

function updateThemeToggleUI(theme) {
    const toggleBtn = document.getElementById('theme-toggle-btn');
    if (!toggleBtn) return;
    const icon = toggleBtn.querySelector('i');
    const text = toggleBtn.querySelector('span');
    if (theme === 'dark') {
        icon.className = 'ti ti-sun';
        text.textContent = '浅色模式';
    } else {
        icon.className = 'ti ti-moon';
        text.textContent = '深色模式';
    }
}

// ==================== 导航 ====================

function setupNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
            item.classList.add('active');
            loadPage(page);
        });
    });
}

function loadPage(pageName) {
    console.log(`加载页面: ${pageName}`);
    AppState.currentPage = pageName;

    document.querySelectorAll('.page').forEach(page => page.classList.remove('active'));
    const targetPage = document.getElementById(`${pageName}-page`);
    if (targetPage) targetPage.classList.add('active');

    switch (pageName) {
        case 'dashboard': loadDashboard(); break;
        case 'memories': loadAllMemories(); break;
        case 'sessions': loadSessions(); break;
        case 'statistics': loadStatistics(); break;
        case 'config': loadConfig(); break;
    }
}

function navigateTo(pageName) {
    loadPage(pageName);
}

// ==================== 加载/Toast 工具 ====================

function showLoading(show) {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) overlay.style.display = show ? 'flex' : 'none';
    AppState.loading = show;
}

function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => container.removeChild(toast), 300);
    }, 3000);
}

function formatNumber(num) {
    if (typeof num !== 'number') return '-';
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function formatBytes(bytes) {
    if (typeof bytes !== 'number') return '-';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = bytes, unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) { size /= 1024; unitIndex++; }
    return `${size.toFixed(2)} ${units[unitIndex]}`;
}

function getStatusIndicator(status) {
    const indicators = {
        'healthy': { iconClass: 'ti-circle-check', text: '健康', class: 'healthy' },
        'unhealthy': { iconClass: 'ti-circle-x', text: '异常', class: 'unhealthy' },
        'degraded': { iconClass: 'ti-alert-triangle', text: '降级', class: 'degraded' },
        'unknown': { iconClass: 'ti-circle-dashed', text: '未知', class: 'unknown' }
    };
    return indicators[status] || indicators.unknown;
}

// ==================== 仪表板页面 ====================

async function loadDashboard() {
    console.log('加载仪表板数据...');
    showLoading(true);
    try {
        const data = await apiGet('monitoring/dashboard');
        AppState.dashboardData = data;
        renderSystemStatus(data.status);
        renderResourceSummary(data.resources);
        renderComponentsHealth(data.status.components);
        renderPerformanceMetrics(data.metrics);
        showToast('仪表板数据加载成功', 'success');
    } catch (error) {
        console.error('加载仪表板失败:', error);
        showDashboardError('仪表板数据加载失败');
    } finally {
        showLoading(false);
    }
}

function refreshDashboard() { loadDashboard(); }

function renderSystemStatus(statusData) {
    const statusCard = document.getElementById('overall-status');
    if (!statusCard) return;
    const indicator = getStatusIndicator(statusData.overall_status);
    const cardIcon = statusCard.querySelector('.card-icon i');
    if (cardIcon) { cardIcon.className = ''; cardIcon.className = `ti ${indicator.iconClass}`; }
    statusCard.querySelector('.status-text').textContent = indicator.text;
    statusCard.querySelector('.status-text').className = `status-text ${indicator.class}`;
}

function renderResourceSummary(resourcesData) {
    const totalMemoriesEl = document.getElementById('total-memories');
    if (totalMemoriesEl && resourcesData.vector_database) {
        totalMemoriesEl.textContent = formatNumber(resourcesData.vector_database.total_records);
    }
    const activeSessionsEl = document.getElementById('active-sessions');
    if (activeSessionsEl && resourcesData.sessions) {
        activeSessionsEl.textContent = `${resourcesData.sessions.active} / ${resourcesData.sessions.total}`;
    }
    const memoryUsageEl = document.getElementById('memory-usage');
    if (memoryUsageEl && resourcesData.memory) {
        memoryUsageEl.textContent = resourcesData.memory.usage_percent != null
            ? `${resourcesData.memory.usage_percent.toFixed(1)}%`
            : `${resourcesData.memory.used_mb.toFixed(0)} MB`;
    }
}

function renderComponentsHealth(componentsData) {
    const container = document.getElementById('components-health');
    if (!container) return;
    container.innerHTML = '';
    for (const [name, component] of Object.entries(componentsData)) {
        const indicator = getStatusIndicator(component.status);
        const componentEl = document.createElement('div');
        componentEl.className = 'component-item';

        const statusDiv = document.createElement('div');
        statusDiv.className = `component-status ${indicator.class}`;
        const infoDiv = document.createElement('div');
        infoDiv.className = 'component-info';
        const h4 = document.createElement('h4');
        h4.textContent = getComponentDisplayName(name);
        const p = document.createElement('p');
        p.textContent = component.message || indicator.text;
        infoDiv.appendChild(h4);
        infoDiv.appendChild(p);
        componentEl.appendChild(statusDiv);
        componentEl.appendChild(infoDiv);
        container.appendChild(componentEl);
    }
}

function renderPerformanceMetrics(metricsData) {
    const container = document.getElementById('performance-metrics');
    if (!container) return;
    container.innerHTML = '';
    if (metricsData.memory_query) addMetricItem(container, '记忆查询 (P95)', `${metricsData.memory_query.p95.toFixed(1)} ms`, '95百分位延迟');
    if (metricsData.vector_search) addMetricItem(container, '向量搜索 (P95)', `${metricsData.vector_search.p95.toFixed(1)} ms`, '95百分位延迟');
    if (metricsData.db_operation) addMetricItem(container, '数据库操作 (P95)', `${metricsData.db_operation.p95.toFixed(1)} ms`, '95百分位延迟');
    if (metricsData.api_success_rate) {
        addMetricItem(container, 'Embedding API', `${metricsData.api_success_rate.embedding.toFixed(1)}%`, '成功率');
        addMetricItem(container, 'Milvus API', `${metricsData.api_success_rate.milvus.toFixed(1)}%`, '成功率');
    }
    if (metricsData.requests) addMetricItem(container, '请求总数', formatNumber(metricsData.requests.total), `成功率: ${metricsData.requests.success_rate.toFixed(1)}%`);
}

function addMetricItem(container, title, value, label) {
    const metricEl = document.createElement('div');
    metricEl.className = 'metric-item';
    const h4 = document.createElement('h4'); h4.textContent = title;
    const valueDiv = document.createElement('div'); valueDiv.className = 'metric-value'; valueDiv.textContent = value;
    const labelDiv = document.createElement('div'); labelDiv.className = 'metric-label'; labelDiv.textContent = label;
    metricEl.appendChild(h4); metricEl.appendChild(valueDiv); metricEl.appendChild(labelDiv);
    container.appendChild(metricEl);
}

function getComponentDisplayName(name) {
    const names = { 'milvus': 'Milvus 向量库', 'embedding_api': 'Embedding API', 'message_counter': '消息计数器', 'background_task': '后台任务' };
    return names[name] || name;
}

function showDashboardError(message) {
    const container = document.getElementById('components-health');
    if (!container) return;
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';
    const icon = document.createElement('i'); icon.className = 'ti ti-alert-circle'; icon.style.cssText = 'font-size: 3rem; margin-bottom: 1rem;';
    const p = document.createElement('p'); p.textContent = message;
    const btn = document.createElement('button'); btn.className = 'btn btn-primary'; btn.style.marginTop = '1rem';
    btn.onclick = refreshDashboard; btn.innerHTML = '<i class="ti ti-refresh"></i> 重试';
    errorDiv.appendChild(icon); errorDiv.appendChild(p); errorDiv.appendChild(btn);
    container.innerHTML = ''; container.appendChild(errorDiv);
}

// ==================== 记忆管理页面 ====================

let currentSearchParams = { keyword: '', session_id: null, persona_id: null, start_date: null, end_date: null, page: 1, page_size: 20, group_by: '' };
let selectedMemoryIds = new Set();
let allMemoriesCache = [];

async function loadAllMemories() {
    showLoading(true);
    try {
        await loadMemories({ page: 1, page_size: 100 });
    } catch (error) {
        console.error('加载记忆失败:', error);
        showMemoriesError('记忆列表加载失败: ' + error.message);
    } finally {
        showLoading(false);
    }
}

async function loadMemories(params = {}) {
    console.log('加载记忆列表...', params);
    showLoading(true);
    currentSearchParams = { ...currentSearchParams, ...params };

    try {
        const queryParams = {};
        if (currentSearchParams.session_id && currentSearchParams.session_id.trim()) queryParams.session_id = currentSearchParams.session_id.trim();
        if (currentSearchParams.persona_id && currentSearchParams.persona_id.trim()) queryParams.persona_id = currentSearchParams.persona_id.trim();
        if (currentSearchParams.keyword && currentSearchParams.keyword.trim()) queryParams.keyword = currentSearchParams.keyword.trim();
        queryParams.limit = currentSearchParams.page_size;
        queryParams.offset = (currentSearchParams.page - 1) * currentSearchParams.page_size;
        queryParams.sort_by = 'create_time';
        queryParams.sort_order = 'desc';

        console.log('查询参数:', queryParams);

        const data = await apiGet('memories/search', queryParams);

        if (data && data.records) {
            allMemoriesCache = data.records;
            AppState.memoriesData = data;
            const groupBy = currentSearchParams.group_by || '';
            if (groupBy) {
                renderGroupedMemories(data.records, groupBy);
            } else {
                renderMemoriesList(data.records);
            }
            if (data.pagination) {
                renderPagination(data.pagination);
            } else if (data.total_count !== undefined) {
                const totalPages = Math.ceil(data.total_count / currentSearchParams.page_size);
                renderPagination({ page: currentSearchParams.page, page_size: currentSearchParams.page_size, total: data.total_count, total_pages: totalPages });
            }
            document.getElementById('memories-count-info').textContent = `共 ${data.total_count || 0} 条记忆`;
            showToast('记忆列表加载成功', 'success');
        }
    } catch (error) {
        console.error('加载记忆失败:', error);
        showMemoriesError('记忆列表加载失败: ' + error.message);
    } finally {
        showLoading(false);
    }
}

function renderMemoriesList(memories) {
    const container = document.getElementById('memories-list');
    if (!container) return;
    if (!memories || memories.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>暂无记忆数据</p></div>';
        return;
    }
    container.innerHTML = '';
    memories.forEach(memory => container.appendChild(createMemoryItem(memory)));
    updateBatchActions();
}

function createMemoryItem(memory) {
    const div = document.createElement('div');
    div.className = 'memory-item';
    div.dataset.memoryId = memory.memory_id;
    const isSelected = selectedMemoryIds.has(memory.memory_id);

    const checkboxDiv = document.createElement('div'); checkboxDiv.className = 'memory-checkbox';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = isSelected;
    checkbox.onchange = () => toggleMemorySelection(memory.memory_id);
    checkboxDiv.appendChild(checkbox);

    const contentDiv = document.createElement('div'); contentDiv.className = 'memory-content';
    const headerDiv = document.createElement('div'); headerDiv.className = 'memory-header';
    const sessionSpan = document.createElement('span'); sessionSpan.className = 'memory-session'; sessionSpan.textContent = `会话: ${memory.session_id}`;
    const timeSpan = document.createElement('span'); timeSpan.className = 'memory-time'; timeSpan.textContent = formatTime(memory.create_time || memory.timestamp);
    headerDiv.appendChild(sessionSpan); headerDiv.appendChild(timeSpan);

    const textDiv = document.createElement('div'); textDiv.className = 'memory-text'; textDiv.textContent = memory.content;
    const footerDiv = document.createElement('div'); footerDiv.className = 'memory-footer';
    const typeSpan = document.createElement('span'); typeSpan.className = 'memory-type';
    typeSpan.textContent = getMemoryTypeText(memory.metadata?.memory_type || memory.memory_type || 'long_term');
    footerDiv.appendChild(typeSpan);
    if (memory.similarity_score != null) {
        const scoreSpan = document.createElement('span'); scoreSpan.className = 'memory-score'; scoreSpan.textContent = `相似度: ${memory.similarity_score.toFixed(3)}`;
        footerDiv.appendChild(scoreSpan);
    }
    contentDiv.appendChild(headerDiv); contentDiv.appendChild(textDiv); contentDiv.appendChild(footerDiv);

    const actionsDiv = document.createElement('div'); actionsDiv.className = 'memory-actions';
    const viewBtn = document.createElement('button'); viewBtn.className = 'btn-icon'; viewBtn.title = '查看详情';
    viewBtn.innerHTML = '<i class="ti ti-eye"></i>'; viewBtn.onclick = () => viewMemoryDetail(memory.memory_id);
    const deleteBtn = document.createElement('button'); deleteBtn.className = 'btn-icon'; deleteBtn.title = '删除';
    deleteBtn.innerHTML = '<i class="ti ti-trash"></i>'; deleteBtn.onclick = () => deleteMemory(memory.memory_id);
    actionsDiv.appendChild(viewBtn); actionsDiv.appendChild(deleteBtn);

    div.appendChild(checkboxDiv); div.appendChild(contentDiv); div.appendChild(actionsDiv);
    return div;
}

function renderPagination(pagination) {
    const container = document.getElementById('memories-pagination');
    if (!container) return;
    if (!pagination || pagination.total_pages <= 1) { container.innerHTML = ''; return; }
    const { page, total, total_pages } = pagination;

    const paginationDiv = document.createElement('div'); paginationDiv.className = 'pagination';
    if (page > 1) {
        const prevBtn = document.createElement('button');
        prevBtn.className = 'btn btn-secondary'; prevBtn.textContent = '上一页';
        prevBtn.onclick = () => loadMemories({ page: page - 1 });
        paginationDiv.appendChild(prevBtn);
    }
    const pageInfo = document.createElement('span'); pageInfo.className = 'page-info'; pageInfo.textContent = `第 ${page} / ${total_pages} 页，共 ${total} 条`;
    paginationDiv.appendChild(pageInfo);
    if (page < total_pages) {
        const nextBtn = document.createElement('button');
        nextBtn.className = 'btn btn-secondary'; nextBtn.textContent = '下一页';
        nextBtn.onclick = () => loadMemories({ page: page + 1 });
        paginationDiv.appendChild(nextBtn);
    }
    container.innerHTML = '';
    container.appendChild(paginationDiv);
}

async function searchMemories() {
    const keyword = document.getElementById('search-keyword')?.value || '';
    const sessionId = document.getElementById('search-session-id')?.value || null;
    const personaId = document.getElementById('search-persona-id')?.value || null;
    await loadMemories({ keyword, session_id: sessionId, persona_id: personaId, page: 1 });
}

async function clearFilters() {
    ['search-keyword', 'search-session-id', 'search-persona-id'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    const groupBy = document.getElementById('search-group-by'); if (groupBy) groupBy.value = '';
    currentSearchParams = { keyword: '', session_id: null, persona_id: null, start_date: null, end_date: null, page: 1, page_size: 20, group_by: '' };
    await loadMemories({ page: 1 });
}

function toggleMemorySelection(memoryId) {
    selectedMemoryIds.has(memoryId) ? selectedMemoryIds.delete(memoryId) : selectedMemoryIds.add(memoryId);
    updateBatchActions();
}

function toggleSelectAll() {
    const checkboxes = document.querySelectorAll('.memory-item input[type="checkbox"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    checkboxes.forEach(checkbox => {
        const memoryId = checkbox.closest('.memory-item').dataset.memoryId;
        checkbox.checked = !allChecked;
        allChecked ? selectedMemoryIds.delete(memoryId) : selectedMemoryIds.add(memoryId);
    });
    updateBatchActions();
}

function updateBatchActions() {
    const batchActionsEl = document.getElementById('batch-actions');
    const selectedCountEl = document.getElementById('selected-count');
    if (batchActionsEl) batchActionsEl.style.display = selectedMemoryIds.size > 0 ? 'flex' : 'none';
    if (selectedCountEl) selectedCountEl.textContent = selectedMemoryIds.size;
}

async function batchDeleteMemories() {
    if (selectedMemoryIds.size === 0) { showToast('请先选择要删除的记忆', 'warning'); return; }
    if (!confirm(`确定要删除选中的 ${selectedMemoryIds.size} 条记忆吗？此操作不可恢复！`)) return;
    showLoading(true);
    try {
        await apiPost('memories/delete', { memory_ids: Array.from(selectedMemoryIds) });
        showToast('删除成功', 'success');
        selectedMemoryIds.clear();
        await loadMemories();
    } catch (error) {
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function deleteMemory(memoryId) {
    if (!confirm('确定要删除这条记忆吗？此操作不可恢复！')) return;
    showLoading(true);
    try {
        await apiPost(`memories/${memoryId}/delete`);
        showToast('删除成功', 'success');
        await loadMemories();
    } catch (error) {
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function viewMemoryDetail(memoryId) {
    const memory = AppState.memoriesData?.records?.find(m => m.memory_id === memoryId);
    if (!memory) { showToast('记忆数据未找到', 'error'); return; }

    const modal = document.createElement('div'); modal.className = 'modal';
    const modalContent = document.createElement('div'); modalContent.className = 'modal-content';
    const modalHeader = document.createElement('div'); modalHeader.className = 'modal-header';
    const title = document.createElement('h3'); title.textContent = '记忆详情';
    const closeBtn = document.createElement('button'); closeBtn.className = 'btn-close'; closeBtn.innerHTML = '<i class="ti ti-x"></i>'; closeBtn.onclick = () => modal.remove();
    modalHeader.appendChild(title); modalHeader.appendChild(closeBtn);

    const modalBody = document.createElement('div'); modalBody.className = 'modal-body';
    const addDetail = (label, value) => {
        const itemDiv = document.createElement('div'); itemDiv.className = 'detail-item';
        const labelEl = document.createElement('label'); labelEl.textContent = label + ':';
        const valueEl = document.createElement('span'); valueEl.textContent = value;
        itemDiv.appendChild(labelEl); itemDiv.appendChild(valueEl);
        modalBody.appendChild(itemDiv);
    };

    addDetail('记忆ID', memory.memory_id);
    addDetail('会话ID', memory.session_id);
    addDetail('时间', formatTime(memory.create_time || memory.timestamp));
    addDetail('类型', getMemoryTypeText(memory.metadata?.memory_type || memory.memory_type || 'long_term'));
    if (memory.similarity_score != null) addDetail('相似度', memory.similarity_score.toFixed(3));

    const contentItem = document.createElement('div'); contentItem.className = 'detail-item';
    const contentLabel = document.createElement('label'); contentLabel.textContent = '内容:';
    const contentValue = document.createElement('div');
    contentValue.style.cssText = 'white-space: pre-wrap; margin-top: 0.5rem; padding: 1rem; background: var(--bg-secondary); border-radius: 4px;';
    contentValue.textContent = memory.content;
    contentItem.appendChild(contentLabel); contentItem.appendChild(contentValue);
    modalBody.appendChild(contentItem);

    const modalFooter = document.createElement('div'); modalFooter.className = 'modal-footer';
    const closeFooterBtn = document.createElement('button'); closeFooterBtn.className = 'btn btn-secondary'; closeFooterBtn.textContent = '关闭'; closeFooterBtn.onclick = () => modal.remove();
    modalFooter.appendChild(closeFooterBtn);

    modalContent.appendChild(modalHeader); modalContent.appendChild(modalBody); modalContent.appendChild(modalFooter);
    modal.appendChild(modalContent);
    document.body.appendChild(modal);
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
}

async function exportMemories(format = 'json') {
    showLoading(true);
    try {
        const params = { format };
        if (currentSearchParams.session_id) params.session_id = currentSearchParams.session_id;
        if (currentSearchParams.start_date) params.start_date = currentSearchParams.start_date;
        if (currentSearchParams.end_date) params.end_date = currentSearchParams.end_date;

        const filename = `memories_${new Date().toISOString().split('T')[0]}.${format}`;
        await bridge.download('memories/export', params, filename);
        showToast('导出成功', 'success');
    } catch (error) {
        console.error('导出失败:', error);
        showToast('导出失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

async function vectorSearchMemories() {
    const query = document.getElementById('search-keyword')?.value || '';
    if (!query) { showToast('请先输入搜索关键词', 'warning'); return; }
    showLoading(true);
    try {
        const result = await apiPost('memories/vector-search', { query, limit: 50 });
        if (result) {
            allMemoriesCache = result.records;
            renderMemoriesList(result.records);
            document.getElementById('memories-count-info').textContent = `向量检索: ${result.total_count || 0} 条结果`;
            showToast('向量检索完成', 'success');
        }
    } catch (error) {
        showToast('向量检索失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function getMemoryTypeText(type) {
    const types = { 'short_term': '短期记忆', 'long_term': '长期记忆', 'summary': '总结' };
    return types[type] || type;
}

function showMemoriesError(message) {
    const container = document.getElementById('memories-list');
    if (!container) return;
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';
    const p = document.createElement('p');
    const icon = document.createElement('i'); icon.className = 'ti ti-alert-circle';
    p.appendChild(icon);
    p.appendChild(document.createTextNode(' ' + message));
    const btn = document.createElement('button'); btn.className = 'btn btn-primary'; btn.style.marginTop = '1rem';
    btn.textContent = '重试'; btn.onclick = () => loadMemories();
    errorDiv.appendChild(p); errorDiv.appendChild(btn);
    container.innerHTML = ''; container.appendChild(errorDiv);
}

function renderGroupedMemories(memories, groupBy) {
    if (!memories || memories.length === 0) { renderMemoriesList(memories); return; }
    const container = document.getElementById('memories-list');
    if (!container) return;
    container.innerHTML = '';

    const groups = {};
    memories.forEach(memory => {
        let key;
        if (groupBy === 'session') key = memory.session_id || '未知';
        else if (groupBy === 'persona') key = memory.persona_id || '未知人格';
        else if (groupBy === 'date') key = (memory.create_time || memory.timestamp || '').toString().substring(0, 10) || '未知日期';
        else key = '其他';
        if (!groups[key]) groups[key] = [];
        groups[key].push(memory);
    });

    for (const [groupName, groupMemories] of Object.entries(groups)) {
        const groupContainer = document.createElement('div'); groupContainer.className = 'group-container';
        const groupHeader = document.createElement('div'); groupHeader.className = 'group-header';
        const h3 = document.createElement('h3'); h3.textContent = groupName;
        const count = document.createElement('span'); count.className = 'group-count'; count.textContent = groupMemories.length + ' 条';
        groupHeader.appendChild(h3); groupHeader.appendChild(count);
        groupHeader.onclick = () => {
            const content = groupContainer.querySelector('.group-content');
            if (content) content.style.display = content.style.display === 'none' ? 'block' : 'none';
        };

        const groupContent = document.createElement('div'); groupContent.className = 'group-content';
        groupMemories.forEach(memory => groupContent.appendChild(createMemoryItem(memory)));

        groupContainer.appendChild(groupHeader); groupContainer.appendChild(groupContent);
        container.appendChild(groupContainer);
    }
}

function applyGrouping() {
    const groupBy = document.getElementById('search-group-by')?.value || '';
    currentSearchParams.group_by = groupBy;
    if (allMemoriesCache.length > 0) {
        if (groupBy) renderGroupedMemories(allMemoriesCache, groupBy);
        else renderMemoriesList(allMemoriesCache);
    }
}

// ==================== 会话列表页面 ====================

async function loadSessions() {
    console.log('加载会话列表...');
    showLoading(true);
    try {
        const data = await apiGet('memories/sessions', { limit: 100 });
        AppState.sessionsData = { sessions: data };
        renderSessionsList(data);
        showToast('会话列表加载成功', 'success');
    } catch (error) {
        console.error('加载会话失败:', error);
        showSessionsError('会话列表加载失败');
    } finally {
        showLoading(false);
    }
}

function renderSessionsList(sessions) {
    const container = document.getElementById('sessions-list');
    if (!container) return;
    if (!sessions || sessions.length === 0) {
        const emptyDiv = document.createElement('div'); emptyDiv.className = 'empty-state';
        const p = document.createElement('p'); p.textContent = '暂无会话数据';
        emptyDiv.appendChild(p); container.innerHTML = ''; container.appendChild(emptyDiv);
        return;
    }
    container.innerHTML = '';
    sessions.forEach(session => container.appendChild(createSessionItem(session)));
}

function createSessionItem(session) {
    const div = document.createElement('div'); div.className = 'session-item'; div.dataset.sessionId = session.session_id;

    const headerDiv = document.createElement('div'); headerDiv.className = 'session-header';
    const h4 = document.createElement('h4'); h4.textContent = session.session_id;
    const badge = document.createElement('span'); badge.className = 'badge'; badge.textContent = `${session.memory_count} 条记忆`;
    headerDiv.appendChild(h4); headerDiv.appendChild(badge);

    const infoDiv = document.createElement('div'); infoDiv.className = 'session-info';
    const lastRow = document.createElement('div'); lastRow.className = 'info-row';
    const lastLabel = document.createElement('span'); lastLabel.className = 'info-label'; lastLabel.textContent = '最后活跃:';
    const lastValue = document.createElement('span'); lastValue.className = 'info-value'; lastValue.textContent = formatTime(session.last_memory_time);
    lastRow.appendChild(lastLabel); lastRow.appendChild(lastValue);

    const firstRow = document.createElement('div'); firstRow.className = 'info-row';
    const firstLabel = document.createElement('span'); firstLabel.className = 'info-label'; firstLabel.textContent = '首次记录:';
    const firstValue = document.createElement('span'); firstValue.className = 'info-value'; firstValue.textContent = formatTime(session.first_memory_time);
    firstRow.appendChild(firstLabel); firstRow.appendChild(firstValue);
    infoDiv.appendChild(lastRow); infoDiv.appendChild(firstRow);

    const actionsDiv = document.createElement('div'); actionsDiv.className = 'session-actions';
    const viewBtn = document.createElement('button'); viewBtn.className = 'btn btn-secondary btn-sm'; viewBtn.textContent = '查看记忆';
    viewBtn.onclick = () => viewSessionMemories(session.session_id);
    const deleteBtn = document.createElement('button'); deleteBtn.className = 'btn btn-danger btn-sm'; deleteBtn.textContent = '删除会话';
    deleteBtn.onclick = () => deleteSession(session.session_id);
    actionsDiv.appendChild(viewBtn); actionsDiv.appendChild(deleteBtn);

    div.appendChild(headerDiv); div.appendChild(infoDiv); div.appendChild(actionsDiv);
    return div;
}

function viewSessionMemories(sessionId) {
    navigateTo('memories');
    setTimeout(() => {
        const sessionInput = document.getElementById('search-session-id');
        if (sessionInput) { sessionInput.value = sessionId; loadMemories({ session_id: sessionId, page: 1 }); }
    }, 200);
}

async function deleteSession(sessionId) {
    const session = AppState.sessionsData?.sessions?.find(s => s.session_id === sessionId);
    if (!session) { showToast('会话数据未找到', 'error'); return; }
    if (!confirm(`确定要删除会话 "${sessionId}" 及其 ${session.memory_count} 条记忆吗？此操作不可恢复！`)) return;
    showLoading(true);
    try {
        await apiPost(`memories/session/${sessionId}/delete`);
        showToast('会话删除成功', 'success');
        await loadSessions();
    } catch (error) {
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

function showSessionsError(message) {
    const container = document.getElementById('sessions-list');
    if (!container) return;
    const errorDiv = document.createElement('div');
    errorDiv.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';
    const p = document.createElement('p');
    const icon = document.createElement('i'); icon.className = 'ti ti-alert-circle';
    p.appendChild(icon);
    p.appendChild(document.createTextNode(' ' + message));
    const btn = document.createElement('button'); btn.className = 'btn btn-primary'; btn.style.marginTop = '1rem';
    btn.textContent = '重试'; btn.onclick = loadSessions;
    errorDiv.appendChild(p); errorDiv.appendChild(btn);
    container.innerHTML = ''; container.appendChild(errorDiv);
}

// ==================== 统计分析页面 ====================

let statisticsChart = null;
let distributionChart = null;

async function loadStatistics() {
    console.log('加载统计数据...');
    showLoading(true);
    try {
        const data = await apiGet('memories/statistics');
        AppState.statisticsData = data;
        renderStatisticsCards(data);
        renderStatisticsChart(data);
        renderTopSessions(data);
        renderDistributionChart(data);
        showToast('统计数据加载成功', 'success');
    } catch (error) {
        console.error('加载统计失败:', error);
        showStatisticsError('统计数据加载失败');
    } finally {
        showLoading(false);
    }
}

function renderStatisticsCards(data) {
    const totalEl = document.getElementById('stat-total-memories');
    if (totalEl) totalEl.textContent = formatNumber(data.total_memories || 0);
    const sessionsEl = document.getElementById('stat-active-sessions');
    if (sessionsEl) sessionsEl.textContent = formatNumber(data.total_sessions || 0);
    const todayEl = document.getElementById('stat-today-added');
    if (todayEl) {
        const today = new Date().toISOString().split('T')[0];
        todayEl.textContent = formatNumber(data.memories_by_date?.[today] || 0);
    }
    const avgEl = document.getElementById('stat-avg-per-session');
    if (avgEl) {
        avgEl.textContent = data.total_sessions > 0 ? (data.total_memories / data.total_sessions).toFixed(1) : '0';
    }
}

function renderStatisticsChart(data) {
    const canvas = document.getElementById('statistics-chart');
    if (!canvas) return;
    if (statisticsChart) statisticsChart.destroy();

    let labels = [], counts = [];
    if (data && data.memories_by_date && typeof data.memories_by_date === 'object') {
        const sortedDates = Object.keys(data.memories_by_date).sort();
        labels = sortedDates.slice(-30);
        counts = labels.map(date => data.memories_by_date[date] || 0);
    }
    if (labels.length === 0) { labels = ['暂无数据']; counts = [0]; }

    const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--primary-color').trim() || '#2563eb';
    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || 'rgba(0, 0, 0, 0.05)';

    const ctx = canvas.getContext('2d');
    statisticsChart = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets: [{ label: '每日新增记忆', data: counts, borderColor: primaryColor, backgroundColor: 'transparent', tension: 0.4, fill: false, pointRadius: 4, pointHoverRadius: 6, pointBackgroundColor: primaryColor, pointBorderColor: '#fff', pointBorderWidth: 2 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: true, position: 'top', labels: { color: textColor, font: { size: 14 } } }, tooltip: { mode: 'index', intersect: false, backgroundColor: 'rgba(0, 0, 0, 0.8)', titleFont: { size: 14 }, bodyFont: { size: 13 }, padding: 12 } },
            scales: {
                x: { display: true, ticks: { color: textColor }, title: { display: true, text: '日期', color: textColor, font: { size: 14, weight: 'bold' } }, grid: { display: false } },
                y: { display: true, ticks: { color: textColor }, title: { display: true, text: '记忆数量', color: textColor, font: { size: 14, weight: 'bold' } }, beginAtZero: true, grid: { color: gridColor } }
            }
        }
    });
}

function renderTopSessions(data) {
    const container = document.getElementById('top-sessions-list');
    if (!container) return;
    if (!data.most_active_sessions || data.most_active_sessions.length === 0) {
        container.innerHTML = '<div class="empty-state"><p>暂无会话数据</p></div>';
        return;
    }
    container.innerHTML = '';
    data.most_active_sessions.forEach((session, index) => {
        const sessionEl = document.createElement('div'); sessionEl.className = 'list-item';
        sessionEl.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';

        const leftDiv = document.createElement('div'); leftDiv.style.cssText = 'display: flex; align-items: center; gap: 1rem;';
        const rank = document.createElement('span');
        rank.style.cssText = 'font-size: 1.5rem; font-weight: bold; color: var(--primary-color); min-width: 30px;';
        rank.textContent = `#${index + 1}`;

        const info = document.createElement('div');
        const name = document.createElement('div'); name.style.cssText = 'font-weight: 600; margin-bottom: 0.25rem;'; name.textContent = session[0];
        const count = document.createElement('div'); count.style.cssText = 'font-size: 0.875rem; color: var(--text-secondary);'; count.textContent = `${session[1]} 条记忆`;
        info.appendChild(name); info.appendChild(count);
        leftDiv.appendChild(rank); leftDiv.appendChild(info);

        const viewBtn = document.createElement('button'); viewBtn.className = 'btn btn-sm btn-secondary';
        viewBtn.textContent = '查看'; viewBtn.onclick = () => viewSessionMemories(session[0]);

        sessionEl.appendChild(leftDiv); sessionEl.appendChild(viewBtn);
        container.appendChild(sessionEl);
    });
}

function renderDistributionChart(data) {
    const canvas = document.getElementById('distribution-chart');
    if (!canvas) return;
    if (distributionChart) distributionChart.destroy();

    let labels = [], counts = [];
    if (data.most_active_sessions && data.most_active_sessions.length > 0) {
        data.most_active_sessions.slice(0, 10).forEach(session => {
            labels.push(session[0].substring(0, 20) + (session[0].length > 20 ? '...' : ''));
            counts.push(session[1]);
        });
    } else { labels = ['暂无数据']; counts = [0]; }

    const textColor = getComputedStyle(document.documentElement).getPropertyValue('--text-primary').trim() || '#0f172a';
    const gridColor = getComputedStyle(document.documentElement).getPropertyValue('--border-color').trim() || 'rgba(0, 0, 0, 0.05)';

    const ctx = canvas.getContext('2d');
    distributionChart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets: [{ label: '记忆数量', data: counts, backgroundColor: ['rgba(37, 99, 235, 0.8)', 'rgba(249, 115, 22, 0.8)', 'rgba(16, 185, 129, 0.8)', 'rgba(239, 68, 68, 0.8)', 'rgba(245, 158, 11, 0.8)', 'rgba(6, 182, 212, 0.8)', 'rgba(236, 72, 153, 0.8)', 'rgba(20, 184, 166, 0.8)', 'rgba(251, 146, 60, 0.8)', 'rgba(59, 130, 246, 0.8)'], borderColor: ['rgb(37, 99, 235)', 'rgb(249, 115, 22)', 'rgb(16, 185, 129)', 'rgb(239, 68, 68)', 'rgb(245, 158, 11)', 'rgb(6, 182, 212)', 'rgb(236, 72, 153)', 'rgb(20, 184, 166)', 'rgb(251, 146, 60)', 'rgb(59, 130, 246)'], borderWidth: 2 }] },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { backgroundColor: 'rgba(0, 0, 0, 0.8)', titleFont: { size: 14 }, bodyFont: { size: 13 }, padding: 12 } },
            scales: {
                x: { display: true, ticks: { color: textColor }, title: { display: true, text: '会话ID', color: textColor, font: { size: 14, weight: 'bold' } }, grid: { display: false } },
                y: { display: true, ticks: { color: textColor }, title: { display: true, text: '记忆数量', color: textColor, font: { size: 14, weight: 'bold' } }, beginAtZero: true, grid: { color: gridColor } }
            }
        }
    });
}

function showStatisticsError(message) {
    const container = document.getElementById('statistics-content');
    if (!container) return;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';

    const p = document.createElement('p');
    const icon = document.createElement('i'); icon.className = 'ti ti-alert-circle';
    p.appendChild(icon);
    p.appendChild(document.createTextNode(' ' + message));

    const btn = document.createElement('button');
    btn.className = 'btn btn-primary'; btn.style.marginTop = '1rem';
    btn.textContent = '重试'; btn.onclick = () => loadStatistics();

    wrapper.appendChild(p); wrapper.appendChild(btn);
    container.innerHTML = ''; container.appendChild(wrapper);
}

// ==================== 系统配置页面 ====================

async function loadConfig() {
    console.log('加载系统配置...');
    showLoading(true);
    try {
        const config = await apiGet('config');
        renderConfigForm(config);
        showToast('配置加载成功', 'success');
    } catch (error) {
        console.error('加载配置失败:', error);
        showConfigError('配置加载失败: ' + error.message);
    } finally {
        showLoading(false);
    }
}

function renderConfigForm(config) {
    const container = document.getElementById('config-content');
    if (!container) return;
    container.innerHTML = '';

    const skipKeys = ['admin_panel', '_internal', 'plugin_data_dir'];
    const entries = Object.entries(config).filter(([k]) => !skipKeys.includes(k));

    if (entries.length === 0) {
        container.innerHTML = '<p class="placeholder">暂无配置项</p>';
        return;
    }

    for (const [key, value] of entries) {
        const card = document.createElement('div');
        card.className = 'config-item';

        // 配置项名称
        const nameEl = document.createElement('div');
        nameEl.className = 'config-item-name';
        nameEl.textContent = key;

        // 配置项值
        const valueEl = document.createElement('div');
        valueEl.className = 'config-item-value';

        if (typeof value === 'boolean') {
            const badge = document.createElement('span');
            badge.className = 'config-badge ' + (value ? 'config-badge-true' : 'config-badge-false');
            badge.textContent = value ? '✓ 开启' : '✗ 关闭';
            valueEl.appendChild(badge);
        } else if (typeof value === 'number') {
            valueEl.className += ' config-value-number';
            valueEl.textContent = value.toLocaleString();
        } else if (typeof value === 'object' && value !== null) {
            const pre = document.createElement('pre');
            pre.className = 'config-json';
            pre.textContent = JSON.stringify(value, null, 2);
            valueEl.appendChild(pre);
        } else if (typeof value === 'string' && value.length > 60) {
            const pre = document.createElement('pre');
            pre.className = 'config-textarea';
            pre.textContent = value;
            valueEl.appendChild(pre);
        } else {
            const span = document.createElement('span');
            span.className = 'config-value-string';
            span.textContent = String(value);
            valueEl.appendChild(span);
        }

        // 类型标签
        const typeEl = document.createElement('span');
        typeEl.className = 'config-type-tag';
        typeEl.textContent = Array.isArray(value) ? 'list' : typeof value;

        card.appendChild(nameEl);
        card.appendChild(typeEl);
        card.appendChild(valueEl);
        container.appendChild(card);
    }
}

function showConfigError(message) {
    const container = document.getElementById('config-content');
    if (!container) return;

    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';

    const p = document.createElement('p');
    const icon = document.createElement('i'); icon.className = 'ti ti-alert-circle';
    p.appendChild(icon);
    p.appendChild(document.createTextNode(' ' + message));

    const btn = document.createElement('button');
    btn.className = 'btn btn-primary'; btn.style.marginTop = '1rem';
    btn.textContent = '重试'; btn.onclick = () => loadConfig();

    wrapper.appendChild(p); wrapper.appendChild(btn);
    container.innerHTML = ''; container.appendChild(wrapper);
}

// ==================== 全局导出 ====================
window.AppState = AppState;
window.escapeHtml = escapeHtml;
window.formatTime = formatTime;
window.formatNumber = formatNumber;
window.formatBytes = formatBytes;
window.getStatusIndicator = getStatusIndicator;
window.showLoading = showLoading;
window.showToast = showToast;
window.loadPage = loadPage;
window.navigateTo = navigateTo;

// 仪表板
window.loadDashboard = loadDashboard;
window.refreshDashboard = refreshDashboard;

// 记忆管理
window.loadAllMemories = loadAllMemories;
window.searchMemories = searchMemories;
window.vectorSearchMemories = vectorSearchMemories;
window.clearFilters = clearFilters;
window.toggleMemorySelection = toggleMemorySelection;
window.toggleSelectAll = toggleSelectAll;
window.batchDeleteMemories = batchDeleteMemories;
window.deleteMemory = deleteMemory;
window.viewMemoryDetail = viewMemoryDetail;
window.exportMemories = exportMemories;
window.applyGrouping = applyGrouping;

// 会话管理
window.loadSessions = loadSessions;
window.viewSessionMemories = viewSessionMemories;
window.deleteSession = deleteSession;

// 统计分析
window.loadStatistics = loadStatistics;

// 配置管理
window.loadConfig = loadConfig;
