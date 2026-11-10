// How alike two names are (D454): the same rules as the API's matcher (eax/dedupe.py closeness, D361/D426), used where
// a list is already in the browser (the drawn view's Bind search). Case, spaces and punctuation are ignored; the same words
// in another order count as alike; names whose numbers differ are versions, not the same thing.
export function normName(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

// the ratio of a character-level edit distance, 0 to 1
function ratio(a, b) {
  if (a === b) return 1;
  if (!a.length || !b.length) return 0;
  let prev = Array.from({ length: b.length + 1 }, (_, j) => j);
  for (let i = 1; i <= a.length; i += 1) {
    const cur = [i];
    for (let j = 1; j <= b.length; j += 1) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return 1 - prev[b.length] / Math.max(a.length, b.length);
}

const numbers = (s) => (s.match(/\d+/g) || []).join(",");
const sorted = (s) => s.split(" ").sort().join(" ");

export function closeness(a, b) {
  const na = normName(a); const nb = normName(b);
  if (na === nb) return 1;
  if (numbers(na) !== numbers(nb)) return 0;
  const sa = sorted(na); const sb = sorted(nb);
  if (sa === sb) return Math.max(ratio(na, nb), 0.95);
  return Math.max(ratio(na, nb), ratio(sa, sb));
}

// a search box's match (0 = no): the text found in the name or ID, else each typed word found in, starting or close to a
// word of the name (near spellings: "platfrom" finds Claims Platform), else the whole name close to what is typed
export function searchScore(q, name, extra = "") {
  const nq = normName(q);
  if (!nq) return 1;
  const nn = normName(name);
  const hay = `${nn} ${normName(extra)}`;
  if (hay.includes(nq)) return nn.startsWith(nq) ? 1 : 0.95;
  const words = nn.split(" ").filter(Boolean);
  const qs = nq.split(" ").filter(Boolean);
  let total = 0;
  for (const w of qs) {
    let best = 0;
    for (const x of words) {
      if (x.startsWith(w)) best = Math.max(best, 0.9);
      else if (w.length >= 3) best = Math.max(best, ratio(w, x.slice(0, Math.max(w.length, x.length))), ratio(w, x.slice(0, w.length)) - 0.05);
    }
    if (best < 0.7) { total = 0; break; }
    total += best;
  }
  const words_ = qs.length ? total / qs.length : 0;
  const whole = nq.length >= 3 ? closeness(nq, nn) : 0;
  const s = Math.max(words_ * 0.9, whole >= 0.75 ? whole * 0.9 : 0);
  return s >= 0.6 ? s : 0;
}

// a list filtered and ordered by searchScore, best first, then by name
export function fuzzyFilter(list, q, nameOf = (x) => x.name, extraOf = (x) => x.display_id || "") {
  if (!normName(q)) return [...list].sort((a, b) => String(nameOf(a)).localeCompare(String(nameOf(b))));
  return list.map((x) => [x, searchScore(q, nameOf(x), extraOf(x))]).filter(([, s]) => s > 0)
    .sort((a, b) => b[1] - a[1] || String(nameOf(a[0])).localeCompare(String(nameOf(b[0])))).map(([x]) => x);
}
