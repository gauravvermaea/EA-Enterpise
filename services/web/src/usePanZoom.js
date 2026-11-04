// Pan and zoom for an SVG picture inside a frame: drag the background to move, scroll to zoom.
import { useEffect, useRef, useState } from "react";

export default function usePanZoom(deps = []) {
  const frame = useRef(null);
  const drag = useRef(null);
  const [view, setView] = useState({ x: 20, y: 20, k: 1 });

  function fit(width, height, maxK = 1.2) {
    const el = frame.current;
    if (!el || !width || !height) return;
    const w = el.clientWidth, h = el.clientHeight;
    const k = Math.min(maxK, (w - 40) / width, (h - 40) / height);
    setView({ k, x: (w - width * k) / 2, y: Math.max(20, (h - height * k) / 2) });
  }
  function zoomAt(factor, cx, cy) {
    setView((v) => {
      const k = Math.min(4, Math.max(0.03, v.k * factor));
      const f = k / v.k;
      return { k, x: cx - (cx - v.x) * f, y: cy - (cy - v.y) * f };
    });
  }
  const zoomCentre = (factor) => frame.current && zoomAt(factor, frame.current.clientWidth / 2, frame.current.clientHeight / 2);

  useEffect(() => {
    const el = frame.current;
    if (!el) return undefined;
    const onWheel = (e) => {
      e.preventDefault();
      const r = el.getBoundingClientRect();
      zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps

  const handlers = {
    onMouseDown: (e) => { if (e.button === 0) drag.current = { x: e.clientX, y: e.clientY, moved: false }; },
    onMouseMove: (e) => {
      const d = drag.current;
      if (!d) return;
      const dx = e.clientX - d.x, dy = e.clientY - d.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) d.moved = true;
      d.x = e.clientX; d.y = e.clientY;
      setView((v) => ({ ...v, x: v.x + dx, y: v.y + dy }));
    },
    onMouseUp: () => { setTimeout(() => { drag.current = null; }, 0); },
    onMouseLeave: () => { drag.current = null; },
  };
  const wasDrag = () => !!drag.current?.moved;
  return { frame, view, fit, zoomCentre, handlers, wasDrag };
}
