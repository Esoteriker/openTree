/**
 * @template T
 * @param {T} initialState
 * @returns {{
 *   getState: () => T,
 *   setState: (update: Partial<T> | ((state: T) => Partial<T>)) => T,
 *   subscribe: (listener: (state: T) => void) => () => void
 * }}
 */
export function createStore(initialState) {
  let state = { ...initialState };
  const listeners = new Set();

  const getState = () => state;

  const setState = (update) => {
    const next = typeof update === "function" ? update(state) : update;
    if (!next || typeof next !== "object") {
      return state;
    }
    state = { ...state, ...next };
    listeners.forEach((listener) => listener(state));
    return state;
  };

  const subscribe = (listener) => {
    listeners.add(listener);
    listener(state);
    return () => listeners.delete(listener);
  };

  return { getState, setState, subscribe };
}
