const $ = (id) => document.getElementById(id);

function setStatus(msg, isErr) {
  const el = $("status");
  el.textContent = msg;
  el.classList.toggle("err", !!isErr);
  if (msg) {
    setTimeout(() => {
      if (el.textContent === msg) {
        el.textContent = "";
        el.classList.remove("err");
      }
    }, 3000);
  }
}

async function load() {
  const cfg = await chrome.storage.sync.get(["provider", "apiKey", "model"]);
  $("provider").value = cfg.provider || "anthropic";
  $("apiKey").value = cfg.apiKey || "";
  $("model").value = cfg.model || "";
}

async function save() {
  const provider = $("provider").value;
  const apiKey = $("apiKey").value.trim();
  const model = $("model").value.trim();
  await chrome.storage.sync.set({ provider, apiKey, model });
  setStatus("已保存");
}

async function clearCache() {
  chrome.runtime.sendMessage({ type: "clear-llm-cache" }, (res) => {
    if (res?.ok) {
      setStatus(`已清空 ${res.cleared} 条缓存`);
    } else {
      setStatus("清空失败：" + (res?.error || "未知错误"), true);
    }
  });
}

$("save").addEventListener("click", save);
$("clearCache").addEventListener("click", clearCache);
load();
