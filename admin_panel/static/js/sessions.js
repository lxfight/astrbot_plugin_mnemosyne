// 会话管理相关功能

// 加载会话列表
async function loadSessions() {
    console.log('加载会话列表...');
    showLoading(true);
    
    try {
        const data = await apiCall('/memories/sessions');
        AppState.sessionsData = data;
        
        // 渲染会话列表
        renderSessionsList(data.sessions);
        
        showToast('会话列表加载成功', 'success');
    } catch (error) {
        console.error('加载会话失败:', error);
        showSessionsError('会话列表加载失败');
    } finally {
        showLoading(false);
    }
}

// 渲染会话列表
function renderSessionsList(sessions) {
    const container = document.getElementById('sessions-list');
    if (!container) return;
    
    if (!sessions || sessions.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>暂无会话数据</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    sessions.forEach(session => {
        const sessionEl = createSessionItem(session);
        container.appendChild(sessionEl);
    });
}

// 创建单个会话项
function createSessionItem(session) {
    const div = document.createElement('div');
    div.className = 'session-item';
    div.dataset.sessionId = session.session_id;
    
    div.innerHTML = `
        <div class="session-header">
            <h4>${session.session_id}</h4>
            <span class="badge">${session.memory_count} 条记忆</span>
        </div>
        <div class="session-info">
            <div class="info-row">
                <span class="info-label">最后活跃:</span>
                <span class="info-value">${formatTime(session.last_activity)}</span>
            </div>
            <div class="info-row">
                <span class="info-label">首次记录:</span>
                <span class="info-value">${formatTime(session.first_activity)}</span>
            </div>
        </div>
        <div class="session-actions">
            <button class="btn btn-secondary btn-sm" onclick="viewSessionMemories('${session.session_id}')">
                查看记忆
            </button>
            <button class="btn btn-danger btn-sm" onclick="deleteSession('${session.session_id}')">
                删除会话
            </button>
        </div>
    `;
    
    return div;
}

// 查看会话的记忆
function viewSessionMemories(sessionId) {
    // 切换到记忆管理页面
    navigateTo('memories');
    
    // 设置会话过滤器
    setTimeout(() => {
        const sessionInput = document.getElementById('search-session');
        if (sessionInput) {
            sessionInput.value = sessionId;
            searchMemories();
        }
    }, 100);
}

// 删除会话
async function deleteSession(sessionId) {
    const session = AppState.sessionsData?.sessions?.find(s => s.session_id === sessionId);
    if (!session) {
        showToast('会话数据未找到', 'error');
        return;
    }
    
    if (!confirm(`确定要删除会话 "${sessionId}" 及其 ${session.memory_count} 条记忆吗？此操作不可恢复！`)) {
        return;
    }
    
    showLoading(true);
    
    try {
        await apiCall('/memories/delete', 'POST', {
            session_id: sessionId
        });
        
        showToast('会话删除成功', 'success');
        
        // 重新加载列表
        await loadSessions();
    } catch (error) {
        console.error('删除会话失败:', error);
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 显示错误
function showSessionsError(message) {
    const container = document.getElementById('sessions-list');
    if (container) {
        container.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: var(--danger-color);">
                <p>❌ ${message}</p>
                <button class="btn btn-primary" onclick="loadSessions()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 导出函数
window.loadSessions = loadSessions;
window.viewSessionMemories = viewSessionMemories;
window.deleteSession = deleteSession;