"""Dashboard route serving the observability UI."""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Product Research Agent</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 20px;
        }
        h1 { font-size: 24px; font-weight: 600; }
        .status {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #666;
        }
        .status-dot.connected { background: #4ade80; }
        .status-dot.disconnected { background: #f87171; }

        .layout { display: grid; grid-template-columns: 400px 1fr; gap: 20px; }

        .traces-panel {
            background: #16213e;
            border-radius: 8px;
            padding: 16px;
            max-height: calc(100vh - 140px);
            overflow-y: auto;
        }
        .traces-panel h2 {
            font-size: 16px;
            margin-bottom: 16px;
            color: #94a3b8;
        }
        .trace-item {
            background: #1e3a5f;
            border-radius: 6px;
            padding: 12px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .trace-item:hover { background: #2563eb; }
        .trace-item.selected { background: #2563eb; border: 1px solid #60a5fa; }
        .trace-item.running { border-left: 3px solid #fbbf24; }
        .trace-item.completed { border-left: 3px solid #4ade80; }
        .trace-item.error { border-left: 3px solid #f87171; }
        .trace-prompt {
            font-size: 14px;
            margin-bottom: 8px;
            line-height: 1.4;
            word-break: break-word;
        }
        .trace-meta {
            display: flex;
            gap: 12px;
            font-size: 12px;
            color: #94a3b8;
        }
        .trace-meta span { display: flex; align-items: center; gap: 4px; }
        .trace-id {
            font-family: monospace;
            font-size: 11px;
            color: #64748b;
            background: #0f172a;
            padding: 2px 6px;
            border-radius: 3px;
            user-select: all;
        }

        .detail-panel {
            background: #16213e;
            border-radius: 8px;
            padding: 20px;
            max-height: calc(100vh - 140px);
            overflow-y: auto;
        }
        .detail-panel h2 {
            font-size: 18px;
            margin-bottom: 16px;
        }
        .detail-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid #333;
        }
        .detail-stats {
            display: flex;
            gap: 24px;
        }
        .stat { text-align: center; }
        .stat-value { font-size: 24px; font-weight: 600; color: #60a5fa; }
        .stat-label { font-size: 12px; color: #94a3b8; }

        .spans-list { display: flex; flex-direction: column; gap: 8px; }
        .span-item {
            background: #1e3a5f;
            border-radius: 6px;
            overflow: hidden;
        }
        .span-header {
            padding: 12px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .span-header:hover { background: rgba(255,255,255,0.05); }
        .span-type {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
            margin-right: 8px;
        }
        .span-type.llm_call { background: #7c3aed; }
        .span-type.tool_call { background: #059669; }
        .span-type.agent_run { background: #2563eb; }
        .span-type.handoff { background: #ea580c; }
        .span-name { font-size: 14px; }
        .span-meta { font-size: 12px; color: #94a3b8; display: flex; gap: 12px; }
        .span-content {
            display: none;
            padding: 12px;
            background: #0f172a;
            border-top: 1px solid #333;
        }
        .span-content.expanded { display: block; }
        .span-section {
            margin-bottom: 12px;
        }
        .span-section-title {
            font-size: 12px;
            color: #94a3b8;
            margin-bottom: 6px;
            text-transform: uppercase;
        }
        .span-section-content {
            background: #1e293b;
            padding: 12px;
            border-radius: 4px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 13px;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 300px;
            overflow-y: auto;
        }

        .empty-state {
            text-align: center;
            padding: 40px;
            color: #94a3b8;
        }

        .results-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            font-size: 13px;
        }
        .results-table th {
            text-align: left;
            padding: 10px 12px;
            background: #1e293b;
            color: #94a3b8;
            font-weight: 600;
            font-size: 11px;
            text-transform: uppercase;
            border-bottom: 1px solid #333;
        }
        .results-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #2d3748;
            vertical-align: middle;
        }
        .results-table tr:hover {
            background: rgba(255,255,255,0.03);
        }
        .results-table a {
            color: #60a5fa;
            text-decoration: none;
        }
        .results-table a:hover {
            text-decoration: underline;
        }
        .whatsapp-btn {
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            background: #25D366;
            color: white;
            border-radius: 4px;
            text-decoration: none;
            font-size: 12px;
            font-weight: 500;
        }
        .whatsapp-btn:hover {
            background: #128C7E;
            text-decoration: none;
        }
        .rating-badge {
            display: inline-block;
            padding: 2px 6px;
            background: #fbbf24;
            color: #000;
            border-radius: 4px;
            font-weight: 600;
            font-size: 12px;
        }
        .price-value {
            font-weight: 600;
            color: #4ade80;
        }

        .badge {
            display: inline-block;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge.running { background: #fbbf24; color: #000; }
        .badge.completed { background: #4ade80; color: #000; }
        .badge.error { background: #f87171; color: #000; }
        .badge.cached { background: #a78bfa; color: #000; }
        .badge.fresh { background: #38bdf8; color: #000; }
        .badge.bundle { background: #f59e0b; color: #000; }

        .bundle-section {
            background: linear-gradient(135deg, #1e3a5f 0%, #16213e 100%);
            border: 1px solid #f59e0b;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 16px;
        }
        .bundle-section h4 {
            color: #f59e0b;
            margin-bottom: 12px;
            font-size: 14px;
        }
        .bundle-table td { vertical-align: top; }
        .bundle-products {
            font-size: 12px;
            color: #94a3b8;
            line-height: 1.6;
        }
        .price-link {
            color: #60a5fa;
            text-decoration: none;
            font-weight: 600;
        }
        .price-link:hover {
            color: #93c5fd;
            text-decoration: underline;
        }
        .bundle-total {
            font-weight: 700;
            font-size: 16px;
            color: #4ade80;
        }
        .negotiation-tip {
            font-size: 11px;
            color: #f59e0b;
            font-style: italic;
        }

        .search-bar {
            display: flex;
            gap: 12px;
            margin-bottom: 20px;
            padding: 16px;
            background: #16213e;
            border-radius: 8px;
        }
        .search-input {
            flex: 1;
            padding: 12px 16px;
            font-size: 16px;
            border: 2px solid #2563eb;
            border-radius: 6px;
            background: #1e3a5f;
            color: #fff;
            outline: none;
        }
        .search-input:focus {
            border-color: #60a5fa;
            box-shadow: 0 0 0 3px rgba(96, 165, 250, 0.2);
        }
        .search-input::placeholder {
            color: #94a3b8;
        }
        .search-btn {
            padding: 12px 24px;
            font-size: 16px;
            font-weight: 600;
            background: #2563eb;
            color: #fff;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }
        .search-btn:hover {
            background: #1d4ed8;
        }
        .search-btn:disabled {
            background: #475569;
            cursor: not-allowed;
        }

        /* Draft Modal Styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.7);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal-content {
            background: #16213e;
            border-radius: 12px;
            max-width: 700px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .modal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 16px 20px;
            border-bottom: 1px solid #333;
        }
        .modal-header h2 { margin: 0; font-size: 18px; }
        .modal-close {
            background: none;
            border: none;
            color: #94a3b8;
            font-size: 24px;
            cursor: pointer;
        }
        .modal-body { padding: 12px; }
        .modal-footer {
            padding: 16px 20px;
            border-top: 1px solid #333;
            display: flex;
            justify-content: flex-end;
            gap: 12px;
        }
        .draft-card {
            background: #1e3a5f;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 12px;
        }
        .draft-card.sent {
            opacity: 0.6;
            border: 2px solid #4ade80;
        }
        .draft-header {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 8px;
        }
        .draft-header strong { color: #60a5fa; }
        .draft-product { color: #94a3b8; font-size: 13px; margin-bottom: 12px; }
        .draft-field { margin-bottom: 12px; }
        .draft-field label {
            display: block;
            font-size: 12px;
            color: #94a3b8;
            margin-bottom: 4px;
        }
        .draft-phone-input {
            width: 200px;
            padding: 8px 12px;
            background: #0f172a;
            color: #fff;
            border: 1px solid #333;
            border-radius: 4px;
            font-size: 14px;
        }
        .draft-textarea {
            width: 100%;
            min-height: 80px;
            background: #0f172a;
            color: #fff;
            border: 1px solid #333;
            border-radius: 6px;
            padding: 12px;
            font-family: inherit;
            font-size: 14px;
            resize: vertical;
        }
        .draft-actions {
            display: flex;
            gap: 8px;
            margin-top: 12px;
        }
        .draft-send-btn {
            background: #25D366;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .draft-send-btn:hover { background: #128C7E; }
        .draft-copy-btn {
            background: #475569;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 13px;
        }
        .bulk-actions {
            display: none;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            background: #1e3a5f;
            border-radius: 8px;
            margin-bottom: 12px;
        }
        .negotiate-btn {
            background: #7c3aed;
            color: white;
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-weight: 500;
        }
        .negotiate-btn:hover { background: #6d28d9; }
        .seller-checkbox { width: 16px; height: 16px; cursor: pointer; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Product Research Agent</h1>
            <div class="status">
                <span class="status-dot" id="statusDot"></span>
                <span id="statusText">Connecting...</span>
            </div>
        </header>

        <div class="search-bar">
            <input type="text" class="search-input" id="queryInput"
                   placeholder="Enter product to search (e.g., iPhone 15, Samsung TV...)"
                   onkeydown="if(event.key==='Enter') runQuery()">
            <button class="search-btn" id="searchBtn" onclick="runQuery()">Search</button>
        </div>

        <div class="layout">
            <div class="traces-panel">
                <h2>Recent Traces</h2>
                <div id="tracesList"></div>
            </div>

            <div class="detail-panel">
                <div id="traceDetail">
                    <div class="empty-state">
                        <p>Select a trace to view details</p>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws = null;
        let traces = {};
        let selectedTraceId = null;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/traces/ws`);

            ws.onopen = () => {
                document.getElementById('statusDot').className = 'status-dot connected';
                document.getElementById('statusText').textContent = 'Connected';
                loadTraces();
            };

            ws.onclose = () => {
                document.getElementById('statusDot').className = 'status-dot disconnected';
                document.getElementById('statusText').textContent = 'Disconnected';
                setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                document.getElementById('statusDot').className = 'status-dot disconnected';
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleEvent(data);
            };
        }

        function handleEvent(event) {
            switch (event.event_type) {
                case 'trace_started':
                case 'trace_ended':
                    loadTraces();
                    if (selectedTraceId === event.trace_id) {
                        loadTraceDetail(event.trace_id);
                    }
                    break;
                case 'span_started':
                case 'span_ended':
                    if (selectedTraceId === event.trace_id) {
                        loadTraceDetail(event.trace_id);
                    }
                    break;
            }
        }

        async function loadTraces() {
            try {
                const response = await fetch('/traces/');
                const data = await response.json();
                renderTraces(data.traces);
            } catch (error) {
                console.error('Failed to load traces:', error);
            }
        }

        function renderTraces(traceList) {
            const container = document.getElementById('tracesList');
            if (!traceList.length) {
                container.innerHTML = '<div class="empty-state">No traces yet</div>';
                return;
            }

            container.innerHTML = traceList.map(trace => `
                <div class="trace-item ${trace.status} ${selectedTraceId === trace.id ? 'selected' : ''}"
                     onclick="selectTrace('${trace.id}')">
                    <div class="trace-prompt">${escapeHtml(trace.input_prompt)}</div>
                    <div class="trace-meta">
                        <span class="trace-id">${trace.id.substring(0, 8)}</span>
                        <span class="badge ${trace.status}">${trace.status}</span>
                        <span>${formatDuration(trace.total_duration_ms)}</span>
                        <span>${trace.total_tokens} tokens</span>
                    </div>
                </div>
            `).join('');
        }

        async function selectTrace(traceId) {
            selectedTraceId = traceId;
            loadTraces();
            loadTraceDetail(traceId);
        }

        async function loadTraceDetail(traceId) {
            try {
                const response = await fetch(`/traces/${traceId}`);
                const trace = await response.json();
                renderTraceDetail(trace);
            } catch (error) {
                console.error('Failed to load trace detail:', error);
            }
        }

        function renderTraceDetail(trace) {
            const container = document.getElementById('traceDetail');

            // Find ALL search tool outputs for structured results
            const searchSpans = trace.spans.filter(s =>
                s.span_type === 'tool_call' &&
                (s.tool_name === 'search_products' || s.tool_name === 'search_multiple_products') &&
                s.tool_output
            );

            container.innerHTML = `
                <div class="detail-header">
                    <div>
                        <h2>Trace Details</h2>
                        <div style="margin-top: 8px;">
                            <span class="badge ${trace.status}">${trace.status}</span>
                            <span class="trace-id" style="margin-left: 8px;" title="Click to copy full ID" onclick="navigator.clipboard.writeText('${trace.id}')">${trace.id}</span>
                        </div>
                    </div>
                    <div class="detail-stats">
                        <div class="stat">
                            <div class="stat-value">${trace.total_tokens}</div>
                            <div class="stat-label">Total Tokens</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">${formatDuration(trace.total_duration_ms)}</div>
                            <div class="stat-label">Duration</div>
                        </div>
                        <div class="stat">
                            <div class="stat-value">${trace.spans.length}</div>
                            <div class="stat-label">Spans</div>
                        </div>
                    </div>
                </div>

                <div class="span-section">
                    <div class="span-section-title">Input Prompt</div>
                    <div class="span-section-content">${escapeHtml(trace.input_prompt)}</div>
                </div>

                ${trace.final_output ? `
                <div class="span-section">
                    <div class="span-section-title">Final Output</div>
                    <div class="span-section-content">${escapeHtml(trace.final_output)}</div>
                </div>
                ` : ''}

                ${searchSpans.map(span => renderSearchResultsTable(span)).join('')}

                ${trace.error ? `
                <div class="span-section">
                    <div class="span-section-title">Error</div>
                    <div class="span-section-content" style="color: #f87171;">${escapeHtml(trace.error)}</div>
                </div>
                ` : ''}

                <h3 style="margin: 20px 0 12px; font-size: 16px;">Spans</h3>
                <div class="spans-list">
                    ${trace.spans.map((span, idx) => renderSpan(span, idx)).join('')}
                </div>
            `;
        }

        function renderSpan(span, idx) {
            return `
                <div class="span-item">
                    <div class="span-header" onclick="toggleSpan(${idx})">
                        <div>
                            <span class="span-type ${span.span_type}">${span.span_type.toUpperCase()}</span>
                            <span class="span-name">${escapeHtml(span.name)}${span.cached === true ? ' (Cached)' : ''}</span>
                        </div>
                        <div class="span-meta">
                            ${span.input_tokens ? `<span>${span.input_tokens} in</span>` : ''}
                            ${span.output_tokens ? `<span>${span.output_tokens} out</span>` : ''}
                            ${span.cached !== null && span.cached !== undefined ? `<span class="badge ${span.cached ? 'cached' : 'fresh'}">${span.cached ? 'CACHED' : 'FRESH'}</span>` : ''}
                            <span>${formatDuration(span.duration_ms)}</span>
                            <span class="badge ${span.status}">${span.status}</span>
                        </div>
                    </div>
                    <div class="span-content" id="span-${idx}">
                        ${span.system_prompt ? `
                        <div class="span-section">
                            <div class="span-section-title">System Prompt</div>
                            <div class="span-section-content">${escapeHtml(span.system_prompt)}</div>
                        </div>
                        ` : ''}

                        ${span.input_messages ? `
                        <div class="span-section">
                            <div class="span-section-title">Input Messages</div>
                            <div class="span-section-content">${escapeHtml(JSON.stringify(span.input_messages, null, 2))}</div>
                        </div>
                        ` : ''}

                        ${span.output_content ? `
                        <div class="span-section">
                            <div class="span-section-title">Output</div>
                            <div class="span-section-content">${escapeHtml(span.output_content)}</div>
                        </div>
                        ` : ''}

                        ${span.tool_input ? `
                        <div class="span-section">
                            <div class="span-section-title">Tool Input</div>
                            <div class="span-section-content">${escapeHtml(JSON.stringify(span.tool_input, null, 2))}</div>
                        </div>
                        ` : ''}

                        ${span.tool_output ? `
                        <div class="span-section">
                            <div class="span-section-title">Tool Output</div>
                            <div class="span-section-content">${escapeHtml(span.tool_output)}</div>
                        </div>
                        ` : ''}

                        ${span.error ? `
                        <div class="span-section">
                            <div class="span-section-title">Error</div>
                            <div class="span-section-content" style="color: #f87171;">${escapeHtml(span.error)}</div>
                        </div>
                        ` : ''}
                    </div>
                </div>
            `;
        }

        function toggleSpan(idx) {
            const content = document.getElementById(`span-${idx}`);
            content.classList.toggle('expanded');
        }

        function formatDuration(ms) {
            if (!ms) return '-';
            if (ms < 1000) return `${Math.round(ms)}ms`;
            return `${(ms / 1000).toFixed(1)}s`;
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function parseSearchResults(text) {
            // Try to parse the output as search results
            // Format: "1. Seller Name (Rating: X/5)\\n   Price: X,XXX ILS\\n   URL: https://..."
            const results = [];

            // Split by numbered items (1. 2. 3. etc)
            const itemPattern = /(?:^|\\n)(\\d+)\\.\\s+([^\\n]+)/g;
            let match;

            while ((match = itemPattern.exec(text)) !== null) {
                const index = match[1];
                const sellerLine = match[2];

                // Extract seller name and rating from the seller line
                // Format: "Seller Name (Rating: 4.5/5)"
                const ratingMatch = sellerLine.match(/(.+?)\\s*\\(Rating:\\s*([\\d.]+)\\/5\\)/);
                let seller, rating;
                if (ratingMatch) {
                    seller = ratingMatch[1].trim();
                    rating = ratingMatch[2];
                } else {
                    seller = sellerLine.trim();
                    rating = null;
                }

                // Get the text after this match until the next numbered item or end
                const startPos = match.index + match[0].length;
                const nextMatch = text.slice(startPos).match(/\\n\\d+\\./);
                const endPos = nextMatch ? startPos + nextMatch.index : text.length;
                const detailsText = text.slice(startPos, endPos);

                // Extract price
                const priceMatch = detailsText.match(/Price:\\s*([\\d,]+)/i);
                const price = priceMatch ? priceMatch[1].replace(/,/g, '') : null;

                // Extract URL
                const urlMatch = detailsText.match(/URL:\\s*(https?:\\/\\/[^\\s\\n]+)/i);
                const url = urlMatch ? urlMatch[1] : null;

                // Extract phone/contact
                const phoneMatch = detailsText.match(/(?:Contact|Phone|WhatsApp):\\s*(\\+?[\\d\\s-]+)/i);
                const phone = phoneMatch ? phoneMatch[1].replace(/[\\s-]/g, '') : null;

                results.push({
                    index,
                    seller,
                    rating,
                    price,
                    currency: 'ILS',
                    url,
                    phone
                });
            }

            return results;
        }

        function parseBundleResults(text) {
            // Parse "=== BUNDLE OPPORTUNITIES ===" section
            const bundleMatch = text.match(/=== BUNDLE OPPORTUNITIES \\((\\d+) stores\\) ===/);
            if (!bundleMatch) return [];

            // Stop at the first per-product section (=== ProductName ===) or end
            const bundleSection = text.match(/=== BUNDLE OPPORTUNITIES.*?(?=\\n\\n=== [^B]|$)/s);
            if (!bundleSection) return [];

            const bundles = [];
            // Parse each store entry: "1. Store Name (Rating: X/5)"
            const storePattern = /(\\d+)\\.\\s+([^\\n]+?)(?:\\s+\\(Rating:\\s*([\\d.]+)\\/5\\))?\\n([\\s\\S]*?)(?=\\n\\d+\\.|\\n===|$)/g;
            let match;

            while ((match = storePattern.exec(bundleSection[0])) !== null) {
                const index = match[1];
                const storeName = match[2].trim();
                const rating = match[3] || null;
                const details = match[4];

                // Extract product count: "Offers X/Y products:"
                const offersMatch = details.match(/Offers\\s+(\\d+)\\/(\\d+)\\s+products/);
                const productCount = offersMatch ? parseInt(offersMatch[1]) : 0;
                const totalProducts = offersMatch ? parseInt(offersMatch[2]) : 0;

                // Extract product lines: "- Query: X,XXX ILS | URL"
                const productLines = [];
                const productPattern = /^\\s+-\\s+([^:]+):\\s+([\\d,]+)\\s+(\\w+)(?:\\s*\\|\\s*(https?:\\/\\/[^\\s]+))?/gm;
                let productMatch;
                while ((productMatch = productPattern.exec(details)) !== null) {
                    productLines.push({
                        name: productMatch[1].trim(),
                        price: productMatch[2].replace(/,/g, ''),
                        currency: productMatch[3],
                        url: productMatch[4] || null
                    });
                }

                // Extract total price
                const totalMatch = details.match(/Total:\\s+([\\d,]+)/);
                const totalPrice = totalMatch ? totalMatch[1].replace(/,/g, '') : null;

                // Extract contact
                const contactMatch = details.match(/Contact:\\s*(\\+?[\\d\\s-]+)/);
                const contact = contactMatch ? contactMatch[1].replace(/[\\s-]/g, '') : null;

                bundles.push({
                    index,
                    storeName,
                    rating,
                    productCount,
                    totalProducts,
                    products: productLines,
                    totalPrice,
                    contact
                });
            }

            return bundles;
        }

        function parsePerProductSections(text) {
            // Parse per-product sections: === ProductName ===
            const sections = [];
            // Match each product section header
            const sectionPattern = /\\n=== ([^=\\n]+) ===\\n/g;
            let match;
            const matches = [];

            while ((match = sectionPattern.exec(text)) !== null) {
                // Skip BUNDLE OPPORTUNITIES section
                if (match[1].includes('BUNDLE OPPORTUNITIES')) continue;
                matches.push({ name: match[1].trim(), startIndex: match.index + match[0].length });
            }

            // Extract content for each section
            for (let i = 0; i < matches.length; i++) {
                const startIdx = matches[i].startIndex;
                const endIdx = i + 1 < matches.length ? matches[i + 1].startIndex - matches[i + 1].name.length - 8 : text.length;
                const sectionText = text.slice(startIdx, endIdx);

                // Parse results within this section
                const results = parseSearchResults(sectionText);

                sections.push({
                    productName: matches[i].name,
                    results: results
                });
            }

            return sections;
        }

        function renderBundleTable(bundles) {
            if (bundles.length === 0) return '';

            const totalProducts = bundles.length > 0 ? bundles[0].totalProducts : 0;

            return '<div class="bundle-section">' +
                '<h4>Bundle Opportunities - Stores with Multiple Products</h4>' +
                '<table class="results-table bundle-table">' +
                '<thead><tr>' +
                '<th>#</th><th>Store</th><th>Rating</th><th>Products</th><th>Total Price</th><th>Contact</th>' +
                '</tr></thead>' +
                '<tbody>' + bundles.map(b => {
                    const ratingHtml = b.rating ? '<span class="rating-badge">★ ' + b.rating + '</span>' : '-';
                    const productsHtml = '<div class="bundle-products">' +
                        b.products.map(p => {
                            const priceText = Number(p.price).toLocaleString() + ' ' + p.currency;
                            const priceLink = p.url ? '<a href="' + p.url + '" target="_blank" class="price-link">' + priceText + '</a>' : priceText;
                            return p.name + ': ' + priceLink;
                        }).join('<br>') +
                        '</div><div class="negotiation-tip">Ask for bundle discount</div>';
                    const totalHtml = '<span class="bundle-total">' + Number(b.totalPrice).toLocaleString() + ' ILS</span>' +
                        '<br><span style="font-size: 11px; color: #94a3b8;">' + b.productCount + '/' + b.totalProducts + ' products</span>';
                    const phoneNum = b.contact ? b.contact.replace(/^\\+/, '') : '';
                    const contactHtml = b.contact ? '<a href="https://wa.me/' + phoneNum + '" target="_blank" class="whatsapp-btn">💬 WhatsApp</a>' : '-';

                    return '<tr>' +
                        '<td>' + b.index + '</td>' +
                        '<td>' + escapeHtml(b.storeName) + '</td>' +
                        '<td>' + ratingHtml + '</td>' +
                        '<td>' + productsHtml + '</td>' +
                        '<td>' + totalHtml + '</td>' +
                        '<td>' + contactHtml + '</td>' +
                        '</tr>';
                }).join('') + '</tbody>' +
                '</table></div>';
        }

        function renderSearchResultsTable(span) {
            // Check if this is a multi-product search with bundle results
            if (span.tool_name === 'search_multiple_products') {
                const bundles = parseBundleResults(span.tool_output);
                const productSections = parsePerProductSections(span.tool_output);

                let html = '';

                // Render bundle opportunities first
                if (bundles.length > 0) {
                    html += renderBundleTable(bundles);
                }

                // Render separate table for each product
                for (let idx = 0; idx < productSections.length; idx++) {
                    const section = productSections[idx];
                    if (section.results.length === 0) continue;

                    html += '<div class="span-section">' +
                        '<div class="span-section-title">Results for: ' + escapeHtml(section.productName) + '</div>' +
                        '<div class="bulk-actions" id="bulkActions-' + idx + '">' +
                        '<span><span id="selectedCount-' + idx + '">0</span> selected</span>' +
                        '<button class="negotiate-btn" onclick="openDraftModal()">Generate Drafts</button>' +
                        '</div>' +
                        '<table class="results-table">' +
                        '<thead><tr>' +
                        '<th>#</th><th>Seller</th><th>Rating</th><th>Price</th><th>Link</th><th>Contact</th>' +
                        '</tr></thead>' +
                        '<tbody>' + section.results.map(r => renderResultRow(r, section.productName)).join('') + '</tbody>' +
                        '</table></div>';
                }

                return html || '';
            }

            // Single product search - original logic
            // Get product query from tool_input
            let productQuery = 'Search Results';
            if (span.tool_input) {
                const input = typeof span.tool_input === 'string' ? JSON.parse(span.tool_input) : span.tool_input;
                if (input.query) {
                    productQuery = input.query;
                }
            }

            const results = parseSearchResults(span.tool_output);
            if (results.length === 0) return '';

            return '<div class="span-section">' +
                '<div class="span-section-title">Results for: ' + escapeHtml(productQuery) + '</div>' +
                '<div class="bulk-actions" id="bulkActions-single">' +
                '<span><span id="selectedCount-single">0</span> selected</span>' +
                '<button class="negotiate-btn" onclick="openDraftModal()">Generate Drafts</button>' +
                '</div>' +
                '<table class="results-table">' +
                '<thead><tr>' +
                '<th>#</th><th>Seller</th><th>Rating</th><th>Price</th><th>Link</th><th>Contact</th>' +
                '</tr></thead>' +
                '<tbody>' + results.map(r => renderResultRow(r, productQuery)).join('') + '</tbody>' +
                '</table></div>';
        }

        function renderResultRow(r, productQuery) {
            const ratingHtml = r.rating ? '<span class="rating-badge">★ ' + r.rating + '</span>' : '-';
            const priceHtml = r.price ? '<span class="price-value">' + Number(r.price).toLocaleString() + ' ' + r.currency + '</span>' : '-';
            const linkHtml = r.url ? '<a href="' + escapeHtml(r.url) + '" target="_blank" rel="noopener">View →</a>' : '-';

            let contactHtml = '-';
            if (r.phone) {
                const phoneNum = r.phone.replace(/^\\+/, '');
                const sellerData = JSON.stringify({
                    seller_name: r.seller,
                    phone_number: r.phone,
                    product_name: productQuery || 'Product',
                    listed_price: Number(r.price) || 0
                }).replace(/"/g, '&quot;');

                contactHtml = '<div style="display: flex; align-items: center; gap: 8px;">' +
                    '<input type="checkbox" class="seller-checkbox" ' +
                    'data-seller="' + sellerData + '" ' +
                    'onchange="toggleSellerSelection(this)">' +
                    '<a href="https://wa.me/' + phoneNum + '" target="_blank" class="whatsapp-btn">💬</a>' +
                    '</div>';
            }

            return '<tr>' +
                '<td>' + r.index + '</td>' +
                '<td>' + escapeHtml(r.seller) + '</td>' +
                '<td>' + ratingHtml + '</td>' +
                '<td>' + priceHtml + '</td>' +
                '<td>' + linkHtml + '</td>' +
                '<td>' + contactHtml + '</td>' +
                '</tr>';
        }

        function renderFinalOutput(text) {
            const results = parseSearchResults(text);

            if (results.length > 0) {
                // Render as table
                return `
                    <table class="results-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Seller</th>
                                <th>Rating</th>
                                <th>Price</th>
                                <th>Link</th>
                                <th>Contact</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${results.map(r => `
                                <tr>
                                    <td>${r.index}</td>
                                    <td>${escapeHtml(r.seller)}</td>
                                    <td>${r.rating ? `<span class="rating-badge">★ ${r.rating}</span>` : '-'}</td>
                                    <td><span class="price-value">${r.price ? Number(r.price).toLocaleString() : '-'} ${r.currency}</span></td>
                                    <td>${r.url ? `<a href="${escapeHtml(r.url)}" target="_blank" rel="noopener">View →</a>` : '-'}</td>
                                    <td>${r.phone ? `<a href="https://wa.me/${r.phone.replace(/^\\+/, '')}" target="_blank" class="whatsapp-btn">💬 WhatsApp</a>` : '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                    <details style="margin-top: 12px;">
                        <summary style="cursor: pointer; color: #94a3b8; font-size: 12px;">Show raw output</summary>
                        <div class="span-section-content" style="margin-top: 8px;">${escapeHtml(text)}</div>
                    </details>
                `;
            }

            // Fallback to plain text
            return `<div class="span-section-content">${escapeHtml(text)}</div>`;
        }

        // Initial load
        connect();
        setInterval(loadTraces, 5000); // Refresh every 5 seconds as backup

        async function runQuery() {
            const input = document.getElementById('queryInput');
            const btn = document.getElementById('searchBtn');
            const query = input.value.trim();

            if (!query) return;

            // Disable UI while running
            btn.disabled = true;
            btn.textContent = 'Running...';
            input.disabled = true;

            try {
                const response = await fetch('/agent/run', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ query: query, agent: 'research' })
                });

                if (response.ok) {
                    const data = await response.json();
                    // Clear input and select the new trace
                    input.value = '';
                    selectedTraceId = data.trace_id;
                    loadTraces();
                    loadTraceDetail(data.trace_id);
                } else {
                    alert('Failed to start query: ' + response.statusText);
                }
            } catch (error) {
                console.error('Failed to run query:', error);
                alert('Failed to run query: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.textContent = 'Search';
                input.disabled = false;
            }
        }
        // Draft mode state
        let selectedSellers = [];
        let currentDrafts = [];

        function toggleSellerSelection(checkbox) {
            const sellerData = JSON.parse(checkbox.dataset.seller);

            if (checkbox.checked) {
                selectedSellers.push(sellerData);
            } else {
                selectedSellers = selectedSellers.filter(
                    s => s.phone_number !== sellerData.phone_number
                );
            }

            updateBulkActionsVisibility();
        }

        function updateBulkActionsVisibility() {
            // Show/hide bulk actions based on selection
            const bulkBars = document.querySelectorAll('.bulk-actions');
            bulkBars.forEach(bar => {
                if (selectedSellers.length > 0) {
                    bar.style.display = 'flex';
                    const countSpan = bar.querySelector('[id^="selectedCount"]');
                    if (countSpan) countSpan.textContent = selectedSellers.length;
                } else {
                    bar.style.display = 'none';
                }
            });
        }

        async function openDraftModal() {
            if (selectedSellers.length === 0) {
                alert('Please select at least one seller with a phone number');
                return;
            }

            document.getElementById('draftModal').style.display = 'flex';
            document.getElementById('draftList').innerHTML = '<p style="color: #94a3b8;">Generating drafts...</p>';

            try {
                const response = await fetch('/agent/generate-drafts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sellers: selectedSellers, language: 'he' })
                });

                const data = await response.json();
                currentDrafts = data.drafts;
                renderDrafts();
            } catch (error) {
                document.getElementById('draftList').innerHTML =
                    '<p style="color: #f87171;">Failed to generate drafts: ' + error.message + '</p>';
            }
        }

        function renderDrafts() {
            const container = document.getElementById('draftList');

            container.innerHTML = currentDrafts.map((draft, idx) => `
                <div class="draft-card" data-index="${idx}">
                    <div class="draft-header">
                        <input type="checkbox" checked class="seller-checkbox">
                        <strong>${escapeHtml(draft.seller_name)}</strong>
                    </div>
                    <p class="draft-product">Product: ${escapeHtml(draft.product_name)}</p>

                    <div class="draft-field">
                        <label>Phone Number:</label>
                        <input type="text"
                               class="draft-phone-input"
                               value="${escapeHtml(draft.phone_number)}"
                               onchange="updateDraftPhone(${idx}, this.value)">
                    </div>

                    <div class="draft-field">
                        <label>Message:</label>
                        <textarea class="draft-textarea"
                                  onchange="updateDraftMessage(${idx}, this.value)"
                        >${escapeHtml(draft.message)}</textarea>
                    </div>

                    <div class="draft-actions">
                        <button class="draft-send-btn" onclick="sendDraft(${idx})">
                            Send via WhatsApp
                        </button>
                        <button class="draft-copy-btn" onclick="copyWaLink(${idx})">
                            Copy Link
                        </button>
                    </div>
                </div>
            `).join('');
        }

        function updateDraftMessage(index, message) {
            currentDrafts[index].message = message;
            regenerateWaLink(index);
        }

        function updateDraftPhone(index, phone) {
            currentDrafts[index].phone_number = phone;
            regenerateWaLink(index);
        }

        function regenerateWaLink(index) {
            const draft = currentDrafts[index];
            const phoneClean = draft.phone_number.replace(/[^0-9]/g, '');
            draft.wa_link = 'https://wa.me/' + phoneClean + '?text=' + encodeURIComponent(draft.message);
        }

        function sendDraft(index) {
            const draft = currentDrafts[index];
            window.open(draft.wa_link, '_blank');

            // Visual feedback
            const card = document.querySelector('.draft-card[data-index="' + index + '"]');
            card.classList.add('sent');
            card.querySelector('.draft-send-btn').textContent = 'Opened';
        }

        function sendAllDrafts() {
            const cards = document.querySelectorAll('.draft-card');
            const selectedIndices = [];

            cards.forEach((card, idx) => {
                const checkbox = card.querySelector('.seller-checkbox');
                if (checkbox && checkbox.checked && !card.classList.contains('sent')) {
                    selectedIndices.push(idx);
                }
            });

            if (selectedIndices.length === 0) {
                alert('No drafts selected');
                return;
            }

            // Open with slight delay to avoid popup blocking
            selectedIndices.forEach((idx, i) => {
                setTimeout(() => sendDraft(idx), i * 500);
            });
        }

        function copyWaLink(index) {
            const draft = currentDrafts[index];
            navigator.clipboard.writeText(draft.wa_link).then(() => {
                const btn = document.querySelector('.draft-card[data-index="' + index + '"] .draft-copy-btn');
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = 'Copy Link'; }, 2000);
            });
        }

        function closeDraftModal() {
            document.getElementById('draftModal').style.display = 'none';
            currentDrafts = [];
        }
    </script>

    <!-- Draft Modal -->
    <div class="modal-overlay" id="draftModal">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Review Negotiation Messages</h2>
                <button class="modal-close" onclick="closeDraftModal()">&times;</button>
            </div>
            <div class="modal-body" id="draftList">
                <p style="color: #94a3b8;">Loading...</p>
            </div>
            <div class="modal-footer">
                <button class="negotiate-btn" onclick="sendAllDrafts()">Send All via WhatsApp</button>
                <button class="draft-copy-btn" onclick="closeDraftModal()">Cancel</button>
            </div>
        </div>
    </div>
</body>
</html>
"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Serve the observability dashboard."""
    return DASHBOARD_HTML
