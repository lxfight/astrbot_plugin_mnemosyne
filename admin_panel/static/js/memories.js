// 记忆管理相关功能

// 当前搜索参数
let currentSearchParams = {
    keyword: '',
    session_id: null,
    start_date: null,
    end_date: null,
    page: 1,
    page_size: 20
};

// 选中的记忆ID列表
let selectedMemoryIds = new Set();

// 加载记忆列表
async function loadMemories(params = {}) {
    console.log('加载记忆列表...', params);
    showLoading(true);
    
    // 更新搜索参数
    currentSearchParams = { ...currentSearchParams, ...params };
    
    try {
        const data = await apiCall('/memories/search', 'POST', currentSearchParams);
        AppState.memoriesData = data;
        
        // 渲染记忆列表
        renderMemoriesList(data.memories);
        
        // 更新分页
        renderPagination(data.pagination);
        
        showToast('记忆列表加载成功', 'success');
    } catch (error) {
        console.error('加载记忆失败:', error);
        showMemoriesError('记忆列表加载失败');
    } finally {
        showLoading(false);
    }
}

// 渲染记忆列表
function renderMemoriesList(memories) {
    const container = document.getElementById('memories-list');
    if (!container) return;
    
    if (!memories || memories.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>暂无记忆数据</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    memories.forEach(memory => {
        const memoryEl = createMemoryItem(memory);
        container.appendChild(memoryEl);
    });
    
    // 更新批量操作按钮状态
    updateBatchActions();
}

// 创建单个记忆项
function createMemoryItem(memory) {
    const div = document.createElement('div');
    div.className = 'memory-item';
    div.dataset.memoryId = memory.memory_id;
    
    const isSelected = selectedMemoryIds.has(memory.memory_id);
    
    div.innerHTML = `
        <div class="memory-checkbox">
            <input type="checkbox" 
                   ${isSelected ? 'checked' : ''} 
                   onchange="toggleMemorySelection('${memory.memory_id}')">
        </div>
        <div class="memory-content">
            <div class="memory-header">
                <span class="memory-session">会话: ${memory.session_id}</span>
                <span class="memory-time">${formatTime(memory.timestamp)}</span>
            </div>
            <div class="memory-text">${escapeHtml(memory.content)}</div>
            <div class="memory-footer">
                <span class="memory-type">${getMemoryTypeText(memory.memory_type)}</span>
                ${memory.similarity_score !== null ? 
                    `<span class="memory-score">相似度: ${memory.similarity_score.toFixed(3)}</span>` : ''}
            </div>
        </div>
        <div class="memory-actions">
            <button class="btn-icon" onclick="viewMemoryDetail('${memory.memory_id}')" title="查看详情">
                👁️
            </button>
            <button class="btn-icon" onclick="deleteMemory('${memory.memory_id}')" title="删除">
                🗑️
            </button>
        </div>
    `;
    
    return div;
}

// 渲染分页
function renderPagination(pagination) {
    const container = document.getElementById('memories-pagination');
    if (!container) return;
    
    const { page, page_size, total, total_pages } = pagination;
    
    if (total_pages <= 1) {
        container.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination">';
    
    // 上一页
    if (page > 1) {
        html += `<button class="btn btn-secondary" onclick="loadMemories({page: ${page - 1}})">上一页</button>`;
    }
    
    // 页码信息
    html += `<span class="page-info">第 ${page} / ${total_pages} 页，共 ${total} 条</span>`;
    
    // 下一页
    if (page < total_pages) {
        html += `<button class="btn btn-secondary" onclick="loadMemories({page: ${page + 1}})">下一页</button>`;
    }
    
    html += '</div>';
    container.innerHTML = html;
}

// 搜索记忆
async function searchMemories() {
    const keyword = document.getElementById('search-keyword')?.value || '';
    const sessionId = document.getElementById('search-session')?.value || null;
    const startDate = document.getElementById('search-start-date')?.value || null;
    const endDate = document.getElementById('search-end-date')?.value || null;
    
    await loadMemories({
        keyword,
        session_id: sessionId,
        start_date: startDate,
        end_date: endDate,
        page: 1
    });
}

// 重置搜索
async function resetSearch() {
    // 清空搜索表单
    if (document.getElementById('search-keyword')) {
        document.getElementById('search-keyword').value = '';
    }
    if (document.getElementById('search-session')) {
        document.getElementById('search-session').value = '';
    }
    if (document.getElementById('search-start-date')) {
        document.getElementById('search-start-date').value = '';
    }
    if (document.getElementById('search-end-date')) {
        document.getElementById('search-end-date').value = '';
    }
    
    // 重新加载
    await loadMemories({
        keyword: '',
        session_id: null,
        start_date: null,
        end_date: null,
        page: 1
    });
}

// 切换记忆选择
function toggleMemorySelection(memoryId) {
    if (selectedMemoryIds.has(memoryId)) {
        selectedMemoryIds.delete(memoryId);
    } else {
        selectedMemoryIds.add(memoryId);
    }
    updateBatchActions();
}

// 全选/取消全选
function toggleSelectAll() {
    const checkboxes = document.querySelectorAll('.memory-item input[type="checkbox"]');
    const allChecked = Array.from(checkboxes).every(cb => cb.checked);
    
    checkboxes.forEach(checkbox => {
        const memoryId = checkbox.closest('.memory-item').dataset.memoryId;
        checkbox.checked = !allChecked;
        
        if (!allChecked) {
            selectedMemoryIds.add(memoryId);
        } else {
            selectedMemoryIds.delete(memoryId);
        }
    });
    
    updateBatchActions();
}

// 更新批量操作按钮状态
function updateBatchActions() {
    const batchActionsEl = document.getElementById('batch-actions');
    const selectedCountEl = document.getElementById('selected-count');
    
    if (batchActionsEl) {
        batchActionsEl.style.display = selectedMemoryIds.size > 0 ? 'flex' : 'none';
    }
    
    if (selectedCountEl) {
        selectedCountEl.textContent = selectedMemoryIds.size;
    }
}

// 批量删除
async function batchDeleteMemories() {
    if (selectedMemoryIds.size === 0) {
        showToast('请先选择要删除的记忆', 'warning');
        return;
    }
    
    if (!confirm(`确定要删除选中的 ${selectedMemoryIds.size} 条记忆吗？此操作不可恢复！`)) {
        return;
    }
    
    showLoading(true);
    
    try {
        await apiCall('/memories/delete', 'POST', {
            memory_ids: Array.from(selectedMemoryIds)
        });
        
        showToast('删除成功', 'success');
        
        // 清空选择
        selectedMemoryIds.clear();
        
        // 重新加载列表
        await loadMemories();
    } catch (error) {
        console.error('批量删除失败:', error);
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 删除单个记忆
async function deleteMemory(memoryId) {
    if (!confirm('确定要删除这条记忆吗？此操作不可恢复！')) {
        return;
    }
    
    showLoading(true);
    
    try {
        await apiCall('/memories/delete', 'POST', {
            memory_ids: [memoryId]
        });
        
        showToast('删除成功', 'success');
        
        // 重新加载列表
        await loadMemories();
    } catch (error) {
        console.error('删除失败:', error);
        showToast('删除失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 查看记忆详情
function viewMemoryDetail(memoryId) {
    const memory = AppState.memoriesData?.memories?.find(m => m.memory_id === memoryId);
    if (!memory) {
        showToast('记忆数据未找到', 'error');
        return;
    }
    
    // 创建模态框显示详情
    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.innerHTML = `
        <div class="modal-content">
            <div class="modal-header">
                <h3>记忆详情</h3>
                <button class="btn-close" onclick="this.closest('.modal').remove()">✕</button>
            </div>
            <div class="modal-body">
                <div class="detail-item">
                    <label>记忆ID:</label>
                    <span>${memory.memory_id}</span>
                </div>
                <div class="detail-item">
                    <label>会话ID:</label>
                    <span>${memory.session_id}</span>
                </div>
                <div class="detail-item">
                    <label>时间:</label>
                    <span>${formatTime(memory.timestamp)}</span>
                </div>
                <div class="detail-item">
                    <label>类型:</label>
                    <span>${getMemoryTypeText(memory.memory_type)}</span>
                </div>
                ${memory.similarity_score !== null ? `
                <div class="detail-item">
                    <label>相似度:</label>
                    <span>${memory.similarity_score.toFixed(3)}</span>
                </div>
                ` : ''}
                <div class="detail-item">
                    <label>内容:</label>
                    <div style="white-space: pre-wrap; margin-top: 0.5rem; padding: 1rem; background: var(--bg-secondary); border-radius: 4px;">
                        ${escapeHtml(memory.content)}
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="this.closest('.modal').remove()">关闭</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // 点击背景关闭
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.remove();
        }
    });
}

// 导出记忆
async function exportMemories(format = 'json') {
    showLoading(true);
    
    try {
        const params = new URLSearchParams({
            format,
            ...currentSearchParams
        });
        
        // 使用 fetch 下载文件
        const response = await fetch(`${API_BASE}/memories/export?${params}`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            }
        });
        
        if (!response.ok) {
            throw new Error('导出失败');
        }
        
        // 获取文件名
        const contentDisposition = response.headers.get('Content-Disposition');
        let filename = `memories_${new Date().toISOString().split('T')[0]}.${format}`;
        if (contentDisposition) {
            const match = contentDisposition.match(/filename="(.+)"/);
            if (match) {
                filename = match[1];
            }
        }
        
        // 下载文件
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showToast('导出成功', 'success');
    } catch (error) {
        console.error('导出失败:', error);
        showToast('导出失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 获取记忆类型文本
function getMemoryTypeText(type) {
    const types = {
        'short_term': '短期记忆',
        'long_term': '长期记忆',
        'summary': '总结'
    };
    return types[type] || type;
}

// 显示错误
function showMemoriesError(message) {
    const container = document.getElementById('memories-list');
    if (container) {
        container.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: var(--danger-color);">
                <p>❌ ${message}</p>
                <button class="btn btn-primary" onclick="loadMemories()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 导出函数
window.loadMemories = loadMemories;
window.searchMemories = searchMemories;
window.resetSearch = resetSearch;
window.toggleMemorySelection = toggleMemorySelection;
window.toggleSelectAll = toggleSelectAll;
window.batchDeleteMemories = batchDeleteMemories;
window.deleteMemory = deleteMemory;
window.viewMemoryDetail = viewMemoryDetail;
window.exportMemories = exportMemories;