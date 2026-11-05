// Long work in the background (D192): a request such as "tag this model" answers with a task at once; this module
// follows every task started in this browser (every 2 seconds) until it is done, then refreshes the screens and the
// top bar says what happened. The person can leave the page meanwhile.
import { useEffect, useState } from "react";
import { apiFetch } from "./auth";
import { refreshAll } from "./ModelViews";

const KEY = "eax-tasks";
const listeners = new Set();
let tasks = load();
let timer = null;

function load() {
  try { return JSON.parse(sessionStorage.getItem(KEY) || "[]"); } catch { return []; }
}
function save() {
  try { sessionStorage.setItem(KEY, JSON.stringify(tasks)); } catch { /* storage blocked: followed until the page reloads */ }
  listeners.forEach((f) => f(tasks));
}

async function poll() {
  const open = tasks.filter((t) => !t.done);
  if (!open.length) { clearInterval(timer); timer = null; return; }
  let finished = false;
  for (const t of open) {
    try {
      const now = await apiFetch(`/api/v1/tasks/${t.id}`);
      if (now.done) finished = true;
      tasks = tasks.map((x) => (x.id === t.id ? { ...now, seen: false, href: x.href } : x));
    } catch (e) {
      if (/No such task|404/.test(e.message)) tasks = tasks.filter((x) => x.id !== t.id);
    }
  }
  save();
  if (finished) refreshAll();
}

// follow a task the API answered with; href: where its result is (opened from the top bar)
export function trackTask(task, href) {
  tasks = [{ ...task, href, seen: false }, ...tasks.filter((t) => t.id !== task.id)].slice(0, 20);
  save();
  if (!timer) timer = setInterval(poll, 2000);
}

export function dismissTask(id) {
  tasks = tasks.filter((t) => t.id !== id);
  save();
}

export function useTasks() {
  const [list, setList] = useState(tasks);
  useEffect(() => {
    listeners.add(setList);
    if (tasks.some((t) => !t.done) && !timer) timer = setInterval(poll, 2000);
    return () => listeners.delete(setList);
  }, []);
  return list;
}

export function useTask(id) {
  const list = useTasks();
  return list.find((t) => t.id === id) || null;
}
