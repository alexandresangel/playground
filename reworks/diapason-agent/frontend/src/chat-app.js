      const AGENT_EMBED =
        window.DIAPASON_AGENT_CONFIG && typeof window.DIAPASON_AGENT_CONFIG === "object"
          ? window.DIAPASON_AGENT_CONFIG
          : null;
      function resolveApiPrefix() {
        if (AGENT_EMBED && AGENT_EMBED.apiPrefix) {
          return String(AGENT_EMBED.apiPrefix).replace(/\/$/, "");
        }
        const p = window.location.pathname || "";
        const marker = "/agent";
        const i = p.indexOf(marker);
        if (i >= 0) {
          return p.substring(0, i + marker.length);
        }
        return "";
      }
      const API_PREFIX = resolveApiPrefix();
      function apiPath(path) {
        return API_PREFIX + path;
      }
      function staticAsset(path) {
        const p = path.replace(/^\//, "");
        return apiPath("/static/" + p);
      }
      (function fixEmptyStateLogo() {
        const img = document.querySelector(".empty-state-logo");
        if (img) img.src = staticAsset("agent/logo-pascal.png");
      })();

      const CHAT_SESSION_HDR = "X-Diapason-Chat-Session";
      let chatLocale = "en_us";
      let i18nStrings = {};

      function t(key, params) {
        let text = i18nStrings[key] || key;
        if (params) {
          Object.keys(params).forEach(function (name) {
            text = text.replace("{" + name + "}", String(params[name]));
          });
        }
        return text;
      }

      function applyDomI18n() {
        document.querySelectorAll("[data-i18n]").forEach(function (el) {
          if (el === sendBtn && chatStreaming) return;
          const key = el.getAttribute("data-i18n");
          if (!key) return;
          const text = t(key);
          const attrSpec = el.getAttribute("data-i18n-attr");
          if (attrSpec) {
            attrSpec.split(",").forEach(function (raw) {
              const attr = raw.trim();
              if (attr) el.setAttribute(attr, text);
            });
          } else {
            el.textContent = text;
          }
        });
      }

      async function loadI18n() {
        try {
          let url = apiPath("/api/i18n");
          const q = new URLSearchParams(window.location.search).get("locale");
          if (q) url += "?locale=" + encodeURIComponent(q);
          const r = await fetch(url, { headers: accessHeaders() });
          if (!r.ok) return;
          const data = await r.json();
          if (data && data.strings && typeof data.strings === "object") {
            i18nStrings = data.strings;
          }
          if (data && data.locale) chatLocale = data.locale;
        } catch (_err) {
          /* keep defaults */
        }
        applyDomI18n();
      }

      function escapeHtml(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
      }

      function welcomeHtml() {
        return (
          '<div class="empty-state" id="emptyState">' +
          '<img class="empty-state-logo" src="' +
          staticAsset("agent/logo-pascal.png") +
          '" alt="Pascal" width="143" height="76" decoding="async" />' +
          '<p class="empty-state-tagline">' +
          escapeHtml(t("welcome.tagline")) +
          "</p></div>"
        );
      }

      const thread = document.getElementById("thread");
      const messageEl = document.getElementById("message");
      const sendBtn = document.getElementById("sendBtn");
      let chatStreaming = false;
      let chatStreamAbort = null;
      const newChatBtn = document.getElementById("newChatBtn");
      const aiDisclaimerModal = document.getElementById("aiDisclaimerModal");
      const aiDisclaimerBtn = document.getElementById("aiDisclaimerBtn");
      const aiDisclaimerCloseBtn = document.getElementById("aiDisclaimerClose");
      const deleteSessionModal = document.getElementById("deleteSessionModal");
      const deleteSessionMessageEl = document.getElementById("deleteSessionMessage");
      const deleteSessionErrorEl = document.getElementById("deleteSessionError");
      const deleteSessionCancelBtn = document.getElementById("deleteSessionCancel");
      const deleteSessionConfirmBtn = document.getElementById("deleteSessionConfirm");
      const sessionSidebar = document.getElementById("sessionSidebar");
      const sidebarToggle = document.getElementById("sidebarToggle");
      const sessionListEl = document.getElementById("sessionList");
      const mentionMenuEl = document.getElementById("mentionMenu");
      const composerBoxEl = document.getElementById("composerBox");

      let chatSessionId = null;
      let pendingNewChat = false;
      let historySessions = [];
      let mentionEntries = [];
      let mentionMatches = [];
      let mentionActive = 0;
      let assistantDisplayName = "Pascal";
      let pendingDeleteSessionId = null;
      const IC_SKILL_TOKEN = "capture";
      let icEnabled = false;
      let icRunning = false;
      let icModeActive = false;
      let icPdfFile = null;
      let icTradeTypes = [];
      const icComposerEl = document.getElementById("icComposer");
      const composerAttachInput = document.getElementById("composerAttachInput");
      const composerWrapEl = document.querySelector(".composer-wrap");

      function composerAttachIconSvg() {
        return (
          '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
          '<path d="M16.5 6.5v8.25a4.25 4.25 0 1 1-8.5 0V7a2.75 2.75 0 1 1 5.5 0v7.5a1.25 1.25 0 1 1-2.5 0V7" ' +
          'stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/></svg>'
        );
      }

      function createIcAttachButton() {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "composer-attach";
        btn.setAttribute("aria-label", t("composer.attach"));
        btn.setAttribute("title", t("composer.attach"));
        btn.innerHTML = composerAttachIconSvg();
        btn.addEventListener("click", () => {
          if (composerAttachInput) composerAttachInput.click();
        });
        return btn;
      }

      function composerHasIcSkill() {
        return icModeActive;
      }

      function getIcTradeTypeValue() {
        const sel = icComposerEl && icComposerEl.querySelector(".ic-trade-type-inline");
        return sel && sel.value ? sel.value : icTradeTypes[0] || "";
      }

      function renderIcComposer() {
        if (!icComposerEl) return;
        const prevType = getIcTradeTypeValue();
        icComposerEl.innerHTML = "";
        const meta = mentionMetaFromToken(IC_SKILL_TOKEN);
        const chip = createMentionChipElement(meta);
        const removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "ic-skill-remove";
        removeBtn.setAttribute("aria-label", t("ic.removeSkill"));
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", exitIcComposerMode);
        chip.appendChild(removeBtn);
        icComposerEl.appendChild(chip);

        const importWord = document.createElement("span");
        importWord.className = "ic-intent-word";
        importWord.textContent = t("ic.intentImport");
        icComposerEl.appendChild(importWord);

        const sel = document.createElement("select");
        sel.className = "ic-trade-type-inline";
        sel.setAttribute("aria-label", t("ic.tradeType"));
        const types = icTradeTypes.length ? icTradeTypes : ["mltLoan"];
        for (const tt of types) {
          const opt = document.createElement("option");
          opt.value = tt;
          opt.textContent = tt;
          sel.appendChild(opt);
        }
        if (prevType && types.indexOf(prevType) >= 0) sel.value = prevType;
        icComposerEl.appendChild(sel);

        const fromWord = document.createElement("span");
        fromWord.className = "ic-intent-word";
        fromWord.textContent = t("ic.intentFrom");
        icComposerEl.appendChild(fromWord);

        if (icPdfFile) {
          const fileChip = document.createElement("span");
          fileChip.className = "file-chip";
          fileChip.textContent = icPdfFile.name;
          const removeFile = document.createElement("button");
          removeFile.type = "button";
          removeFile.className = "ic-skill-remove";
          removeFile.setAttribute("aria-label", t("ic.removeFile"));
          removeFile.textContent = "×";
          removeFile.addEventListener("click", () => applyIcPdfFile(null));
          fileChip.appendChild(removeFile);
          icComposerEl.appendChild(fileChip);
        } else {
          icComposerEl.appendChild(createIcAttachButton());
        }
      }

      function enterIcComposerMode() {
        if (!icEnabled) return;
        icModeActive = true;
        if (messageEl) {
          messageEl.innerHTML = "";
          messageEl.hidden = true;
        }
        if (icComposerEl) {
          icComposerEl.hidden = false;
          renderIcComposer();
        }
      }

      function exitIcComposerMode() {
        icModeActive = false;
        icPdfFile = null;
        if (composerAttachInput) composerAttachInput.value = "";
        if (icComposerEl) {
          icComposerEl.hidden = true;
          icComposerEl.innerHTML = "";
        }
        if (messageEl) {
          messageEl.hidden = false;
          messageEl.innerHTML = "";
        }
      }

      function registerIcSkillMention() {
        mentionEntries = mentionEntries.filter(
          (e) => e.type !== "skill" || e.token !== IC_SKILL_TOKEN
        );
        if (!icEnabled) return;
        mentionEntries.push({
          token: IC_SKILL_TOKEN,
          desc: t("ic.skillDesc"),
          type: "skill",
          server: "",
        });
        mentionEntries = uniqMentionEntries(mentionEntries).sort((a, b) => {
          if (a.type === "skill" && b.type !== "skill") return -1;
          if (b.type === "skill" && a.type !== "skill") return 1;
          const aDefault = a.server === "default" || a.type === "server";
          const bDefault = b.server === "default" || b.type === "server";
          if (aDefault !== bDefault) return aDefault ? -1 : 1;
          if (a.type !== b.type) return a.type === "tool" ? -1 : 1;
          return a.token.localeCompare(b.token);
        });
      }

      function applyIcPdfFile(file) {
        if (!file) {
          icPdfFile = null;
          if (icModeActive) renderIcComposer();
          return;
        }
        if (file.type && file.type !== "application/pdf") {
          return;
        }
        icPdfFile = file;
        if (!icModeActive && icEnabled) enterIcComposerMode();
        if (icModeActive) renderIcComposer();
      }

      async function loadIcConfig() {
        try {
          const r = await fetch(apiPath("/api/skills/intelligence-contract"), {
            headers: accessHeaders(),
          });
          if (r.status === 404) {
            icEnabled = false;
            icTradeTypes = [];
            registerIcSkillMention();
            return;
          }
          if (!r.ok) return;
          const data = await r.json();
          icEnabled = !!data.enabled;
          icTradeTypes = Array.isArray(data.trade_types) ? data.trade_types : [];
          if (!icTradeTypes.length) icTradeTypes = ["mltLoan"];
          registerIcSkillMention();
          if (icModeActive) renderIcComposer();
        } catch (_err) {
          icEnabled = false;
          icTradeTypes = [];
          registerIcSkillMention();
        }
      }

      function notifyParentOpenTrade(data) {
        if (!data || !data.success || !data.trade_xml) return;
        if (window.parent && window.parent !== window) {
          window.parent.postMessage(
            {
              type: "dia-agent-open-trade",
              viewEntity: data.view_entity,
              menuName: data.menu_name,
              tradeType: data.trade_type,
              tradeXml: data.trade_xml,
            },
            "*"
          );
        }
      }

      function notifyParentCloseChat() {
        if (window.parent && window.parent !== window) {
          window.parent.postMessage({ type: "dia-agent-close" }, "*");
        }
      }

      function icTradeTypeLabel(shortname) {
        const key = "ic.tradeType." + (shortname || "");
        return i18nStrings[key] || shortname || "";
      }

      function renderIcSuccessOutcome(shell, data) {
        if (!shell || !shell.answerEl) return;
        const fieldCount =
          data && data.extracted_field_count != null
            ? Number(data.extracted_field_count)
            : 0;
        shell.answerEl.innerHTML =
          renderMarkdown(
            t("ic.successOutcome", {
              tradeTypeLabel: icTradeTypeLabel(data && data.trade_type),
              fieldCount: fieldCount,
            })
          ) +
          '<p class="ic-close-chat-wrap"><a href="#" class="ic-close-chat">' +
          escapeHtml(t("ic.closeChat")) +
          "</a></p>";
        const closeLink = shell.answerEl.querySelector(".ic-close-chat");
        if (closeLink) {
          closeLink.addEventListener("click", (e) => {
            e.preventDefault();
            notifyParentCloseChat();
          });
        }
      }

      function renderIcToolTrace(shell, data) {
        if (!shell || !data) return;
        const trace = Array.isArray(data.tool_trace) ? data.tool_trace : [];
        if (!trace.length) return;
        renderTrace(shell, trace);
      }

      function icIntentBubbleHtml(tradeType, fileName) {
        const meta = mentionMetaFromToken(IC_SKILL_TOKEN);
        return (
          '<div class="user-plain ic-intent-bubble">' +
          mentionChipHtml(meta) +
          ' <span class="ic-intent-word">' +
          escapeHtml(t("ic.intentImport")) +
          "</span> " +
          '<span class="ic-trade-type-inline ic-trade-type-readonly">' +
          escapeHtml(tradeType) +
          "</span> " +
          '<span class="ic-intent-word">' +
          escapeHtml(t("ic.intentFrom")) +
          '</span> <span class="file-chip">' +
          escapeHtml(fileName) +
          "</span></div>"
        );
      }

      function addUserBubbleIcIntent(tradeType, fileName) {
        hideEmpty();
        const wrap = document.createElement("div");
        wrap.className = "msg user";
        wrap.innerHTML =
          '<span class="msg-label">' +
          escapeHtml(t("label.you")) +
          '</span><div class="bubble"></div>';
        wrap.querySelector(".bubble").innerHTML = icIntentBubbleHtml(tradeType, fileName);
        thread.appendChild(wrap);
        thread.scrollTop = thread.scrollHeight;
      }

      async function runIntelligenceContract(pdfFile, tradeType) {
        const pdf = pdfFile || icPdfFile;
        const tt = tradeType || getIcTradeTypeValue();
        if (icRunning || !pdf || !tt) return;
        icRunning = true;
        setSendStreaming(true);
        const shell = addAssistantShell();
        setShellThinking(shell, true);
        const form = new FormData();
        form.append("pdf", pdf, pdf.name);
        form.append("trade_type", tt);
        form.append("debug", "false");
        if (chatSessionId) {
          form.append("session_id", chatSessionId);
        }
        const headers = accessHeaders();
        delete headers["Content-Type"];
        if (chatSessionId) {
          headers[CHAT_SESSION_HDR] = chatSessionId;
        }
        try {
          const r = await fetch(apiPath("/api/skills/intelligence-contract"), {
            method: "POST",
            headers,
            body: form,
          });
          const streamSessionHeader = readChatSessionHeader(r);
          if (streamSessionHeader) {
            applyChatSessionId(streamSessionHeader);
          }
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            const detail = data.detail || data.message || r.statusText;
            throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
          }
          setShellThinking(shell, false);
          renderIcToolTrace(shell, data);
          if (data.success) {
            renderIcSuccessOutcome(shell, data);
            notifyParentOpenTrade(data);
          } else {
            let msg = t("ic.error") + ": " + (data.message || t("response.none"));
            shell.answerEl.innerHTML = renderMarkdown(msg);
          }
          thread.scrollTop = thread.scrollHeight;
        } catch (err) {
          setShellThinking(shell, false);
          shell.answerEl.innerHTML = renderMarkdown(
            t("ic.error") + ": " + (err.message || String(err))
          );
        } finally {
          icRunning = false;
          setSendStreaming(false);
          try {
            await fetchSessionList();
          } catch (_e) {
            /* sidebar refresh is best-effort */
          }
        }
      }

      async function loadAssistantName() {
        try {
          const r = await fetch(apiPath("/api/health"), { headers: accessHeaders() });
          if (!r.ok) return;
          const data = await r.json();
          const name = data && data.assistant_name;
          if (typeof name === "string" && name.trim()) {
            assistantDisplayName = name.trim();
          }
        } catch (_err) {
          /* keep default */
        }
        await loadIcConfig();
      }

      function createAssistantLabel() {
        const span = document.createElement("span");
        span.className = "msg-label";
        span.textContent = assistantDisplayName;
        return span;
      }

      function hasAgentEmbed() {
        return !!(AGENT_EMBED && AGENT_EMBED.apiPrefix);
      }

      function accessHeaders() {
        const h = { "Content-Type": "application/json" };
        if (AGENT_EMBED && AGENT_EMBED.userId != null) {
          h["X-Diapason-User-Id"] = String(AGENT_EMBED.userId);
        }
        if (AGENT_EMBED && AGENT_EMBED.customerId != null) {
          h["X-Diapason-Customer-Id"] = String(AGENT_EMBED.customerId);
        }
        return h;
      }

      function showEmbedRequired() {
        thread.innerHTML =
          '<div class="empty-state" id="emptyState"><p class="empty-state-tagline">' +
          escapeHtml(t("embed.required")) +
          "</p></div>";
        sendBtn.disabled = true;
        messageEl.contentEditable = "false";
      }

      function uniqMentionEntries(items) {
        const seen = new Set();
        const out = [];
        for (const item of items) {
          const key = (item && item.token ? String(item.token) : "").toLowerCase();
          if (!key || seen.has(key)) continue;
          seen.add(key);
          out.push(item);
        }
        return out;
      }

      async function loadMentionEntries() {
        if (!hasAgentEmbed()) return;
        try {
          const r = await fetch(apiPath("/api/mcp/tools"), { headers: accessHeaders() });
          if (!r.ok) return;
          const data = await r.json();
          const next = [];
          const tools = Array.isArray(data.tools) ? data.tools : [];
          const servers = Array.isArray(data.servers) ? data.servers : [];
          for (const t of tools) {
            if (!t || !t.native_name || t.mentionable === false) continue;
            const token = String(t.mention_token || t.native_name).trim();
            if (!token) continue;
            const desc = String(t.description || t.mcp_label || t.mcp_server || "tool")
              .replace(/\s+/g, " ")
              .trim();
            next.push({
              token: token,
              desc: desc.length > 72 ? desc.slice(0, 71) + "…" : desc,
              type: "tool",
              server: String(t.mcp_server || ""),
            });
          }
          for (const s of servers) {
            if (!s || !s.ok || s.server_id === "default") continue;
            const prefix = String(s.mention_prefix || "").trim();
            if (!prefix) continue;
            next.push({
              token: prefix,
              desc: "all tools — " + String(s.label || s.server_id),
              type: "server",
              server: String(s.server_id || ""),
            });
          }
          mentionEntries = uniqMentionEntries(next).sort((a, b) => {
            const aDefault = a.server === "default" || a.type === "server";
            const bDefault = b.server === "default" || b.type === "server";
            if (aDefault !== bDefault) return aDefault ? -1 : 1;
            if (a.type !== b.type) return a.type === "tool" ? -1 : 1;
            return a.token.localeCompare(b.token);
          });
          registerIcSkillMention();
        } catch (_e) {
          /* suggestions are best-effort */
        }
      }

      function setSendStreaming(streaming) {
        chatStreaming = streaming;
        sendBtn.classList.toggle("is-streaming", streaming);
        const label = streaming ? t("composer.stop") : t(sendBtn.getAttribute("data-i18n") || "composer.send");
        sendBtn.textContent = label;
        sendBtn.setAttribute("aria-label", label);
      }

      function stopChatStream() {
        if (chatStreamAbort) chatStreamAbort.abort();
      }

      function readChatSessionHeader(response) {
        return response.headers.get(CHAT_SESSION_HDR);
      }

      function applyChatSessionId(id, opts) {
        opts = opts || {};
        const trimmed = id && String(id).trim();
        if (!trimmed) return;
        if (pendingNewChat && !opts.force) return;
        chatSessionId = trimmed;
        pendingNewChat = false;
        renderSessionList();
      }

      function showWelcomeState() {
        thread.innerHTML = welcomeHtml();
      }

      function showEmptyState() {
        showWelcomeState();
      }

      function renderHistory(turns) {
        if (!Array.isArray(turns) || !turns.length) return;
        hideEmpty();
        for (const turn of turns) {
          if (turn.role === "user") {
            addUserBubble(turn.content || "");
          } else if (turn.role === "assistant") {
            const shell = addAssistantShell();
            shell.answerEl.innerHTML = renderMarkdown(turn.content || "");
            if (Array.isArray(turn.tool_trace) && turn.tool_trace.length) {
              renderTrace(shell, turn.tool_trace);
            } else {
              shell.traceDetails.style.display = "none";
            }
            if (Array.isArray(turn.sources) && turn.sources.length) {
              renderSources(shell, turn.sources);
            }
          }
        }
        thread.scrollTop = thread.scrollHeight;
      }

      function renderSessionList() {
        if (!sessionListEl) return;
        sessionListEl.innerHTML = "";
        const items = historySessions.filter((s) => s.has_response);
        if (!items.length) {
          const empty = document.createElement("p");
          empty.className = "session-list-empty";
          empty.textContent = t("sidebar.noChats");
          sessionListEl.appendChild(empty);
          return;
        }
        for (const row of items) {
          const li = document.createElement("li");
          li.className = "session-list-item";
          const title = (row.title || "").trim() || "Chat";
          const isActive = row.session_id === chatSessionId;
          if (isActive) li.classList.add("active");

          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "session-select-btn";
          btn.textContent = title;
          btn.title = title;
          btn.addEventListener("click", () => selectHistorySession(row.session_id));
          li.appendChild(btn);

          if (isActive) {
            const del = document.createElement("button");
            del.type = "button";
            del.className = "session-delete-btn";
            del.setAttribute("aria-label", t("sidebar.deleteChat"));
            del.title = "Delete chat";
            del.textContent = "\u{1F5D1}\uFE0E";
            del.addEventListener("click", (e) => {
              e.stopPropagation();
              openDeleteSessionDialog(row.session_id, title);
            });
            li.appendChild(del);
          }

          sessionListEl.appendChild(li);
        }
      }

      async function fetchSessionList() {
        const r = await fetch(apiPath("/api/sessions"), { headers: accessHeaders() });
        if (!r.ok) {
          throw new Error("Could not list sessions (" + r.status + ")");
        }
        const data = await r.json();
        historySessions = Array.isArray(data.sessions) ? data.sessions : [];
        const headerId = readChatSessionHeader(r);
        if (headerId) {
          applyChatSessionId(headerId);
        }
        renderSessionList();
        return headerId;
      }

      async function loadSessionDetail(sessionId) {
        const r = await fetch(apiPath("/api/sessions/" + encodeURIComponent(sessionId)), {
          headers: accessHeaders(),
        });
        if (!r.ok) {
          throw new Error("Could not load session (" + r.status + ")");
        }
        const data = await r.json();
        const headerId = readChatSessionHeader(r);
        applyChatSessionId(headerId || data.session_id || sessionId, { force: true });
        thread.innerHTML = "";
        renderHistory(data.turns);
        if (!data.turns || !data.turns.length) {
          showWelcomeState();
        }
        return chatSessionId;
      }

      async function selectHistorySession(sessionId) {
        if (!sessionId) return;
        pendingNewChat = false;
        try {
          await loadSessionDetail(sessionId);
          messageEl.focus();
        } catch (err) {
          console.error("Load session failed", err);
        }
      }

      async function initAgentChat() {
        if (!hasAgentEmbed()) return;
        try {
          const headerId = await fetchSessionList();
          await loadMentionEntries();
          if (pendingNewChat) {
            showWelcomeState();
            return;
          }
          if (headerId) {
            await loadSessionDetail(headerId);
          } else {
            chatSessionId = null;
            showWelcomeState();
          }
        } catch (err) {
          console.error("Agent chat init failed", err);
        }
      }

      function startNewChat() {
        if (!hasAgentEmbed()) return;
        pendingNewChat = true;
        chatSessionId = null;
        messageEl.innerHTML = "";
        exitIcComposerMode();
        showWelcomeState();
        renderSessionList();
        messageEl.focus();
      }

      function openDeleteSessionDialog(sessionId, label) {
        if (!sessionId) return;
        pendingDeleteSessionId = sessionId;
        const name = (label || t("delete.defaultName")).trim() || t("delete.defaultName");
        deleteSessionMessageEl.textContent = t("delete.message", { name: name });
        deleteSessionErrorEl.hidden = true;
        deleteSessionErrorEl.textContent = "";
        deleteSessionModal.hidden = false;
        deleteSessionConfirmBtn.focus();
      }

      function openAiDisclaimerDialog() {
        if (!aiDisclaimerModal) return;
        aiDisclaimerModal.hidden = false;
        if (aiDisclaimerCloseBtn) aiDisclaimerCloseBtn.focus();
      }

      function closeAiDisclaimerDialog() {
        if (aiDisclaimerModal) aiDisclaimerModal.hidden = true;
      }

      function closeDeleteSessionDialog() {
        deleteSessionModal.hidden = true;
        pendingDeleteSessionId = null;
        deleteSessionErrorEl.hidden = true;
        deleteSessionErrorEl.textContent = "";
      }

      async function deleteSessionById(sessionId) {
        if (!sessionId) return;
        try {
          const r = await fetch(apiPath("/api/sessions/" + encodeURIComponent(sessionId)), {
            method: "DELETE",
            headers: accessHeaders(),
          });
          if (r.status === 404) {
            if (sessionId === chatSessionId) {
              pendingNewChat = true;
              chatSessionId = null;
              showWelcomeState();
            }
            await fetchSessionList();
            return;
          }
          if (!r.ok) {
            throw new Error("Could not delete session (" + r.status + ")");
          }
          if (sessionId === chatSessionId) {
            pendingNewChat = true;
            chatSessionId = null;
            showWelcomeState();
          }
          await fetchSessionList();
          messageEl.focus();
        } catch (err) {
          console.error("Delete session failed", err);
          pendingDeleteSessionId = sessionId;
          deleteSessionErrorEl.textContent = t("delete.error");
          deleteSessionErrorEl.hidden = false;
          deleteSessionModal.hidden = false;
        }
      }

      async function confirmDeleteSession() {
        const sessionId = pendingDeleteSessionId;
        if (!sessionId) return;
        closeDeleteSessionDialog();
        await deleteSessionById(sessionId);
      }

      async function initApp() {
        await loadI18n();
        if (!hasAgentEmbed()) {
          showEmbedRequired();
          return;
        }
        try {
          await loadAssistantName();
          await initAgentChat();
        } catch (err) {
          console.error("Agent init failed", err);
        }
      }

      marked.setOptions({
        gfm: true,
        breaks: true,
        headerIds: false,
        mangle: false,
      });

      function renderMarkdown(md) {
        const raw = marked.parse(md || "");
        return DOMPurify.sanitize(raw, {
          ADD_ATTR: ["target"],
          ALLOWED_TAGS: [
            "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "strong", "em", "b", "i", "u",
            "ul", "ol", "li", "blockquote", "code", "pre", "hr", "a", "table", "thead",
            "tbody", "tr", "th", "td", "span", "del", "input",
          ],
        });
      }

      function hideEmpty() {
        const el = document.getElementById("emptyState");
        if (el && el.parentNode) el.remove();
      }

      function chipLabelFromEntry(entry) {
        if (!entry) return "";
        if (entry.type === "skill") {
          return t("ic.skillLabel");
        }
        if (entry.type === "server") {
          const d = String(entry.desc || "");
          const dash = d.indexOf(" — ");
          if (dash >= 0) return d.slice(dash + 3).trim();
          const token = String(entry.token || "");
          return token ? token.charAt(0).toUpperCase() + token.slice(1) : "";
        }
        const token = String(entry.token || "");
        const dot = token.indexOf(".");
        if (dot >= 0) return token.slice(dot + 1);
        return token;
      }

      function mentionMetaFromToken(token) {
        const entry = mentionEntries.find(
          (e) => String(e.token || "").toLowerCase() === String(token || "").toLowerCase()
        );
        if (!entry) {
          return {
            token: String(token || ""),
            label: String(token || ""),
            type: "unknown",
            server: "",
          };
        }
        return {
          token: entry.token,
          label: chipLabelFromEntry(entry),
          type: entry.type,
          server: entry.server || "",
        };
      }

      function isKnownMentionToken(token) {
        return mentionEntries.some(
          (e) => String(e.token || "").toLowerCase() === String(token || "").toLowerCase()
        );
      }

      function createMentionChipElement(meta) {
        const span = document.createElement("span");
        span.className =
          meta.type === "skill" ? "mention-chip mention-chip-skill" : "mention-chip";
        span.setAttribute("contenteditable", "false");
        span.setAttribute("data-mention-token", meta.token);
        span.setAttribute("title", meta.label || meta.token);
        const label = document.createElement("span");
        label.className = "mention-chip-label";
        label.textContent = meta.label || meta.token;
        span.appendChild(label);
        return span;
      }

      function mentionChipHtml(meta) {
        const label = escapeHtml(meta.label || meta.token);
        const token = escapeHtml(meta.token);
        const chipClass =
          meta.type === "skill" ? "mention-chip mention-chip-skill" : "mention-chip";
        return (
          '<span class="' +
          chipClass +
          '" contenteditable="false" data-mention-token="' +
          token +
          '" title="' +
          label +
          '"><span class="mention-chip-label">' +
          label +
          "</span></span>"
        );
      }

      function serializeNodeToPlain(root) {
        let out = "";
        function walk(node) {
          if (node.nodeType === Node.TEXT_NODE) {
            out += node.textContent || "";
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node;
            if (el.classList && el.classList.contains("mention-chip")) {
              const tok = el.getAttribute("data-mention-token");
              if (tok) out += "@" + tok;
            } else if (el.tagName === "BR") {
              out += "\n";
            } else {
              for (let i = 0; i < el.childNodes.length; i++) walk(el.childNodes[i]);
            }
          }
        }
        walk(root);
        return out;
      }

      function getComposerPlainText() {
        if (!messageEl) return "";
        return serializeNodeToPlain(messageEl);
      }

      function renderPlainTextWithInlineChips(text) {
        const raw = String(text || "");
        const re = /(^|[\s(])@(\S+)/g;
        let html = "";
        let last = 0;
        let m;
        while ((m = re.exec(raw)) !== null) {
          const prefix = m[1];
          const token = m[2];
          const atStart = m.index + prefix.length;
          html += escapeHtml(raw.slice(last, atStart));
          if (isKnownMentionToken(token)) {
            html += mentionChipHtml(mentionMetaFromToken(token));
          } else {
            html += escapeHtml("@" + token);
          }
          last = m.index + m[0].length;
        }
        html += escapeHtml(raw.slice(last));
        return html;
      }

      function setComposerPlainText(text) {
        if (!messageEl) return;
        messageEl.innerHTML = "";
        const raw = String(text || "");
        if (!raw) return;
        const re = /(^|[\s(])@(\S+)/g;
        const frag = document.createDocumentFragment();
        let last = 0;
        let m;
        while ((m = re.exec(raw)) !== null) {
          const prefix = m[1];
          const token = m[2];
          const atStart = m.index + prefix.length;
          if (atStart > last) {
            frag.appendChild(document.createTextNode(raw.slice(last, atStart)));
          }
          if (isKnownMentionToken(token)) {
            frag.appendChild(createMentionChipElement(mentionMetaFromToken(token)));
          } else {
            frag.appendChild(document.createTextNode("@" + token));
          }
          last = m.index + m[0].length;
        }
        if (last < raw.length) {
          frag.appendChild(document.createTextNode(raw.slice(last)));
        }
        messageEl.appendChild(frag);
      }

      function placeComposerCaretAtPlainOffset(offset) {
        if (!messageEl) return;
        messageEl.focus();
        const sel = window.getSelection();
        if (!sel) return;
        let pos = 0;
        const range = document.createRange();
        let placed = false;

        function walk(node) {
          if (placed) return;
          if (node.nodeType === Node.TEXT_NODE) {
            const len = (node.textContent || "").length;
            if (pos + len >= offset) {
              range.setStart(node, Math.max(0, offset - pos));
              range.collapse(true);
              placed = true;
              return;
            }
            pos += len;
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node;
            if (el.classList && el.classList.contains("mention-chip")) {
              const tok = el.getAttribute("data-mention-token");
              const len = tok ? tok.length + 1 : 0;
              if (pos + len >= offset) {
                range.setStartAfter(el);
                range.collapse(true);
                placed = true;
                return;
              }
              pos += len;
            } else if (el.tagName === "BR") {
              if (pos + 1 >= offset) {
                range.setStartAfter(el);
                range.collapse(true);
                placed = true;
                return;
              }
              pos += 1;
            } else {
              for (let i = 0; i < el.childNodes.length; i++) walk(el.childNodes[i]);
            }
          }
        }

        walk(messageEl);
        if (!placed) {
          range.selectNodeContents(messageEl);
          range.collapse(false);
        }
        sel.removeAllRanges();
        sel.addRange(range);
      }

      function getTextAroundCaret() {
        const sel = window.getSelection();
        if (!sel || !sel.rangeCount || !messageEl) {
          return { before: "", after: "" };
        }
        const endRange = sel.getRangeAt(0);
        const beforeRange = document.createRange();
        beforeRange.selectNodeContents(messageEl);
        beforeRange.setEnd(endRange.endContainer, endRange.endOffset);
        const afterRange = document.createRange();
        afterRange.selectNodeContents(messageEl);
        afterRange.setStart(endRange.endContainer, endRange.endOffset);
        const beforeDiv = document.createElement("div");
        beforeDiv.appendChild(beforeRange.cloneContents());
        const afterDiv = document.createElement("div");
        afterDiv.appendChild(afterRange.cloneContents());
        return {
          before: serializeNodeToPlain(beforeDiv),
          after: serializeNodeToPlain(afterDiv),
        };
      }

      function fillUserBubble(bubbleEl, text) {
        const plain = document.createElement("div");
        plain.className = "user-plain";
        plain.style.whiteSpace = "pre-wrap";
        plain.style.wordBreak = "break-word";
        plain.innerHTML = renderPlainTextWithInlineChips(text);
        bubbleEl.innerHTML = "";
        bubbleEl.appendChild(plain);
      }

      function addUserBubble(text) {
        hideEmpty();
        const wrap = document.createElement("div");
        wrap.className = "msg user";
        wrap.innerHTML =
          '<span class="msg-label">' +
          escapeHtml(t("label.you")) +
          '</span><div class="bubble"></div>';
        fillUserBubble(wrap.querySelector(".bubble"), text);
        thread.appendChild(wrap);
        thread.scrollTop = thread.scrollHeight;
      }

      function addAssistantShell() {
        hideEmpty();
        const wrap = document.createElement("div");
        wrap.className = "msg assistant";
        wrap.appendChild(createAssistantLabel());
        const bubble = document.createElement("div");
        bubble.className = "bubble";
        const answer = document.createElement("div");
        answer.className = "md-content answer-body";
        bubble.appendChild(answer);
        wrap.appendChild(bubble);
        wrap.insertAdjacentHTML(
          "beforeend",
          '<div class="chart-slot"></div>' +
            '<div class="sources-slot"></div>' +
            '<details class="trace-panel"><summary>' +
            escapeHtml(t("trace.title")) +
            '</summary><div class="trace-body trace-slot"></div></details>'
        );
        thread.appendChild(wrap);
        thread.scrollTop = thread.scrollHeight;
        return {
          answerEl: wrap.querySelector(".answer-body"),
          chartSlot: wrap.querySelector(".chart-slot"),
          sourcesSlot: wrap.querySelector(".sources-slot"),
          traceSlot: wrap.querySelector(".trace-slot"),
          traceDetails: wrap.querySelector("details.trace-panel"),
          root: wrap,
        };
      }

      function thinkingMarkup() {
        return (
          '<div class="typing" role="status" aria-live="polite" aria-label="' +
          escapeHtml(t("thinking")) +
          '"><span></span><span></span><span></span></div>'
        );
      }

      function setTyping(show) {
        let el = document.getElementById("typingRow");
        if (show) {
          if (el) return;
          hideEmpty();
          el = document.createElement("div");
          el.id = "typingRow";
          el.className = "msg assistant";
          el.appendChild(createAssistantLabel());
          const bubble = document.createElement("div");
          bubble.className = "bubble";
          bubble.innerHTML = thinkingMarkup();
          el.appendChild(bubble);
          thread.appendChild(el);
          thread.scrollTop = thread.scrollHeight;
        } else if (el) {
          el.remove();
        }
      }

      function setShellThinking(shell, on) {
        if (!shell) return;
        if (on) {
          shell.answerEl.innerHTML = thinkingMarkup();
        } else if (shell.answerEl.querySelector(".typing")) {
          shell.answerEl.innerHTML = "";
        }
      }

      function setTracePanelVisible(shell, visible) {
        if (!shell) return;
        shell.traceDetails.hidden = !visible;
        shell.traceDetails.classList.toggle("trace-pending", visible);
      }

      function showTraceStatus(shell, text) {
        if (!shell) return;
        const msg = String(text || "").trim();
        if (!msg) return;
        setTracePanelVisible(shell, true);
        shell.traceDetails.open = false;
        shell.traceSlot.innerHTML =
          '<p class="trace-status">' + escapeHtml(msg) + "</p>";
      }

      function formatToolArguments(args) {
        if (args == null) return "(no parameters)";
        if (typeof args !== "object") return String(args);
        if (Array.isArray(args) && !args.length) return "(no parameters)";
        if (!Array.isArray(args) && !Object.keys(args).length) return "(no parameters)";
        try {
          return JSON.stringify(args, null, 2);
        } catch (_e) {
          return String(args);
        }
      }

      function renderTrace(shell, traceItems) {
        if (!traceItems.length) {
          setTracePanelVisible(shell, false);
          shell.traceSlot.innerHTML = "";
          return;
        }
        setTracePanelVisible(shell, true);
        shell.traceDetails.classList.remove("trace-pending");
        const chips = traceItems
            .map((item, idx) => {
              const tool = item.tool || item.name || "unknown";
              const serverLabel =
                item.mcp_label &&
                item.mcp_server &&
                item.mcp_server !== "default" &&
                item.mcp_server !== "diapason"
                  ? item.mcp_label + " · "
                  : "";
              const fullLabel = serverLabel + tool;
              const args = escapeHtml(formatToolArguments(item.arguments));
              const ms = item.duration_ms ?? "?";
              return (
                '<details class="trace-entry">' +
                '<summary class="trace-entry-summary" title="' +
                escapeHtml(fullLabel) +
                '">' +
                '<span class="trace-label">' +
                (idx + 1) +
                ". " +
                escapeHtml(fullLabel) +
                "</span>" +
                '<span class="trace-ms">' +
                ms +
                " ms</span></summary>" +
                '<pre class="trace-args">' +
                args +
                "</pre></details>"
              );
            })
            .join("");
        shell.traceSlot.innerHTML = '<div class="trace-list">' + chips + "</div>";
        shell.traceDetails.open = true;
      }

      function normalizeSourceKey(url) {
        const raw = String(url || "").trim();
        if (!raw) return "";
        try {
          const u = new URL(raw, window.location.href);
          if (u.protocol === "http:" || u.protocol === "https:") {
            const normPath = u.pathname.replace(/\/+$/, "") || "/";
            return (u.protocol + "//" + u.host + normPath).toLowerCase();
          }
        } catch (e) {
          /* fall through */
        }
        const pathOnly = raw.split("?")[0].split("#")[0].replace(/\/+$/, "") || "/";
        return pathOnly.toLowerCase();
      }

      function sourceMatchesDocLocale(url) {
        const raw = String(url || "").toLowerCase();
        if (raw.indexOf("/doc-internal/") < 0) return true;
        const loc = String(chatLocale || "en_us").toLowerCase();
        if (raw.indexOf("/" + loc + "/") >= 0) return true;
        if (loc !== "en_us" && raw.indexOf("/en_us/") >= 0) return true;
        return false;
      }

      function isDocSourceItem(item) {
        const qualified = String(item.tool || item.name || "").trim();
        if (!qualified) return false;
        const base = qualified.indexOf("__") >= 0 ? qualified.split("__").pop() : qualified;
        return base === "ask_docs" || base === "search_docs";
      }

      function renderSources(shell, rawItems) {
        const items = Array.isArray(rawItems) ? rawItems : [];
        if (!items.length) {
          shell.sourcesSlot.innerHTML = "";
          return;
        }
        const seen = new Set();
        const rows = [];
        for (const item of items) {
          if (!item || typeof item !== "object") continue;
          if (!isDocSourceItem(item)) continue;
          const url = String(item.url || "").trim();
          if (!url) continue;
          if (!sourceMatchesDocLocale(url)) continue;
          const key = normalizeSourceKey(url);
          if (!key || seen.has(key)) continue;
          seen.add(key);
          const label =
            String(item.link_text || item.title || "").trim() || "Documentation";
          const excerpt = String(item.snippet || item.content || "").trim();
          const liClass = excerpt ? ' class="source-item-with-excerpt"' : "";
          let row =
            "<li" +
            liClass +
            '><a href="' +
            escapeHtml(url) +
            '" target="_blank" rel="noopener noreferrer">' +
            escapeHtml(label) +
            "</a>";
          if (excerpt) {
            row +=
              '<p class="source-excerpt">' + escapeHtml(excerpt) + "</p>";
          }
          row += "</li>";
          rows.push(row);
        }
        if (!rows.length) {
          shell.sourcesSlot.innerHTML = "";
          return;
        }
        shell.sourcesSlot.innerHTML =
          '<div class="sources-panel"><h5>' +
          escapeHtml(t("label.sources")) +
          '</h5><ul class="sources-list">' +
          rows.join("") +
          "</ul></div>";
      }

      function parseSseChunk(buffer, onEvent) {
        const parts = buffer.split("\n\n");
        const rest = parts.pop() || "";
        for (const block of parts) {
          for (const line of block.split("\n")) {
            if (!line.startsWith("data: ")) continue;
            const raw = line.slice(6).trim();
            if (raw === "[DONE]") continue;
            onEvent(JSON.parse(raw));
          }
        }
        return rest;
      }

      async function sendMessage() {
        if (chatStreaming) return;
        const hasIc = composerHasIcSkill();
        const message = getComposerPlainText().trim();
        if (icEnabled && /^(?:\/capture|@capture|@intelligence-contract)\s*$/i.test(message)) {
          enterIcComposerMode();
          return;
        }
        if (!message && !hasIc) return;

        if (!hasAgentEmbed()) return;

        if (hasIc) {
          if (!icPdfFile) return;
          if (icRunning) return;
          const pdf = icPdfFile;
          const tradeType = getIcTradeTypeValue();
          addUserBubbleIcIntent(tradeType, pdf.name);
          exitIcComposerMode();
          await runIntelligenceContract(pdf, tradeType);
          return;
        }

        const abort = new AbortController();
        chatStreamAbort = abort;
        setSendStreaming(true);
        addUserBubble(message);
        messageEl.innerHTML = "";
        setTyping(true);

        let shell = null;
        let markdownBuf = "";
        let stopped = false;
        const traceItems = [];
        const sourceItems = [];
        let renderScheduled = false;

        function scheduleRender() {
          if (!shell || renderScheduled) return;
          renderScheduled = true;
          requestAnimationFrame(() => {
            renderScheduled = false;
            if (shell) shell.answerEl.innerHTML = renderMarkdown(markdownBuf);
            thread.scrollTop = thread.scrollHeight;
          });
        }

        try {
          const streamHeaders = accessHeaders();
          streamHeaders.Accept = "text/event-stream";
          const streamBody = {
            message,
            client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          };
          if (chatSessionId) {
            streamBody.session_id = chatSessionId;
          }
          const response = await fetch(apiPath("/api/chat/stream"), {
            method: "POST",
            headers: streamHeaders,
            body: JSON.stringify(streamBody),
            signal: abort.signal,
          });
          const streamSessionHeader = readChatSessionHeader(response);
          if (streamSessionHeader) {
            applyChatSessionId(streamSessionHeader, { force: true });
          }
          if (response.status === 401) {
            setTyping(false);
            const lastUser = thread.querySelector(".msg.user:last-of-type");
            if (lastUser) lastUser.remove();
            shell = addAssistantShell();
            shell.answerEl.innerHTML = renderMarkdown(
              "**Authentication failed.** Set `diapason.agent.chat.jwt` in Tomcat config and restart."
            );
            return;
          }
          if (!response.ok || !response.body) {
            throw new Error("HTTP " + response.status);
          }

          shell = addAssistantShell();
          setShellThinking(shell, true);
          setTracePanelVisible(shell, false);
          setTyping(false);

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let sseBuffer = "";

          try {
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              sseBuffer += decoder.decode(value, { stream: true });
              sseBuffer = parseSseChunk(sseBuffer, (evt) => {
              if (evt.type === "delta" && evt.content) {
                if (shell.answerEl.querySelector(".typing")) {
                  setShellThinking(shell, false);
                }
                markdownBuf += evt.content;
                scheduleRender();
              } else if (evt.type === "status" && evt.content) {
                showTraceStatus(shell, evt.content);
              } else if (evt.type === "tool") {
                traceItems.push({
                  name: evt.name,
                  tool: evt.tool || evt.name,
                  mcp_server: evt.mcp_server,
                  mcp_label: evt.mcp_label,
                  duration_ms: evt.duration_ms,
                  arguments: evt.arguments != null ? evt.arguments : {},
                });
                renderTrace(shell, traceItems);
              } else if (evt.type === "sources") {
                if (Array.isArray(evt.items) && evt.items.length) {
                  sourceItems.push(...evt.items);
                  renderSources(shell, sourceItems);
                }
              } else if (evt.type === "done") {
                setShellThinking(shell, false);
                if (evt.session_id) {
                  applyChatSessionId(evt.session_id, { force: true });
                }
                if (Array.isArray(evt.tool_trace) && evt.tool_trace.length) {
                  traceItems.length = 0;
                  traceItems.push(...evt.tool_trace);
                  renderTrace(shell, traceItems);
                } else if (!traceItems.length) {
                  setTracePanelVisible(shell, false);
                }
                if (Array.isArray(evt.sources) && evt.sources.length) {
                  sourceItems.length = 0;
                  sourceItems.push(...evt.sources);
                  renderSources(shell, sourceItems);
                } else if (sourceItems.length) {
                  renderSources(shell, sourceItems);
                }
                if (typeof evt.answer_markdown === "string") {
                  markdownBuf = evt.answer_markdown;
                  scheduleRender();
                }
              } else if (evt.type === "error") {
                markdownBuf += "\n\n**Error:** " + (evt.content || "Unknown error");
                scheduleRender();
              }
              });
            }
          } catch (readErr) {
            if (abort.signal.aborted) {
              stopped = true;
              try {
                await reader.cancel();
              } catch (_e) {
                /* ignore */
              }
            } else {
              throw readErr;
            }
          }

          if (shell) {
            setShellThinking(shell, false);
            if (!markdownBuf) {
              if (!stopped) {
                shell.answerEl.innerHTML = renderMarkdown(t("response.none"));
              }
            } else {
              shell.answerEl.innerHTML = renderMarkdown(markdownBuf);
            }
          }
          if (!stopped) {
            try {
              await fetchSessionList();
            } catch (_e) {
              /* sidebar refresh is best-effort */
            }
          }
        } catch (err) {
          if (abort.signal.aborted) {
            stopped = true;
            setTyping(false);
            if (shell) {
              setShellThinking(shell, false);
              if (markdownBuf) {
                shell.answerEl.innerHTML = renderMarkdown(markdownBuf);
              }
            }
          } else {
            setTyping(false);
            if (shell) setShellThinking(shell, false);
            if (!shell) shell = addAssistantShell();
            shell.answerEl.innerHTML = renderMarkdown(
              "**Request failed**\n\n```\n" + String(err) + "\n```"
            );
          }
        } finally {
          setTyping(false);
          chatStreamAbort = null;
          setSendStreaming(false);
          messageEl.focus();
        }
      }

      function hideMentionMenu() {
        mentionMenuEl.style.display = "none";
        mentionMenuEl.innerHTML = "";
        mentionMatches = [];
        mentionActive = 0;
      }

      function mentionContext() {
        const parts = getTextAroundCaret();
        const before = parts.before;
        const at = before.lastIndexOf("@");
        if (at < 0) return null;
        const prev = at > 0 ? before.charAt(at - 1) : " ";
        if (!/\s/.test(prev) && at > 0) return null;
        const fragment = before.slice(at + 1);
        if (/\s/.test(fragment)) return null;
        return { at, fragment: fragment.toLowerCase(), before: before, after: parts.after };
      }

      function renderMentionMenu(matches) {
        if (!matches.length) return hideMentionMenu();
        mentionMenuEl.innerHTML = matches
          .map((m, idx) => {
            const active = idx === mentionActive ? " active" : "";
            return (
              '<button type="button" class="mention-item' +
              active +
              '" data-mention-token="' +
              escapeHtml(m.token) +
              '">' +
              '<span class="mention-item-chip">' +
              escapeHtml(chipLabelFromEntry(m) || m.token) +
              "</span>" +
              "<small>" +
              escapeHtml(m.desc || m.type || "") +
              "</small></button>"
            );
          })
          .join("");
        mentionMenuEl.style.display = "block";
      }

      function updateMentionMenu() {
        const ctx = mentionContext();
        if (!ctx || !mentionEntries.length) return hideMentionMenu();
        const q = ctx.fragment || "";
        const matches = mentionEntries
          .filter((e) => e.token.toLowerCase().startsWith(q))
          .slice(0, 8);
        mentionMatches = matches;
        mentionActive = Math.min(mentionActive, Math.max(0, matches.length - 1));
        renderMentionMenu(matches);
      }

      function applyMentionToken(token) {
        const ctx = mentionContext();
        if (!ctx) return;
        if ((token === IC_SKILL_TOKEN || token === "intelligence-contract") && icEnabled) {
          enterIcComposerMode();
          hideMentionMenu();
          return;
        }
        const before = ctx.before.slice(0, ctx.at);
        const after = ctx.after;
        const inserted = before + "@" + token + " ";
        setComposerPlainText(inserted + after);
        placeComposerCaretAtPlainOffset(inserted.length);
        hideMentionMenu();
      }

      sendBtn.addEventListener("click", function () {
        if (chatStreaming) {
          stopChatStream();
          return;
        }
        sendMessage();
      });
      if (newChatBtn) {
        newChatBtn.addEventListener("click", startNewChat);
      }
      if (aiDisclaimerBtn) {
        aiDisclaimerBtn.addEventListener("click", openAiDisclaimerDialog);
      }
      if (aiDisclaimerCloseBtn) {
        aiDisclaimerCloseBtn.addEventListener("click", closeAiDisclaimerDialog);
      }
      if (aiDisclaimerModal) {
        aiDisclaimerModal.addEventListener("click", (e) => {
          if (e.target === aiDisclaimerModal) closeAiDisclaimerDialog();
        });
      }

      if (deleteSessionCancelBtn) {
        deleteSessionCancelBtn.addEventListener("click", closeDeleteSessionDialog);
      }
      if (deleteSessionConfirmBtn) {
        deleteSessionConfirmBtn.addEventListener("click", confirmDeleteSession);
      }
      if (deleteSessionModal) {
        deleteSessionModal.addEventListener("click", (e) => {
          if (e.target === deleteSessionModal) closeDeleteSessionDialog();
        });
      }
      document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        if (aiDisclaimerModal && !aiDisclaimerModal.hidden) {
          e.preventDefault();
          closeAiDisclaimerDialog();
          return;
        }
        if (deleteSessionModal && !deleteSessionModal.hidden) {
          e.preventDefault();
          closeDeleteSessionDialog();
        }
      });
      if (sidebarToggle && sessionSidebar) {
        sidebarToggle.addEventListener("click", () => {
          const collapsed = sessionSidebar.classList.toggle("collapsed");
          sidebarToggle.setAttribute(
            "aria-label",
            collapsed ? "Expand chat history" : "Collapse chat history"
          );
        });
      }
      window.addEventListener("message", (event) => {
        if (!event.data || event.data.type !== "dia-agent-open") return;
        if (!hasAgentEmbed()) return;
        initAgentChat();
      });
      if (composerAttachInput) {
        composerAttachInput.addEventListener("change", () => {
          const file = composerAttachInput.files && composerAttachInput.files[0];
          applyIcPdfFile(file || null);
          composerAttachInput.value = "";
        });
      }
      if (composerWrapEl) {
        composerWrapEl.addEventListener("dragover", (e) => {
          if (!icEnabled) return;
          e.preventDefault();
          composerWrapEl.classList.add("ic-drag");
        });
        composerWrapEl.addEventListener("dragleave", () => {
          composerWrapEl.classList.remove("ic-drag");
        });
        composerWrapEl.addEventListener("drop", (e) => {
          if (!icEnabled || !icModeActive) return;
          e.preventDefault();
          composerWrapEl.classList.remove("ic-drag");
          const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
          applyIcPdfFile(file || null);
        });
      }
      messageEl.addEventListener("keydown", (e) => {
        if (mentionMatches.length && e.key === "ArrowDown") {
          e.preventDefault();
          mentionActive = Math.min(mentionActive + 1, mentionMatches.length - 1);
          renderMentionMenu(mentionMatches);
          return;
        }
        if (mentionMatches.length && e.key === "ArrowUp") {
          e.preventDefault();
          mentionActive = Math.max(mentionActive - 1, 0);
          renderMentionMenu(mentionMatches);
          return;
        }
        if (mentionMatches.length && (e.key === "Tab" || e.key === "Enter")) {
          e.preventDefault();
          const chosen = mentionMatches[mentionActive] || mentionMatches[0];
          if (chosen) applyMentionToken(chosen.token);
          return;
        }
        if (mentionMatches.length && e.key === "Escape") {
          e.preventDefault();
          hideMentionMenu();
          return;
        }
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          e.preventDefault();
          sendMessage();
        }
      });
      messageEl.addEventListener("input", () => {
        updateMentionMenu();
      });
      messageEl.addEventListener("click", updateMentionMenu);
      messageEl.addEventListener("blur", () => {
        setTimeout(hideMentionMenu, 120);
      });
      mentionMenuEl.addEventListener("mousedown", (e) => {
        const btn = e.target.closest("[data-mention-token]");
        if (!btn) return;
        e.preventDefault();
        applyMentionToken(btn.getAttribute("data-mention-token"));
        if (icModeActive && icComposerEl) {
          const sel = icComposerEl.querySelector(".ic-trade-type-inline");
          if (sel) sel.focus();
        } else {
          messageEl.focus();
        }
      });

      initApp();
