// Load the dashboard's browser scripts in Node, against the smallest DOM they
// touch, a scripted fetch, and a clock the test drives.
//
// The SPA files are plain browser IIFEs (they assign to `window.*`), so they
// run unmodified inside a vm context. What they need from the page is provided
// here: getElementById returns inert elements that keep their innerHTML,
// querySelector(All) find nothing (so no handlers bind), and timers and
// Date.now() run on a fake clock, which lets a test advance ten minutes of
// polling in milliseconds and count exactly which requests went out.

import vm from "node:vm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const DASHBOARD = join(dirname(fileURLToPath(import.meta.url)), "..");

export class FakeClock {
  constructor(start = Date.parse("2026-09-25T14:00:00Z")) {
    this.now = start;
    this.timers = [];
    this.nextId = 1;
    this.setTimeout = (fn, ms = 0) => this.#add(fn, ms, null);
    this.setInterval = (fn, ms = 0) => this.#add(fn, ms, Math.max(1, ms));
    this.clear = (id) => { this.timers = this.timers.filter((timer) => timer.id !== id); };
  }

  #add(fn, ms, every) {
    const id = this.nextId++;
    this.timers.push({ id, at: this.now + Math.max(0, Number(ms) || 0), fn, every });
    return id;
  }

  /** Run every timer due within `ms`, in order, settling promises between them. */
  async advance(ms) {
    const end = this.now + ms;
    for (;;) {
      this.timers.sort((a, b) => a.at - b.at || a.id - b.id);
      const next = this.timers[0];
      if (!next || next.at > end) break;
      this.now = next.at;
      if (next.every) next.at += next.every;
      else this.timers.shift();
      next.fn();
      await settle();
    }
    this.now = end;
    await settle();
  }
}

export async function settle() {
  for (let index = 0; index < 20; index += 1) await new Promise((resolve) => setImmediate(resolve));
}

function inertElement(id) {
  return {
    id, innerHTML: "", textContent: "", style: {}, dataset: {}, value: "",
    classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    querySelectorAll: () => [], querySelector: () => null,
    addEventListener() {}, removeEventListener() {}, focus() {}, setSelectionRange() {},
  };
}

function eventTarget() {
  const listeners = new Map();
  return {
    addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, []); listeners.get(type).push(fn); },
    removeEventListener(type, fn) { listeners.set(type, (listeners.get(type) || []).filter((item) => item !== fn)); },
    dispatch(type, event = {}) { for (const fn of listeners.get(type) || []) fn({ type, ...event }); },
  };
}

/**
 * Run `scripts` (paths relative to dashboard/) in one browser-like context.
 *
 * `routes(url, init)` answers fetch: return a JSON body, or
 * `{ __status: 500, __body: {...} }` for an error.
 */
export function loadScripts(scripts, { routes = () => ({}), clock = new FakeClock(), hidden = false } = {}) {
  const elements = new Map();
  const fetches = [];
  const documentEvents = eventTarget();
  const windowEvents = eventTarget();
  const storage = new Map();

  const document = {
    hidden,
    get visibilityState() { return this.hidden ? "hidden" : "visible"; },
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, inertElement(id));
      return elements.get(id);
    },
    querySelectorAll: () => [],
    querySelector: () => null,
    createElement: (tag) => inertElement(tag),
    addEventListener: documentEvents.addEventListener,
    removeEventListener: documentEvents.removeEventListener,
  };
  const window = {
    addEventListener: windowEvents.addEventListener,
    removeEventListener: windowEvents.removeEventListener,
    location: { hash: "", href: "https://dash.example/" },
  };
  const fetch = async (url, init = {}) => {
    const path = String(url);
    fetches.push(path);
    const answer = await routes(path, init);
    const status = answer?.__status ?? 200;
    const body = answer?.__body ?? answer;
    return { ok: status >= 200 && status < 300, status, json: async () => JSON.parse(JSON.stringify(body)), text: async () => JSON.stringify(body) };
  };

  const context = vm.createContext({
    window, document, fetch, console,
    navigator: { languages: ["en-US"], language: "en-US" },
    localStorage: {
      getItem: (key) => (storage.has(key) ? storage.get(key) : null),
      setItem: (key, value) => storage.set(key, String(value)),
      removeItem: (key) => storage.delete(key),
    },
    setTimeout: clock.setTimeout, clearTimeout: clock.clear,
    setInterval: clock.setInterval, clearInterval: clock.clear,
    __clockNow: () => clock.now,
  });
  vm.runInContext("Date.now = () => __clockNow();", context);
  for (const script of scripts) {
    vm.runInContext(readFileSync(join(DASHBOARD, script), "utf8"), context, { filename: script });
  }

  return {
    window, document, clock, fetches, elements,
    element: (id) => document.getElementById(id),
    setHidden(value) {
      document.hidden = value;
      documentEvents.dispatch("visibilitychange");
    },
    focus() { windowEvents.dispatch("focus"); },
  };
}
