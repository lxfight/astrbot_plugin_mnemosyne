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
    
    // 使用 DOM 方法创建元素，避免 innerHTML 导致的 XSS 风险
    const checkboxDiv = document.createElement('div');
    checkboxDiv.className = 'memory-checkbox';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = isSelected;
    checkbox.onchange = () => toggleMemorySelection(memory.memory_id);
    checkboxDiv.appendChild(checkbox);
    
    const contentDiv = document.createElement('div');
    contentDiv.className = 'memory-content';
    
    const headerDiv = document.createElement('div');
    headerDiv.className = 'memory-header';
    const sessionSpan = document.createElement('span');
    sessionSpan.className = 'memory-session';
    sessionSpan.textContent = `会话: ${memory.session_id}`;
    const timeSpan = document.createElement('span');
    timeSpan.className = 'memory-time';
    timeSpan.textContent = formatTime(memory.timestamp);
    headerDiv.appendChild(sessionSpan);
    headerDiv.appendChild(timeSpan);
    
    const textDiv = document.createElement('div');
    textDiv.className = 'memory-text';
    textDiv.textContent = memory.content;  // 使用 textContent 自动转义
    
    const footerDiv = document.createElement('div');
    footerDiv.className = 'memory-footer';
    const typeSpan = document.createElement('span');
    typeSpan.className = 'memory-type';
    typeSpan.textContent = getMemoryTypeText(memory.memory_type);
    footerDiv.appendChild(typeSpan);
    
    if (memory.similarity_score !== null) {
        const scoreSpan = document.createElement('span');
        scoreSpan.className = 'memory-score';
        scoreSpan.textContent = `相似度: ${memory.similarity_score.toFixed(3)}`;
        footerDiv.appendChild(scoreSpan);
    }
    
    contentDiv.appendChild(headerDiv);
    contentDiv.appendChild(textDiv);
    contentDiv.appendChild(footerDiv);
    
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'memory-actions';
    
    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn-icon';
    viewBtn.title = '查看详情';
    viewBtn.textContent = '👁️';
    viewBtn.onclick = () => viewMemoryDetail(memory.memory_id);
    
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-icon';
    deleteBtn.title = '删除';
    deleteBtn.textContent = '🗑️';
    deleteBtn.onclick = () => deleteMemory(memory.memory_id);
    
    actionsDiv.appendChild(viewBtn);
    actionsDiv.appendChild(deleteBtn);
    
    div.appendChild(checkboxDiv);
    div.appendChild(contentDiv);
    div.appendChild(actionsDiv);
    
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
    
    // 使用 DOM 方法创建模态框，避免 XSS 风险
    const modal = document.createElement('div');
    modal.className = 'modal';
    
    const modalContent = document.createElement('div');
    modalContent.className = 'modal-content';
    
    const modalHeader = document.createElement('div');
    modalHeader.className = 'modal-header';
    const title = document.createElement('h3');
    title.textContent = '记忆详情';
    const closeBtn = document.createElement('button');
    closeBtn.className = 'btn-close';
    closeBtn.textContent = '✕';
    closeBtn.onclick = () => modal.remove();
    modalHeader.appendChild(title);
    modalHeader.appendChild(closeBtn);
    
    const modalBody = document.createElement('div');
    modalBody.className = 'modal-body';
    
    // 添加各个详情项
    const addDetailItem = (label, value) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'detail-item';
        const labelEl = document.createElement('label');
        labelEl.textContent = label + ':';
        const valueEl = document.createElement('span');
        valueEl.textContent = value;
        itemDiv.appendChild(labelEl);
        itemDiv.appendChild(valueEl);
        modalBody.appendChild(itemDiv);
    };
    
    addDetailItem('记忆ID', memory.memory_id);
    addDetailItem('会话ID', memory.session_id);
    addDetailItem('时间', formatTime(memory.timestamp));
    addDetailItem('类型', getMemoryTypeText(memory.memory_type));
    
    if (memory.similarity_score !== null) {
        addDetailItem('相似度', memory.similarity_score.toFixed(3));
    }
    
    // 内容项特殊处理
    const contentItem = document.createElement('div');
    contentItem.className = 'detail-item';
    const contentLabel = document.createElement('label');
    contentLabel.textContent = '内容:';
    const contentValue = document.createElement('div');
    contentValue.style.whiteSpace = 'pre-wrap';
    contentValue.style.marginTop = '0.5rem';
    contentValue.style.padding = '1rem';
    contentValue.style.background = 'var(--bg-secondary)';
    contentValue.style.borderRadius = '4px';
    contentValue.textContent = memory.content;  // 使用 textContent 自动转义
    contentItem.appendChild(contentLabel);
    contentItem.appendChild(contentValue);
    modalBody.appendChild(contentItem);
    
    const modalFooter = document.createElement('div');
    modalFooter.className = 'modal-footer';
    const closeFooterBtn = document.createElement('button');
    closeFooterBtn.className = 'btn btn-secondary';
    closeFooterBtn.textContent = '关闭';
    closeFooterBtn.onclick = () => modal.remove();
    modalFooter.appendChild(closeFooterBtn);
    
    modalContent.appendChild(modalHeader);
    modalContent.appendChild(modalBody);
    modalContent.appendChild(modalFooter);
    modal.appendChild(modalContent);
    
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