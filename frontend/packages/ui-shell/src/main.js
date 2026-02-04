import "./components/knowledge-tree.js";
import "./components/question-suggestions.js";
import { OpenTreeApi } from "./api.js";
import { createStore } from "./state.js";

const STORAGE_KEY = "opentree.api_base_url";
const DEFAULT_API_BASE_URL = "http://127.0.0.1:8101";
const MAX_ACTIVITY = 40;

class OpenTreeMVP {
  constructor() {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    this.store = createStore({
      apiBaseUrl: saved || DEFAULT_API_BASE_URL,
      sessionId: "",
      status: "Idle",
      activity: [],
    });
    this.api = new OpenTreeApi(() => this.store.getState().apiBaseUrl);

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
    this.elements.apiBaseUrl.value = this.store.getState().apiBaseUrl;

    this.store.subscribe((state) => {
      this.elements.status.textContent = state.status;
      this.elements.sessionId.textContent = state.sessionId || "not created";
      this._renderActivity(state.activity);
    });

    this.elements.createSession.addEventListener("click", () => this.createSession());
    this.elements.sendForm.addEventListener("submit", (event) => {
      event.preventDefault();
      this.sendTurn();
    });

    const commitApiBaseUrl = () => {
      const raw = this.elements.apiBaseUrl.value.trim();
      const next = raw ? raw.replace(/\/$/, "") : this.store.getState().apiBaseUrl;
      this.elements.apiBaseUrl.value = next;
      window.localStorage.setItem(STORAGE_KEY, next);
      this.store.setState({ apiBaseUrl: next });
    };

    this.elements.apiBaseUrl.addEventListener("change", commitApiBaseUrl);
    this.elements.apiBaseUrl.addEventListener("blur", commitApiBaseUrl);
    this.elements.apiBaseUrl.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        commitApiBaseUrl();
        this.elements.apiBaseUrl.blur();
      }
    });

    this.elements.suggestions.addEventListener("suggestion-picked", (event) => {
      this.elements.content.value = event.detail.question;
      this.elements.content.focus();
    });
  }

  _setStatus(text) {
    this.store.setState({ status: text });
  }

  _addActivity(text) {
    this.store.setState((state) => {
      const next = [text, ...state.activity].slice(0, MAX_ACTIVITY);
      return { activity: next };
    });
  }

  _renderActivity(items) {
    this.elements.activity.innerHTML = "";
    items.forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      this.elements.activity.appendChild(item);
    });
  }

  async createSession() {
    this._setStatus("Creating session...");
    try {
      const data = await this.api.createSession({
        userId: "ui-shell-user",
        metadata: { source: "ui-shell" },
      });
      this.store.setState({ sessionId: data.session_id });
      this._setStatus("Session ready");
      this._addActivity(`Session created: ${data.session_id}`);
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

    const { sessionId } = this.store.getState();
    if (!sessionId) {
      await this.createSession();
      if (!this.store.getState().sessionId) {
        return;
      }
    }

    this._setStatus("Sending turn...");
    try {
      const payload = await this.api.sendTurn({
        sessionId: this.store.getState().sessionId,
        speaker: this.elements.speaker.value,
        content,
      });
      const parse = payload.parse || { concepts: [], relations: [] };
      this._addActivity(
        `Turn ${payload.turn.turn_id}: ${parse.concepts.length} concepts, ${parse.relations.length} relations`
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
    const { sessionId } = this.store.getState();
    if (!sessionId) {
      return;
    }
    const graph = await this.api.fetchGraph(sessionId);
    this.elements.tree.setGraph(graph.concepts || [], graph.relations || []);
  }
}

window.addEventListener("DOMContentLoaded", () => {
  const app = new OpenTreeMVP();
  app.init();
});
