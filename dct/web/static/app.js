/**
 * DCT-Agent Web UI Client Logic
 * Handles real-time SSE streaming, tool visualizer, server/model management,
 * slash commands, task boards, and interactive agent communication.
 */

document.addEventListener('DOMContentLoaded', () => {
  // DOM Elements
  const serverSelect = document.getElementById('serverSelect');
  const modelSelect = document.getElementById('modelSelect');
  const serverStatusPill = document.getElementById('serverStatusPill');
  const agentModeBtn = document.getElementById('agentModeBtn');
  const planModeBtn = document.getElementById('planModeBtn');
  const planModeBanner = document.getElementById('planModeBanner');
  const exitPlanModeBtn = document.getElementById('exitPlanModeBtn');

  const taskList = document.getElementById('taskList');
  const taskCountBadge = document.getElementById('taskCountBadge');
  const serverList = document.getElementById('serverList');
  const probeAllBtn = document.getElementById('probeAllBtn');
  const openAddServerModalBtn = document.getElementById('openAddServerModalBtn');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const newSessionBtn = document.getElementById('newSessionBtn');

  const chatFeed = document.getElementById('chatFeed');
  const welcomeCard = document.getElementById('welcomeCard');
  const composerForm = document.getElementById('composerForm');
  const messageInput = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const stopBtn = document.getElementById('stopBtn');
  const tokenCounter = document.getElementById('tokenCounter');

  const slashAutocomplete = document.getElementById('slashAutocomplete');
  const autocompleteItems = document.getElementById('autocompleteItems');

  const addServerModal = document.getElementById('addServerModal');
  const closeAddServerModalBtn = document.getElementById('closeAddServerModalBtn');
  const cancelAddServerBtn = document.getElementById('cancelAddServerBtn');
  const addServerForm = document.getElementById('addServerForm');

  const askUserModal = document.getElementById('askUserModal');
  const askUserQuestion = document.getElementById('askUserQuestion');
  const askUserChoices = document.getElementById('askUserChoices');
  const askUserCustomInput = document.getElementById('askUserCustomInput');
  const submitAskUserBtn = document.getElementById('submitAskUserBtn');

  // Application State
  let state = {
    servers: [],
    activeServer: null,
    activeModel: '',
    agentMode: true,
    sessionMode: 'execute',
    isStreaming: false,
    abortController: null,
    currentAssistantRow: null,
    currentAssistantTextEl: null,
    currentRawResponse: '',
  };

  const SLASH_COMMANDS = [
    { cmd: '/servers', desc: 'List all registered servers and latencies' },
    { cmd: '/probe', desc: 'Probe and test all servers in parallel' },
    { cmd: '/models', desc: 'List available models on active server' },
    { cmd: '/plan', desc: 'Toggle safe Plan Mode for strategic thinking' },
    { cmd: '/agent', desc: 'Toggle autonomous Agent Mode ON/OFF' },
    { cmd: '/tasks', desc: 'Show active structured task board' },
    { cmd: '/clear', desc: 'Clear conversation history and reset tasks' },
    { cmd: '/help', desc: 'Display full command and tool help' },
  ];

  // ── Initialization ────────────────────────────────────────────────────────
  async function init() {
    setupEventListeners();
    await fetchStatus();
    await fetchServers();
    await fetchTasks();
    await fetchHistory();
  }

  // ── Event Listeners ───────────────────────────────────────────────────────
  function setupEventListeners() {
    // Form Submit
    composerForm.addEventListener('submit', (e) => {
      e.preventDefault();
      sendMessage();
    });

    // Auto-resize textarea & keyboard shortcuts
    messageInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    });

    messageInput.addEventListener('input', () => {
      messageInput.style.height = 'auto';
      messageInput.style.height = Math.min(messageInput.scrollHeight, 180) + 'px';
      handleSlashAutocomplete();
    });

    // Stop Streaming
    stopBtn.addEventListener('click', () => {
      if (state.abortController) {
        state.abortController.abort();
        setStreaming(false);
      }
    });

    // Dropdowns
    serverSelect.addEventListener('change', async () => {
      const alias = serverSelect.value;
      await apiPost('/api/select', { alias });
      await fetchStatus();
    });

    modelSelect.addEventListener('change', async () => {
      const model = modelSelect.value;
      await apiPost('/api/select', { model });
      await fetchStatus();
    });

    // Mode Toggles
    agentModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_agent', { enabled: !state.agentMode });
      state.agentMode = res.agent_mode;
      updateModeUI();
    });

    planModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_plan', {});
      state.sessionMode = res.session_mode;
      updateModeUI();
    });

    exitPlanModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_plan', { mode: 'execute' });
      state.sessionMode = res.session_mode;
      updateModeUI();
    });

    // Sidebar buttons
    probeAllBtn.addEventListener('click', async () => {
      probeAllBtn.style.transform = 'rotate(360deg)';
      await apiPost('/api/servers/probe', {});
      probeAllBtn.style.transform = 'none';
      await fetchServers();
      await fetchStatus();
    });

    clearChatBtn.addEventListener('click', clearConversation);
    newSessionBtn.addEventListener('click', clearConversation);

    // Quick Prompts
    document.querySelectorAll('.quick-prompt-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const p = btn.getAttribute('data-prompt');
        if (p) {
          messageInput.value = p;
          sendMessage();
        }
      });
    });

    // Modals
    openAddServerModalBtn.addEventListener('click', () => {
      addServerModal.style.display = 'flex';
    });

    closeAddServerModalBtn.addEventListener('click', () => {
      addServerModal.style.display = 'none';
    });

    cancelAddServerBtn.addEventListener('click', () => {
      addServerModal.style.display = 'none';
    });

    addServerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const host = document.getElementById('serverHostInput').value;
      const port = parseInt(document.getElementById('serverPortInput').value, 10);
      const alias = document.getElementById('serverAliasInput').value;
      const apiKey = document.getElementById('serverApiKeyInput').value;

      const res = await apiPost('/api/servers/add', { host, port, alias, api_key: apiKey });
      if (res.ok) {
        addServerModal.style.display = 'none';
        addServerForm.reset();
        await fetchServers();
        await fetchStatus();
      } else {
        alert(res.error || 'Failed to add server');
      }
    });

    submitAskUserBtn.addEventListener('click', submitAskUser);
  }

  // ── Slash Command Autocompletion ──────────────────────────────────────────
  function handleSlashAutocomplete() {
    const val = messageInput.value;
    if (val.startsWith('/')) {
      const match = val.toLowerCase();
      const filtered = SLASH_COMMANDS.filter((c) => c.cmd.toLowerCase().startsWith(match));
      if (filtered.length > 0) {
        autocompleteItems.innerHTML = '';
        filtered.forEach((item) => {
          const el = document.createElement('div');
          el.className = 'autocomplete-item';
          el.innerHTML = `<strong>${escapeHtml(item.cmd)}</strong> <span>${escapeHtml(item.desc)}</span>`;
          el.addEventListener('click', () => {
            messageInput.value = item.cmd;
            slashAutocomplete.style.display = 'none';
            messageInput.focus();
          });
          autocompleteItems.appendChild(el);
        });
        slashAutocomplete.style.display = 'block';
        return;
      }
    }
    slashAutocomplete.style.display = 'none';
  }

  // ── Data Fetching ─────────────────────────────────────────────────────────
  async function fetchStatus() {
    try {
      const data = await apiGet('/api/status');
      state.agentMode = data.agent_mode;
      state.sessionMode = data.session_mode;
      state.activeModel = data.active_model;

      tokenCounter.textContent = `${data.user_turns} turns · ~${data.token_estimate} tok`;

      // Status Pill
      if (data.active_server && data.active_server.status === 'online') {
        serverStatusPill.innerHTML = `<span class="status-dot"></span><span class="status-label">${escapeHtml(data.active_server.alias)} (${data.active_server.latency_ms}ms)</span>`;
      } else {
        serverStatusPill.innerHTML = `<span class="status-dot offline"></span><span class="status-label">Offline / No Server</span>`;
      }

      updateModeUI();
      renderTasks(data.tasks || []);
    } catch (err) {
      console.error('fetchStatus failed', err);
    }
  }

  async function fetchServers() {
    try {
      const data = await apiGet('/api/servers');
      state.servers = data.servers || [];

      // Populate Server Dropdown
      serverSelect.innerHTML = '';
      serverList.innerHTML = '';

      state.servers.forEach((s) => {
        const opt = document.createElement('option');
        opt.value = s.alias;
        opt.textContent = `${s.alias} (${s.host}:${s.port})`;
        if (s.is_active) opt.selected = true;
        serverSelect.appendChild(opt);

        // Sidebar Server List
        const srvCard = document.createElement('div');
        srvCard.className = `server-item ${s.is_active ? 'active' : ''}`;
        srvCard.innerHTML = `
          <div>
            <div class="server-name">${escapeHtml(s.alias)}</div>
            <div class="server-meta">${escapeHtml(s.host)}:${s.port} · ${s.models.length} models</div>
          </div>
          <div class="server-latency">${s.status === 'online' ? `${s.latency_ms}ms` : 'offline'}</div>
        `;
        srvCard.addEventListener('click', async () => {
          await apiPost('/api/select', { alias: s.alias });
          await fetchServers();
          await fetchStatus();
        });
        serverList.appendChild(srvCard);
      });

      // Populate Models Dropdown for active server
      const active = state.servers.find((s) => s.is_active) || state.servers[0];
      modelSelect.innerHTML = '';
      if (active && active.models) {
        active.models.forEach((m) => {
          const mOpt = document.createElement('option');
          mOpt.value = m;
          mOpt.textContent = m;
          if (m === state.activeModel) mOpt.selected = true;
          modelSelect.appendChild(mOpt);
        });
      }
    } catch (err) {
      console.error('fetchServers failed', err);
    }
  }

  async function fetchTasks() {
    try {
      const data = await apiGet('/api/tasks');
      renderTasks(data.tasks || []);
    } catch (err) {
      console.error('fetchTasks failed', err);
    }
  }

  async function fetchHistory() {
    try {
      const data = await apiGet('/api/history');
      if (data.history && data.history.length > 0) {
        if (welcomeCard) welcomeCard.style.display = 'none';
        data.history.forEach((m) => {
          appendMessage(m.role, m.content);
        });
      }
    } catch (err) {
      console.error('fetchHistory failed', err);
    }
  }

  function renderTasks(tasks) {
    taskCountBadge.textContent = `${tasks.length} tasks`;
    if (!tasks || tasks.length === 0) {
      taskList.innerHTML = `<div class="empty-state">No active tasks. Start a request to see the agent decompose goals!</div>`;
      return;
    }

    taskList.innerHTML = '';
    tasks.forEach((t) => {
      const item = document.createElement('div');
      item.className = `task-item ${t.status}`;
      const icon = t.status === 'completed' ? '✅' : t.status === 'in_progress' ? '⚡' : '⏳';
      item.innerHTML = `
        <span class="task-status-icon">${icon}</span>
        <div class="task-details">
          <div class="task-subject">${escapeHtml(t.subject)}</div>
          ${t.description ? `<div class="task-desc">${escapeHtml(t.description)}</div>` : ''}
        </div>
      `;
      taskList.appendChild(item);
    });
  }

  function updateModeUI() {
    if (state.agentMode) {
      agentModeBtn.classList.add('active');
    } else {
      agentModeBtn.classList.remove('active');
    }

    if (state.sessionMode === 'plan') {
      planModeBtn.classList.add('plan-active');
      planModeBanner.style.display = 'flex';
    } else {
      planModeBtn.classList.remove('plan-active');
      planModeBanner.style.display = 'none';
    }
  }

  // ── Send Message & SSE Streaming ──────────────────────────────────────────
  async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || state.isStreaming) return;

    if (welcomeCard) welcomeCard.style.display = 'none';

    // Handle instant slash commands locally if needed
    if (text === '/clear') {
      messageInput.value = '';
      clearConversation();
      return;
    }

    // Append user message to UI
    appendMessage('user', text);
    messageInput.value = '';
    messageInput.style.height = 'auto';
    slashAutocomplete.style.display = 'none';

    setStreaming(true);

    // Prepare Assistant Stream Bubble
    state.currentAssistantRow = createMessageRow('assistant');
    state.currentAssistantTextEl = state.currentAssistantRow.querySelector('.message-content');
    state.currentRawResponse = '';
    chatFeed.appendChild(state.currentAssistantRow);
    scrollToBottom();

    state.abortController = new AbortController();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
        signal: state.abortController.signal,
      });

      if (!response.ok) {
        const errJson = await response.json().catch(() => ({}));
        throw new Error(errJson.error || `HTTP error ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep last incomplete chunk

        let currentEvent = null;
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.substring(6).trim();
          } else if (line.startsWith('data:')) {
            const dataStr = line.substring(5).trim();
            if (currentEvent && dataStr) {
              handleSSEEvent(currentEvent, dataStr);
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        appendSystemError(err.message);
      }
    } finally {
      setStreaming(false);
      await fetchStatus();
    }
  }

  function handleSSEEvent(eventType, dataStr) {
    let data;
    try {
      data = JSON.parse(dataStr);
    } catch (e) {
      data = dataStr;
    }

    switch (eventType) {
      case 'text_chunk':
        state.currentRawResponse += data.chunk;
        state.currentAssistantTextEl.innerHTML = renderMarkdown(state.currentRawResponse);
        scrollToBottom();
        break;

      case 'tool_start':
        appendToolStartCard(data.tool, data.args);
        scrollToBottom();
        break;

      case 'tool_result':
        updateToolResultCard(data.tool, data.result);
        if (data.tasks) renderTasks(data.tasks);
        scrollToBottom();
        break;

      case 'task_update':
        if (data.tasks) renderTasks(data.tasks);
        break;

      case 'done':
        if (data.final && !state.currentRawResponse) {
          state.currentAssistantTextEl.innerHTML = renderMarkdown(data.final);
        }
        break;

      case 'error':
        appendSystemError(data.error);
        break;
    }
  }

  function setStreaming(streaming) {
    state.isStreaming = streaming;
    if (streaming) {
      sendBtn.style.display = 'none';
      stopBtn.style.display = 'inline-flex';
      messageInput.disabled = true;
    } else {
      sendBtn.style.display = 'inline-flex';
      stopBtn.style.display = 'none';
      messageInput.disabled = false;
      messageInput.focus();
    }
  }

  // ── DOM Helpers ───────────────────────────────────────────────────────────
  function appendMessage(role, text) {
    const row = createMessageRow(role);
    row.querySelector('.message-content').innerHTML = renderMarkdown(text);
    chatFeed.appendChild(row);
    scrollToBottom();
  }

  function createMessageRow(role) {
    const row = document.createElement('div');
    row.className = `message-row ${role}`;
    const avatar = role === 'user' ? '👤' : '⚡';
    const label = role === 'user' ? 'You' : 'DCT-Agent';
    row.innerHTML = `
      <div class="message-header">
        <span class="message-avatar">${avatar}</span>
        <span class="message-author">${label}</span>
      </div>
      <div class="message-bubble">
        <div class="message-content"></div>
      </div>
    `;
    return row;
  }

  function appendToolStartCard(toolName, argsRaw) {
    const bubble = state.currentAssistantRow.querySelector('.message-bubble');
    const card = document.createElement('div');
    card.className = 'tool-card';
    card.id = `tool-${Date.now()}`;
    card.innerHTML = `
      <div class="tool-header">
        <div class="tool-badge">
          <span>⚡ Running tool:</span>
          <code>${escapeHtml(toolName)}</code>
        </div>
        <span class="tool-toggle-icon">▼</span>
      </div>
      <div class="tool-body">${escapeHtml(argsRaw || '(Executing...)')}</div>
    `;

    card.querySelector('.tool-header').addEventListener('click', () => {
      const body = card.querySelector('.tool-body');
      body.style.display = body.style.display === 'none' ? 'block' : 'none';
    });

    bubble.appendChild(card);
  }

  function updateToolResultCard(toolName, resultText) {
    const bubble = state.currentAssistantRow.querySelector('.message-bubble');
    const cards = bubble.querySelectorAll('.tool-card');
    if (cards.length > 0) {
      const lastCard = cards[cards.length - 1];
      const badge = lastCard.querySelector('.tool-badge');
      badge.classList.add('completed');
      badge.innerHTML = `<span>✓ Completed:</span> <code>${escapeHtml(toolName)}</code>`;

      const body = lastCard.querySelector('.tool-body');
      body.innerHTML = escapeHtml(resultText);
    }
  }

  function appendSystemError(errMsg) {
    const row = document.createElement('div');
    row.className = 'message-row assistant';
    row.innerHTML = `
      <div class="message-bubble" style="border-color: var(--accent-rose); background-color: rgba(244, 63, 94, 0.1);">
        <strong style="color: var(--accent-rose);">Error:</strong> ${escapeHtml(errMsg)}
      </div>
    `;
    chatFeed.appendChild(row);
    scrollToBottom();
  }

  async function clearConversation() {
    await apiPost('/api/clear', {});
    chatFeed.innerHTML = '';
    if (welcomeCard) {
      chatFeed.appendChild(welcomeCard);
      welcomeCard.style.display = 'block';
    }
    await fetchStatus();
    await fetchTasks();
  }

  function scrollToBottom() {
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  // ── Simple Markdown Renderer ──────────────────────────────────────────────
  function renderMarkdown(md) {
    if (!md) return '';
    let html = escapeHtml(md);

    // Code blocks with syntax copy button
    html = html.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `
        <div class="code-container">
          <div class="code-header">
            <span>${lang || 'text'}</span>
            <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-container').querySelector('code').innerText)">Copy</button>
          </div>
          <pre><code>${code.trim()}</code></pre>
        </div>
      `;
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold & Italics
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // Lists
    html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');

    return html;
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ── Interactive Ask User Dialog ───────────────────────────────────────────
  function showAskUserDialog(question, choices) {
    askUserQuestion.textContent = question;
    askUserChoices.innerHTML = '';
    askUserCustomInput.value = '';

    if (choices && choices.length > 0) {
      choices.forEach((c) => {
        const btn = document.createElement('button');
        btn.className = 'ask-choice-btn';
        btn.textContent = c;
        btn.addEventListener('click', async () => {
          await apiPost('/api/ask_user_response', { answer: c });
          askUserModal.style.display = 'none';
        });
        askUserChoices.appendChild(btn);
      });
    }
    askUserModal.style.display = 'flex';
  }

  async function submitAskUser() {
    const val = askUserCustomInput.value.trim();
    if (val) {
      await apiPost('/api/ask_user_response', { answer: val });
      askUserModal.style.display = 'none';
    }
  }

  // ── Fetch Wrappers ────────────────────────────────────────────────────────
  async function apiGet(url) {
    const res = await fetch(url);
    return await res.json();
  }

  async function apiPost(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    return await res.json();
  }

  // Kick off application
  init();
});
