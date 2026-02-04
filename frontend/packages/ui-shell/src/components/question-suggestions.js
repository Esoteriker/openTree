class QuestionSuggestions extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.suggestions = [];
  }

  connectedCallback() {
    this.render();
  }

  setSuggestions(items) {
    this.suggestions = Array.isArray(items) ? items : [];
    this.render();
  }

  render() {
    const items = this.suggestions.length
      ? this.suggestions.map(
          (item) => `
            <li>
              <div>${item.question}</div>
              <small>${item.reason || "Suggested by gap analysis"}</small>
              <button data-question="${item.question}">Use Prompt</button>
            </li>
          `
        )
      : [
          `
            <li>
              <div>No suggestions yet.</div>
              <small>Send a dialogue turn to generate follow-up prompts.</small>
            </li>
          `,
        ];

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        h2 {
          margin: 0;
          font-size: 1.05rem;
        }
        ul {
          list-style: none;
          margin: 10px 0 0;
          padding: 0;
          display: grid;
          gap: 8px;
        }
        li {
          border: 1px solid #89b6a8;
          border-radius: 10px;
          background: #f6fffc;
          padding: 10px;
        }
        button {
          margin-top: 6px;
          border: 1px solid #0f766e;
          background: #0f766e;
          color: #fff;
          border-radius: 6px;
          padding: 4px 8px;
          cursor: pointer;
          font-size: 0.85rem;
        }
        small {
          color: #4b5563;
          display: block;
          margin-top: 4px;
        }
      </style>
      <h2>Suggested Follow-up Questions</h2>
      <ul>
        ${items.join("")}
      </ul>
    `;

    this.shadowRoot.querySelectorAll("button[data-question]").forEach((button) => {
      button.addEventListener("click", (event) => {
        const q = event.currentTarget.dataset.question;
        this.dispatchEvent(
          new CustomEvent("suggestion-picked", {
            bubbles: true,
            composed: true,
            detail: { question: q },
          })
        );
      });
    });
  }
}

customElements.define("question-suggestions", QuestionSuggestions);
