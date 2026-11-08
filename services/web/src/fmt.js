// Phase 10 (D182): dates, times and numbers follow the installation's application settings for everyone (not the
// browser): its time zone, date format and number separators. Loaded once after sign-in (App.jsx), changed in
// Administration > Application settings.
let S = {
  time_zone: "Africa/Johannesburg", date_format: "YYYY-MM-DD", decimal_separator: ".", thousands_separator: " ",
  currency_symbol: "$", base_currency: "USD", first_day_of_week: "Monday", financial_year_start: 3, country: "South Africa",
};
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function setAppSettings(values) { S = { ...S, ...(values || {}) }; }
export function appSettings() { return S; }
// the optional services switched on or off in the config file (D191): unknown means on
export function serviceOn(key) { return !S.services || S.services[key] !== false; }

function parts(v) {
  const d = v instanceof Date ? v : new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  let p;
  try {
    p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
      timeZone: S.time_zone, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).formatToParts(d).map((x) => [x.type, x.value]));
  } catch (e) {
    p = { year: String(d.getFullYear()), month: String(d.getMonth() + 1).padStart(2, "0"), day: String(d.getDate()).padStart(2, "0"),
      hour: String(d.getHours()).padStart(2, "0"), minute: String(d.getMinutes()).padStart(2, "0"), second: String(d.getSeconds()).padStart(2, "0") };
  }
  if (p.hour === "24") p.hour = "00";
  return p;
}

// a date (no time): a plain YYYY-MM-DD value is shown as it is (no time zone shift)
export function fmtDate(v) {
  if (v === null || v === undefined || v === "") return "";
  let p;
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) { const [y, m, d] = v.split("-"); p = { year: y, month: m, day: d }; }
  else p = parts(v);
  if (!p) return String(v);
  return S.date_format.replace("YYYY", p.year).replace("MMM", MON[Number(p.month) - 1]).replace("MM", p.month).replace("DD", p.day);
}
export function fmtTime(v) { const p = parts(v); return p ? `${p.hour}:${p.minute}` : ""; }
export function fmtDateTime(v) { if (v === null || v === undefined || v === "") return ""; const p = parts(v); return p ? `${fmtDate(v)} ${p.hour}:${p.minute}` : String(v); }

export function fmtNumber(n, decimals) {
  if (n === null || n === undefined || n === "" || Number.isNaN(Number(n))) return n ?? "";
  const x = Number(n);
  const fixed = decimals === undefined ? String(Math.round(x * 100) / 100) : x.toFixed(decimals);
  const [whole, frac] = fixed.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, S.thousands_separator);
  return `${x < 0 ? "-" : ""}${grouped}${frac ? S.decimal_separator + frac : ""}`;
}
export function fmtMoney(n) { return n === null || n === undefined || n === "" ? "" : `${S.currency_symbol} ${fmtNumber(n, 0)}`; }

// a backup's stamp (20261106T010000Z or 20261106-010000, UTC) -> a date and time to read, in local time
export function fmtStamp(stamp) {
  const m = /^(\d{4})(\d{2})(\d{2})[T-](\d{2})(\d{2})(\d{2})Z?/.exec(stamp || "");
  return m ? fmtDateTime(`${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}Z`) : stamp || "";
}
