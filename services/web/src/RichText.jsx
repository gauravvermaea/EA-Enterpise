// A small rich-text editor (phase 13.0.1): bold, italic, underline, headings, lists, quotes and links. The HTML is cleaned
// by the server before it is stored (eax/project_work.clean_html): only plain formatting survives.
import { useEffect, useRef } from "react";

const TOOLS = [
  ["bold", "B", "Bold"], ["italic", "I", "Italic"], ["underline", "U", "Underline"],
  ["h3", "H", "Heading"], ["insertUnorderedList", "•", "Bulleted list"], ["insertOrderedList", "1.", "Numbered list"],
  ["blockquote", "❝", "Quote"], ["link", "🔗", "Link"], ["removeFormat", "⌫", "Clear the formatting"],
];

export default function RichText({ value, onChange, placeholder, readOnly }) {
  const ref = useRef(null);
  useEffect(() => {
    if (ref.current && ref.current.innerHTML !== (value || "")) ref.current.innerHTML = value || "";
  }, [value]);
  if (readOnly) {
    // eslint-disable-next-line react/no-danger -- cleaned by the server
    return <div className="rich-view" dangerouslySetInnerHTML={{ __html: value || "" }} />;
  }
  function run(cmd) {
    ref.current?.focus();
    if (cmd === "h3" || cmd === "blockquote") document.execCommand("formatBlock", false, cmd);
    else if (cmd === "link") {
      // eslint-disable-next-line no-alert
      const url = window.prompt("Link to (https://...)", "https://");
      if (url && /^(https?:|mailto:)/i.test(url)) document.execCommand("createLink", false, url);
    } else document.execCommand(cmd, false, null);
    onChange(ref.current.innerHTML);
  }
  return (
    <div className="rich">
      <div className="rich-tools" role="toolbar" aria-label="Formatting">
        {TOOLS.map(([cmd, label, title]) => (
          <button key={cmd} type="button" title={title} aria-label={title} onMouseDown={(e) => e.preventDefault()} onClick={() => run(cmd)}>{label}</button>
        ))}
      </div>
      <div ref={ref} className="rich-edit" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true"
        aria-label={placeholder || "Notes"} data-placeholder={placeholder || ""} onInput={(e) => onChange(e.currentTarget.innerHTML)} />
    </div>
  );
}
