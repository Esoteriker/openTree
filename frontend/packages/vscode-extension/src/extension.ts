import * as vscode from "vscode";

type DialogueTurnResponse = {
  suggested_questions?: Array<{ question: string; reason: string; priority: number }>;
};

async function getOrCreateSessionId(context: vscode.ExtensionContext, apiBaseUrl: string): Promise<string> {
  const key = "openTreeSessionId";
  const existing = context.workspaceState.get<string>(key);
  if (existing) {
    return existing;
  }

  const response = await fetch(`${apiBaseUrl}/v1/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: "vscode-user", metadata: { source: "vscode-extension" } }),
  });

  if (!response.ok) {
    throw new Error(`Failed to create OpenTree session: ${response.status}`);
  }

  const payload = (await response.json()) as { session_id: string };
  await context.workspaceState.update(key, payload.session_id);
  return payload.session_id;
}

async function pushTurn(
  context: vscode.ExtensionContext,
  apiBaseUrl: string,
  content: string,
  speaker = "user"
): Promise<DialogueTurnResponse> {
  const sessionId = await getOrCreateSessionId(context, apiBaseUrl);
  const response = await fetch(`${apiBaseUrl}/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ speaker, content }),
  });

  if (!response.ok) {
    throw new Error(`Failed to upload turn: ${response.status}`);
  }

  return (await response.json()) as DialogueTurnResponse;
}

function renderSuggestionPanel(suggestions: string[]) {
  const panel = vscode.window.createWebviewPanel(
    "openTreeSuggestions",
    "OpenTree Suggestions",
    vscode.ViewColumn.Beside,
    {}
  );

  const items = suggestions.length
    ? suggestions.map((q) => `<li>${q}</li>`).join("")
    : "<li>No suggestions yet. Capture a selection first.</li>";

  panel.webview.html = `
    <!doctype html>
    <html>
      <body style="font-family: sans-serif; padding: 12px;">
        <h2>Follow-up Questions</h2>
        <ul>${items}</ul>
      </body>
    </html>
  `;
}

export function activate(context: vscode.ExtensionContext) {
  const suggestionsKey = "openTreeLatestSuggestions";

  const captureSelection = vscode.commands.registerCommand("opentree.captureSelection", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("OpenTree: No active editor.");
      return;
    }

    const text = editor.document.getText(editor.selection).trim();
    if (!text) {
      vscode.window.showInformationMessage("OpenTree: Select text first.");
      return;
    }

    const apiBaseUrl = vscode.workspace.getConfiguration().get<string>("opentree.apiBaseUrl") || "http://127.0.0.1:8101";

    try {
      const result = await pushTurn(context, apiBaseUrl, text, "assistant");
      const suggestions = (result.suggested_questions || []).map((s) => s.question);
      await context.workspaceState.update(suggestionsKey, suggestions);
      vscode.window.showInformationMessage("OpenTree: Selection captured.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      vscode.window.showErrorMessage(`OpenTree: ${message}`);
    }
  });

  const showPanel = vscode.commands.registerCommand("opentree.showPanel", async () => {
    const suggestions = context.workspaceState.get<string[]>(suggestionsKey) || [];
    renderSuggestionPanel(suggestions);
  });

  context.subscriptions.push(captureSelection, showPanel);
}

export function deactivate() {
  // no-op
}
