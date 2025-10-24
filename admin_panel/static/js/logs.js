// 日志查看器相关功能

// 日志过滤参数
let logFilters = {
    level: 'all',
    keyword: '',
    limit: 100
};

// 自动刷新定时器
let logRefreshTimer = null;

// 加载日志
async function loadLogs() {
    console.log('加载日志...');
    showLoading(true);
    
    try {
        const params = new URLSearchParams(logFilters);
        const data = await apiCall(`/logs/recent?${params}`);
        AppState.logsData = data;
        
        // 渲染日志列表
        renderLogsList(data.logs);
        
        // 更新统计
        updateLogsStats(data.stats);
        
    } catch (error) {
        console.error('加载日志失败:', error);
        showLogsError('日志加载失败');
    } finally {
        showLoading(false);
    }
}

// 渲染日志列表
function renderLogsList(logs) {
    const container = document.getElementById('logs-list');
    if (!container) return;
    
    if (!logs || logs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>暂无日志数据</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    logs.forEach(log => {
        const logEl = createLogItem(log);
        container.appendChild(logEl);
    });
    
    // 自动滚动到底部
    container.scrollTop = container.scrollHeight;
}

// 创建单个日志项
function createLogItem(log) {
    const div = document.createElement('div');
    div.className = `log-item log-${log.level.toLowerCase()}`;
    
    div.innerHTML = `
        <div class="log-time">${formatTime(log.timestamp)}</div>
        <div class="log-level">${log.level}</div>
        <div class="log-message">${escapeHtml(log.message)}</div>
    `;
    
    return div;
}

// 更新日志统计
function updateLogsStats(stats) {
    if (!stats) return;
    
    const statsEl = document.getElementById('logs-stats');
    if (statsEl) {
        statsEl.innerHTML = `
            <span class="stat-item">
                <span class="stat-label">总计:</span>
                <span class="stat-value">${stats.total || 0}</span>
            </span>
            <span class="stat-item">
                <span class="stat-label">错误:</span>
                <span class="stat-value text-danger">${stats.error || 0}</span>
            </span>
            <span class="stat-item">
                <span class="stat-label">警告:</span>
                <span class="stat-value text-warning">${stats.warning || 0}</span>
            </span>
            <span class="stat-item">
                <span class="stat-label">信息:</span>
                <span class="stat-value">${stats.info || 0}</span>
            </span>
        `;
    }
}

// 过滤日志
async function filterLogs() {
    const levelSelect = document.getElementById('log-level-filter');
    const keywordInput = document.getElementById('log-keyword-filter');
    
    if (levelSelect) {
        logFilters.level = levelSelect.value;
    }
    
    if (keywordInput) {
        logFilters.keyword = keywordInput.value;
    }
    
    await loadLogs();
}

// 清空日志显示
function clearLogsDisplay() {
    const container = document.getElementById('logs-list');
    if (container) {
        container.innerHTML = `
            <div class="empty-state">
                <p>日志已清空</p>
            </div>
        `;
    }
}

// 导出日志
async function exportLogs() {
    showLoading(true);
    
    try {
        const params = new URLSearchParams(logFilters);
        
        const response = await fetch(`${API_BASE}/logs/export?${params}`, {
            method: 'GET'
        });
        
        if (!response.ok) {
            throw new Error('导出失败');
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `logs_${new Date().toISOString().split('T')[0]}.txt`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showToast('日志导出成功', 'success');
    } catch (error) {
        console.error('导出日志失败:', error);
        showToast('导出失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 切换自动刷新
function toggleAutoRefresh() {
    const checkbox = document.getElementById('auto-refresh-logs');
    
    if (checkbox && checkbox.checked) {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
}

// 开始自动刷新
function startAutoRefresh() {
    stopAutoRefresh(); // 先停止已有的定时器
    
    logRefreshTimer = setInterval(() => {
        loadLogs();
    }, 5000); // 每5秒刷新一次
    
    showToast('已开启自动刷新', 'info');
}

// 停止自动刷新
function stopAutoRefresh() {
    if (logRefreshTimer) {
        clearInterval(logRefreshTimer);
        logRefreshTimer = null;
    }
}

// 显示错误
function showLogsError(message) {
    const container = document.getElementById('logs-list');
    if (container) {
        container.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: var(--danger-color);">
                <p>❌ ${message}</p>
                <button class="btn btn-primary" onclick="loadLogs()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 页面卸载时清理
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// 导出函数
window.loadLogs = loadLogs;
window.filterLogs = filterLogs;
window.clearLogsDisplay = clearLogsDisplay;
window.exportLogs = exportLogs;
window.toggleAutoRefresh = toggleAutoRefresh;