// 会话管理相关功能

// 加载会话列表
async function loadSessions() {
    console.log('加载会话列表...');
    showLoading(true);
    
    try {
        const data = await apiCall('/memories/sessions');
        AppState.sessionsData = { sessions: data };  // data 本身就是会话数组
        
        // 渲染会话列表
        renderSessionsList(data);
        
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
    
    // 使用 DOM 方法创建元素，避免 XSS 风险
    const headerDiv = document.createElement('div');
    headerDiv.className = 'session-header';
    const h4 = document.createElement('h4');
    h4.textContent = session.session_id;
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = `${session.memory_count} 条记忆`;
    headerDiv.appendChild(h4);
    headerDiv.appendChild(badge);
    
    const infoDiv = document.createElement('div');
    infoDiv.className = 'session-info';
    
    const lastActivityRow = document.createElement('div');
    lastActivityRow.className = 'info-row';
    const lastLabel = document.createElement('span');
    lastLabel.className = 'info-label';
    lastLabel.textContent = '最后活跃:';
    const lastValue = document.createElement('span');
    lastValue.className = 'info-value';
    lastValue.textContent = formatTime(session.last_memory_time);
    lastActivityRow.appendChild(lastLabel);
    lastActivityRow.appendChild(lastValue);
    
    const firstActivityRow = document.createElement('div');
    firstActivityRow.className = 'info-row';
    const firstLabel = document.createElement('span');
    firstLabel.className = 'info-label';
    firstLabel.textContent = '首次记录:';
    const firstValue = document.createElement('span');
    firstValue.className = 'info-value';
    firstValue.textContent = formatTime(session.first_memory_time);
    firstActivityRow.appendChild(firstLabel);
    firstActivityRow.appendChild(firstValue);
    
    infoDiv.appendChild(lastActivityRow);
    infoDiv.appendChild(firstActivityRow);
    
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'session-actions';
    
    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn btn-secondary btn-sm';
    viewBtn.textContent = '查看记忆';
    viewBtn.onclick = () => viewSessionMemories(session.session_id);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-danger btn-sm';
    deleteBtn.textContent = '删除会话';
    deleteBtn.onclick = () => deleteSession(session.session_id);
    
    actionsDiv.appendChild(viewBtn);
    actionsDiv.appendChild(deleteBtn);
    
    div.appendChild(headerDiv);
    div.appendChild(infoDiv);
    div.appendChild(actionsDiv);
    
    return div;
}

// 查看会话的记忆
function viewSessionMemories(sessionId) {
    // 切换到记忆管理页面
    navigateTo('memories');
    
    // 设置会话过滤器并搜索
    setTimeout(() => {
        const sessionInput = document.getElementById('search-session-id');
        if (sessionInput) {
            sessionInput.value = sessionId;
            // 直接调用 loadMemories 并传递 session_id 参数
            loadMemories({ session_id: sessionId, page: 1 });
        }
    }, 200);
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
        await apiCall(`/memories/session/${sessionId}`, 'DELETE');
        
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