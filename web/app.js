/**
 * Meme Token Hunter — Live Dashboard App
 * WebSocket-powered real-time token feed with filtering, export, and detail modals.
 */

(function () {
    'use strict';

    // ---- State ----
    const state = {
        tokens: [],
        filters: { chain: 'all', minSafety: 0, hours: 24 },
        ws: null,
        wsRetries: 0,
        stats: { total: 0, safe: 0, honeypots: 0 },
    };

    // ---- DOM Refs ----
    const dom = {
        feedBody: document.getElementById('feed-body'),
        loading: document.getElementById('loading'),
        statusDot: document.querySelector('.status-dot'),
        statusText: document.querySelector('.status-text'),
        totalTokens: document.getElementById('total-tokens'),
        safeTokens: document.getElementById('safe-tokens'),
        honeypotCount: document.getElementById('honeypot-count'),
        safetyFilter: document.getElementById('safety-filter'),
        safetyValue: document.getElementById('safety-value'),
        timeFilter: document.getElementById('time-filter'),
        modalOverlay: document.getElementById('modal-overlay'),
        modalContent: document.getElementById('modal-content'),
        modalClose: document.getElementById('modal-close'),
        btnExport: document.getElementById('btn-export'),
        matrixCanvas: document.getElementById('matrix-bg'),
    };

    // ---- Matrix Rain Background ----
    function initMatrix() {
        const canvas = dom.matrixCanvas;
        const ctx = canvas.getContext('2d');
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;

        const chars = '01アイウエオカキクケコサシスセソタチツテト$ETHSOLBSCBASE';
        const fontSize = 14;
        const columns = Math.floor(canvas.width / fontSize);
        const drops = Array(columns).fill(1);

        function draw() {
            ctx.fillStyle = 'rgba(10, 14, 23, 0.05)';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#22d3ee';
            ctx.font = `${fontSize}px JetBrains Mono`;

            for (let i = 0; i < drops.length; i++) {
                const char = chars[Math.floor(Math.random() * chars.length)];
                ctx.fillText(char, i * fontSize, drops[i] * fontSize);
                if (drops[i] * fontSize > canvas.height && Math.random() > 0.975) {
                    drops[i] = 0;
                }
                drops[i]++;
            }
            requestAnimationFrame(draw);
        }
        draw();

        window.addEventListener('resize', () => {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
        });
    }

    // ---- WebSocket ----
    function connectWS() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/feed`;

        state.ws = new WebSocket(wsUrl);

        state.ws.onopen = () => {
            state.wsRetries = 0;
            dom.statusDot.classList.add('connected');
            dom.statusDot.classList.remove('error');
            dom.statusText.textContent = 'Live';
        };

        state.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'new_token') {
                    addToken(msg.data);
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        state.ws.onclose = () => {
            dom.statusDot.classList.remove('connected');
            dom.statusText.textContent = 'Disconnected';
            // Reconnect with backoff
            const delay = Math.min(1000 * Math.pow(2, state.wsRetries), 30000);
            state.wsRetries++;
            setTimeout(connectWS, delay);
        };

        state.ws.onerror = () => {
            dom.statusDot.classList.add('error');
            dom.statusText.textContent = 'Error';
        };
    }

    // ---- Load Initial Data ----
    async function loadTokens() {
        try {
            const params = new URLSearchParams({
                hours: state.filters.hours,
                limit: 200,
            });
            if (state.filters.chain !== 'all') params.set('chain', state.filters.chain);
            if (state.filters.minSafety > 0) params.set('min_safety', state.filters.minSafety);

            const resp = await fetch(`/api/v1/tokens/?${params}`);
            if (resp.ok) {
                const tokens = await resp.json();
                state.tokens = tokens;
                renderTokens();
                updateStats();
            }
        } catch (e) {
            console.error('Load tokens error:', e);
        }

        // Load stats
        try {
            const resp = await fetch('/api/v1/stats/');
            if (resp.ok) {
                const stats = await resp.json();
                state.stats = stats;
                dom.totalTokens.textContent = stats.total_tokens || 0;
                dom.safeTokens.textContent = stats.safe_tokens || 0;
                dom.honeypotCount.textContent = stats.honeypots_detected || 0;
            }
        } catch (e) { /* stats optional */ }
    }

    // ---- Add Token from WS ----
    function addToken(tokenData) {
        // Check filters
        if (state.filters.chain !== 'all' && tokenData.token?.chain !== state.filters.chain) return;
        if (tokenData.analysis?.safety_score < state.filters.minSafety) return;

        const token = {
            address: tokenData.token?.address,
            symbol: tokenData.token?.symbol || '???',
            name: tokenData.token?.name,
            chain: tokenData.token?.chain,
            safety_score: tokenData.analysis?.safety_score,
            rugpull_risk: tokenData.analysis?.rugpull_risk,
            is_honeypot: tokenData.analysis?.is_honeypot,
            social_score: tokenData.analysis?.social_score,
            liquidity_usd: tokenData.market?.liquidity_usd,
            price_usd: tokenData.market?.price_usd,
            dex: tokenData.market?.dex,
            discovered_at: tokenData.timestamp,
        };

        state.tokens.unshift(token);
        if (state.tokens.length > 500) state.tokens.pop();

        // Insert DOM element
        const row = createTokenRow(token, true);
        if (dom.loading) dom.loading.style.display = 'none';
        dom.feedBody.prepend(row);

        updateStats();
    }

    // ---- Render ----
    function renderTokens() {
        dom.feedBody.innerHTML = '';
        if (state.tokens.length === 0) {
            dom.feedBody.innerHTML = `
                <div class="empty-state">
                    <div class="emoji">🔭</div>
                    <p>No tokens found. Scanner is running...</p>
                </div>`;
            return;
        }
        const fragment = document.createDocumentFragment();
        for (const token of state.tokens) {
            fragment.appendChild(createTokenRow(token));
        }
        dom.feedBody.appendChild(fragment);
    }

    function createTokenRow(token, isNew = false) {
        const row = document.createElement('div');
        row.className = `token-row${isNew ? ' new' : ''}`;
        row.dataset.address = token.address;

        const chainEmojis = { solana: '◎', bsc: '🔶', ethereum: '⟠', base: '🔵' };
        const safety = token.safety_score ?? 0;
        const safetyClass = safety >= 60 ? 'safe' : safety >= 30 ? 'warn' : 'danger';
        const rugRisk = token.rugpull_risk ?? 0;
        const rugClass = rugRisk < 30 ? 'safe' : rugRisk < 60 ? 'warn' : 'danger';
        const liq = token.liquidity_usd ? `$${formatNumber(token.liquidity_usd)}` : '—';
        const timeAgo = token.discovered_at ? getTimeAgo(token.discovered_at) : '—';

        row.innerHTML = `
            <div class="chain-badge">
                <span>${chainEmojis[token.chain] || '•'}</span>
                <span class="chain-label">${(token.chain || '').toUpperCase()}</span>
            </div>
            <div class="token-info">
                <span class="token-symbol">${escapeHtml(token.symbol || '???')}${token.is_honeypot ? ' <span class="honeypot-tag">🍯 HP</span>' : ''}</span>
                <span class="token-address">${(token.address || '').slice(0, 8)}...${(token.address || '').slice(-6)}</span>
            </div>
            <div class="safety-score">
                <div class="score-bar"><div class="score-fill ${safetyClass}" style="width:${safety}%"></div></div>
                <span class="score-value ${safetyClass}">${safety.toFixed(0)}</span>
            </div>
            <div class="rug-risk ${rugClass}">${rugRisk.toFixed(0)}%</div>
            <div class="liquidity">${liq}</div>
            <div class="dex-name">${escapeHtml(token.dex || '—')}</div>
            <div class="time-ago">${timeAgo}</div>
        `;

        row.addEventListener('click', () => showTokenDetail(token));
        return row;
    }

    // ---- Token Detail Modal ----
    function showTokenDetail(token) {
        const safety = token.safety_score ?? 0;
        const safetyClass = safety >= 60 ? 'safe' : safety >= 30 ? 'warn' : 'danger';
        const rugRisk = token.rugpull_risk ?? 0;
        const chain = token.chain || 'unknown';

        const explorerUrls = {
            solana: `https://solscan.io/token/${token.address}`,
            bsc: `https://bscscan.com/token/${token.address}`,
            ethereum: `https://etherscan.io/token/${token.address}`,
            base: `https://basescan.org/token/${token.address}`,
        };

        dom.modalContent.innerHTML = `
            <div class="modal-header">
                <span class="modal-token-symbol">${escapeHtml(token.symbol || '???')}</span>
                <span class="modal-chain-badge">${chain.toUpperCase()}</span>
                ${token.is_honeypot ? '<span class="honeypot-tag">🍯 HONEYPOT</span>' : ''}
            </div>

            <div class="modal-address" onclick="navigator.clipboard.writeText('${token.address}').then(()=>this.textContent='✅ Copied!')" title="Click to copy">
                ${token.address}
            </div>

            <div class="modal-section">
                <h3>Analysis</h3>
                <div class="modal-grid">
                    <div class="modal-stat">
                        <div class="modal-stat-label">Safety Score</div>
                        <div class="modal-stat-value ${safetyClass}">${safety.toFixed(0)}/100</div>
                    </div>
                    <div class="modal-stat">
                        <div class="modal-stat-label">Rug Pull Risk</div>
                        <div class="modal-stat-value" style="color:${rugRisk < 30 ? 'var(--safe)' : rugRisk < 60 ? 'var(--warn)' : 'var(--danger)'}">${rugRisk.toFixed(0)}%</div>
                    </div>
                    <div class="modal-stat">
                        <div class="modal-stat-label">Liquidity</div>
                        <div class="modal-stat-value">${token.liquidity_usd ? '$' + formatNumber(token.liquidity_usd) : '—'}</div>
                    </div>
                    <div class="modal-stat">
                        <div class="modal-stat-label">Social Score</div>
                        <div class="modal-stat-value">${(token.social_score ?? 0).toFixed(0)}/100</div>
                    </div>
                </div>
            </div>

            <div class="modal-section">
                <h3>Market</h3>
                <div class="modal-grid">
                    <div class="modal-stat">
                        <div class="modal-stat-label">Price</div>
                        <div class="modal-stat-value">${token.price_usd ? '$' + token.price_usd.toFixed(8) : '—'}</div>
                    </div>
                    <div class="modal-stat">
                        <div class="modal-stat-label">DEX</div>
                        <div class="modal-stat-value">${escapeHtml(token.dex || '—')}</div>
                    </div>
                </div>
            </div>

            <div class="modal-links">
                <a class="modal-link" href="https://dexscreener.com/${chain}/${token.address}" target="_blank" rel="noopener">📊 DexScreener</a>
                <a class="modal-link" href="${explorerUrls[chain] || '#'}" target="_blank" rel="noopener">🔗 Explorer</a>
            </div>
        `;

        dom.modalOverlay.classList.add('active');
    }

    function closeModal() {
        dom.modalOverlay.classList.remove('active');
    }

    // ---- Export CSV ----
    function exportCSV() {
        const headers = ['Address', 'Symbol', 'Chain', 'Safety', 'Rug Risk', 'Honeypot', 'Liquidity', 'DEX', 'Discovered'];
        const rows = state.tokens.map(t => [
            t.address, t.symbol, t.chain, t.safety_score, t.rugpull_risk,
            t.is_honeypot ? 'YES' : 'NO', t.liquidity_usd || '', t.dex || '', t.discovered_at || '',
        ]);

        let csv = headers.join(',') + '\n';
        rows.forEach(r => { csv += r.map(v => `"${v}"`).join(',') + '\n'; });

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `meme-tokens-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    // ---- Helpers ----
    function formatNumber(n) {
        if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
        if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
        return n.toFixed(0);
    }

    function getTimeAgo(dateStr) {
        const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
        if (diff < 60) return `${Math.floor(diff)}s`;
        if (diff < 3600) return `${Math.floor(diff / 60)}m`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
        return `${Math.floor(diff / 86400)}d`;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function updateStats() {
        dom.totalTokens.textContent = state.tokens.length;
        dom.safeTokens.textContent = state.tokens.filter(t => (t.safety_score ?? 0) >= 60).length;
        dom.honeypotCount.textContent = state.tokens.filter(t => t.is_honeypot).length;
    }

    // ---- Event Listeners ----
    function setupEvents() {
        // Chain filter buttons
        document.querySelectorAll('.chain-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.chain-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                state.filters.chain = btn.dataset.chain;
                loadTokens();
            });
        });

        // Safety slider
        dom.safetyFilter.addEventListener('input', (e) => {
            const val = parseInt(e.target.value);
            state.filters.minSafety = val;
            dom.safetyValue.textContent = `${val}+`;
        });
        dom.safetyFilter.addEventListener('change', () => loadTokens());

        // Time filter
        dom.timeFilter.addEventListener('change', (e) => {
            state.filters.hours = parseInt(e.target.value);
            loadTokens();
        });

        // Modal
        dom.modalClose.addEventListener('click', closeModal);
        dom.modalOverlay.addEventListener('click', (e) => {
            if (e.target === dom.modalOverlay) closeModal();
        });
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closeModal();
        });

        // Export
        dom.btnExport.addEventListener('click', exportCSV);
    }

    // ---- Init ----
    function init() {
        initMatrix();
        setupEvents();
        loadTokens();
        connectWS();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
