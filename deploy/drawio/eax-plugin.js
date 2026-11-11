/**
 * EA Explorer's plugin for drawn views (phases 28 and 29: D354, D387 to D398). Loaded by our own draw.io image (from
 * its index.html), it acts only in embed mode with eax=1, that is inside EA Explorer. The repository is the truth; the
 * view only shows it:
 *
 *  - the stencil is the model's metamodel (types, never entities), its relationship types (lines) and the two
 *    junctions; a dropped type is a dashed placeholder until it is realised (Choose instance..., or EA Explorer's search
 *    panel: "bind", "place-at-pointer");
 *  - EA Explorer places realised entities ("place"), each a shape carrying ea_id and ea_type, and draws the
 *    relationships the model has with what is already on the view;
 *  - a line between two realised objects (or through a junction) becomes a relationship only of a type the metamodel
 *    allows: EA Explorer asks which (and its attributes) and answers ("rel" or "rel-cancel"); anything else goes away;
 *  - deleting or hiding a relationship's line only hides it in this view (the view's hidden list); deleting an object
 *    takes it off the view, never out of the model; nesting must match a relationship (EA Explorer decides);
 *  - EA objects and relationship lines are locked to layout: position, size, fonts and routing change; colours, shapes,
 *    names and the ea_ attributes do not (any other change is put back). Text, notes and other decoration are free;
 *  - a heat map recolours objects on screen only; the saved file keeps the standard colours.
 *
 * Messages are JSON strings over postMessage, beside draw.io's own embed protocol, marked {"eax": ...}. The full
 * protocol is in docs/phase-28.md ("As built: the plugin protocol"). The plugin makes no network calls.
 */
(function () {
  var q = window.location.search;
  if (!/[?&]embed=1(&|$)/.test(q) || !/[?&]eax=1(&|$)/.test(q)) return;      // only inside EA Explorer
  function start() {
    if (!window.Draw || !window.Draw.loadPlugin || !window.mxUtils) { setTimeout(start, 50); return; }
    window.Draw.loadPlugin(plugin);
  }

  // ArchiMate's line notation (the same drawings as draw.io's own ArchiMate library), used when EA Explorer sends none
  var DEFAULT_REL_STYLES = {
    Composition: "html=1;startArrow=diamondThin;startFill=1;startSize=10;endArrow=none;endFill=0;",
    Aggregation: "html=1;startArrow=diamondThin;startFill=0;startSize=10;endArrow=none;endFill=0;",
    Assignment: "html=1;endArrow=block;endFill=1;startArrow=oval;startFill=1;",
    Realization: "html=1;endArrow=block;endFill=0;dashed=1;",
    Serving: "html=1;endArrow=open;endFill=1;",
    Access: "html=1;endArrow=open;endFill=0;dashed=1;dashPattern=1 4;",
    Influence: "html=1;endArrow=open;endFill=0;dashed=1;dashPattern=6 4;",
    Triggering: "html=1;endArrow=block;endFill=1;",
    Flow: "html=1;endArrow=block;endFill=1;dashed=1;dashPattern=6 4;",
    Specialization: "html=1;endArrow=block;endFill=0;",
    Association: "html=1;endArrow=none;"
  };
  var JUNCTION_STYLES = {
    and: "ellipse;html=1;aspect=fixed;fillColor=#000000;strokeColor=#000000;verticalLabelPosition=bottom;verticalAlign=top;",
    or: "ellipse;html=1;aspect=fixed;fillColor=#ffffff;strokeColor=#000000;verticalLabelPosition=bottom;verticalAlign=top;"
  };
  // the style keys a person may change on an EA object or relationship line: layout only (D354 rule 8)
  var LAYOUT_KEYS = ["fontSize", "fontStyle", "fontFamily", "align", "verticalAlign", "labelPosition", "verticalLabelPosition",
    "spacing", "spacingTop", "spacingBottom", "spacingLeft", "spacingRight", "whiteSpace", "overflow", "rotation", "html",
    "edgeStyle", "elbow", "curved", "rounded", "orthogonalLoop", "jettySize", "jumpStyle", "jumpSize", "entryX", "entryY",
    "exitX", "exitY", "entryDx", "entryDy", "exitDx", "exitDy", "entryPerimeter", "exitPerimeter", "labelBackgroundColor",
    "sourcePerimeterSpacing", "targetPerimeterSpacing"];
  var UNCOMMITTED = "dashed=1;dashPattern=8 4;strokeColor=#1565C0;";
  var DELETED = "strokeColor=#C62828;dashed=1;dashPattern=3 3;strokeWidth=2;";

  function plugin(ui) {
    var graph = ui.editor.graph;
    var model = graph.getModel();
    var host = window.opener || window.parent;
    var meta = { types: {}, allowed: [], rels: {}, readOnly: false };
    var shown = {};                            // stencil groups the person hid (D409): {group: false}; never saved in the view
    var icons = {};                        // entity id -> data URI (part 2)
    var heat = null;                       // entity id -> colour while a heat map is on (part 2)
    var quiet = 0;                         // > 0 while the plugin itself changes the view
    var asked = {};                        // lines EA Explorer is asked about
    var nesting = {};                      // cell id -> where it was before it was dropped into another object
    var gone = {};                         // relationship id -> a deleted line EA Explorer is asking about (D413)
    var undoing = 0;                       // > 0 while draw.io undoes or redoes (Ctrl+Z, Ctrl+Y, the toolbar)
    var removedRels = {};                  // relationships deleted from the model from this view: an undo never brings them back
    var relValues = {};                    // relationship id -> {attribute name: value}, for the line's label (D565); never saved
    var relAttrsShown = true;              // "Line labels: with attributes" (D565), per person in EA Explorer

    function post(msg) { msg.eax = msg.eax || "event"; host.postMessage(JSON.stringify(msg), "*"); }
    function attr(cell, name) {
      var v = cell && cell.value;
      return v != null && typeof v === "object" && v.getAttribute ? v.getAttribute(name) : null;
    }
    function node(attrs) {
      var obj = mxUtils.createXmlDocument().createElement("object");
      for (var k in attrs) { if (attrs[k] != null && attrs[k] !== false) obj.setAttribute(k, attrs[k]); }
      if (!obj.getAttribute("label")) obj.setAttribute("label", "");
      return obj;
    }
    function withAttrs(cell, attrs) {      // the cell's value with some attributes changed (null removes)
      var v = cell.value != null && typeof cell.value === "object" ? cell.value.cloneNode(true) : node({ label: cell.value || "" });
      for (var k in attrs) { if (attrs[k] == null || attrs[k] === false) v.removeAttribute(k); else v.setAttribute(k, attrs[k]); }
      return v;
    }
    // undo and redo cover what the person does on the drawing; what the plugin does for EA Explorer (setup, resync, a bind,
    // a relationship's id) is not undone on its own, so an undo never leaves the view out of step with the model
    var um = ui.editor.undoManager;
    var origHappened = um.undoableEditHappened;
    um.undoableEditHappened = function () { if (quiet) return; return origHappened.apply(this, arguments); };
    ["undo", "redo"].forEach(function (k) {
      var f = um[k];
      um[k] = function () { undoing++; try { return f.apply(this, arguments); } finally { undoing--; } };
    });
    function silently(fn) { quiet++; try { model.beginUpdate(); try { fn(); } finally { model.endUpdate(); } } finally { quiet--; } }
    function isEa(cell) { return !!(attr(cell, "ea_id") || attr(cell, "ea_type") || attr(cell, "ea_rel") || attr(cell, "ea_junction_kind")); }
    function isRealised(cell) { return !!attr(cell, "ea_id"); }
    function isJunction(cell) { return !!attr(cell, "ea_junction_kind"); }
    function typeName(code) { return (meta.types[code] || {}).name || code; }
    function relStyle(code) { return (meta.rels[code] || {}).style || DEFAULT_REL_STYLES[code] || "html=1;endArrow=block;"; }
    function dataUri(u) { return String(u || "").replace(";base64,", ","); }   // draw.io styles split on ";"
    function relName(code) { return (meta.rels[code] || {}).name || code; }
    function esc(t) { return mxUtils.htmlEntities(String(t == null ? "" : t), false); }

    // what the canvas shows (owner, 10 Nov 2026, D460 and D412): an entity as "<name> : <Entity Type>" (a placeholder as
    // "(unbound) : <Entity Type>"), a relationship's line with its name, or its type when it has none. Display only: the
    // file keeps the name alone in label, so renaming changes the name part and nothing else
    var origLabel = graph.convertValueToString;
    graph.convertValueToString = function (cell) {
      var base = origLabel.apply(this, arguments);
      if (!cell || cell.value == null || typeof cell.value !== "object" || meta.plainLabels) return base;   // D585: as made
      var html = this.isHtmlLabel(cell);
      if (model.isEdge(cell)) {
        if (attr(cell, "ea_decor") === "1") return base;
        var rc = attr(cell, "ea_rel") || (attr(cell, "ea_waiting") === "1" ? attr(cell, "ea_rel_type") : null);
        if (!rc) return base;
        return lineLabel(attr(cell, "label") || "", relName(rc), relAttrsShown ? relValues[attr(cell, "ea_rel_id")] : null, html);
      }
      if (model.isVertex(cell) && attr(cell, "ea_type") && !isJunction(cell)) {
        var unbound = attr(cell, "ea_placeholder") === "1" && !attr(cell, "ea_id");
        var nm = unbound ? "(unbound)" : (attr(cell, "label") || "");
        var tn = typeName(attr(cell, "ea_type"));
        // the name in bold, the type in italics a size smaller (owner, 21:03); a narrow shape puts the type on a second line
        if (!html) return nm + " : " + tn;
        return (unbound ? esc(nm) : "<b>" + esc(nm) + "</b>") + ' <span style="font-size:0.85em;white-space:nowrap;">: <i>' + esc(tn) + "</i></span>";
      }
      return base;
    };
    // a line: "<name> (<Type>) [key:value key:value]" (owner, 11 Nov 2026, D565). The name never hides the type; no name:
    // "(<Type>)"; no values: no brackets; more than 3 values: the first 3 and "+n". The name bold, the type italic a size
    // smaller, the values smaller and grey (as the shapes, D460); everything escaped
    function lineLabel(name, type, values, html) {
      var keys = values ? Object.keys(values).filter(function (k) { return values[k] !== null && values[k] !== "" && values[k] !== undefined; }) : [];
      var pairs = keys.slice(0, 3).map(function (k) { return k + ":" + String(values[k]).split("\n")[0]; });
      var more = keys.length > 3 ? " +" + (keys.length - 3) : "";
      if (!html) return (name ? name + " " : "") + "(" + type + ")" + (pairs.length ? " [" + pairs.join(" ") + more + "]" : "");
      return (name ? "<b>" + esc(name) + "</b> " : "") + '<span style="font-size:0.85em;"><i>(' + esc(type) + ")</i></span>" +
        (pairs.length ? ' <span style="font-size:0.8em;color:#6a737d;">[' + pairs.map(esc).join(" ") + esc(more) + "]</span>" : "");
    }
    ui.eaxLineLabel = lineLabel;             // for the tests
    // editing a label in place starts from the plain name, never the bold and italic markup (the type is not part of it)
    var origEditing = graph.getEditingValue;
    graph.getEditingValue = function (cell) {
      if (cell && model.isVertex(cell) && attr(cell, "ea_type") && !isJunction(cell)) {
        var nm = attr(cell, "label") || "";
        return this.isHtmlLabel(cell) ? esc(nm) : nm;
      }
      if (cell && model.isEdge(cell) && attr(cell, "ea_rel")) { var t = attr(cell, "label") || ""; return this.isHtmlLabel(cell) ? esc(t) : t; }
      return origEditing.apply(this, arguments);
    };

    // the standard look of an object: its type's box (or shape), colour, and its state (placeholder, deleted, icon)
    function objectStyle(code, form, flags) {
      flags = flags || {};
      var t = meta.types[code] || {};
      var box = t.box || t.style || "rounded=0;whiteSpace=wrap;html=1;";
      var s;
      if (form === "shape" && t.shape) s = t.shape;
      else if (flags.icon) {
        s = "shape=label;whiteSpace=wrap;html=1;align=center;verticalAlign=middle;image=" + dataUri(flags.icon) +
          ";imageAlign=right;imageVerticalAlign=top;imageWidth=18;imageHeight=18;spacingTop=4;" +
          (/archiType=rounded/.test(box) ? "rounded=1;arcSize=12;" : "rounded=0;");
      } else s = box;
      if (!/;$/.test(s)) s += ";";
      s += "fillColor=#" + String(t.colour || "E4DED2").replace("#", "") + ";";
      if (form !== "shape") s += "container=1;collapsible=0;recursiveResize=0;dropTarget=1;";
      if (flags.placeholder) s += "dashed=1;fontStyle=2;opacity=70;";
      if (flags.deleted) s += DELETED;
      return s;
    }
    function styleOf(cell) {
      return objectStyle(attr(cell, "ea_type"), attr(cell, "ea_form"), {
        placeholder: attr(cell, "ea_placeholder") === "1", deleted: attr(cell, "ea_deleted") === "1",
        icon: icons[attr(cell, "ea_id")] });
    }
    function lineStyle(cell) {
      return relStyle(attr(cell, "ea_rel")) + "labelBackgroundColor=#ffffff;fontSize=11;" + (attr(cell, "ea_uncommitted") === "1" ? UNCOMMITTED : "") +
        (attr(cell, "ea_deleted") === "1" ? DELETED : "");
    }
    // the standard look, keeping the layout the person gave it (fonts, routing)
    function restyle(cell) { model.setStyle(cell, lockedStyle(model.isEdge(cell) ? lineStyle(cell) : styleOf(cell), model.getStyle(cell))); }

    // ------------------------------------------------------------ the hidden list, kept with the view (D354 rule 4)
    function root() { return model.getCell("0") || model.getRoot(); }
    function hidden() { try { return JSON.parse(attr(root(), "ea_hidden") || "[]"); } catch (e) { return []; } }
    function setHidden(list) { model.setValue(root(), withAttrs(root(), { ea_hidden: JSON.stringify(list) })); }
    function relOf(edge) {
      return { rel: attr(edge, "ea_rel"), id: attr(edge, "ea_rel_id"), source: attr(edge.source, "ea_id") || attr(edge.source, "ea_junction"),
        target: attr(edge.target, "ea_id") || attr(edge.target, "ea_junction") };
    }
    function hide(edge) {
      var rel = relOf(edge);
      silently(function () {
        setHidden(hidden().filter(function (h) { return h.id !== rel.id; }).concat([rel]));
        graph.removeCells([edge], false);
      });
      post({ event: "eax-hidden", relationship: rel });
    }
    function showHidden(cell) {
      var id = attr(cell, "ea_id") || attr(cell, "ea_junction"), keep = [], shown = [];
      hidden().forEach(function (h) { (h.source === id || h.target === id ? shown : keep).push(h); });
      silently(function () {
        shown.forEach(function (h) {
          var s = findEntity(h.source), t = findEntity(h.target);
          if (s && t) addRelationshipEdge(s, t, h.rel, h.id, false); else keep.push(h);
        });
        setHidden(keep);
      });
      post({ event: "eax-shown", entity: id, count: shown.length });
    }
    function allCells() { return Object.keys(model.cells).map(function (k) { return model.cells[k]; }); }
    function vertices() { return allCells().filter(function (c) { return model.isVertex(c); }); }
    function findEntity(id) {
      var all = vertices();
      for (var i = 0; i < all.length; i++) if (attr(all[i], "ea_id") === id || attr(all[i], "ea_junction") === id) return all[i];
      return null;
    }
    function findRelationship(id) {
      var all = allCells();
      for (var i = 0; i < all.length; i++) if (model.isEdge(all[i]) && attr(all[i], "ea_rel_id") === id) return all[i];
      return null;
    }
    // a relationship's name is its line's label, on the line (D412); with no name the canvas shows its type (D460)
    function addRelationshipEdge(s, t, rel, relId, uncommitted, name) {
      var v = node({ label: name || "", ea_rel: rel, ea_rel_id: relId, ea_uncommitted: uncommitted ? "1" : null });
      var e = graph.insertEdge(graph.getDefaultParent(), null, v, s, t, "");
      model.setStyle(e, lineStyle(e));
      if (nestedPair(s, t)) markNested(e, true);
      return e;
    }
    function nestedPair(a, b) { return model.getParent(a) === b || model.getParent(b) === a; }
    function markNested(edge, on) {           // a nested relationship's line is not drawn (rule 6); not the hidden list
      model.setValue(edge, withAttrs(edge, { ea_nested: on ? "1" : null }));
      model.setVisible(edge, !on);
    }

    // ------------------------------------------------------------ the stencil (D387, D388, D396, D397)
    function clearPalettes() {
      var sb = ui.sidebar;
      if (!sb) return;
      for (var id in sb.palettes) {
        (sb.palettes[id] || []).forEach(function (el) { if (el && el.parentNode) el.parentNode.removeChild(el); });
        delete sb.palettes[id];
      }
      clearPalettesExtras();
    }
    function clearPalettesExtras() {
      Array.prototype.forEach.call(ui.sidebar.container.querySelectorAll("button, a"), function (b) {
        if (/More Shapes/i.test(b.textContent || "")) b.style.display = "none";
      });
    }
    // the stencil's groups (D409): each domain's types, Relationships, Junctions; the host shows or hides each as the person
    // likes (it remembers the choice in the browser); nothing of it is saved in the view
    // in ArchiMate's order (owner, 10 Nov 2026, D412): the domains as the owner's ArchiMate 4 guide lists them (and a
    // TOGAF-metamodel model's), any other after alphabetically; each domain's types in the metamodel's order, extensions
    // last; the relationships structural, dependency, dynamic, other
    var DOMAIN_ORDER = ["Motivation", "Strategy", "Common", "Business", "Data", "Application", "Technology",
      "Implementation & Migration", "Implementation and Migration", "Governance"];
    var REL_ORDER = ["Composition", "Aggregation", "Assignment", "Realization", "Serving", "Access", "Influence", "Association",
      "Triggering", "Flow", "Specialization"];
    function rankOf(list, x) { var i = list.indexOf(x); return i < 0 ? list.length : i; }
    function domainCompare(a, b) {
      return rankOf(DOMAIN_ORDER, a) - rankOf(DOMAIN_ORDER, b) || (a.toLowerCase() < b.toLowerCase() ? -1 : a.toLowerCase() > b.toLowerCase() ? 1 : 0);
    }
    function orderedTypes() {             // the setup's order (the metamodel's), extensions after the rest of their domain
      var codes = Object.keys(meta.types);
      return codes.map(function (c, i) { return [c, i]; }).sort(function (x, y) {
        var tx = meta.types[x[0]], ty = meta.types[y[0]];
        return domainCompare(tx.domain || "Other", ty.domain || "Other") || ((tx.extension ? 1 : 0) - (ty.extension ? 1 : 0)) || x[1] - y[1];
      }).map(function (x) { return x[0]; });
    }
    // draw.io's own standard palettes, for decoration only (owner, 10 Nov 2026, D414): text, notes, comments, callouts,
    // arrows, containers. Never its ArchiMate libraries (D396) nor More Shapes. Their shapes carry no ea_ attributes and are
    // freely styled; their lines are marked ea_decor="1", so a decoration arrow between two objects never becomes a relationship
    var DECOR = [["General", "general", "addGeneralPalette"], ["Misc", "misc", "addMiscPalette"], ["Basic", "basic", "addBasicPalette"]];
    var DECOR_IDS = DECOR.map(function (d) { return d[1]; });
    var decorDepth = 0;
    function paletteGroups() {
      var g = [];
      orderedTypes().forEach(function (code) {
        var d = meta.types[code].domain || "Other";
        if (g.indexOf(d) < 0) g.push(d);
      });
      return g.concat(["Relationships", "Junctions"]).concat(DECOR.map(function (d) { return d[0]; }));
    }
    function paletteId(group) {
      for (var i = 0; i < DECOR.length; i++) if (DECOR[i][0] === group) return DECOR[i][1];
      return group === "Relationships" ? "eax-relationships" : group === "Junctions" ? "eax-junctions" : "eax-" + group;
    }
    function ours(id) { return id.indexOf("eax-") === 0 || DECOR_IDS.indexOf(id) >= 0; }
    function markDecor(cells) {               // the lines among a decoration palette's cells (and inside groups)
      (cells || []).forEach(function (c) {
        if (!c) return;
        if (c.edge) c.value = withAttrs(c, { ea_decor: "1" });
        for (var i = 0; i < (c.children || []).length; i++) markDecor([c.children[i]]);
      });
    }
    function addDecorPalettes() {
      var sb = ui.sidebar;
      if (!sb.eaxDecorWrapped) {               // once: the palettes' items are built later, when a palette is opened
        sb.eaxDecorWrapped = true;
        var origItem = sb.createItem, origFns = sb.addPaletteFunctions;
        sb.createItem = function (cells) { if (decorDepth > 0) markDecor(cells); return origItem.apply(this, arguments); };
        sb.addPaletteFunctions = function (id, title, expand, fns) {
          if (DECOR_IDS.indexOf(id) < 0) return origFns.apply(this, arguments);
          return origFns.call(this, id, title, false, (fns || []).map(function (fn) {
            return function () { decorDepth++; try { return fn.apply(this, arguments); } finally { decorDepth--; } };
          }));
        };
      }
      DECOR.forEach(function (d) {
        try { if (typeof sb[d[2]] === "function") sb[d[2]](false); } catch (x) { /* this draw.io has no such palette */ }
      });
    }
    function applyPalettes() {
      var sb = ui.sidebar;
      if (!sb) return;
      paletteGroups().forEach(function (group) {
        (sb.palettes[paletteId(group)] || []).forEach(function (el) {
          if (!el || !el.style) return;
          if (shown[group] === false) {
            if (el.getAttribute("data-eax-hid") == null) el.setAttribute("data-eax-hid", el.style.display || "");
            el.style.display = "none";
          } else if (el.getAttribute("data-eax-hid") != null) {   // as it was: a collapsed palette stays collapsed
            el.style.display = el.getAttribute("data-eax-hid");
            el.removeAttribute("data-eax-hid");
          }
        });
      });
    }
    // the stencil's size: small (draw.io's own), medium (twice as big, the default) or large, so the ArchiMate icons can
    // be seen (owner, 10 Nov 2026, D412); EA Explorer remembers the person's choice and sends it ("stencil-size")
    var THUMBS = { small: 42, medium: 84, large: 120 };
    var thumb = THUMBS.medium;
    function buildStencil() {
      var sb = ui.sidebar;
      if (!sb) return;
      sb.thumbWidth = thumb; sb.thumbHeight = Math.round(thumb * 0.6);
      clearPalettes();
      if (meta.readOnly) return;
      sb.sidebarTitles = true;                 // each type and line with its name under it
      var byDomain = {}, domains = [];
      orderedTypes().forEach(function (code) {
        var d = meta.types[code].domain || "Other";
        if (!byDomain[d]) { byDomain[d] = []; domains.push(d); }
        byDomain[d].push(code);
      });
      domains.forEach(function (domain) {
        sb.addPalette("eax-" + domain, domain, true, function (content) {
          byDomain[domain].forEach(function (code) {
            var cell = new mxCell(node({ label: typeName(code), ea_type: code, ea_placeholder: "1" }), new mxGeometry(0, 0, 120, 60),
              objectStyle(code, "box", { placeholder: true }));
            cell.vertex = true;
            var title = typeName(code) + (meta.types[code].extension ? " (extension)" : "");
            content.appendChild(sb.createVertexTemplateFromCells([cell], 120, 60, title, true));
          });
        });
      });
      // the relationship types the metamodel allows somewhere, as lines to drag between two objects
      var used = {};
      meta.allowed.forEach(function (a) { used[a[1]] = true; });
      var codes = Object.keys(meta.rels).length ? Object.keys(meta.rels).filter(function (c) { return used[c]; })
        : Object.keys(DEFAULT_REL_STYLES).filter(function (c) { return used[c]; });
      codes = codes.map(function (c, i) { return [c, i]; })
        .sort(function (x, y) { return rankOf(REL_ORDER, x[0]) - rankOf(REL_ORDER, y[0]) || x[1] - y[1]; }).map(function (x) { return x[0]; });
      if (codes.length) sb.addPalette("eax-relationships", "Relationships", true, function (content) {
        codes.forEach(function (code) {
          var e = new mxCell(node({ ea_rel_type: code }), new mxGeometry(0, 0, 0, 0), relStyle(code));
          e.geometry.setTerminalPoint(new mxPoint(0, 0), true);
          e.geometry.setTerminalPoint(new mxPoint(100, 0), false);
          e.geometry.relative = true;
          e.edge = true;
          content.appendChild(sb.createEdgeTemplateFromCells([e], 100, 0, (meta.rels[code] || {}).name || code, true));
        });
      });
      sb.addPalette("eax-junctions", "Junctions", true, function (content) {
        ["and", "or"].forEach(function (kind) {
          var j = new mxCell(node({ ea_junction_kind: kind }), new mxGeometry(0, 0, 14, 14), JUNCTION_STYLES[kind]);
          j.vertex = true;
          content.appendChild(sb.createVertexTemplateFromCells([j], 14, 14, kind === "and" ? "And junction" : "Or junction", true));
        });
      });
      addDecorPalettes();
      applyPalettes();
    }
    function readOnly(on) {
      graph.setCellsMovable(!on); graph.setCellsResizable(!on); graph.setCellsDeletable(!on);
      graph.setCellsEditable(!on); graph.setConnectable(!on); graph.setDropEnabled(!on);
      graph.setCellsDisconnectable(!on); graph.setCellsBendable(!on); graph.setCellsCloneable(!on);
    }

    // ------------------------------------------------------------ the working space (owner, 10 Nov 2026, D420)
    // draw.io's Format panel (Style, Text, Arrange) is gone for good: EA objects take their look from the notation (D396).
    // Alignment, distribution, order and size stay in the right-click menu and the Arrange menu. Its toggle button, the
    // View > Format item and Ctrl+Shift+P do nothing
    function noFormatPanel() {
      try {
        if (!ui.eaxNoFormat) {
          ui.eaxNoFormat = true;
          var origToggle = ui.toggleFormatPanel;
          ui.toggleFormatPanel = function () { if (origToggle) return origToggle.call(ui, false); };
        }
        ui.toggleFormatPanel(false);
        if (ui.formatWidth) { ui.formatWidth = 0; if (ui.formatContainer) ui.formatContainer.style.width = "0px"; }
        var a = ui.actions && ui.actions.get("format");
        if (a) { a.visible = false; a.setEnabled(false); a.funct = function () {}; }
        [ui.toggleFormatElement, ui.fullscreenElement].forEach(function (el) { if (el) el.style.display = "none"; });
        if (ui.formatWindow && ui.formatWindow.window) ui.formatWindow.window.setVisible(false);
        ui.refresh();
      } catch (x) { /* another draw.io: its own panel stays */ }
    }
    noFormatPanel();

    // ------------------------------------------------------------ File > Export as > .drawio file (owner, 11 Nov 2026, D585)
    // embed mode offers PNG, SVG, PDF and "XML..." (a dialog, compressed by default) but no plain .drawio file: ours
    // downloads the current diagram, uncompressed, named after the view or picture. Read-only views offer it too
    function fileTitle() {
      var t = meta.title;
      try { if (!t && ui.getCurrentFile && ui.getCurrentFile()) t = ui.getCurrentFile().getTitle(); } catch (x) { /* none */ }
      t = String(t || "diagram").replace(/\.(drawio|xml)$/i, "").replace(/[\\/:*?"<>|]+/g, "-").trim();
      return (t || "diagram") + ".drawio";
    }
    function drawioFileXml() {
      var prev = Graph.compressXml, xml = "";
      Graph.compressXml = false;
      try { xml = ui.getFileData(true); } catch (x) { xml = ""; } finally { Graph.compressXml = prev; }
      if (!/<mxfile/.test(xml) || !/<mxGraphModel/.test(xml)) {      // another draw.io: build it ourselves
        xml = '<mxfile host="EA Explorer"><diagram name="' + mxUtils.htmlEntities(fileTitle().replace(/\.drawio$/, "")) +
          '" id="eax">' + mxUtils.getXml(ui.editor.getGraphXml()) + "</diagram></mxfile>";
      }
      return xml;
    }
    function exportDrawioFile() {
      var xml = drawioFileXml(), name = fileTitle();
      try {
        var url = URL.createObjectURL(new Blob([xml], { type: "application/vnd.jgraph.mxfile" }));
        var a = document.createElement("a");
        a.href = url; a.download = name; a.style.display = "none";
        document.body.appendChild(a); a.click();
        setTimeout(function () { URL.revokeObjectURL(url); if (a.parentNode) a.parentNode.removeChild(a); }, 1000);
      } catch (x) { /* the host is told below */ }
      post({ event: "eax-exported-drawio", name: name, size: xml.length });
    }
    try {
      ui.actions.put("eaxExportDrawio", new Action(".drawio file...", exportDrawioFile));
      var exportMenu = ui.menus.get("exportAs");
      if (exportMenu && !exportMenu.eaxDrawio) {
        exportMenu.eaxDrawio = true;
        var origExport = exportMenu.funct;
        exportMenu.funct = function (menu, parent) {
          ui.menus.addMenuItems(menu, ["eaxExportDrawio", "-"], parent);
          return origExport.apply(this, arguments);
        };
      }
    } catch (x) { /* another draw.io: its own menu stays */ }
    // the stencil is draw.io's left sidebar; EA Explorer pins and unpins it (its strip is EA Explorer's) and keeps its width
    var stencilWidth = 0, stencilOpen = true;
    function stencilPanel(open, width) {
      if (width > 80) stencilWidth = Math.min(600, Math.round(width));
      stencilOpen = !!open;
      var w = stencilOpen ? (stencilWidth || ui.hsplitPosition || EditorUi.prototype.hsplitPosition || 220) : 0;
      if (ui.hsplitPosition !== w) { ui.hsplitPosition = w; ui.refresh(); }
    }
    var origRefresh = ui.refresh, widthTimer = null;
    ui.refresh = function () {                // the person dragged the stencil's edge: EA Explorer remembers the width
      var r = origRefresh.apply(this, arguments);
      if (stencilOpen && ui.hsplitPosition > 80 && ui.hsplitPosition !== stencilWidth) {
        stencilWidth = ui.hsplitPosition;
        clearTimeout(widthTimer);
        widthTimer = setTimeout(function () { post({ event: "eax-stencil-width", width: stencilWidth }); }, 400);
      }
      return r;
    };
    // a click on the drawing: EA Explorer folds away a panel it opened over it
    graph.addListener(mxEvent.CLICK, function () { post({ event: "eax-canvas-click" }); });

    // somewhere free next to an object, for what is added from the Relationships and Allowed relationships tabs (D420):
    // right, below, left, above, then further out; never on top of another object
    function bounds(c) {
      var st = graph.view.getState(c), s = graph.view.scale, tr = graph.view.translate;
      if (st) return { x: st.x / s - tr.x, y: st.y / s - tr.y, w: st.width / s, h: st.height / s };
      var g = model.getGeometry(c) || { x: 0, y: 0, width: 140, height: 70 };
      return { x: g.x, y: g.y, w: g.width, h: g.height };
    }
    function freeSpot(near, w, h) {
      var b = bounds(near), gap = 60, taken = vertices().filter(function (v) { return v !== near && model.isVisible(v); }).map(bounds);
      function free(x, y) {
        return x >= 0 && y >= 0 && !taken.some(function (o) { return x < o.x + o.w + 20 && x + w + 20 > o.x && y < o.y + o.h + 20 && y + h + 20 > o.y; });
      }
      for (var ring = 1; ring <= 8; ring++) {
        var dx = (b.w + gap) * ring, dy = (b.h + gap) * ring;
        var tries = [[b.x + dx, b.y], [b.x, b.y + dy], [b.x - (w + gap) * ring, b.y], [b.x, b.y - (h + gap) * ring],
          [b.x + dx, b.y + dy], [b.x - (w + gap) * ring, b.y + dy], [b.x + dx, b.y - (h + gap) * ring]];
        for (var i = 0; i < tries.length; i++) if (free(tries[i][0], tries[i][1])) return { x: Math.round(tries[i][0]), y: Math.round(tries[i][1]) };
      }
      return { x: Math.round(b.x + b.w + gap), y: Math.round(b.y + b.h + gap) };
    }
    // a line waiting for its placeholder (D420): the relationship type chosen from Allowed relationships, drawn faint;
    // when the placeholder is bound or created, EA Explorer makes the relationship (committed at once, D413)
    var WAITING = "dashed=1;dashPattern=2 4;strokeColor=#8A96A3;fontColor=#8A96A3;";
    function waitingLine(s, t, rel) {
      var v = node({ label: "", ea_rel_type: rel, ea_waiting: "1" });
      var e = graph.insertEdge(graph.getDefaultParent(), null, v, s, t, "");
      model.setStyle(e, relStyle(rel) + WAITING);
      return e;
    }
    function askWaiting(c) {                  // the bound object's waiting lines whose other end is real: made now
      (model.getEdges(c) || []).forEach(function (e) {
        if (attr(e, "ea_waiting") !== "1" || attr(e, "ea_rel") || !e.source || !e.target) return;
        if (!isRealised(e.source) || !isRealised(e.target) || asked[e.id]) return;
        asked[e.id] = true;
        post({ event: "eax-waiting-line", cell: e.id, source: attr(e.source, "ea_id"), target: attr(e.target, "ea_id"), type: attr(e, "ea_rel_type") });
      });
    }

    // ------------------------------------------------------------ what the person does: checked, locked or reported
    var origEditable = graph.isCellEditable;
    // a bound line's name may be edited in place (D565): only its name changes, the type stays (eax-rel-rename)
    function namedLine(cell) { return model.isEdge(cell) && !!attr(cell, "ea_rel") && !!attr(cell, "ea_rel_id"); }
    graph.isCellEditable = function (cell) {
      return !meta.readOnly && (!isEa(cell) || namedLine(cell)) && origEditable.apply(this, arguments);
    };
    ["editData", "editStyle", "editTooltip", "editLink", "editShape"].forEach(function (name) {
      var a = ui.actions.get(name);
      if (!a) return;
      var f = a.funct;
      a.funct = function () {
        var c = graph.getSelectionCell();
        if (meta.readOnly || (c && isEa(c))) { post({ event: "eax-refused", reason: "EA objects and relationships show the model: change them in EA Explorer; on the view only their layout changes." }); return; }
        return f.apply(this, arguments);
      };
    });

    function parseStyle(s) {
      var out = { names: [], keys: {} };
      String(s || "").split(";").forEach(function (part) {
        if (!part) return;
        var i = part.indexOf("=");
        if (i < 0) out.names.push(part); else out.keys[part.substring(0, i)] = part.substring(i + 1);
      });
      return out;
    }
    function lockedStyle(oldStyle, newStyle) {   // the old style with only the layout keys taken from the new one
      var o = parseStyle(oldStyle), n = parseStyle(newStyle), k;
      LAYOUT_KEYS.forEach(function (key) { if (key in n.keys) o.keys[key] = n.keys[key]; });
      var s = o.names.join(";") + (o.names.length ? ";" : "");
      for (k in o.keys) s += k + "=" + o.keys[k] + ";";
      return s;
    }
    function sameStyle(a, b) {
      var x = parseStyle(a), y = parseStyle(b), k;
      if (x.names.join(";") !== y.names.join(";")) return false;
      for (k in x.keys) if (x.keys[k] !== y.keys[k]) return false;
      for (k in y.keys) if (x.keys[k] !== y.keys[k]) return false;
      return true;
    }

    var changeTimer = null;
    function changed() {
      clearTimeout(changeTimer);
      changeTimer = setTimeout(function () {
        var ph = vertices().filter(function (c) { return attr(c, "ea_placeholder") === "1"; }).length;
        post({ event: "eax-changed", dirty: true, placeholders: ph,
          unboundJunctions: vertices().filter(function (c) { return isJunction(c) && !attr(c, "ea_junction"); }).length });
      }, 300);
    }

    model.addListener(mxEvent.CHANGE, function (sender, evt) {
      changed();
      if (quiet) return;
      var changes = evt.getProperty("edit").changes, reverts = [];
      var geo = {}, byUndo = undoing > 0;
      changes.forEach(function (ch) { if (ch instanceof mxGeometryChange && ch.cell) geo[ch.cell.id] = ch.previous; });
      changes.forEach(function (ch) {
        var c = ch.cell || ch.child;
        // colours, shapes, names and the ea_ attributes of EA cells do not change on the view: put back
        if (ch instanceof mxStyleChange && isEa(c) && c !== root()) {
          // the standard look, with only the layout keys of what the person did (worked out when putting back, so
          // several changes in a row end in one right style)
          reverts.push(function () {
            if (!model.contains(c) || !isEa(c)) return;          // a value put back restyles it
            var std = isJunction(c) ? JUNCTION_STYLES[attr(c, "ea_junction_kind")] || ch.previous : (model.isEdge(c) && !attr(c, "ea_rel") ? ch.previous : (model.isEdge(c) ? lineStyle(c) : styleOf(c)));
            var keep = lockedStyle(std, model.getStyle(c));
            if (!sameStyle(keep, model.getStyle(c))) model.setStyle(c, keep);
          });
        } else if (ch instanceof mxValueChange && c && model.isEdge(c) && attr(c, "ea_rel_id") && !meta.readOnly && meta.mayChange !== false &&
                   ch.previous && typeof ch.previous === "object" && ch.previous.getAttribute && onlyLabelChanged(ch.previous, c.value)) {
          // a line renamed in place (D565): the name only; its type stays. EA Explorer changes it in the model at once
          // (D413) and puts it back if it cannot
          var oldName = ch.previous.getAttribute("label") || "";
          var relId = attr(c, "ea_rel_id"), newName = attr(c, "label") || "";
          if (newName !== oldName) setTimeout(function () { post({ event: "eax-rel-rename", relationship: relId, name: newName, previous: oldName }); }, 0);
        } else if (ch instanceof mxValueChange && c !== root() && (isEa(c) || (ch.previous && typeof ch.previous === "object" &&
                   ch.previous.getAttribute && (ch.previous.getAttribute("ea_id") || ch.previous.getAttribute("ea_rel"))))) {
          var prev = ch.previous;
          reverts.push(function () { model.setValue(c, prev); if (c !== root() && !isJunction(c) && (attr(c, "ea_type") || attr(c, "ea_rel"))) restyle(c); });
        } else if (byUndo && ch instanceof mxTerminalChange) {
          // undo or redo moves a line's ends back as they were: nothing to check or put back
        } else if (byUndo && ch instanceof mxChildChange && ch.child && model.isEdge(ch.child) && attr(ch.child, "ea_rel_id")) {
          // undo takes a relationship's line off the view only (the model keeps it); redo puts it back, bound
          undoneLine(ch.child, ch.parent != null);
        } else if (byUndo && ch instanceof mxChildChange && ch.parent == null && ch.child && model.isVertex(ch.child) && isRealised(ch.child)) {
          undoneObject(ch.child);
        } else if (byUndo && ch instanceof mxChildChange && ch.parent != null && ch.child && model.isVertex(ch.child) && isRealised(ch.child)
                   && ch.previous == null) {
          setTimeout(function () { post({ event: "eax-undo-back", entity: attr(ch.child, "ea_id") }); }, 0);   // its lines drawn again
        } else if (ch instanceof mxTerminalChange && attr(c, "ea_rel_id")) {
          // a relationship's ends are the model's: put back
          var prevT = ch.previous, isSource = ch.source;
          reverts.push(function () { model.setTerminal(c, prevT, isSource); });
          post({ event: "eax-refused", reason: "A relationship's ends are kept: draw a new line for another relationship." });
        } else if (ch instanceof mxTerminalChange && model.isEdge(c) && !attr(c, "ea_rel") && !isDecor(c)) {
          setTimeout(function () { checkEdge(c); }, 0);
        } else if (ch instanceof mxChildChange && ch.parent == null && ch.child && attr(ch.child, "ea_rel_id")) {
          // a relationship's line deleted by the person: EA Explorer asks each time (owner, 10 Nov 2026, D413): hide it in
          // this view (the hidden list), or delete the relationship from the model; cancelled, the line comes back.
          // Lines that went with a deleted object are not asked about (they come back when the object does)
          var e = ch.child;
          setTimeout(function () {
            if (!e.source || !e.target || !model.contains(e.source) || !model.contains(e.target)) return;
            var rel = relOf(e);
            rel.name = attr(e, "label") || ""; rel.pending = attr(e, "ea_uncommitted") === "1";
            gone[rel.id] = { s: e.source, t: e.target, rel: rel };
            post({ event: "eax-line-deleted", relationship: rel });
          }, 0);
        } else if (ch instanceof mxChildChange && ch.parent && ch.child && model.isVertex(ch.child) && isRealised(ch.child)
                   && ch.previous && ch.previous !== ch.parent) {
          // nesting must match a relationship (rule 6): dropped into another object, or taken out of one
          var child = ch.child, from = ch.previous, to = ch.parent, g = geo[child.id];
          if (isRealised(to)) {
            nesting[child.id] = { parent: from, geometry: g };
            setTimeout(function () {
              post({ event: "eax-nest", cell: child.id, entity: attr(child, "ea_id"), parentCell: to.id, parent: attr(to, "ea_id") });
            }, 0);
          }
          if (isRealised(from)) setTimeout(function () { unnested(child, from); }, 0);
        }
      });
      if (reverts.length) setTimeout(function () { silently(function () { reverts.forEach(function (f) { f(); }); }); }, 0);
    });
    function onlyLabelChanged(prev, cur) {
      if (!cur || typeof cur !== "object" || !cur.attributes) return false;
      var names = {}, i;
      for (i = 0; i < prev.attributes.length; i++) names[prev.attributes[i].name] = true;
      for (i = 0; i < cur.attributes.length; i++) names[cur.attributes[i].name] = true;
      return Object.keys(names).every(function (k) { return k === "label" || (prev.getAttribute(k) || "") === (cur.getAttribute(k) || ""); });
    }
    function undoneLine(e, back) {
      var rel = relOf(e);
      setTimeout(function () {
        if (back) {
          if (removedRels[rel.id]) {
            silently(function () { if (model.contains(e)) graph.removeCells([e], false); });
            post({ event: "eax-refused", reason: "That relationship was deleted from the model, so its line cannot come back." });
            return;
          }
          silently(function () { setHidden(hidden().filter(function (h) { return h.id !== rel.id; })); });
          return;
        }
        if (findRelationship(rel.id) || removedRels[rel.id]) return;      // another line still shows it, or it is gone anyway
        silently(function () {
          setHidden(hidden().filter(function (h) { return h.id !== rel.id; }).concat([{ rel: rel.rel, id: rel.id, source: rel.source, target: rel.target }]));
        });
        post({ event: "eax-undo-note", text: "Still in the model; delete the line to remove it from the model." });
      }, 0);
    }
    function undoneObject(v) {                // undo took an object off the view: its lines go with it, the model keeps it
      setTimeout(function () {
        var dangling = allCells().filter(function (e) {
          return model.isEdge(e) && model.contains(e) && ((e.source && !model.contains(e.source)) || (e.target && !model.contains(e.target)));
        });
        if (dangling.length) silently(function () { graph.removeCells(dangling, false); });
        post({ event: "eax-undo-note", text: "Taken off this view only; it is still in the model." });
      }, 0);
    }
    function unnested(child, from) {           // out of its parent: the line between them is drawn again
      silently(function () {
        allCells().forEach(function (e) {
          if (model.isEdge(e) && attr(e, "ea_nested") === "1" && ((e.source === child && e.target === from) || (e.source === from && e.target === child)))
            markNested(e, false);
        });
      });
    }

    graph.addListener(mxEvent.CELLS_ADDED, function (sender, evt) {
      if (quiet) return;
      var cells = evt.getProperty("cells") || [];
      cells.forEach(function (c) {
        if (model.isEdge(c)) { if (!isDecor(c)) setTimeout(function () { checkEdge(c); }, 0); }
        else if (isJunction(c) && !attr(c, "ea_junction")) setTimeout(function () { post({ event: "eax-junction-new", cell: c.id, kind: attr(c, "ea_junction_kind") }); }, 0);
      });
      // one placeholder dropped (or clicked in) from the stencil: EA Explorer asks what it is (D420): bind it to an
      // existing entity, create a new one, or leave it as a placeholder
      var drops = cells.filter(function (c) { return model.isVertex(c) && attr(c, "ea_placeholder") === "1" && !isJunction(c); });
      if (drops.length === 1 && !meta.readOnly) {
        var d = drops[0];
        setTimeout(function () { if (model.contains(d)) post({ event: "eax-dropped", cell: d.id, type: attr(d, "ea_type") }); }, 0);
      }
    });
    graph.connectionHandler.addListener(mxEvent.CONNECT, function (sender, evt) {
      if (!quiet) setTimeout(function () { checkEdge(evt.getProperty("cell")); }, 0);
    });
    function refuse(edge, why) {
      silently(function () { if (model.contains(edge)) graph.removeCells([edge], false); });
      post({ event: "eax-refused", reason: why });
    }
    function allowedBetween(s, r, t) {
      return meta.allowed.some(function (a) { return a[0] === s && a[1] === r && a[2] === t; });
    }
    function typesBetween(s, t) {
      return meta.allowed.filter(function (a) { return a[0] === s && a[2] === t; }).map(function (a) { return a[1]; });
    }
    function junctionLines(j) { return model.getEdges(j).filter(function (e) { return attr(e, "ea_rel"); }); }
    function isDecor(cell) { return attr(cell, "ea_decor") === "1"; }
    function checkEdge(edge) {
      if (!edge || !model.contains(edge) || attr(edge, "ea_rel") || isDecor(edge) || asked[edge.id]) return;
      if (attr(edge, "ea_waiting") === "1") return;            // waits for its placeholder (D420)
      var preset = attr(edge, "ea_rel_type");
      var s = edge.source, t = edge.target;
      // a line to or from a decoration (a note, a comment, text) is decoration too, never a relationship (D414)
      if (!preset && ((s && !isEa(s)) || (t && !isEa(t)))) {
        silently(function () { model.setValue(edge, withAttrs(edge, { ea_decor: "1" })); });
        return;
      }
      if (!s || !t) {
        if (preset) return;                      // a line from the stencil, not yet joined at both ends: wait
        return refuse(edge, "A line must join two objects of the model.");
      }
      if ((!isRealised(s) && !isJunction(s)) || (!isRealised(t) && !isJunction(t)))
        return refuse(edge, "Relationships join realised objects only: choose the instance of a placeholder first.");
      if (isJunction(s) && isJunction(t)) return refuse(edge, "A line joins a junction to an object, not to another junction.");
      var j = isJunction(s) ? s : isJunction(t) ? t : null, options, through = [];
      if (j) {
        if (!attr(j, "ea_junction")) return refuse(edge, "The junction is not in the model yet: try again in a moment.");
        var lines = junctionLines(j), fixed = lines.length ? attr(lines[0], "ea_rel") : null;
        // the objects on the junction's other side: the line is checked as if it ran to each of them (D397)
        var objectEnd = j === s ? t : s, outgoing = j === s;
        lines.forEach(function (e) {
          if (outgoing && e.target === j && e.source) through.push(e.source);
          if (!outgoing && e.source === j && e.target) through.push(e.target);
        });
        var candidates = fixed ? [fixed] : Object.keys(DEFAULT_REL_STYLES).concat(Object.keys(meta.rels));
        var ot = attr(objectEnd, "ea_type");
        options = candidates.filter(function (r, i, all) {
          if (all.indexOf(r) !== i) return false;
          if (!through.length) return meta.allowed.some(function (a) { return a[1] === r && (outgoing ? a[2] === ot : a[0] === ot); });
          return through.every(function (x) {
            return outgoing ? allowedBetween(attr(x, "ea_type"), r, ot) : allowedBetween(ot, r, attr(x, "ea_type"));
          });
        });
        if (preset) options = options.indexOf(preset) >= 0 ? [preset] : [];
        if (!options.length)
          return refuse(edge, fixed ? "Every line at a junction is one relationship type (" + fixed + "), allowed as if it ran straight through."
            : "No relationship the metamodel allows fits through this junction.");
        asked[edge.id] = true;
        post({ event: "eax-relationship", cell: edge.id, source: attr(s, "ea_id") || attr(s, "ea_junction"),
          target: attr(t, "ea_id") || attr(t, "ea_junction"), options: options, junction: attr(j, "ea_junction"),
          through: through.map(function (x) { return attr(x, "ea_id"); }) });
        return;
      }
      options = typesBetween(attr(s, "ea_type"), attr(t, "ea_type"));
      if (preset) {
        if (options.indexOf(preset) < 0)
          return refuse(edge, "The metamodel does not allow " + preset + " from " + typeName(attr(s, "ea_type")) + " to " + typeName(attr(t, "ea_type")) + ".");
        options = [preset];
      }
      if (!options.length)
        return refuse(edge, "The metamodel allows no relationship from " + typeName(attr(s, "ea_type")) + " to " + typeName(attr(t, "ea_type")) + ".");
      asked[edge.id] = true;
      // EA Explorer asks which one, with its attributes, and answers rel (or rel-cancel)
      post({ event: "eax-relationship", cell: edge.id, source: attr(s, "ea_id"), target: attr(t, "ea_id"), options: options });
    }

    // ------------------------------------------------------------ the right-click menu
    var oldPopup = ui.menus.createPopupMenu;
    ui.menus.createPopupMenu = function (menu, cell, evt) {
      oldPopup.apply(this, arguments);
      var c = graph.getSelectionCell();
      if (!c) return;
      if (meta.readOnly) {
        if (isRealised(c)) { menu.addSeparator(); menu.addItem("Open in EA Explorer", null, function () { post({ event: "eax-open", entity: attr(c, "ea_id") }); }); }
        return;
      }
      if (model.isEdge(c) && attr(c, "ea_rel")) {
        menu.addSeparator();
        menu.addItem("Hide this relationship (in this view)", null, function () { hide(c); });
        if (attr(c, "ea_rel_id") && meta.mayChange !== false)
          menu.addItem("Delete from the model...", null, function () { graph.removeCells([c], false); });
      } else if (model.isVertex(c) && attr(c, "ea_placeholder") === "1") {
        menu.addSeparator();
        menu.addItem("Choose instance...", null, function () { post({ event: "eax-choose", cell: c.id, type: attr(c, "ea_type") }); });
      } else if (model.isVertex(c) && isRealised(c)) {
        menu.addSeparator();
        var id = attr(c, "ea_id");
        var n = hidden().filter(function (h) { return h.source === id || h.target === id; }).length;
        menu.addItem("Add a relationship...", null, function () { addRelationshipAsk(c); });
        menu.addItem("Show hidden relationships (" + n + ")", null, function () { showHidden(c); }, null, null, n > 0);
        var shape = attr(c, "ea_form") === "shape";
        if ((meta.types[attr(c, "ea_type")] || {}).shape || shape)
          menu.addItem(shape ? "Show as box" : "Show as shape", null, function () { setForm(c, shape ? "box" : "shape"); });
        menu.addItem("Change instance...", null, function () { post({ event: "eax-choose", cell: c.id, type: attr(c, "ea_type") }); });
        menu.addItem("Open in EA Explorer", null, function () { post({ event: "eax-open", entity: id }); });
      } else if (model.isVertex(c) && isJunction(c) && attr(c, "ea_junction")) {
        menu.addSeparator();
        menu.addItem("Show hidden relationships", null, function () { showHidden(c); });
      }
    };
    function addRelationshipAsk(c) {
      var candidates = vertices().filter(function (v) { return v !== c && isRealised(v); }).map(function (v) {
        return { cell: v.id, entity: attr(v, "ea_id"), type: attr(v, "ea_type"), name: attr(v, "label") };
      });
      post({ event: "eax-add-relationship", cell: c.id, entity: attr(c, "ea_id"), type: attr(c, "ea_type"), candidates: candidates });
    }
    function setForm(c, form) {               // box or shape (D398): layout, kept with the view
      silently(function () {
        model.setValue(c, withAttrs(c, { ea_form: form === "shape" ? "shape" : null }));
        restyle(c);
      });
      post({ event: "eax-form", cell: c.id, entity: attr(c, "ea_id"), form: form });
    }

    // ------------------------------------------------------------ the heat map: on screen only (part 2)
    var origCellStyle = graph.getCellStyle;
    graph.getCellStyle = function (cell) {
      var st = origCellStyle.apply(this, arguments);
      if (!heat || !model.isVertex(cell) || !isRealised(cell)) return st;
      var id = attr(cell, "ea_id");
      st = mxUtils.clone(st);
      st.fillColor = heat[id] ? "#" + String(heat[id]).replace("#", "") : "#F2F2F2";    // no value: pale grey
      st.gradientColor = "none";
      return st;
    };

    // ------------------------------------------------------------ messages from EA Explorer
    function place(e, x, y, relationships, prefer) {
      var placed;
      silently(function () {
        if (e.icon) icons[e.id] = e.icon;
        placed = graph.insertVertex(graph.getDefaultParent(), null, node({ label: e.name, ea_id: e.id, ea_type: e.type }), x, y, 140, 70, "");
        model.setStyle(placed, styleOf(placed));
        (relationships || []).forEach(function (r) {        // drawn automatically: what the model has with what is on the view (rule 5)
          if (hidden().some(function (h) { return h.id === r.id; }) || findRelationship(r.id)) return;
          var oid = r.source === e.id ? r.target : r.source;
          var other = (prefer && prefer[oid]) || findEntity(oid);
          if (other && other !== placed) addRelationshipEdge(r.source === e.id ? placed : other, r.source === e.id ? other : placed, r.type, r.id, !!r.pending, r.name);
        });
      });
      return placed;
    }
    // a placeholder realised, or a realised object shown as another entity of its type ("Change instance"); its lines are
    // then the new entity's: those of the old one go (not into the hidden list), and the model's relationships with
    // what is on the view are drawn, as when placing (rule 5)
    function bind(c, e, relationships) {
      var before = attr(c, "ea_id");
      // a placeholder from Allowed relationships bound to an entity already on the view (D420): no second copy; its
      // waiting lines move to the object there and the placeholder goes
      var there = findEntity(e.id), waits = (model.getEdges(c) || []).filter(function (x) { return attr(x, "ea_waiting") === "1"; });
      if (there && there !== c && attr(c, "ea_placeholder") === "1" && waits.length) {
        silently(function () {
          waits.forEach(function (x) { model.setTerminal(x, there, x.source === c); });
          graph.removeCells([c], false);
        });
        post({ event: "eax-bound", cell: there.id, entity: e.id, merged: true });
        graph.setSelectionCell(there);
        selected(there);
        askWaiting(there);
        return;
      }
      silently(function () {
        if (e.icon) icons[e.id] = e.icon;
        if (before && before !== e.id) {
          var gone = (model.getEdges(c) || []).filter(function (x) { return attr(x, "ea_rel_id") || attr(x, "ea_rel"); });
          if (gone.length) graph.removeCells(gone, false);
        }
        if (attr(c, "ea_placeholder") === "1") {           // the placeholder's dashed, italic, faded look goes
          var ps = model.getStyle(c) || "";
          ["dashed", "fontStyle", "opacity"].forEach(function (k) { ps = mxUtils.setStyle(ps, k, null); });
          model.setStyle(c, ps);
        }
        model.setValue(c, withAttrs(c, { label: e.name, ea_id: e.id, ea_type: e.type, ea_placeholder: null }));
        restyle(c);
        (relationships || []).forEach(function (r) {
          if (hidden().some(function (h) { return h.id === r.id; }) || findRelationship(r.id)) return;
          var other = findEntity(r.source === e.id ? r.target : r.source);
          if (other && other !== c) addRelationshipEdge(r.source === e.id ? c : other, r.source === e.id ? other : c, r.type, r.id, !!r.pending, r.name);
        });
      });
      post({ event: "eax-bound", cell: c.id, entity: e.id });
      graph.setSelectionCell(c);
      selected(c);
      askWaiting(c);
    }
    // from the Relationships tab (D420): the related entity next to the selected object with the relationship's line; on
    // the view already, the line only (or the line selected, if it is there)
    function addRelated(near, e, rel, relationships) {
      // the same entity may be on the view more than once: the line that matters is the one at this shape
      function lineHere() {
        return allCells().filter(function (x) { return model.isEdge(x) && attr(x, "ea_rel_id") === rel.id && (x.source === near || x.target === near); })[0];
      }
      var other = findEntity(e.id), line = lineHere();
      if (line) { graph.setSelectionCell(line); graph.scrollCellToVisible(line); return { line: line.id, already: true }; }
      silently(function () {
        if (rel.id) setHidden(hidden().filter(function (h) { return h.id !== rel.id; }));     // shown again on purpose
        if (!other) {
          var at = freeSpot(near, 140, 70), prefer = {};
          prefer[attr(near, "ea_id")] = near;
          other = place(e, at.x, at.y, relationships, prefer);
        }
        line = lineHere();
        if (!line) {
          var s = rel.source === e.id ? other : near, t = rel.source === e.id ? near : other;
          line = addRelationshipEdge(s, t, rel.type, rel.id, !!rel.pending, rel.name);
        }
      });
      graph.setSelectionCell(other);
      graph.scrollCellToVisible(other);
      return { cell: other.id, line: line && line.id };
    }
    // from the Allowed relationships tab (D420): a placeholder of the other type next to the selected object, joined by a
    // line waiting for it; EA Explorer then asks what the placeholder is, as for a stencil drop
    function addAllowed(near, type, rel, outgoing) {
      var ph, line;
      silently(function () {
        var at = freeSpot(near, 120, 60);
        ph = graph.insertVertex(graph.getDefaultParent(), null, node({ label: typeName(type), ea_type: type, ea_placeholder: "1" }), at.x, at.y, 120, 60, "");
        model.setStyle(ph, objectStyle(type, "box", { placeholder: true }));
        line = outgoing ? waitingLine(near, ph, rel) : waitingLine(ph, near, rel);
      });
      graph.setSelectionCell(ph);
      graph.scrollCellToVisible(ph);
      return { cell: ph.id, line: line.id };
    }

    window.addEventListener("message", function (ev) {
      var m;
      try { m = typeof ev.data === "string" ? JSON.parse(ev.data) : ev.data; } catch (x) { return; }
      if (!m || !m.eax || ev.source !== host) return;
      var c, n;
      // relationships EA Explorer sends carry their attribute values: kept for the lines' labels (D565)
      (Array.isArray(m.relationships) ? m.relationships : []).forEach(function (r) {
        if (r && r.id && typeof r === "object" && "values" in r) relValues[r.id] = r.values || {};
      });
      if (m.eax === "setup") {
        meta.types = m.types || {}; meta.allowed = m.allowed || []; meta.readOnly = !!m.readOnly;
        meta.rels = m.relationshipTypes || {};
        if (m.title) meta.title = String(m.title);            // the .drawio file's name (D585)
        meta.plainLabels = !!m.plainLabels;                     // a picture of types, or of no model, opened to look at (D585)
        meta.mayChange = m.mayChange;
        if (m.relStyles) Object.keys(m.relStyles).forEach(function (k) { meta.rels[k] = meta.rels[k] || { name: k, style: m.relStyles[k] }; });
        icons = m.entityIcons || {};
        buildStencil();
        readOnly(meta.readOnly);
        // draw.io adds its scratchpad and other libraries on its own: only ours stay (D396)
        [300, 1500].forEach(function (ms) { setTimeout(function () {
          for (var id in ui.sidebar.palettes) if (!ours(id)) {
            ui.sidebar.palettes[id].forEach(function (el) { if (el && el.parentNode) el.parentNode.removeChild(el); });
            delete ui.sidebar.palettes[id];
          }
          clearPalettesExtras();
        }, ms); });
        // restyle what a loaded file holds, so it shows today's notation, colours and icons
        // (not a picture opened to look at, D585: it keeps the colours it was made with, a heat map's among them)
        if (!m.keepLook) silently(function () { vertices().forEach(function (v) { if (attr(v, "ea_type") && !isJunction(v)) restyle(v); }); });
        graph.refresh();
        post({ event: "eax-setup-done", types: Object.keys(meta.types).length, readOnly: meta.readOnly, groups: paletteGroups() });
      } else if (m.eax === "undo" || m.eax === "redo") {          // Ctrl+Z / Ctrl+Y pressed in EA Explorer's page
        var ua = ui.actions.get(m.eax);
        if (ua && ua.isEnabled() && !meta.readOnly) ua.funct();
      } else if (m.eax === "stencil-panel") {                   // pinned or opened: shown; unpinned: folded (D420)
        stencilPanel(!!m.open, m.width || 0);
      } else if (m.eax === "add-related") {                     // the Relationships tab (D420)
        n = model.getCell(m.cell) || findEntity(m.near);
        if (!n) return;
        var res = addRelated(n, m.entity, m.relationship || {}, m.relationships);
        post({ event: "eax-related-added", cell: res.cell || null, line: res.line || null, already: !!res.already, entity: m.entity.id });
      } else if (m.eax === "add-allowed") {                     // the Allowed relationships tab (D420)
        n = model.getCell(m.cell) || findEntity(m.near);
        if (!n || !meta.types[m.type]) return;
        var ad = addAllowed(n, m.type, m.rel, m.outgoing !== false);
        post({ event: "eax-dropped", cell: ad.cell, type: m.type, types: m.types || [m.type], rel: m.rel, line: ad.line, via: "allowed" });
      } else if (m.eax === "waiting-cancel") {                  // its relationship could not be made: the line goes
        c = model.getCell(m.cell);
        delete asked[m.cell];
        if (c) silently(function () { graph.removeCells([c], false); });
      } else if (m.eax === "stencil-size") {
        thumb = THUMBS[m.size] || THUMBS.medium;
        buildStencil();
        post({ event: "eax-stencil-size", size: m.size in THUMBS ? m.size : "medium", px: thumb });
      } else if (m.eax === "palettes") {                        // show or hide stencil groups (D409)
        Object.keys(m.show || {}).forEach(function (group) { shown[group] = m.show[group] !== false; });
        applyPalettes();
        post({ event: "eax-palettes", groups: paletteGroups(), hidden: paletteGroups().filter(function (g) { return shown[g] === false; }) });
      } else if (m.eax === "place") {
        var pt = m.at || { x: 40, y: 40 };
        var placed = place(m.entity, pt.x, pt.y, m.relationships);
        post({ event: "eax-placed", cell: placed.id, entity: m.entity.id });
      } else if (m.eax === "place-at-pointer") {
        // dropped from EA Explorer's search panel: clientX, clientY relative to this frame
        var p = mxUtils.convertPoint(graph.container, m.clientX, m.clientY);
        var under = graph.getCellAt(p.x, p.y);
        var s = graph.view.scale, tr = graph.view.translate;
        if (under && attr(under, "ea_placeholder") === "1" && attr(under, "ea_type") === m.entity.type) { bind(under, m.entity, m.relationships); return; }
        var pl = place(m.entity, Math.round(p.x / s - tr.x - 70), Math.round(p.y / s - tr.y - 35), m.relationships);
        post({ event: "eax-placed", cell: pl.id, entity: m.entity.id });
      } else if (m.eax === "bind") {                            // a placeholder realised (D388)
        c = model.getCell(m.cell);
        if (c) bind(c, m.entity, m.relationships);
      } else if (m.eax === "rel") {                             // the relationship chosen (an uncommitted change, dashed)
        c = model.getCell(m.cell);
        if (!c) return;
        silently(function () {
          model.setValue(c, node({ label: m.name || "", ea_rel: m.type, ea_rel_id: m.id, ea_uncommitted: m.pending === false ? null : "1" }));
          restyle(c);
          if (nestedPair(c.source, c.target)) markNested(c, true);
        });
        delete asked[m.cell];
      } else if (m.eax === "rel-cancel") {
        c = model.getCell(m.cell);
        if (c) silently(function () { graph.removeCells([c], false); });
        delete asked[m.cell];
      } else if (m.eax === "rel-create") {                      // from "Add a relationship..."
        var a = model.getCell(m.source), b = model.getCell(m.target);
        if (a && b) silently(function () { addRelationshipEdge(a, b, m.type, m.id, m.pending !== false, m.name); });
      } else if (m.eax === "line-hide" || m.eax === "line-restore" || m.eax === "line-removed") {
        // the answer to eax-line-deleted (D413): hidden in this view, drawn again (cancelled), or deleted from the model
        var g0 = gone[m.id];
        delete gone[m.id];
        if (m.eax === "line-removed") removedRels[m.id] = true;
        if (!g0) return;
        if (m.eax === "line-hide") {
          silently(function () { setHidden(hidden().filter(function (h) { return h.id !== g0.rel.id; }).concat([{ rel: g0.rel.rel, id: g0.rel.id, source: g0.rel.source, target: g0.rel.target }])); });
          post({ event: "eax-hidden", relationship: g0.rel });
        } else if (m.eax === "line-restore" && model.contains(g0.s) && model.contains(g0.t) && !findRelationship(g0.rel.id)) {
          silently(function () { addRelationshipEdge(g0.s, g0.t, g0.rel.rel, g0.rel.id, g0.rel.pending, g0.rel.name); });
        }
      } else if (m.eax === "placeholder-type") {                // a placeholder shown as another type (D413): the type dropdown
        c = model.getCell(m.cell);
        if (c && attr(c, "ea_placeholder") === "1" && meta.types[m.type]) {
          silently(function () { model.setValue(c, withAttrs(c, { ea_type: m.type, label: typeName(m.type) })); restyle(c); });
          selected(c);
        }
      } else if (m.eax === "junction-bound") {
        c = model.getCell(m.cell);
        if (c) silently(function () { model.setValue(c, withAttrs(c, { ea_junction: m.id })); });
      } else if (m.eax === "nest-ok") {
        c = model.getCell(m.cell);
        delete nesting[m.cell];
        if (c) silently(function () {
          var parent = model.getParent(c);
          allCells().forEach(function (e) {
            if (model.isEdge(e) && attr(e, "ea_rel") && ((e.source === c && e.target === parent) || (e.source === parent && e.target === c))) markNested(e, true);
          });
        });
      } else if (m.eax === "nest-refused") {
        c = model.getCell(m.cell);
        var was = nesting[m.cell];
        delete nesting[m.cell];
        if (c && was) silently(function () {
          model.add(was.parent || graph.getDefaultParent(), c);
          if (was.geometry) model.setGeometry(c, was.geometry.clone());
        });
        post({ event: "eax-unnested", cell: m.cell, reason: m.reason || "" });
      } else if (m.eax === "resync") {
        var ents = m.entities || {}, goneEnts = {}, goneRels = {}, added = 0, renamed = 0, deleted = 0, solid = 0;
        (m.deleted || []).forEach(function (id) { goneEnts[id] = true; });
        (m.deletedRelationships || []).forEach(function (id) { goneRels[id] = true; });
        silently(function () {
          vertices().forEach(function (v) {
            var id = attr(v, "ea_id");
            if (!id) return;
            var e = ents[id];
            if (goneEnts[id]) {
              if (attr(v, "ea_deleted") !== "1") { model.setValue(v, withAttrs(v, { ea_deleted: "1", tooltip: "Deleted from the model" })); deleted++; }
            } else if (e) {
              if ("icon" in e) { if (e.icon) icons[id] = e.icon; else delete icons[id]; }
              if (e.name !== attr(v, "label") || (e.type && e.type !== attr(v, "ea_type"))) {
                model.setValue(v, withAttrs(v, { label: e.name, ea_type: e.type || attr(v, "ea_type"), ea_deleted: null, tooltip: null }));
                renamed++;
              }
            }
            restyle(v);
          });
          var hid = {};
          hidden().forEach(function (h) { hid[h.id] = true; });
          (m.relationships || []).forEach(function (r) {
            var e = findRelationship(r.id);
            if (e) {
              var unc = r.pending ? "1" : null;
              if (attr(e, "ea_uncommitted") !== unc) { if (!unc) solid++; model.setValue(e, withAttrs(e, { ea_uncommitted: unc })); }
              if ("name" in r && (r.name || "") !== (attr(e, "label") || "")) { model.setValue(e, withAttrs(e, { label: r.name || "" })); renamed++; }
              restyle(e);
              return;
            }
            if (hid[r.id]) return;
            var s = findEntity(r.source), t = findEntity(r.target);
            if (s && t && s !== t) { addRelationshipEdge(s, t, r.type, r.id, !!r.pending, r.name); added++; }
          });
          allCells().forEach(function (e) {
            if (model.isEdge(e) && goneRels[attr(e, "ea_rel_id")] && attr(e, "ea_deleted") !== "1") {
              model.setValue(e, withAttrs(e, { ea_deleted: "1", tooltip: "Deleted from the model" }));
              restyle(e);
              deleted++;
            }
          });
        });
        graph.refresh();
        post({ event: "eax-resynced", added: added, renamed: renamed, deleted: deleted, committed: solid, auto: !!m.auto, quiet: !!m.quiet });
      } else if (m.eax === "rel-values") {                      // a line's attribute values changed (D565)
        Object.keys(m.values || {}).forEach(function (id) { relValues[id] = m.values[id] || {}; });
        graph.refresh();
      } else if (m.eax === "rel-name") {                        // a line's name as the model has it (a rename refused: put back)
        c = findRelationship(m.id);
        if (c) silently(function () { model.setValue(c, withAttrs(c, { label: m.name || "" })); });
        graph.refresh();
      } else if (m.eax === "line-labels") {                     // "Line labels: name and type | with attributes" (D565)
        relAttrsShown = m.attrs !== false;
        graph.refresh();
      } else if (m.eax === "heat") {                            // part 2: on screen only, never saved
        heat = m.colours || {};
        graph.refresh();
        post({ event: "eax-heat-on", count: Object.keys(heat).length });
      } else if (m.eax === "heat-off") {
        heat = null;
        graph.refresh();
        post({ event: "eax-heat-off" });
      } else if (m.eax === "icons") {                           // part 2: an entity's own icon, set or removed
        Object.keys(m.icons || {}).forEach(function (id) { if (m.icons[id]) icons[id] = m.icons[id]; else delete icons[id]; });
        silently(function () { vertices().forEach(function (v) { if (attr(v, "ea_id") && attr(v, "ea_id") in (m.icons || {})) restyle(v); }); });
      } else if (m.eax === "placeholders") {
        post({ event: "eax-placeholders", list: vertices().filter(function (v) { return attr(v, "ea_placeholder") === "1"; })
          .map(function (v) { return { cell: v.id, type: attr(v, "ea_type") }; }) });
      } else if (m.eax === "hidden") {
        post({ event: "eax-hidden-list", hidden: hidden() });
      } else if (m.eax === "add-relationship") {                // EA Explorer's own button for the selected object
        n = model.getCell(m.cell) || findEntity(m.entity);
        if (n) addRelationshipAsk(n);
      } else if (m.eax === "select") {                          // EA Explorer shows an entity: select it on the view
        n = findEntity(m.entity);
        if (n) { graph.setSelectionCell(n); graph.scrollCellToVisible(n); }
      }
    });

    // what is selected, for EA Explorer's properties panel: an entity, a placeholder (with its type) or a line
    function selected(c) {
      var msg = { event: "eax-selected", entity: null, relationship: null, cell: c ? c.id : null };
      if (c && model.isVertex(c)) {
        msg.entity = attr(c, "ea_id");
        msg.type = attr(c, "ea_type");
        msg.placeholder = attr(c, "ea_placeholder") === "1";
        msg.junction = isJunction(c);
      } else if (c && model.isEdge(c)) {
        msg.relationship = attr(c, "ea_rel_id");
        msg.relType = attr(c, "ea_rel") || attr(c, "ea_rel_type");
        msg.source = c.source ? attr(c.source, "ea_id") : null;
        msg.target = c.target ? attr(c.target, "ea_id") : null;
        msg.pending = attr(c, "ea_uncommitted") === "1";
      }
      post(msg);
    }
    graph.getSelectionModel().addListener(mxEvent.CHANGE, function () { selected(graph.getSelectionCell()); });

    ui.eax = { exportDrawio: exportDrawioFile, drawioFileXml: drawioFileXml, hide: hide, showHidden: showHidden, hidden: hidden, findEntity: findEntity, findRelationship: findRelationship,
      setForm: setForm, checkEdge: checkEdge };
    window.eaxEditorUi = ui;                 // for EA Explorer's own tests
    post({ event: "eax-ready", version: "2" });
  }

  start();
})();
