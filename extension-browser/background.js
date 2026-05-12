// codelang background service worker
// - loads dict.json once and caches in memory
// - serves lookup requests from content script
// - on miss, optionally calls LLM (Anthropic / OpenAI) using key from chrome.storage.sync
// - caches LLM responses to chrome.storage.local

const DICT_URL = chrome.runtime.getURL("dict.json");
let DICT = null;
let DICT_LOADING = null;

function normalize(s) {
  return String(s || "").trim().toLowerCase().replace(/[\s\-_]/g, "");
}

async function loadDict() {
  if (DICT) return DICT;
  if (DICT_LOADING) return DICT_LOADING;
  DICT_LOADING = fetch(DICT_URL)
    .then((r) => r.json())
    .then((data) => {
      DICT = data;
      return data;
    })
    .catch((e) => {
      console.error("[codelang] failed to load dict.json", e);
      DICT_LOADING = null;
      throw e;
    });
  return DICT_LOADING;
}

function lookupLocal(dict, query) {
  const nk = normalize(query);
  if (!nk) return null;
  const idx = dict.index[nk];
  if (idx === undefined) return null;
  return { source: "local", ...dict.entries[idx] };
}

async function getLlmCache(query) {
  const key = "llm:" + normalize(query);
  const obj = await chrome.storage.local.get(key);
  return obj[key] || null;
}

async function setLlmCache(query, entry) {
  const key = "llm:" + normalize(query);
  await chrome.storage.local.set({ [key]: entry });
}

const ANTHROPIC_SYSTEM = `你是中文程序员/职场术语解释器。给定一个词，输出 JSON：
{"literal":"字面意思（一句）","meaning":"实际含义（1-3 句，讲清在中文互联网语境里到底是什么）","example":"一个具体例句"}
规则：
- 只输出 JSON，不要解释、不要 markdown 围栏
- 如果词有歧义，按"中文互联网公司/程序员日常"语境解释
- 如果词不属于任何技术/职场/网络语境，meaning 字段填"暂无相关释义"`;

async function callAnthropic(apiKey, model, query) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true",
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: model || "claude-haiku-4-5-20251001",
      max_tokens: 400,
      system: ANTHROPIC_SYSTEM,
      messages: [{ role: "user", content: `解释这个词：${query}` }],
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Anthropic ${res.status}: ${text}`);
  }
  const data = await res.json();
  const text = data.content?.[0]?.text || "";
  return parseLlmJson(text);
}

async function callOpenAI(apiKey, model, query) {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: model || "gpt-4o-mini",
      response_format: { type: "json_object" },
      messages: [
        { role: "system", content: ANTHROPIC_SYSTEM },
        { role: "user", content: `解释这个词：${query}` },
      ],
    }),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`OpenAI ${res.status}: ${text}`);
  }
  const data = await res.json();
  const text = data.choices?.[0]?.message?.content || "";
  return parseLlmJson(text);
}

function parseLlmJson(text) {
  let s = String(text).trim();
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) s = fence[1];
  return JSON.parse(s);
}

async function lookupRemote(query) {
  const cached = await getLlmCache(query);
  if (cached) return { source: "llm-cache", ...cached };

  const cfg = await chrome.storage.sync.get(["provider", "apiKey", "model"]);
  if (!cfg.apiKey) {
    return { source: "no-key", error: "未配置 API key，请到扩展选项页设置" };
  }

  let parsed;
  try {
    if (cfg.provider === "openai") {
      parsed = await callOpenAI(cfg.apiKey, cfg.model, query);
    } else {
      parsed = await callAnthropic(cfg.apiKey, cfg.model, query);
    }
  } catch (e) {
    return { source: "llm-error", error: String(e.message || e) };
  }

  const entry = {
    term: query,
    category: "llm",
    literal: parsed.literal || "",
    meaning: parsed.meaning || "",
    example: parsed.example || "",
  };
  await setLlmCache(query, entry);
  return { source: "llm", ...entry };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "lookup") {
    (async () => {
      try {
        const dict = await loadDict();
        const local = lookupLocal(dict, msg.query);
        if (local) {
          sendResponse({ ok: true, hit: true, entry: local });
        } else {
          sendResponse({ ok: true, hit: false });
        }
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg?.type === "lookup-llm") {
    (async () => {
      try {
        const entry = await lookupRemote(msg.query);
        sendResponse({ ok: true, entry });
      } catch (e) {
        sendResponse({ ok: false, error: String(e.message || e) });
      }
    })();
    return true;
  }
  if (msg?.type === "clear-llm-cache") {
    (async () => {
      const all = await chrome.storage.local.get(null);
      const keys = Object.keys(all).filter((k) => k.startsWith("llm:"));
      await chrome.storage.local.remove(keys);
      sendResponse({ ok: true, cleared: keys.length });
    })();
    return true;
  }
});
