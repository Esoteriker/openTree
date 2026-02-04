/**
 * @typedef {Object} Concept
 * @property {string} node_id
 * @property {string} canonical_name
 * @property {number} confidence
 */

/**
 * @typedef {Object} Relation
 * @property {string} source_node_id
 * @property {string} target_node_id
 * @property {string} relation_type
 */

/**
 * @typedef {Object} ParseResult
 * @property {Concept[]} concepts
 * @property {Relation[]} relations
 */

/**
 * @typedef {Object} TurnResponse
 * @property {{ turn_id: string }} turn
 * @property {ParseResult} parse
 * @property {{ question: string, reason?: string }[]} [suggested_questions]
 */

/**
 * @typedef {Object} GraphResponse
 * @property {Concept[]} concepts
 * @property {Relation[]} relations
 */

/**
 * @typedef {Object} SessionResponse
 * @property {string} session_id
 */

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   * @param {unknown} payload
   */
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

export class OpenTreeApi {
  /**
   * @param {() => string} getBaseUrl
   * @param {{ tenantId?: string }} [options]
   */
  constructor(getBaseUrl, options = {}) {
    this.getBaseUrl = getBaseUrl;
    this.tenantId = options.tenantId || "public";
  }

  _headers() {
    return {
      "Content-Type": "application/json",
      "X-Tenant-ID": this.tenantId,
    };
  }

  _url(path) {
    const raw = (this.getBaseUrl() || "").trim().replace(/\/$/, "");
    return `${raw}${path}`;
  }

  async _request(path, options) {
    const response = await fetch(this._url(path), {
      headers: this._headers(),
      ...options,
    });
    const text = await response.text();
    let payload = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch (error) {
        payload = text;
      }
    }
    if (!response.ok) {
      throw new ApiError(`Request failed (${response.status})`, response.status, payload);
    }
    return payload;
  }

  /**
   * @param {{ userId?: string, metadata?: Record<string, unknown> }} [input]
   * @returns {Promise<SessionResponse>}
   */
  async createSession(input = {}) {
    const body = {
      user_id: input.userId || "ui-shell-user",
      metadata: input.metadata || { source: "ui-shell" },
    };
    return this._request("/v1/sessions", {
      method: "POST",
      body: JSON.stringify(body),
    });
  }

  /**
   * @param {{ sessionId: string, speaker: string, content: string }} input
   * @returns {Promise<TurnResponse>}
   */
  async sendTurn(input) {
    return this._request(`/v1/sessions/${input.sessionId}/turns`, {
      method: "POST",
      body: JSON.stringify({
        speaker: input.speaker,
        content: input.content,
      }),
    });
  }

  /**
   * @param {string} sessionId
   * @returns {Promise<GraphResponse>}
   */
  async fetchGraph(sessionId) {
    return this._request(`/v1/sessions/${sessionId}/graph`, {
      method: "GET",
    });
  }
}
