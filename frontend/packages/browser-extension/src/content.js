const OPEN_TREE_API = "http://127.0.0.1:8101";

async function getOrCreateSessionId() {
  const key = "openTreeSessionId";
  const cached = localStorage.getItem(key);
  if (cached) {
    return cached;
  }

  const response = await fetch(`${OPEN_TREE_API}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: "browser-extension-user",
      metadata: { source: "webextension" },
    }),
  });

  if (!response.ok) {
    throw new Error(`Session creation failed: ${response.status}`);
  }

  const data = await response.json();
  localStorage.setItem(key, data.session_id);
  return data.session_id;
}

async function pushTurn(content, speaker = "user") {
  const sessionId = await getOrCreateSessionId();
  const response = await fetch(`${OPEN_TREE_API}/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speaker, content }),
  });

  if (!response.ok) {
    throw new Error(`Turn upload failed: ${response.status}`);
  }

  return response.json();
}

async function captureSelection() {
  const selection = window.getSelection();
  const text = selection ? selection.toString().trim() : "";
  if (!text) {
    return;
  }

  try {
    const result = await pushTurn(text, "assistant");
    const message = result.suggested_questions?.[0]?.question;
    if (message) {
      console.info("OpenTree suggestion:", message);
    }
  } catch (error) {
    console.warn("OpenTree capture failed", error);
  }
}

window.addEventListener("keydown", (event) => {
  if (event.altKey && event.shiftKey && event.key.toLowerCase() === "k") {
    captureSelection();
  }
});

console.info("OpenTree content script ready. Use Alt+Shift+K to capture selected text.");
