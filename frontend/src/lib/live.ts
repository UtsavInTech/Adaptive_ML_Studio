/** Live run store: one SSE connection, frame-batched notifications.
 *
 * Messages mutate arrays in place and bump a version counter; components subscribe to the version
 * through useSyncExternalStore, so a burst of updates causes at most one render per frame.
 * On (re)connect the full state is fetched from /api/live/state, so nothing is lost if a message
 * is dropped for a slow client.
 */

import { useSyncExternalStore } from "react";

import { api, type BlockRecord, type EngineBlock, type EventRecord, type Extras, type JobProgress,
  type Lifecycle, type LiveSnapshot, type ResourceSample } from "./api";

const MAX_BLOCKS = 4000;
const MAX_EVENTS = 2000;

export type Connection = "connecting" | "live" | "offline";

export type LiveStore = {
  connection: Connection;
  active: boolean;
  name: string | null;
  config: any | null;
  status: { lifecycle: Lifecycle; sample: number; total: number };
  blocks: Record<string, BlockRecord[]>;
  engine: EngineBlock[];
  events: EventRecord[];
  resources: ResourceSample[];
  extras: Extras | null;
  final: LiveSnapshot["final"];
  error: LiveSnapshot["error"];
  job: JobProgress | null;
};

const empty = (): LiveStore => ({
  connection: "connecting",
  active: false,
  name: null,
  config: null,
  status: { lifecycle: "starting", sample: 0, total: 0 },
  blocks: {},
  engine: [],
  events: [],
  resources: [],
  extras: null,
  final: null,
  error: null,
  job: null,
});

export const store: LiveStore = empty();

let version = 0;
let frame = 0;
const listeners = new Set<() => void>();
let source: EventSource | null = null;
let refs = 0;

function bump() {
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    version += 1;
    listeners.forEach((l) => l());
  });
}

function reset(next: Partial<LiveStore>) {
  Object.assign(store, empty(), next);
}

function trim<T>(list: T[], max: number) {
  if (list.length > max) list.splice(0, list.length - max);
}

export function applyMessage(message: any) {
  switch (message.type) {
    case "run_started":
      reset({ connection: store.connection, active: true, name: message.name, config: message.config });
      break;
    case "status":
      store.status = { lifecycle: message.lifecycle, sample: message.sample, total: message.total };
      break;
    case "blocks":
      for (const [method, records] of Object.entries(message.blocks as Record<string, BlockRecord[]>)) {
        const list = (store.blocks[method] ??= []);
        list.push(...records);
        trim(list, MAX_BLOCKS);
      }
      store.engine.push(...(message.engine as EngineBlock[]));
      trim(store.engine, MAX_BLOCKS);
      if (message.engine.length) {
        const last = message.engine[message.engine.length - 1];
        store.status = { ...store.status, sample: last.start + last.n };
      }
      break;
    case "events":
      store.events.push(...(message.events as EventRecord[]));
      trim(store.events, MAX_EVENTS);
      break;
    case "extras":
      store.extras = message;
      break;
    case "resources":
      store.resources.push(message);
      break;
    case "final":
      store.final = message;
      store.active = false;
      break;
    case "error":
      store.error = message;
      store.active = false;
      store.status = { ...store.status, lifecycle: "error" };
      break;
    case "experiment_progress":
      store.job = message;
      break;
    default:
      return;
  }
  bump();
}

export function applySnapshot(snapshot: LiveSnapshot | { active: false }) {
  if (!("config" in snapshot)) {
    reset({ connection: store.connection, job: store.job });
  } else {
    reset({
      connection: store.connection,
      job: store.job,
      active: snapshot.active,
      name: snapshot.name,
      config: snapshot.config,
      status: snapshot.status,
      blocks: snapshot.blocks,
      engine: snapshot.engine,
      events: snapshot.events,
      resources: snapshot.resources,
      extras: snapshot.extras,
      final: snapshot.final,
      error: snapshot.error,
    });
  }
  bump();
}

async function resync() {
  try {
    applySnapshot(await api.liveState());
    store.job = (await api.job()).progress;
    bump();
  } catch {
    /* the next reconnect retries */
  }
}

function connect() {
  source = new EventSource("/api/live/stream");
  source.onopen = () => {
    store.connection = "live";
    void resync();
    bump();
  };
  source.onerror = () => {
    store.connection = "offline"; // EventSource reconnects on its own
    bump();
  };
  for (const type of ["run_started", "status", "blocks", "events", "extras", "resources", "final", "error", "experiment_progress"]) {
    source.addEventListener(type, (e) => {
      const { data } = (e as MessageEvent) ?? {};
      // A keep-alive or an empty frame is not an error. A malformed one must not throw out of the
      // handler either: the stream keeps running and the next resync restores the true state.
      if (typeof data !== "string" || data === "") return;
      try {
        applyMessage(JSON.parse(data));
      } catch {
        /* ignored deliberately; see above */
      }
    });
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  if (refs++ === 0 && !source) connect();
  return () => {
    listeners.delete(listener);
    refs -= 1;
  };
}

/** Subscribe to live updates; returns a version that changes at most once per frame. */
export function useLive(): number {
  return useSyncExternalStore(subscribe, () => version, () => version);
}

export const liveActions = {
  refresh: resync,
  async start(body: { preset?: string; profile?: string; config?: unknown; name?: string }) {
    reset({ connection: store.connection, active: true });
    bump();
    await api.startLive(body);
    await resync();
  },
  command: (command: "pause" | "resume" | "stop" | "inject-drift", body?: unknown) => api.liveCommand(command, body),
};
