// codelang content script
// - listens for mouseup, detects selected text
// - asks background for lookup, renders card next to selection
// - card closes on outside click or Esc

(() => {
  if (window.__codelangInjected) return;
  window.__codelangInjected = true;

  let cardEl = null;

  const CATEGORY_LABEL = {
    devterm: "开发术语",
    jargon: "互联网黑话",
    abbr: "缩写",
    slang: "职场俚语",
    llm: "AI 解释",
    misc: "其他",
  };

  function isInsideOurCard(node) {
    return cardEl && (node === cardEl || cardEl.contains(node));
  }

  function isInsideEditable(node) {
    let n = node;
    while (n && n !== document.body) {
      if (n.nodeType === 1) {
        const el = n;
        if (el.isContentEditable) return true;
        const tag = el.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA") return true;
      }
      n = n.parentNode;
    }
    return false;
  }

  function removeCard() {
    if (cardEl) {
      cardEl.remove();
      cardEl = null;
    }
  }

  function makeCard() {
    removeCard();
    const el = document.createElement("div");
    el.className = "codelang-card";
    el.innerHTML = `
      <div class="cl-head">
        <span class="cl-term"></span>
        <span class="cl-cat"></span>
        <button class="cl-close" title="关闭">×</button>
      </div>
      <div class="cl-body">
        <div class="cl-row cl-literal"><span class="cl-label">字面</span><span class="cl-val"></span></div>
        <div class="cl-row cl-meaning"><span class="cl-label">含义</span><span class="cl-val"></span></div>
        <div class="cl-row cl-example"><span class="cl-label">例句</span><span class="cl-val"></span></div>
        <div class="cl-empty" style="display:none">本地词库未收录</div>
        <button class="cl-ask" style="display:none">用 AI 解释</button>
        <div class="cl-loading" style="display:none">查询中...</div>
        <div class="cl-error" style="display:none"></div>
      </div>
      <div class="cl-foot">
        <span class="cl-source"></span>
      </div>
    `;
    document.documentElement.appendChild(el);
    el.querySelector(".cl-close").addEventListener("click", removeCard);
    cardEl = el;
    return el;
  }

  function positionCard(rect) {
    if (!cardEl) return;
    const margin = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    cardEl.style.visibility = "hidden";
    cardEl.style.left = "0px";
    cardEl.style.top = "0px";
    const cw = cardEl.offsetWidth;
    const ch = cardEl.offsetHeight;

    let left = rect.left + rect.width / 2 - cw / 2;
    left = Math.max(margin, Math.min(vw - cw - margin, left));

    let top = rect.bottom + margin;
    if (top + ch > vh - margin) {
      top = rect.top - ch - margin;
      if (top < margin) top = vh - ch - margin;
    }

    cardEl.style.left = left + window.scrollX + "px";
    cardEl.style.top = top + window.scrollY + "px";
    cardEl.style.visibility = "visible";
  }

  function renderEntry(entry) {
    if (!cardEl) return;
    cardEl.querySelector(".cl-term").textContent = entry.term;
    const cat = CATEGORY_LABEL[entry.category] || entry.category || "";
    cardEl.querySelector(".cl-cat").textContent = cat;
    const setRow = (cls, val) => {
      const row = cardEl.querySelector("." + cls);
      if (val) {
        row.style.display = "";
        row.querySelector(".cl-val").textContent = val;
      } else {
        row.style.display = "none";
      }
    };
    setRow("cl-literal", entry.literal);
    setRow("cl-meaning", entry.meaning);
    setRow("cl-example", entry.example);
    cardEl.querySelector(".cl-empty").style.display = "none";
    cardEl.querySelector(".cl-ask").style.display = "none";
    cardEl.querySelector(".cl-loading").style.display = "none";
    cardEl.querySelector(".cl-error").style.display = "none";
    const sourceMap = {
      local: "本地词库",
      llm: "AI 解释",
      "llm-cache": "AI 解释（缓存）",
    };
    cardEl.querySelector(".cl-source").textContent = sourceMap[entry.source] || "";
  }

  function renderMiss(query) {
    if (!cardEl) return;
    cardEl.querySelector(".cl-term").textContent = query;
    cardEl.querySelector(".cl-cat").textContent = "未收录";
    ["cl-literal", "cl-meaning", "cl-example"].forEach((c) => {
      cardEl.querySelector("." + c).style.display = "none";
    });
    cardEl.querySelector(".cl-empty").style.display = "";
    const askBtn = cardEl.querySelector(".cl-ask");
    askBtn.style.display = "";
    askBtn.onclick = () => askLlm(query);
    cardEl.querySelector(".cl-loading").style.display = "none";
    cardEl.querySelector(".cl-error").style.display = "none";
    cardEl.querySelector(".cl-source").textContent = "";
  }

  function showLoading() {
    if (!cardEl) return;
    cardEl.querySelector(".cl-loading").style.display = "";
    cardEl.querySelector(".cl-ask").style.display = "none";
    cardEl.querySelector(".cl-error").style.display = "none";
  }

  function showError(msg) {
    if (!cardEl) return;
    const el = cardEl.querySelector(".cl-error");
    el.textContent = msg;
    el.style.display = "";
    cardEl.querySelector(".cl-loading").style.display = "none";
  }

  function askLlm(query) {
    showLoading();
    chrome.runtime.sendMessage({ type: "lookup-llm", query }, (res) => {
      if (chrome.runtime.lastError) {
        showError("扩展通信失败：" + chrome.runtime.lastError.message);
        return;
      }
      if (!res?.ok) {
        showError(res?.error || "查询失败");
        return;
      }
      const entry = res.entry;
      if (entry.error) {
        showError(entry.error);
        return;
      }
      renderEntry(entry);
    });
  }

  function isReasonableQuery(text) {
    const t = text.trim();
    if (!t) return false;
    if (t.length > 32) return false;
    if (/\n/.test(t)) return false;
    return true;
  }

  function onMouseUp(e) {
    if (isInsideOurCard(e.target)) return;
    setTimeout(() => {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed) return;
      const text = sel.toString();
      if (!isReasonableQuery(text)) return;
      const anchor = sel.anchorNode;
      if (anchor && isInsideEditable(anchor)) return;

      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      makeCard();
      positionCard(rect);
      cardEl.querySelector(".cl-term").textContent = text;
      cardEl.querySelector(".cl-cat").textContent = "查询中...";

      chrome.runtime.sendMessage({ type: "lookup", query: text }, (res) => {
        if (chrome.runtime.lastError) {
          showError("扩展通信失败：" + chrome.runtime.lastError.message);
          return;
        }
        if (!res?.ok) {
          showError(res?.error || "查询失败");
          return;
        }
        if (res.hit) {
          renderEntry(res.entry);
          positionCard(rect);
        } else {
          renderMiss(text);
          positionCard(rect);
        }
      });
    }, 10);
  }

  document.addEventListener("mouseup", onMouseUp, true);
  document.addEventListener("mousedown", (e) => {
    if (cardEl && !isInsideOurCard(e.target)) removeCard();
  }, true);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") removeCard();
  });
})();
