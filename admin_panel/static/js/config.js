// 配置管理相关功能

let originalConfig = null;

// 加载配置
async function loadConfig() {
    console.log('加载配置...');
    showLoading(true);
    
    try {
        // 修复: 使用正确的API路径 /api/config
        const data = await apiCall('/config');
        AppState.configData = data;
        originalConfig = JSON.parse(JSON.stringify(data)); // 深拷贝
        
        // 渲染配置表单 - 后端返回的就是config对象，不需要.config
        renderConfigForm(data);
        
        showToast('配置加载成功', 'success');
    } catch (error) {
        console.error('加载配置失败:', error);
        showConfigError('配置加载失败: ' + error.message);
    } finally {
        showLoading(false);
    }
}

// 渲染配置表单
function renderConfigForm(config) {
    const container = document.getElementById('config-form');
    if (!container) return;
    
    container.innerHTML = '';
    
    // 按类别组织配置
    const categories = {
        'Milvus配置': ['milvus_host', 'milvus_port', 'milvus_user', 'milvus_password', 'milvus_db_name', 'milvus_collection_name'],
        'Embedding配置': ['embedding_api_url', 'embedding_model', 'embedding_dim'],
        '记忆管理配置': ['memory_window_size', 'max_context_messages', 'summary_threshold', 'similarity_threshold'],
        '性能配置': ['enable_cache', 'cache_ttl', 'max_retries', 'request_timeout']
    };
    
    for (const [category, fields] of Object.entries(categories)) {
        const section = document.createElement('div');
        section.className = 'config-section';
        
        const header = document.createElement('h3');
        header.textContent = category;
        section.appendChild(header);
        
        fields.forEach(field => {
            if (config.hasOwnProperty(field)) {
                const formGroup = createConfigField(field, config[field]);
                section.appendChild(formGroup);
            }
        });
        
        container.appendChild(section);
    }
    
    // 添加其他配置字段
    const otherSection = document.createElement('div');
    otherSection.className = 'config-section';
    const otherHeader = document.createElement('h3');
    otherHeader.textContent = '其他配置';
    otherSection.appendChild(otherHeader);
    
    const allCategoryFields = Object.values(categories).flat();
    for (const [key, value] of Object.entries(config)) {
        if (!allCategoryFields.includes(key)) {
            const formGroup = createConfigField(key, value);
            otherSection.appendChild(formGroup);
        }
    }
    
    if (otherSection.children.length > 1) {
        container.appendChild(otherSection);
    }
}

// 创建配置字段
function createConfigField(name, value) {
    const formGroup = document.createElement('div');
    formGroup.className = 'form-group';
    
    const label = document.createElement('label');
    label.textContent = formatConfigName(name);
    label.setAttribute('for', `config-${name}`);
    
    let input;
    const valueType = typeof value;
    
    if (valueType === 'boolean') {
        input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = value;
        input.id = `config-${name}`;
        input.name = name;
    } else if (valueType === 'number') {
        input = document.createElement('input');
        input.type = 'number';
        input.value = value;
        input.id = `config-${name}`;
        input.name = name;
        input.className = 'form-control';
    } else {
        input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.id = `config-${name}`;
        input.name = name;
        input.className = 'form-control';
        
        // 敏感字段使用密码输入
        if (name.toLowerCase().includes('password') || name.toLowerCase().includes('token')) {
            input.type = 'password';
        }
    }
    
    formGroup.appendChild(label);
    formGroup.appendChild(input);
    
    // 添加字段说明
    const hint = getConfigHint(name);
    if (hint) {
        const hintEl = document.createElement('small');
        hintEl.className = 'form-hint';
        hintEl.textContent = hint;
        formGroup.appendChild(hintEl);
    }
    
    return formGroup;
}

// 格式化配置名称
function formatConfigName(name) {
    return name
        .replace(/_/g, ' ')
        .replace(/\b\w/g, l => l.toUpperCase());
}

// 获取配置字段说明
function getConfigHint(name) {
    const hints = {
        'milvus_host': 'Milvus服务器地址',
        'milvus_port': 'Milvus服务器端口',
        'embedding_api_url': 'Embedding API的完整URL',
        'embedding_dim': '向量维度，需与模型匹配',
        'memory_window_size': '短期记忆窗口大小',
        'max_context_messages': '最大上下文消息数',
        'summary_threshold': '触发总结的消息数阈值',
        'similarity_threshold': '记忆检索相似度阈值(0-1)',
        'cache_ttl': '缓存过期时间（秒）',
        'request_timeout': '请求超时时间（秒）'
    };
    return hints[name] || '';
}

// 保存配置
async function saveConfig() {
    const formData = collectFormData();
    
    if (!validateConfig(formData)) {
        showToast('配置验证失败，请检查输入', 'error');
        return;
    }
    
    if (!confirm('确定要保存配置吗？某些配置更改可能需要重启插件才能生效。')) {
        return;
    }
    
    showLoading(true);
    
    try {
        // 修复: 使用正确的API路径，直接发送formData
        await apiCall('/config', 'POST', formData);
        
        showToast('配置保存成功', 'success');
        
        // 重新加载配置
        await loadConfig();
    } catch (error) {
        console.error('保存配置失败:', error);
        showToast('保存失败：' + error.message, 'error');
    } finally {
        showLoading(false);
    }
}

// 收集表单数据
function collectFormData() {
    const formData = {};
    const inputs = document.querySelectorAll('#config-form input');
    
    inputs.forEach(input => {
        const name = input.name;
        let value;
        
        if (input.type === 'checkbox') {
            value = input.checked;
        } else if (input.type === 'number') {
            value = parseFloat(input.value);
        } else {
            value = input.value;
        }
        
        formData[name] = value;
    });
    
    return formData;
}

// 验证配置
function validateConfig(config) {
    // 必填字段验证
    const requiredFields = ['milvus_host', 'milvus_port', 'embedding_api_url'];
    
    for (const field of requiredFields) {
        if (!config[field] || config[field] === '') {
            alert(`${formatConfigName(field)} 不能为空`);
            return false;
        }
    }
    
    // 数值范围验证
    if (config.similarity_threshold < 0 || config.similarity_threshold > 1) {
        alert('相似度阈值必须在0-1之间');
        return false;
    }
    
    if (config.memory_window_size < 1) {
        alert('记忆窗口大小必须大于0');
        return false;
    }
    
    return true;
}

// 重置配置
function resetConfig() {
    if (!confirm('确定要重置为原始配置吗？')) {
        return;
    }
    
    if (originalConfig) {
        // 修复: 后端返回的就是config对象
        renderConfigForm(originalConfig);
        showToast('配置已重置', 'info');
    }
}

// 导出配置
async function exportConfig() {
    try {
        // 修复: 后端返回的就是config对象
        const configJson = JSON.stringify(AppState.configData, null, 2);
        const blob = new Blob([configJson], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `config_${new Date().toISOString().split('T')[0]}.json`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        showToast('配置导出成功', 'success');
    } catch (error) {
        console.error('导出配置失败:', error);
        showToast('导出失败：' + error.message, 'error');
    }
}

// 显示错误 (使用DOM创建，避免XSS)
function showConfigError(message) {
    const container = document.getElementById('config-form');
    if (container) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = 'padding: 2rem; text-align: center; color: var(--danger-color);';
        
        const p = document.createElement('p');
        p.textContent = `❌ ${message}`;
        
        const btn = document.createElement('button');
        btn.className = 'btn btn-primary';
        btn.style.marginTop = '1rem';
        btn.textContent = '重试';
        btn.onclick = loadConfig;
        
        errorDiv.appendChild(p);
        errorDiv.appendChild(btn);
        
        container.innerHTML = '';
        container.appendChild(errorDiv);
    }
}

// 导出函数
window.loadConfig = loadConfig;
window.saveConfig = saveConfig;
window.resetConfig = resetConfig;
window.exportConfig = exportConfig;