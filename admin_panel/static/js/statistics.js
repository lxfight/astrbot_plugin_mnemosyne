// 统计分析相关功能

let statisticsChart = null;
let distributionChart = null;

// 加载统计数据
async function loadStatistics() {
    console.log('加载统计数据...');
    showLoading(true);
    
    try {
        const data = await apiCall('/memories/statistics');
        AppState.statisticsData = data;
        
        // 渲染统计卡片
        renderStatisticsCards(data);
        
        // 渲染图表
        renderStatisticsChart(data);
        
        // 渲染最活跃会话列表
        renderTopSessions(data);
        
        // 渲染分布图表
        renderDistributionChart(data);
        
        showToast('统计数据加载成功', 'success');
    } catch (error) {
        console.error('加载统计失败:', error);
        showStatisticsError('统计数据加载失败');
    } finally {
        showLoading(false);
    }
}

// 渲染统计卡片
function renderStatisticsCards(data) {
    // 总记忆数
    const totalMemoriesEl = document.getElementById('stat-total-memories');
    if (totalMemoriesEl) {
        totalMemoriesEl.textContent = formatNumber(data.total_memories || 0);
    }
    
    // 活跃会话数
    const activeSessionsEl = document.getElementById('stat-active-sessions');
    if (activeSessionsEl) {
        activeSessionsEl.textContent = formatNumber(data.total_sessions || 0);
    }
    
    // 今日新增
    const todayAddedEl = document.getElementById('stat-today-added');
    if (todayAddedEl) {
        const today = new Date().toISOString().split('T')[0];
        let todayCount = 0;
        
        if (data.memories_by_date && data.memories_by_date[today]) {
            todayCount = data.memories_by_date[today];
        }
        
        todayAddedEl.textContent = formatNumber(todayCount);
    }
    
    // 平均每会话
    const avgPerSessionEl = document.getElementById('stat-avg-per-session');
    if (avgPerSessionEl) {
        const avg = data.total_sessions > 0 ?
            (data.total_memories / data.total_sessions).toFixed(1) : '0';
        avgPerSessionEl.textContent = avg;
    }
}

// 渲染统计图表
function renderStatisticsChart(data) {
    const canvas = document.getElementById('statistics-chart');
    if (!canvas) return;
    
    // 销毁旧图表
    if (statisticsChart) {
        statisticsChart.destroy();
    }
    
    // 准备图表数据 - 从 memories_by_date 对象生成
    let labels = [];
    let counts = [];
    
    // 检查 data 和 memories_by_date 是否存在
    if (data && data.memories_by_date && typeof data.memories_by_date === 'object') {
        // 获取最近30天的数据
        const sortedDates = Object.keys(data.memories_by_date).sort();
        labels = sortedDates.slice(-30);
        counts = labels.map(date => data.memories_by_date[date] || 0);
    }
    
    // 如果没有数据，显示空图表
    if (labels.length === 0) {
        labels = ['暂无数据'];
        counts = [0];
    }
    
    // 创建新图表
    const ctx = canvas.getContext('2d');
    statisticsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '每日新增记忆',
                data: counts,
                borderColor: 'rgb(79, 70, 229)',
                backgroundColor: 'rgba(79, 70, 229, 0.1)',
                tension: 0.4,
                fill: true,
                pointRadius: 4,
                pointHoverRadius: 6,
                pointBackgroundColor: 'rgb(79, 70, 229)',
                pointBorderColor: '#fff',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        font: {
                            size: 14
                        }
                    }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false,
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleFont: {
                        size: 14
                    },
                    bodyFont: {
                        size: 13
                    },
                    padding: 12
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: '日期',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    grid: {
                        display: false
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: '记忆数量',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });
}

// 渲染最活跃会话列表
function renderTopSessions(data) {
    const container = document.getElementById('top-sessions-list');
    if (!container) return;
    
    if (!data.most_active_sessions || data.most_active_sessions.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>暂无会话数据</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    data.most_active_sessions.forEach((session, index) => {
        const sessionEl = document.createElement('div');
        sessionEl.className = 'list-item';
        sessionEl.style.cssText = 'display: flex; justify-content: space-between; align-items: center;';
        
        const leftDiv = document.createElement('div');
        leftDiv.style.cssText = 'display: flex; align-items: center; gap: 1rem;';
        
        const rank = document.createElement('span');
        rank.style.cssText = 'font-size: 1.5rem; font-weight: bold; color: var(--primary-color); min-width: 30px;';
        rank.textContent = `#${index + 1}`;
        
        const info = document.createElement('div');
        const sessionName = document.createElement('div');
        sessionName.style.cssText = 'font-weight: 600; margin-bottom: 0.25rem;';
        sessionName.textContent = session[0];
        
        const sessionCount = document.createElement('div');
        sessionCount.style.cssText = 'font-size: 0.875rem; color: var(--text-secondary);';
        sessionCount.textContent = `${session[1]} 条记忆`;
        
        info.appendChild(sessionName);
        info.appendChild(sessionCount);
        
        leftDiv.appendChild(rank);
        leftDiv.appendChild(info);
        
        const viewBtn = document.createElement('button');
        viewBtn.className = 'btn btn-sm btn-secondary';
        viewBtn.textContent = '查看';
        viewBtn.onclick = () => viewSessionMemories(session[0]);
        
        sessionEl.appendChild(leftDiv);
        sessionEl.appendChild(viewBtn);
        
        container.appendChild(sessionEl);
    });
}

// 渲染分布图表
function renderDistributionChart(data) {
    const canvas = document.getElementById('distribution-chart');
    if (!canvas) return;
    
    // 销毁旧图表
    if (distributionChart) {
        distributionChart.destroy();
    }
    
    // 准备会话分布数据 - 显示前10个会话
    let labels = [];
    let counts = [];
    
    if (data.most_active_sessions && data.most_active_sessions.length > 0) {
        data.most_active_sessions.slice(0, 10).forEach(session => {
            labels.push(session[0].substring(0, 20) + (session[0].length > 20 ? '...' : ''));
            counts.push(session[1]);
        });
    } else {
        labels = ['暂无数据'];
        counts = [0];
    }
    
    // 创建新图表
    const ctx = canvas.getContext('2d');
    distributionChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: '记忆数量',
                data: counts,
                backgroundColor: [
                    'rgba(79, 70, 229, 0.8)',
                    'rgba(249, 115, 22, 0.8)',
                    'rgba(16, 185, 129, 0.8)',
                    'rgba(239, 68, 68, 0.8)',
                    'rgba(245, 158, 11, 0.8)',
                    'rgba(99, 102, 241, 0.8)',
                    'rgba(236, 72, 153, 0.8)',
                    'rgba(20, 184, 166, 0.8)',
                    'rgba(251, 146, 60, 0.8)',
                    'rgba(139, 92, 246, 0.8)'
                ],
                borderColor: [
                    'rgb(79, 70, 229)',
                    'rgb(249, 115, 22)',
                    'rgb(16, 185, 129)',
                    'rgb(239, 68, 68)',
                    'rgb(245, 158, 11)',
                    'rgb(99, 102, 241)',
                    'rgb(236, 72, 153)',
                    'rgb(20, 184, 166)',
                    'rgb(251, 146, 60)',
                    'rgb(139, 92, 246)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleFont: {
                        size: 14
                    },
                    bodyFont: {
                        size: 13
                    },
                    padding: 12
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: '会话ID',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    grid: {
                        display: false
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: '记忆数量',
                        font: {
                            size: 14,
                            weight: 'bold'
                        }
                    },
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    }
                }
            }
        }
    });
}

// 显示错误
function showStatisticsError(message) {
    const container = document.getElementById('statistics-content');
    if (container) {
        container.innerHTML = `
            <div style="padding: 2rem; text-align: center; color: var(--danger-color);">
                <p><i class="ti ti-alert-circle"></i> ${message}</p>
                <button class="btn btn-primary" onclick="loadStatistics()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 导出函数
window.loadStatistics = loadStatistics;