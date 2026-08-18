/**
 * DCT-Agent Web UI Client Logic
 * Mobile-First Autonomous Agent Interface
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

  const sidebar = document.getElementById('sidebar');
  const sidebarToggleBtn = document.getElementById('sidebarToggleBtn');
  const sidebarBackdrop = document.getElementById('sidebarBackdrop');
  const sidebarCloseBtn = document.getElementById('sidebarCloseBtn');
  const openTasksDrawerBtn = document.getElementById('openTasksDrawerBtn');
  const headerNewSessionBtn = document.getElementById('headerNewSessionBtn');

  const taskList = document.getElementById('taskList');
  const taskCountBadge = document.getElementById('taskCountBadge');
  const headerTaskCount = document.getElementById('headerTaskCount');
  const taskIndicatorDot = document.getElementById('taskIndicatorDot');

  const serverList = document.getElementById('serverList');
  const probeAllBtn = document.getElementById('probeAllBtn');
  const openAddServerModalBtn = document.getElementById('openAddServerModalBtn');
  const clearChatBtn = document.getElementById('clearChatBtn');
  const newSessionBtn = document.getElementById('newSessionBtn');
  const sidebarSystemInfo = document.getElementById('sidebarSystemInfo');

  const chatFeed = document.getElementById('chatFeed');
  const welcomeCard = document.getElementById('welcomeCard');
  const scrollToBottomBtn = document.getElementById('scrollToBottomBtn');

  const composerForm = document.getElementById('composerForm');
  const messageInput = document.getElementById('messageInput');
  const sendBtn = document.getElementById('sendBtn');
  const stopBtn = document.getElementById('stopBtn');
  const slashHelperBtn = document.getElementById('slashHelperBtn');
  const tokenCounter = document.getElementById('tokenCounter');
  const composerModePill = document.getElementById('composerModePill');

  const slashAutocomplete = document.getElementById('slashAutocomplete');
  const autocompleteItems = document.getElementById('autocompleteItems');
  const closeAutocompleteBtn = document.getElementById('closeAutocompleteBtn');

  const addServerModal = document.getElementById('addServerModal');
  const closeAddServerModalBtn = document.getElementById('closeAddServerModalBtn');
  const cancelAddServerBtn = document.getElementById('cancelAddServerBtn');
  const addServerForm = document.getElementById('addServerForm');

  const askUserModal = document.getElementById('askUserModal');
  const askUserQuestion = document.getElementById('askUserQuestion');
  const askUserChoices = document.getElementById('askUserChoices');
  const askUserCustomInput = document.getElementById('askUserCustomInput');
  const submitAskUserBtn = document.getElementById('submitAskUserBtn');

  // Discussion Board Modal Elements
  const headerBoardBtn = document.getElementById('headerBoardBtn');
  const openBoardBtn = document.getElementById('openBoardBtn');
  const sidebarOpenBoardBtn = document.getElementById('sidebarOpenBoardBtn');
  const boardModal = document.getElementById('boardModal');
  const closeBoardModalBtn = document.getElementById('closeBoardModalBtn');
  const boardChannelSelect = document.getElementById('boardChannelSelect');
  const refreshBoardBtn = document.getElementById('refreshBoardBtn');
  const clearBoardChannelBtn = document.getElementById('clearBoardChannelBtn');
  const boardMessagesContainer = document.getElementById('boardMessagesContainer');
  const boardPostForm = document.getElementById('boardPostForm');
  const boardPostInput = document.getElementById('boardPostInput');

  const toastContainer = document.getElementById('toastContainer');

  // Skills Elements
  const activeSkillBadge = document.getElementById('activeSkillBadge');
  const skillChipsGrid = document.getElementById('skillChipsGrid');

  // Telegram Elements
  const telegramStatusBadge = document.getElementById('telegramStatusBadge');
  const openTelegramModalBtn = document.getElementById('openTelegramModalBtn');
  const telegramModal = document.getElementById('telegramModal');
  const closeTelegramModalBtn = document.getElementById('closeTelegramModalBtn');
  const cancelTelegramBtn = document.getElementById('cancelTelegramBtn');
  const telegramConfigForm = document.getElementById('telegramConfigForm');
  const telegramTokenInput = document.getElementById('telegramTokenInput');
  const telegramAllowedUsersInput = document.getElementById('telegramAllowedUsersInput');
  const toggleTelegramDaemonBtn = document.getElementById('toggleTelegramDaemonBtn');

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

  // ── Toast Notification Helper ─────────────────────────────────────────────
  function showToast(text, icon = 'ℹ️') {
    if (!toastContainer) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(text)}</span>`;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(-10px)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => toast.remove(), 200);
    }, 2500);
  }

  // ── Initialization ────────────────────────────────────────────────────────
  async function init() {
    setupEventListeners();
    await fetchStatus();
    await fetchServers();
    await fetchSkills();
    await fetchTelegramStatus();
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
      if (e.key === 'Enter' && !e.shiftKey && window.innerWidth > 768) {
        e.preventDefault();
        sendMessage();
      }
    });

    messageInput.addEventListener('input', () => {
      messageInput.style.height = 'auto';
      messageInput.style.height = Math.min(messageInput.scrollHeight, 140) + 'px';
      handleSlashAutocomplete();
    });

    // Slash Helper Button (/)
    if (slashHelperBtn) {
      slashHelperBtn.addEventListener('click', () => {
        if (slashAutocomplete.style.display === 'block') {
          slashAutocomplete.style.display = 'none';
        } else {
          messageInput.value = '/';
          handleSlashAutocomplete();
          messageInput.focus();
        }
      });
    }

    if (closeAutocompleteBtn) {
      closeAutocompleteBtn.addEventListener('click', () => {
        slashAutocomplete.style.display = 'none';
      });
    }

    // Scroll to Bottom Button
    chatFeed.addEventListener('scroll', () => {
      const dist = chatFeed.scrollHeight - chatFeed.scrollTop - chatFeed.clientHeight;
      if (dist > 180) {
        scrollToBottomBtn.style.display = 'flex';
      } else {
        scrollToBottomBtn.style.display = 'none';
      }
    });

    scrollToBottomBtn.addEventListener('click', scrollToBottom);

    // Stop Streaming
    stopBtn.addEventListener('click', () => {
      if (state.abortController) {
        state.abortController.abort();
        setStreaming(false);
        showToast('Generation stopped', '⏹');
      }
    });

    // Dropdowns
    serverSelect.addEventListener('change', async () => {
      const alias = serverSelect.value;
      await apiPost('/api/select', { alias });
      showToast(`Switched to server: ${alias}`, '🌐');
      await fetchStatus();
    });

    modelSelect.addEventListener('change', async () => {
      const model = modelSelect.value;
      await apiPost('/api/select', { model });
      showToast(`Model set to: ${model}`, '⚡');
      await fetchStatus();
    });

    // Mode Toggles
    agentModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_agent', { enabled: !state.agentMode });
      state.agentMode = res.agent_mode;
      updateModeUI();
      showToast(state.agentMode ? 'Autonomous Agent Mode ON' : 'Direct Chat Mode ON', state.agentMode ? '🤖' : '💬');
    });

    planModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_plan', {});
      state.sessionMode = res.session_mode;
      updateModeUI();
      showToast(state.sessionMode === 'plan' ? 'Plan Mode Activated' : 'Plan Mode Deactivated', '📋');
    });

    exitPlanModeBtn.addEventListener('click', async () => {
      const res = await apiPost('/api/toggle_plan', { mode: 'execute' });
      state.sessionMode = res.session_mode;
      updateModeUI();
      showToast('Exited Plan Mode', '🚀');
    });

    // Mobile Sidebar Drawer
    function openMobileSidebar() {
      sidebar.classList.add('open');
      sidebarBackdrop.classList.add('active');
    }

    function closeMobileSidebar() {
      sidebar.classList.remove('open');
      sidebarBackdrop.classList.remove('active');
    }

    if (sidebarToggleBtn) {
      sidebarToggleBtn.addEventListener('click', () => {
        if (sidebar.classList.contains('open')) {
          closeMobileSidebar();
        } else {
          openMobileSidebar();
        }
      });
    }

    if (openTasksDrawerBtn) {
      openTasksDrawerBtn.addEventListener('click', () => {
        openMobileSidebar();
        const tracker = document.querySelector('.task-tracker-section');
        if (tracker) tracker.scrollIntoView({ behavior: 'smooth' });
      });
    }

    if (sidebarCloseBtn) {
      sidebarCloseBtn.addEventListener('click', closeMobileSidebar);
    }

    if (sidebarBackdrop) {
      sidebarBackdrop.addEventListener('click', closeMobileSidebar);
    }

    // Keyboard ESC to close modal/drawer
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        closeMobileSidebar();
        addServerModal.style.display = 'none';
        askUserModal.style.display = 'none';
        slashAutocomplete.style.display = 'none';
      }
    });

    // Sidebar buttons
    probeAllBtn.addEventListener('click', async () => {
      probeAllBtn.style.transform = 'rotate(360deg)';
      showToast('Probing all servers…', '🔄');
      await apiPost('/api/servers/probe', {});
      probeAllBtn.style.transform = 'none';
      await fetchServers();
      await fetchStatus();
      showToast('Probe completed', '✅');
    });

    clearChatBtn.addEventListener('click', () => {
      clearConversation();
      if (window.innerWidth <= 768) closeMobileSidebar();
    });

    newSessionBtn.addEventListener('click', () => {
      clearConversation();
      if (window.innerWidth <= 768) closeMobileSidebar();
    });

    if (headerNewSessionBtn) {
      headerNewSessionBtn.addEventListener('click', clearConversation);
    }

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
      if (window.innerWidth <= 768) closeMobileSidebar();
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

      showToast('Registering server…', '⏳');
      const res = await apiPost('/api/servers/add', { host, port, alias, api_key: apiKey });
      if (res.ok) {
        addServerModal.style.display = 'none';
        addServerForm.reset();
        await fetchServers();
        await fetchStatus();
        showToast(`Server ${alias || host} added successfully!`, '✅');
      } else {
        alert(res.error || 'Failed to add server');
      }
    });

    // Discussion Board Events
    if (headerBoardBtn) {
      headerBoardBtn.addEventListener('click', openBoardModal);
    }
    if (openBoardBtn) {
      openBoardBtn.addEventListener('click', openBoardModal);
    }
    if (sidebarOpenBoardBtn) {
      sidebarOpenBoardBtn.addEventListener('click', () => {
        openBoardModal();
        if (window.innerWidth <= 768) closeMobileSidebar();
      });
    }
    if (closeBoardModalBtn) {
      closeBoardModalBtn.addEventListener('click', () => {
        boardModal.style.display = 'none';
      });
    }
    if (boardChannelSelect) {
      boardChannelSelect.addEventListener('change', () => {
        fetchBoardMessages(boardChannelSelect.value);
      });
    }
    if (refreshBoardBtn) {
      refreshBoardBtn.addEventListener('click', () => {
        fetchBoardChannels();
        fetchBoardMessages(boardChannelSelect.value || 'general');
        showToast('Board refreshed', '🔄');
      });
    }
    if (clearBoardChannelBtn) {
      clearBoardChannelBtn.addEventListener('click', async () => {
        const ch = boardChannelSelect.value || 'general';
        if (confirm(`Clear all messages in #${ch}?`)) {
          await apiPost('/api/board/clear', { channel: ch });
          await fetchBoardMessages(ch);
          showToast(`Cleared #${ch}`, '🗑️');
        }
      });
    }
    if (boardPostForm) {
      boardPostForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const content = boardPostInput.value.trim();
        if (!content) return;
        const ch = boardChannelSelect.value || 'general';
        await apiPost('/api/board/post', { channel: ch, content, sender: 'user' });
        boardPostInput.value = '';
        await fetchBoardMessages(ch);
        showToast('Message posted to board', '💬');
      });
    }

    // Telegram Modal Events
    if (openTelegramModalBtn) {
      openTelegramModalBtn.addEventListener('click', async () => {
        telegramModal.style.display = 'flex';
        await fetchTelegramStatus();
        if (window.innerWidth <= 768) closeMobileSidebar();
      });
    }
    if (closeTelegramModalBtn) {
      closeTelegramModalBtn.addEventListener('click', () => {
        telegramModal.style.display = 'none';
      });
    }
    if (cancelTelegramBtn) {
      cancelTelegramBtn.addEventListener('click', () => {
        telegramModal.style.display = 'none';
      });
    }
    if (toggleTelegramDaemonBtn) {
      toggleTelegramDaemonBtn.addEventListener('click', async () => {
        const isRunning = toggleTelegramDaemonBtn.getAttribute('data-running') === 'true';
        if (isRunning) {
          await apiPost('/api/telegram/stop', {});
          showToast('Telegram bot daemon stopped', '⏹');
        } else {
          const token = telegramTokenInput.value.trim();
          const allowed = telegramAllowedUsersInput.value.trim();
          const res = await apiPost('/api/telegram/start', { token, allowed_users: allowed });
          if (res.ok) {
            showToast('Telegram bot daemon started', '✈️');
          } else {
            alert(res.error || 'Failed to start Telegram bot');
          }
        }
        await fetchTelegramStatus();
      });
    }
    if (telegramConfigForm) {
      telegramConfigForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const token = telegramTokenInput.value.trim();
        const allowed = telegramAllowedUsersInput.value.trim();
        await apiPost('/api/telegram/config', { token, allowed_users: allowed });
        showToast('Telegram configuration saved', '✅');
        await fetchTelegramStatus();
        telegramModal.style.display = 'none';
      });
    }

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
          el.innerHTML = `<strong>${escapeHtml(item.cmd)}</strong> <span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(item.desc)}</span>`;
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
        serverStatusPill.innerHTML = `<span class="status-dot"></span><span class="status-label">${escapeHtml(data.active_server.alias)} · ${data.active_server.latency_ms}ms</span>`;
      } else {
        serverStatusPill.innerHTML = `<span class="status-dot offline"></span><span class="status-label">Offline</span>`;
      }

      if (sidebarSystemInfo) {
        sidebarSystemInfo.textContent = `${data.online_servers_count}/${data.servers_count} nodes online`;
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
        const isOnline = s.status === 'online';
        srvCard.innerHTML = `
          <div class="server-info-col">
            <div class="server-name">${escapeHtml(s.alias)}</div>
            <div class="server-meta">${escapeHtml(s.host)}:${s.port} · ${s.models.length} model(s)</div>
          </div>
          <div class="server-latency ${isOnline ? '' : 'offline'}">${isOnline ? `${s.latency_ms}ms` : 'offline'}</div>
        `;
        srvCard.addEventListener('click', async () => {
          await apiPost('/api/select', { alias: s.alias });
          await fetchServers();
          await fetchStatus();
          showToast(`Active server: ${s.alias}`, '🌐');
          if (window.innerWidth <= 768) {
            sidebar.classList.remove('open');
            sidebarBackdrop.classList.remove('active');
          }
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
    const total = tasks ? tasks.length : 0;
    const activeCount = tasks ? tasks.filter((t) => t.status === 'in_progress').length : 0;
    taskCountBadge.textContent = `${total} task${total === 1 ? '' : 's'}`;
    if (headerTaskCount) headerTaskCount.textContent = total;

    if (taskIndicatorDot) {
      taskIndicatorDot.style.display = activeCount > 0 ? 'block' : 'none';
    }

    if (!tasks || tasks.length === 0) {
      taskList.innerHTML = `
        <div class="empty-state compact">
          <span class="empty-icon">🎯</span>
          <p>No active tasks. Ask the agent a goal to decompose subtasks!</p>
        </div>
      `;
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
      if (composerModePill) composerModePill.textContent = '🤖 Agent Mode';
    } else {
      agentModeBtn.classList.remove('active');
      if (composerModePill) composerModePill.textContent = '💬 Direct Chat Mode';
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
          <span>⚡ Running:</span>
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
      <div class="message-bubble" style="border-color: var(--accent-rose); background-color: rgba(244, 63, 94, 0.08);">
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
    showToast('Conversation cleared', '🗑️');
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
            <button class="copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-container').querySelector('code').innerText); window.dctShowToast && window.dctShowToast('Code copied!', '📋')">Copy</button>
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
    html = html.replace(/^### (.*$)/gim, '<h3 style="margin: 8px 0 4px 0; font-size: 14px;">$1</h3>');
    html = html.replace(/^## (.*$)/gim, '<h2 style="margin: 10px 0 6px 0; font-size: 15px;">$1</h2>');
    html = html.replace(/^# (.*$)/gim, '<h1 style="margin: 12px 0 8px 0; font-size: 16px;">$1</h1>');

    // Lists
    html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul style="margin: 6px 0; padding-left: 20px;">$1</ul>');

    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');

    return html;
  }

  window.dctShowToast = showToast;

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

  // ── Discussion Board Handlers ─────────────────────────────────────────────
  async function openBoardModal() {
    boardModal.style.display = 'flex';
    await fetchBoardChannels();
    const currentCh = boardChannelSelect.value || 'general';
    await fetchBoardMessages(currentCh);
  }

  async function fetchBoardChannels() {
    try {
      const res = await apiGet('/api/board/channels');
      const channels = res.channels || [];
      const currVal = boardChannelSelect.value;
      boardChannelSelect.innerHTML = '';

      let hasGeneral = false;
      channels.forEach((ch) => {
        if (ch.channel === 'general') hasGeneral = true;
        const opt = document.createElement('option');
        opt.value = ch.channel;
        opt.textContent = `#${ch.channel} (${ch.message_count})`;
        boardChannelSelect.appendChild(opt);
      });

      if (!hasGeneral) {
        const opt = document.createElement('option');
        opt.value = 'general';
        opt.textContent = '#general (0)';
        boardChannelSelect.insertBefore(opt, boardChannelSelect.firstChild);
      }

      if (currVal) {
        boardChannelSelect.value = currVal;
      }
    } catch (e) {
      console.error('fetchBoardChannels failed', e);
    }
  }

  async function fetchBoardMessages(channel = 'general') {
    try {
      const res = await apiGet(`/api/board?channel=${encodeURIComponent(channel)}&limit=50`);
      const messages = res.messages || [];
      if (messages.length === 0) {
        boardMessagesContainer.innerHTML = `
          <div class="empty-state compact">
            <span class="empty-icon">💬</span>
            <p>No messages in #${escapeHtml(channel)} yet.</p>
          </div>
        `;
        return;
      }

      boardMessagesContainer.innerHTML = '';
      messages.forEach((m) => {
        const card = document.createElement('div');
        card.className = 'board-msg-card';
        const isUser = m.sender === 'user';
        const d = new Date(m.timestamp * 1000);
        const timeStr = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const replyHtml = m.reply_to ? `<span class="board-msg-reply-badge">reply to #${m.reply_to}</span>` : '';

        card.innerHTML = `
          <div class="board-msg-header">
            <div class="board-msg-sender-wrap">
              <span class="board-msg-sender ${isUser ? 'user' : ''}">@${escapeHtml(m.sender)}</span>
              ${replyHtml}
              <span class="board-msg-id">[#${m.id}]</span>
            </div>
            <span class="board-msg-time">${timeStr}</span>
          </div>
          <div class="board-msg-body">${escapeHtml(m.content)}</div>
        `;
        boardMessagesContainer.appendChild(card);
      });
      boardMessagesContainer.scrollTop = boardMessagesContainer.scrollHeight;
    } catch (e) {
      console.error('fetchBoardMessages failed', e);
    }
  }

  // ── Agent Skills Handlers ─────────────────────────────────────────────────
  async function fetchSkills() {
    if (!skillChipsGrid) return;
    try {
      const res = await apiGet('/api/skills');
      const skills = res.skills || [];
      const currentSys = (res.current_system || '').trim();

      skillChipsGrid.innerHTML = '';
      let activeSkillName = null;

      skills.forEach((s) => {
        const btn = document.createElement('button');
        btn.className = 'skill-chip-btn';
        btn.innerHTML = `<span style="font-size: 13px;">🧠</span> <span>${escapeHtml(s.name)}</span>`;
        btn.title = s.desc;

        // Check if current system prompt matches this skill
        if (currentSys && s.prompt && currentSys.includes(s.prompt.substring(0, 40))) {
          btn.classList.add('active');
          activeSkillName = s.name;
        }

        btn.addEventListener('click', async () => {
          if (btn.classList.contains('active')) {
            await apiPost('/api/skills/load', { name: '' });
            showToast('Reset to default system prompt', '🔄');
          } else {
            await apiPost('/api/skills/load', { name: s.name });
            showToast(`Loaded skill: ${s.name}`, '🧠');
          }
          await fetchSkills();
          if (window.innerWidth <= 768) {
            sidebar.classList.remove('open');
            sidebarBackdrop.classList.remove('active');
          }
        });
        skillChipsGrid.appendChild(btn);
      });

      if (activeSkillBadge) {
        if (activeSkillName) {
          activeSkillBadge.textContent = activeSkillName;
          activeSkillBadge.className = 'badge badge-active';
        } else if (currentSys) {
          activeSkillBadge.textContent = 'Custom';
          activeSkillBadge.className = 'badge badge-active';
        } else {
          activeSkillBadge.textContent = 'Default';
          activeSkillBadge.className = 'badge badge-subtle';
        }
      }
    } catch (e) {
      console.error('fetchSkills failed', e);
    }
  }

  // ── Telegram Bridge Handlers ──────────────────────────────────────────────
  async function fetchTelegramStatus() {
    try {
      const res = await apiGet('/api/telegram');
      const isRunning = res.running;
      if (telegramStatusBadge) {
        if (isRunning) {
          telegramStatusBadge.textContent = 'Running';
          telegramStatusBadge.className = 'badge badge-active';
        } else {
          telegramStatusBadge.textContent = 'Stopped';
          telegramStatusBadge.className = 'badge badge-subtle';
        }
      }
      if (toggleTelegramDaemonBtn) {
        toggleTelegramDaemonBtn.setAttribute('data-running', isRunning ? 'true' : 'false');
        if (isRunning) {
          toggleTelegramDaemonBtn.textContent = 'Stop Telegram Bot';
          toggleTelegramDaemonBtn.className = 'btn btn-danger btn-block btn-touch';
        } else {
          toggleTelegramDaemonBtn.textContent = 'Start Telegram Bot';
          toggleTelegramDaemonBtn.className = 'btn btn-primary btn-block btn-touch';
        }
      }
      if (telegramAllowedUsersInput && res.allowed_users) {
        telegramAllowedUsersInput.value = res.allowed_users.join(', ');
      }
    } catch (e) {
      console.error('fetchTelegramStatus failed', e);
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
