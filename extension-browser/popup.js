const $ = (id) => document.getElementById(id);

function render(entry) {
  if (!entry) return;
  const parts = [];
  if (entry.literal) parts.push(`字面：${entry.literal}`);
  if (entry.meaning) parts.push(`含义：${entry.meaning}`);
  if (entry.example) parts.push(`例句：${entry.example}`);
  $("result").textContent = parts.join("\n");
  const sourceMap = { local: "本地词库", llm: "AI 解释", "llm-cache": "AI 缓存" };
  $("meta").textContent = (sourceMap[entry.source] || "") + (entry.category ? `  ·  ${entry.category}` : "");
}

async function query() {
  const q = $("q").value.trim();
  if (!q) return;
  $("result").textContent = "查询中...";
  $("meta").textContent = "";
  chrome.runtime.sendMessage({ type: "lookup", query: q }, (res) => {
    if (!res?.ok) {
      $("result").textContent = "查询失败：" + (res?.error || "未知");
      return;
    }
    if (res.hit) {
      render(res.entry);
      return;
    }
    // 本地未命中，尝试 LLM
    $("result").textContent = "本地未收录，调用 AI...";
    chrome.runtime.sendMessage({ type: "lookup-llm", query: q }, (r2) => {
      if (!r2?.ok) {
        $("result").textContent = "AI 失败：" + (r2?.error || "未知");
        return;
      }
      if (r2.entry.error) {
        $("result").textContent = r2.entry.error;
        return;
      }
      render(r2.entry);
    });
  });
}

$("go").addEventListener("click", query);
$("q").addEventListener("keydown", (e) => {
  if (e.key === "Enter") query();
});
$("openOptions").addEventListener("click", (e) => {
  e.preventDefault();
  chrome.runtime.openOptionsPage();
});
