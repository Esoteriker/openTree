import "./components/knowledge-tree.js";
import "./components/question-suggestions.js";

const STORAGE_KEY = "opentree.api_base_url";

class OpenTreeMVP {
  constructor() {
    this.state = {
      apiBaseUrl: "http://127.0.0.1:8101",
      sessionId: "",
    };

    this.elements = {
      apiBaseUrl: document.querySelector("#api-base-url"),
      sessionId: document.querySelector("#session-id"),
      status: document.querySelector("#status"),
      createSession: document.querySelector("#create-session"),
      sendForm: document.querySelector("#send-turn-form"),
      speaker: document.querySelector("#speaker"),
      content: document.querySelector("#content"),
      activity: document.querySelector("#activity"),
      tree: document.querySelector("knowledge-tree-editor"),
      suggestions: document.querySelector("question-suggestions"),
    };
  }

  init() {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (saved) {
      this.state.apiBaseUrl = saved;
    }

    this.elements.apiBaseUrl.value = this.state.apiBaseUrl;
    this._setStatus("Idle");

    this.elements.createSession.addEventListener("click", () => this.createSession());
    this.elements.sendForm.addEventListener("submit", (event) => {
      event.preventDefault();
      this.sendTurn();
    });

    this.elements.suggestions.addEventListener("suggestion-picked", (event) => {
      this.elements.content.value = event.detail.question;
      this.elements.content.focus();
    });
  }

  _headers() {
    return {
      "Content-Type": "application/json",
      "X-Tenant-ID": "public",
    };
  }

  _setStatus(text) {
    this.elements.status.textContent = text;
  }

  _addActivity(text) {
    const item = document.createElement("li");
    item.textContent = text;
    this.elements.activity.prepend(item);
  }

  _api(path) {
    const raw = this.elements.apiBaseUrl.value.trim() || this.state.apiBaseUrl;
    this.state.apiBaseUrl = raw.replace(/\/$/, "");
    window.localStorage.setItem(STORAGE_KEY, this.state.apiBaseUrl);
    return `${this.state.apiBaseUrl}${path}`;
  }

  async createSession() {
    this._setStatus("Creating session...");
    try {
      const response = await fetch(this._api("/v1/sessions"), {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify({ user_id: "ui-shell-user", metadata: { source: "ui-shell" } }),
      });
      if (!response.ok) {
        throw new Error(`Session request failed (${response.status})`);
      }
      const data = await response.json();
      this.state.sessionId = data.session_id;
      this.elements.sessionId.textContent = this.state.sessionId;
      this._setStatus("Session ready");
      this._addActivity(`Session created: ${this.state.sessionId}`);
    } catch (error) {
      this._setStatus("Session failed");
      this._addActivity(`Error: ${error.message}`);
    }
  }

  async sendTurn() {
    const content = this.elements.content.value.trim();
    if (!content) {
      return;
    }

    if (!this.state.sessionId) {
      await this.createSession();
      if (!this.state.sessionId) {
        return;
      }
    }

    this._setStatus("Sending turn...");
    try {
      const response = await fetch(this._api(`/v1/sessions/${this.state.sessionId}/turns`), {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify({
          speaker: this.elements.speaker.value,
          content,
        }),
      });
      if (!response.ok) {
        throw new Error(`Turn request failed (${response.status})`);
      }
      const payload = await response.json();
      this._addActivity(
        `Turn ${payload.turn.turn_id}: ${payload.parse.concepts.length} concepts, ${payload.parse.relations.length} relations`
      );

      this.elements.suggestions.setSuggestions(payload.suggested_questions || []);
      await this.refreshGraph();

      this.elements.content.value = "";
      this._setStatus("Turn processed");
    } catch (error) {
      this._setStatus("Turn failed");
      this._addActivity(`Error: ${error.message}`);
    }
  }

  async refreshGraph() {
    const response = await fetch(this._api(`/v1/sessions/${this.state.sessionId}/graph`), {
      method: "GET",
      headers: this._headers(),
    });
    if (!response.ok) {
      throw new Error(`Graph fetch failed (${response.status})`);
    }
    const graph = await response.json();
    this.elements.tree.setGraph(graph.concepts || [], graph.relations || []);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const app = new OpenTreeMVP();
  app.init();
});
