// 统计分析相关功能

let statisticsChart = null;

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
        totalMemoriesEl.textContent = formatNumber(data.total_memories);
    }
    
    // 活跃会话数
    const activeSessionsEl = document.getElementById('stat-active-sessions');
    if (activeSessionsEl) {
        activeSessionsEl.textContent = formatNumber(data.total_sessions);
    }
    
    // 今日新增
    const todayAddedEl = document.getElementById('stat-today-added');
    if (todayAddedEl && data.daily_stats) {
        const today = new Date().toISOString().split('T')[0];
        const todayStats = data.daily_stats.find(s => s.date === today);
        todayAddedEl.textContent = todayStats ? formatNumber(todayStats.count) : '0';
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
    
    // 准备图表数据
    const labels = data.daily_stats.map(s => s.date);
    const counts = data.daily_stats.map(s => s.count);
    
    // 创建新图表
    const ctx = canvas.getContext('2d');
    statisticsChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '每日新增记忆',
                data: counts,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            scales: {
                x: {
                    display: true,
                    title: {
                        display: true,
                        text: '日期'
                    }
                },
                y: {
                    display: true,
                    title: {
                        display: true,
                        text: '记忆数量'
                    },
                    beginAtZero: true
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
                <p>❌ ${message}</p>
                <button class="btn btn-primary" onclick="loadStatistics()" style="margin-top: 1rem;">
                    重试
                </button>
            </div>
        `;
    }
}

// 导出函数
window.loadStatistics = loadStatistics;