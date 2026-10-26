(function registerMemoryField() {
    const TAU = Math.PI * 2;
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function formatCompact(value) {
        return new Intl.NumberFormat('zh-CN', {
            notation: 'compact',
            maximumFractionDigits: 1,
        }).format(Number(value || 0));
    }

    class MemoryField {
        constructor(canvas) {
            this.canvas = canvas;
            this.context = canvas.getContext('2d', { alpha: true });
            this.stage = canvas.closest('.memory-field-stage');
            this.summary = document.getElementById('memory-field-summary');
            this.count = document.getElementById('memory-field-count');
            this.nodes = [];
            this.edges = [];
            this.width = 1;
            this.height = 1;
            this.pixelRatio = 1;
            this.pointer = { x: -1000, y: -1000, active: false, draggedNode: null };
            this.visible = true;
            this.time = 0;
            this.frame = null;
            this.palette = {};
            this.abortController = new AbortController();
            this.resizeObserver = new ResizeObserver(() => this.resize());
            this.resizeObserver.observe(this.stage);
            this.intersectionObserver = new IntersectionObserver(([entry]) => {
                this.visible = entry.isIntersecting;
                if (this.visible) this.start();
                else this.stop();
            }, { threshold: 0.05 });
            this.intersectionObserver.observe(this.stage);
            this.bindEvents();
            this.refreshPalette();
            this.resize();
        }

        bindEvents() {
            const eventOptions = { signal: this.abortController.signal };
            this.canvas.addEventListener('pointermove', event => {
                const rect = this.canvas.getBoundingClientRect();
                this.pointer.x = event.clientX - rect.left;
                this.pointer.y = event.clientY - rect.top;
                this.pointer.active = true;
                if (this.pointer.draggedNode) {
                    this.pointer.draggedNode.x = this.pointer.x;
                    this.pointer.draggedNode.y = this.pointer.y;
                    this.pointer.draggedNode.vx = 0;
                    this.pointer.draggedNode.vy = 0;
                }
            }, eventOptions);
            this.canvas.addEventListener('pointerleave', () => {
                this.pointer.active = false;
                this.pointer.draggedNode = null;
            }, eventOptions);
            this.canvas.addEventListener('pointerdown', event => {
                const rect = this.canvas.getBoundingClientRect();
                const x = event.clientX - rect.left;
                const y = event.clientY - rect.top;
                this.pointer.draggedNode = this.findNearestNode(x, y, 48);
                if (this.pointer.draggedNode) this.canvas.setPointerCapture(event.pointerId);
            }, eventOptions);
            this.canvas.addEventListener('pointerup', event => {
                this.pointer.draggedNode = null;
                if (this.canvas.hasPointerCapture(event.pointerId)) this.canvas.releasePointerCapture(event.pointerId);
            }, eventOptions);
            prefersReducedMotion.addEventListener('change', () => {
                if (prefersReducedMotion.matches) this.stop();
                this.draw();
            }, eventOptions);
        }

        destroy() {
            this.stop();
            this.abortController.abort();
            this.resizeObserver.disconnect();
            this.intersectionObserver.disconnect();
        }

        refreshPalette() {
            const styles = getComputedStyle(document.documentElement);
            this.palette = {
                ink: styles.getPropertyValue('--ink').trim() || '#243237',
                muted: styles.getPropertyValue('--muted').trim() || '#68797a',
                line: styles.getPropertyValue('--line-strong').trim() || 'rgba(62, 91, 91, 0.28)',
                core: styles.getPropertyValue('--water').trim()
                    || styles.getPropertyValue('--violet').trim()
                    || '#6f9dab',
                live: styles.getPropertyValue('--mint').trim() || '#cee1c8',
                warn: styles.getPropertyValue('--coral').trim() || '#d99b91',
                surface: styles.getPropertyValue('--glass-strong').trim() || 'rgba(255, 255, 255, 0.9)',
            };
            this.draw();
        }

        resize() {
            const rect = this.canvas.getBoundingClientRect();
            this.width = Math.max(1, rect.width);
            this.height = Math.max(1, rect.height);
            this.pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
            this.canvas.width = Math.round(this.width * this.pixelRatio);
            this.canvas.height = Math.round(this.height * this.pixelRatio);
            this.context.setTransform(this.pixelRatio, 0, 0, this.pixelRatio, 0, 0);
            this.nodes.forEach(node => {
                node.x = clamp(node.x, node.radius, this.width - node.radius);
                node.y = clamp(node.y, node.radius, this.height - node.radius);
            });
            this.draw();
        }

        setData(data) {
            const resources = data?.resources || {};
            const components = data?.status?.components || {};
            const totalMemories = resources.vector_database?.total_records || 0;
            const activeSessions = resources.sessions?.active || 0;
            const totalSessions = resources.sessions?.total || 0;
            const componentEntries = Object.entries(components);
            const seeds = [
                { id: 'core', label: '记忆档案', value: formatCompact(totalMemories), type: 'core', nx: 0.48, ny: 0.5, radius: 58 },
                { id: 'sessions', label: '活跃会话', value: `${activeSessions}/${totalSessions}`, type: 'live', nx: 0.19, ny: 0.28, radius: 42 },
                { id: 'memory', label: '进程内存', value: `${Number(resources.memory?.usage_percent || 0).toFixed(1)}%`, type: 'live', nx: 0.78, ny: 0.24, radius: 39 },
                ...componentEntries.map(([id, component], index) => ({
                    id,
                    label: this.componentName(id),
                    value: component.status === 'healthy' ? '正常'
                        : component.status === 'degraded' ? '注意'
                        : component.status === 'unknown' ? '未知'
                        : '异常',
                    type: component.status === 'healthy' || component.status === 'unknown' ? 'live' : 'warn',
                    nx: [0.2, 0.34, 0.69, 0.82][index % 4],
                    ny: [0.72, 0.82, 0.78, 0.64][index % 4],
                    radius: 31,
                })),
            ];

            const previous = new Map(this.nodes.map(node => [node.id, node]));
            this.nodes = seeds.map(seed => {
                const old = previous.get(seed.id);
                const anchorX = seed.nx * this.width;
                const anchorY = seed.ny * this.height;
                return {
                    ...seed,
                    anchorX,
                    anchorY,
                    x: old?.x ?? anchorX,
                    y: old?.y ?? anchorY,
                    vx: old?.vx ?? 0,
                    vy: old?.vy ?? 0,
                    phase: old?.phase ?? Math.random() * TAU,
                };
            });
            this.edges = this.nodes.filter(node => node.id !== 'core').map((node, index) => ({
                source: 'core',
                target: node.id,
                phase: index / Math.max(1, this.nodes.length - 1),
            }));
            if (this.summary) {
                this.summary.textContent = `${formatCompact(totalMemories)} 条记忆连接 ${totalSessions} 个会话与 ${componentEntries.length} 个运行组件`;
            }
            if (this.count) this.count.textContent = String(this.edges.length).padStart(2, '0');
            this.start();
        }

        componentName(name) {
            const labels = {
                milvus: '向量索引',
                embedding_api: '语义模型',
                message_counter: '消息流',
                background_task: '后台任务',
            };
            return labels[name] || name;
        }

        findNearestNode(x, y, padding = 0) {
            return this.nodes.find(node => Math.hypot(node.x - x, node.y - y) <= node.radius + padding) || null;
        }

        start() {
            if (this.frame || !this.visible) return;
            if (prefersReducedMotion.matches) {
                this.draw();
                return;
            }
            const animate = timestamp => {
                this.frame = requestAnimationFrame(animate);
                this.time = timestamp * 0.001;
                this.update();
                this.draw();
            };
            this.frame = requestAnimationFrame(animate);
        }

        stop() {
            if (this.frame) cancelAnimationFrame(this.frame);
            this.frame = null;
        }

        update() {
            for (let i = 0; i < this.nodes.length; i += 1) {
                const node = this.nodes[i];
                if (node === this.pointer.draggedNode) continue;
                node.anchorX = node.nx * this.width;
                node.anchorY = node.ny * this.height;
                node.vx += (node.anchorX - node.x) * 0.0035;
                node.vy += (node.anchorY - node.y) * 0.0035;

                if (this.pointer.active) {
                    const dx = node.x - this.pointer.x;
                    const dy = node.y - this.pointer.y;
                    const distance = Math.max(1, Math.hypot(dx, dy));
                    const influence = clamp((150 - distance) / 150, 0, 1);
                    node.vx += (dx / distance) * influence * 0.62;
                    node.vy += (dy / distance) * influence * 0.62;
                }

                for (let j = i + 1; j < this.nodes.length; j += 1) {
                    const other = this.nodes[j];
                    const dx = node.x - other.x;
                    const dy = node.y - other.y;
                    const distance = Math.max(1, Math.hypot(dx, dy));
                    const minimum = node.radius + other.radius + 18;
                    if (distance < minimum) {
                        const force = (minimum - distance) * 0.004;
                        node.vx += (dx / distance) * force;
                        node.vy += (dy / distance) * force;
                        other.vx -= (dx / distance) * force;
                        other.vy -= (dy / distance) * force;
                    }
                }

                node.vx *= 0.92;
                node.vy *= 0.92;
                node.x = clamp(node.x + node.vx, node.radius, this.width - node.radius);
                node.y = clamp(node.y + node.vy, node.radius, this.height - node.radius);
            }
        }

        draw() {
            if (!this.context) return;
            const ctx = this.context;
            ctx.clearRect(0, 0, this.width, this.height);
            this.drawGrid(ctx);
            this.edges.forEach(edge => this.drawEdge(ctx, edge));
            this.nodes.forEach(node => this.drawNode(ctx, node));
        }

        drawGrid(ctx) {
            ctx.save();
            ctx.strokeStyle = this.palette.line;
            ctx.globalAlpha = 0.18;
            ctx.lineWidth = 1;
            const spacing = this.width < 620 ? 42 : 56;
            for (let x = spacing; x < this.width; x += spacing) {
                ctx.beginPath();
                ctx.moveTo(x, 0);
                ctx.lineTo(x, this.height);
                ctx.stroke();
            }
            for (let y = spacing; y < this.height; y += spacing) {
                ctx.beginPath();
                ctx.moveTo(0, y);
                ctx.lineTo(this.width, y);
                ctx.stroke();
            }
            ctx.restore();
        }

        drawEdge(ctx, edge) {
            const source = this.nodes.find(node => node.id === edge.source);
            const target = this.nodes.find(node => node.id === edge.target);
            if (!source || !target) return;
            const bend = (target.x - source.x) * 0.08;
            const controlX = (source.x + target.x) / 2 + bend;
            const controlY = (source.y + target.y) / 2 - Math.abs(target.x - source.x) * 0.06;
            ctx.save();
            ctx.strokeStyle = this.palette.line;
            ctx.lineWidth = 1;
            ctx.setLineDash([4, 8]);
            ctx.beginPath();
            ctx.moveTo(source.x, source.y);
            ctx.quadraticCurveTo(controlX, controlY, target.x, target.y);
            ctx.stroke();
            ctx.setLineDash([]);

            const progress = (this.time * 0.12 + edge.phase) % 1;
            const inverse = 1 - progress;
            const pulseX = inverse * inverse * source.x + 2 * inverse * progress * controlX + progress * progress * target.x;
            const pulseY = inverse * inverse * source.y + 2 * inverse * progress * controlY + progress * progress * target.y;
            ctx.fillStyle = target.type === 'warn' ? this.palette.warn : this.palette.core;
            ctx.beginPath();
            ctx.arc(pulseX, pulseY, 2.5, 0, TAU);
            ctx.fill();
            ctx.restore();
        }

        drawNode(ctx, node) {
            const hover = this.pointer.active && Math.hypot(node.x - this.pointer.x, node.y - this.pointer.y) < node.radius + 18;
            const size = node.radius * (hover ? 1.06 : 1);
            const fill = node.type === 'core' ? this.palette.core : node.type === 'warn' ? this.palette.warn : this.palette.live;
            ctx.save();
            ctx.translate(node.x, node.y);
            ctx.rotate(Math.sin(this.time * 0.35 + node.phase) * 0.035);
            ctx.shadowColor = 'rgba(38, 60, 59, 0.14)';
            ctx.shadowBlur = hover ? 28 : 16;
            ctx.shadowOffsetY = 8;
            ctx.fillStyle = fill;
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.72)';
            ctx.lineWidth = 1;
            const corner = Math.min(13, size * 0.24);
            ctx.beginPath();
            this.roundedRectPath(ctx, -size, -size * 0.72, size * 2, size * 1.44, corner);
            ctx.fill();
            ctx.stroke();
            ctx.shadowColor = 'transparent';
            ctx.fillStyle = node.type === 'core' ? '#f8fbfa' : this.palette.ink;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.font = `500 ${node.type === 'core' ? 17 : 12}px "Noto Sans SC", sans-serif`;
            ctx.fillText(node.label, 0, -7);
            ctx.font = `500 ${node.type === 'core' ? 14 : 10}px "IBM Plex Mono", monospace`;
            ctx.globalAlpha = 0.72;
            ctx.fillText(node.value, 0, 13);
            ctx.restore();
        }

        roundedRectPath(ctx, x, y, width, height, radius) {
            if (typeof ctx.roundRect === 'function') {
                ctx.roundRect(x, y, width, height, radius);
                return;
            }
            const right = x + width;
            const bottom = y + height;
            ctx.moveTo(x + radius, y);
            ctx.lineTo(right - radius, y);
            ctx.quadraticCurveTo(right, y, right, y + radius);
            ctx.lineTo(right, bottom - radius);
            ctx.quadraticCurveTo(right, bottom, right - radius, bottom);
            ctx.lineTo(x + radius, bottom);
            ctx.quadraticCurveTo(x, bottom, x, bottom - radius);
            ctx.lineTo(x, y + radius);
            ctx.quadraticCurveTo(x, y, x + radius, y);
        }
    }

    window.MnemosyneMemoryField = MemoryField;
}());
