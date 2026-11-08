// The TOGAF ADM "crop circle" (phase 13.0.1, D279): Preliminary above, phases A to H around Requirements Management,
// each with how far its steps are and how many documents it holds. Click (or Enter on) a phase to open it.
const RING = ["A", "B", "C", "D", "E", "F", "G", "H"];
const SHORT = {
  P: ["Preliminary"], A: ["A. Architecture", "Vision"], B: ["B. Business", "Architecture"], C: ["C. Information", "Systems Arch."],
  D: ["D. Technology", "Architecture"], E: ["E. Opportunities", "& Solutions"], F: ["F. Migration", "Planning"],
  G: ["G. Implementation", "Governance"], H: ["H. Architecture", "Change Mgmt"], RM: ["Requirements", "Management"],
};

// choosing (the project wizard, owner 7 Nov 2026): the ring shows the steps kept and the documents chosen instead
function Petal({ code, x, y, r, stat, on, onSelect, center, choosing }) {
  const lines = SHORT[code] || [code];
  const s = stat || {};
  const frac = s.steps ? s.done / s.steps : 0;
  const circ = 2 * Math.PI * (r + 5);
  const label = choosing
    ? `${lines.join(" ")}: ${s.done || 0} of ${s.steps || 0} steps kept, ${s.docs || 0} of ${s.items || 0} deliverables and artifacts chosen`
    : `${lines.join(" ")}: ${s.done || 0} of ${s.steps || 0} steps done, ${s.items || 0} deliverables and artifacts, ${s.docs || 0} documents`;
  return (
    <g className={`adm-petal${on ? " on" : ""}${center ? " center" : ""}${s.items || s.steps ? "" : " empty"}`} role="button" tabIndex={0}
      aria-pressed={on} aria-label={label} onClick={() => onSelect(code)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(code); } }}>
      <title>{label}</title>
      <circle cx={x} cy={y} r={r} className="adm-disc" />
      {s.steps > 0 && <circle cx={x} cy={y} r={r + 5} className="adm-progress" strokeDasharray={`${circ * frac} ${circ}`}
        transform={`rotate(-90 ${x} ${y})`} />}
      {lines.map((t, i) => (
        <text key={t} x={x} y={y + (i - (lines.length - 1) / 2) * 14 - (s.items ? 4 : 0)} className={i === 0 ? "adm-t1" : "adm-t2"} textAnchor="middle">{t}</text>
      ))}
      {(s.items > 0 || s.docs > 0) && <text x={x} y={y + lines.length * 7 + 8} className="adm-count" textAnchor="middle">{choosing ? `${s.docs || 0} docs · ${s.done || 0} steps` : `${s.docs || 0} docs · ${s.done || 0}/${s.steps || 0}`}</text>}
    </g>
  );
}

export default function AdmWheel({ stats, selected, onSelect, choosing = false }) {
  const cx = 230, cy = 312, R = 168, r = 54;
  const pos = (i) => {
    const a = (-90 + i * 45) * (Math.PI / 180);
    return [cx + R * Math.cos(a), cy + R * Math.sin(a)];
  };
  return (
    <svg className="adm-wheel" viewBox="0 0 460 550" role="group" aria-label="The ADM cycle: choose a phase">
      <circle cx={cx} cy={cy} r={R} className="adm-ring" />
      {RING.map((c, i) => {
        const [x1, y1] = pos(i);
        const [x2, y2] = pos((i + 1) % 8);
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        const ang = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI);
        return <path key={`arrow${c}`} d="M -6 -5 L 6 0 L -6 5 z" className="adm-arrow" transform={`translate(${mx} ${my}) rotate(${ang})`} />;
      })}
      <line x1={cx} y1={82} x2={cx} y2={cy - R - r} className="adm-link" />
      <Petal code="P" x={cx} y={44} r={38} stat={stats.P} on={selected === "P"} onSelect={onSelect} choosing={choosing} />
      {RING.map((c, i) => {
        const [x, y] = pos(i);
        return <Petal key={c} code={c} x={x} y={y} r={r} stat={stats[c]} on={selected === c} onSelect={onSelect} choosing={choosing} />;
      })}
      <Petal code="RM" x={cx} y={cy} r={70} stat={stats.RM} on={selected === "RM"} onSelect={onSelect} center choosing={choosing} />
    </svg>
  );
}
