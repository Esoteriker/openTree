class KnowledgeTreeEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.concepts = [];
    this.relations = [];
    this.draggedId = null;
    this.notes = new Map();
    this.parentOverrides = new Map();
  }

  connectedCallback() {
    this.render();
  }

  setGraph(concepts, relations) {
    this.concepts = Array.isArray(concepts) ? concepts : [];
    this.relations = Array.isArray(relations) ? relations : [];
    this.render();
  }

  _buildNodeMap() {
    const nodeMap = new Map();
    for (const concept of this.concepts) {
      nodeMap.set(concept.node_id, {
        id: concept.node_id,
        title: concept.canonical_name,
        confidence: concept.confidence,
        parentId: null,
        relationLabel: "",
      });
    }

    for (const relation of this.relations) {
      const child = nodeMap.get(relation.target_node_id);
      if (!child || child.parentId) {
        continue;
      }
      if (!nodeMap.has(relation.source_node_id)) {
        continue;
      }
      child.parentId = relation.source_node_id;
      child.relationLabel = relation.relation_type;
    }

    for (const [nodeId, parentId] of this.parentOverrides.entries()) {
      const node = nodeMap.get(nodeId);
      if (!node) {
        continue;
      }
      node.parentId = parentId;
      node.relationLabel = "manual";
    }

    return nodeMap;
  }

  _children(nodeMap, parentId) {
    return Array.from(nodeMap.values()).filter((node) => node.parentId === parentId);
  }

  _isDescendant(nodeMap, sourceId, targetId) {
    let current = nodeMap.get(targetId);
    let guard = 0;
    while (current && current.parentId && guard < 2000) {
      if (current.parentId === sourceId) {
        return true;
      }
      current = nodeMap.get(current.parentId);
      guard += 1;
    }
    return false;
  }

  _renderNode(nodeMap, node, depth = 0) {
    const item = document.createElement("li");
    item.className = "node";
    item.draggable = true;
    item.dataset.nodeId = node.id;
    item.style.setProperty("--depth", String(depth));

    const note = this.notes.get(node.id) || "No annotation";
    const confidence = Number(node.confidence || 0).toFixed(2);

    item.innerHTML = `
      <article>
        <header>
          <strong>${node.title}</strong>
          <button data-action="annotate" data-node="${node.id}">Annotate</button>
        </header>
        <p>confidence: ${confidence}${node.relationLabel ? ` | ${node.relationLabel}` : ""}</p>
        <small>${note}</small>
      </article>
    `;

    const children = this._children(nodeMap, node.id);
    if (children.length) {
      const list = document.createElement("ul");
      for (const child of children) {
        list.appendChild(this._renderNode(nodeMap, child, depth + 1));
      }
      item.appendChild(list);
    }

    return item;
  }

  render() {
    const nodeMap = this._buildNodeMap();
    const roots = this._children(nodeMap, null);

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        .head {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin-bottom: 10px;
        }
        h2 {
          margin: 0;
          font-size: 1.05rem;
        }
        small.meta {
          color: #6b7280;
        }
        ul {
          list-style: none;
          margin: 0;
          padding-left: 0;
        }
        .node {
          margin-top: 8px;
          border: 1px solid #d2b48c;
          border-radius: 10px;
          padding: 10px;
          margin-left: calc(var(--depth) * 14px);
          background: #fff;
          transition: transform 0.12s ease;
        }
        .node:hover {
          transform: translateX(3px);
        }
        article > header {
          display: flex;
          justify-content: space-between;
          gap: 8px;
        }
        p {
          margin: 6px 0 2px;
          color: #374151;
          font-size: 0.85rem;
        }
        button {
          border: 1px solid #c59e63;
          background: #fffaef;
          border-radius: 6px;
          padding: 3px 8px;
          font-size: 0.8rem;
          cursor: pointer;
        }
      </style>
      <div class="head">
        <h2>Knowledge Tree</h2>
        <small class="meta">${this.concepts.length} concepts, ${this.relations.length} relations</small>
      </div>
      <ul id="root"></ul>
    `;

    const root = this.shadowRoot.querySelector("#root");
    if (!roots.length) {
      root.innerHTML = "<li class='node' style='--depth:0'>No graph data yet. Send a turn first.</li>";
    } else {
      roots.forEach((node) => root.appendChild(this._renderNode(nodeMap, node)));
    }

    this.shadowRoot.querySelectorAll(".node").forEach((element) => {
      element.addEventListener("dragstart", (event) => {
        this.draggedId = event.currentTarget.dataset.nodeId;
      });

      element.addEventListener("dragover", (event) => {
        event.preventDefault();
      });

      element.addEventListener("drop", (event) => {
        event.preventDefault();
        const targetId = event.currentTarget.dataset.nodeId;
        if (!this.draggedId || this.draggedId === targetId) {
          return;
        }
        if (this._isDescendant(nodeMap, this.draggedId, targetId)) {
          return;
        }
        this.parentOverrides.set(this.draggedId, targetId);
        this.render();
      });
    });

    this.shadowRoot.querySelectorAll("button[data-action='annotate']").forEach((button) => {
      button.addEventListener("click", (event) => {
        const nodeId = event.currentTarget.dataset.node;
        const current = this.notes.get(nodeId) || "";
        const next = window.prompt("Add note or reference link", current);
        if (next !== null) {
          this.notes.set(nodeId, next);
          this.render();
        }
      });
    });
  }
}

customElements.define("knowledge-tree-editor", KnowledgeTreeEditor);
