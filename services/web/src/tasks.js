// Long work in the background (D192, D273). Every slow button answers with a task at once; this module follows the
// person's tasks (the server keeps them, so they survive a reload and show in every browser tab) and the task drawer
// on the right shows them with their progress. When one ends the screens refresh, a file it made is downloaded if
// asked for, and the Background tasks tab of Notifications says so.
//
//   runTask(request, href)                 await the API's answer; if it is a task, follow it and resolve with its result
//   downloadTask(path, body, href)         a file made in the background: downloaded when done, kept 24 hours
//   startDownload(path, body, href)        the same, answering as soon as it is queued (a dialog closes at once)
//   trackTask(task, href)                  follow a task an answer carried (older screens)
//   useTasks() / useTask(id) / dismissTask(id) / clearFinished()
import { useEffect, useState } from "react";
import { apiDownload, apiFetch } from "./auth";
import { refreshAll } from "./ModelViews";

const DISMISSED = "eax-tasks-dismissed";
const DOWNLOAD = "eax-tasks-download";
const listeners = new Set();
const waiters = new Map();          // task id -> [resolve]
let tasks = [];
let timer = null;
let slow = null;
let started = false;

function read(key, session) {
  try { return new Set(JSON.parse((session ? sessionStorage : localStorage).getItem(key) || "[]")); } catch { return new Set(); }
}
function write(key, set, session) {
  try { (session ? sessionStorage : localStorage).setItem(key, JSON.stringify([...set].slice(-200))); } catch { /* storage blocked: kept until the page reloads */ }
}
const dismissed = read(DISMISSED, false);
const toDownload = read(DOWNLOAD, true);   // this browser tab asked for the file: it downloads it when done

function emit() {
  listeners.forEach((f) => f(tasks));
}

function finished(t) {
  (waiters.get(t.id) || []).forEach((resolve) => resolve(t));
  waiters.delete(t.id);
  if (t.status === "done" && t.file && toDownload.has(t.id)) {
    toDownload.delete(t.id);
    write(DOWNLOAD, toDownload, true);
    apiDownload(`/api/v1/tasks/${t.id}/file`, t.file).catch(() => {});
  }
}

function merge(list) {
  const before = new Map(tasks.map((t) => [t.id, t]));
  let ended = false;
  for (const t of list) {
    const was = before.get(t.id);
    if (t.done && (!was || !was.done)) {
      if (was) ended = true;
      finished(t);
    }
  }
  const ids = new Set(list.map((t) => t.id));
  // keep a task an answer carried that the list does not show yet (made a moment ago)
  tasks = [...list, ...tasks.filter((t) => !ids.has(t.id) && !t.done)]
    .map((t) => ({ ...t, href: t.link || before.get(t.id)?.href || t.href || "" }));
  emit();
  if (ended) refreshAll();
}

async function poll() {
  try {
    const out = await apiFetch("/api/v1/tasks?active=true");
    merge(out.tasks || []);
  } catch { /* signed out or offline: the next round tries again */ }
  const running = tasks.some((t) => !t.done);
  if (running && !timer) timer = setInterval(poll, 2000);
  if (!running && timer) { clearInterval(timer); timer = null; }
}

function start() {
  if (started) return;
  started = true;
  poll();
  slow = setInterval(() => { if (!timer) poll(); }, 30000);   // tasks started in another browser tab
}

// follow a task an answer carried; href: the screen that asked (the server keeps it as the task's link too)
export function trackTask(task, href) {
  if (!task?.id) return;
  dismissed.delete(task.id);
  tasks = [{ ...task, href: href || task.link || "" }, ...tasks.filter((t) => t.id !== task.id)];
  emit();
  start();
  if (task.done) finished(task);
  else if (!timer) timer = setInterval(poll, 2000);
}

function waitFor(task) {
  const known = tasks.find((t) => t.id === task.id);
  if (task.done || known?.done) return Promise.resolve(known?.done ? known : task);
  return new Promise((resolve) => {
    waiters.set(task.id, [...(waiters.get(task.id) || []), resolve]);
  });
}

// await the API's answer; when it is a background task, follow it and resolve with its result (or throw its reason)
export async function runTask(request, href) {
  const out = await request;
  if (!out || !out.task || !out.task.id || !out.task.kind) return out;
  trackTask(out.task, href || window.location.hash);
  const t = await waitFor(out.task);
  if (t.status === "failed") {
    const err = new Error(t.message || "The background task failed.");
    err.task = t;
    throw err;
  }
  return t.result;
}

// a file made in the background (D273): GET path (with background=true) or POST body; downloaded here when done
// (while the site is open), and from the task drawer, the notification or the page for 24 hours
export async function startDownload(path, body = undefined, href = "") {
  const url = body === undefined ? `${path}${path.includes("?") ? "&" : "?"}background=true` : path;
  const out = await apiFetch(url, body === undefined ? {} : { method: "POST", body: JSON.stringify(body) });
  if (!out?.task) return out;
  toDownload.add(out.task.id);
  write(DOWNLOAD, toDownload, true);
  trackTask(out.task, href || window.location.hash);
  return out.task;
}

export async function downloadTask(path, body = undefined, href = "") {
  const task = await startDownload(path, body, href);
  if (!task?.id) return task;
  const t = await waitFor(task);
  if (t.status === "failed") throw new Error(t.message || "The file could not be made.");
  return t;
}

export function downloadTaskFile(t) {
  return apiDownload(`/api/v1/tasks/${t.id}/file`, t.file || "download");
}

export function dismissTask(id) {
  dismissed.add(id);
  write(DISMISSED, dismissed, false);
  emit();
}

export function clearFinished() {
  tasks.filter((t) => t.done).forEach((t) => dismissed.add(t.id));
  write(DISMISSED, dismissed, false);
  emit();
}

export function isDismissed(id) {
  return dismissed.has(id);
}

// every task of yours the server lists (running, and finished in the last 24 hours), newest first
export function useAllTasks() {
  const [list, setList] = useState(tasks);
  useEffect(() => {
    listeners.add(setList);
    start();
    return () => listeners.delete(setList);
  }, []);
  return list;
}

// the drawer's list: dismissed ones left out
export function useTasks() {
  return useAllTasks().filter((t) => !dismissed.has(t.id));
}

export function useTask(id) {
  return useAllTasks().find((t) => t.id === id) || null;
}
