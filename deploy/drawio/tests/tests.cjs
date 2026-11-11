// EA Explorer's draw.io plugin: automated test (Playwright). Test only, never in the image. See README.md.
// Usage: node tests.cjs [base URL of a draw.io web app holding plugins/eax.js and test-host.html] [screenshot folder]
const { chromium } = require('playwright');
const BASE = process.argv[2] || 'http://localhost:8771';
const SHOTS = process.argv[3] || '.';
let pass = 0, fail = 0;
const check = (ok, what, extra) => { if (ok) { pass++; console.log('  ok   ' + what); } else { fail++; console.log('  FAIL ' + what + (extra ? ' :: ' + JSON.stringify(extra) : '')); } };

const AM = 'html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.application;';
const SETUP = {
  eax: 'setup',
  types: {
    ApplicationComponent: { name: 'Application Component', domain: 'Application', colour: 'B0D0D9', box: AM + 'appType=comp;archiType=square;', shape: 'html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.component;' },
    Process: { name: 'Process', domain: 'Common', colour: 'E4DED2', box: AM + 'appType=proc;archiType=rounded;', shape: 'html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.process;' },
    Service: { name: 'Service', domain: 'Common', colour: 'E4DED2', box: AM + 'appType=serv;archiType=rounded;', shape: 'html=1;outlineConnect=0;whiteSpace=wrap;shape=mxgraph.archimate3.service;' },
    Capability: { name: 'Capability', domain: 'Strategy', colour: 'EFBD5D', box: AM + 'appType=capability;archiType=rounded;' },
  },
  allowed: [['ApplicationComponent', 'Assignment', 'Process'], ['Process', 'Realization', 'Service'], ['Process', 'Realization', 'Capability'],
    ['Service', 'Serving', 'Process'], ['ApplicationComponent', 'Association', 'Capability'], ['Process', 'Composition', 'Service'],
    ['Process', 'Aggregation', 'Service']],
  relationshipTypes: { Assignment: { name: 'Assignment' }, Realization: { name: 'Realization' }, Serving: { name: 'Serving' },
    Association: { name: 'Association' }, Composition: { name: 'Composition' }, Aggregation: { name: 'Aggregation' } },
  entityIcons: { 'e-app': 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==' },
};

(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1320, height: 880 } });
  const errs = []; p.on('pageerror', e => errs.push('host: ' + e.message));
  await p.goto(BASE + '/test-host.html');
  await p.waitForFunction(() => window.ready === true, null, { timeout: 30000 }).catch(() => {});
  const fr = p.frames().find(f => f.url().includes('index.html'));
  fr.on && p.on('console', m => { if (m.type() === 'error') errs.push('frame: ' + m.text()); });
  const send = (m) => p.evaluate((m) => window.send(m), m);
  const wait = (ms) => p.waitForTimeout(ms);
  const events = (name) => p.evaluate((n) => window.log.filter(m => m.event === n), name);
  const last = async (name) => (await events(name)).pop();
  // inside draw.io: run fn(ui, g, m, helpers)
  const inFrame = (body, arg) => fr.evaluate(new Function('arg', `
    const ui = window.eaxEditorUi, g = ui.editor.graph, m = g.getModel();
    const a = (c, n) => c && c.value && c.value.getAttribute ? c.value.getAttribute(n) : null;
    const F = (id) => ui.eax.findEntity(id), R = (id) => ui.eax.findRelationship(id);
    const cells = () => Object.values(m.cells);
    ${body}`), arg);

  console.log('1. the plugin and the stencil');
  check(!!(await last('eax-ready')), 'eax-ready');
  await send(SETUP); await wait(1800);
  check((await last('eax-setup-done'))?.types === 4, 'setup done with 4 types');
  const pal = await inFrame('return Object.keys(ui.sidebar.palettes);');
  check(['eax-Application', 'eax-Common', 'eax-Strategy', 'eax-relationships', 'eax-junctions'].every(x => pal.includes(x)) && pal.every(x => x.startsWith('eax-') || ['general', 'misc', 'basic'].includes(x)), 'only our palettes (types by domain, relationships, junctions) and the decoration ones', pal);
  check(['general', 'misc', 'basic'].every(x => pal.includes(x)), "draw.io's General, Misc and Basic palettes for decoration (D414)", pal);
  check(!pal.some(x => /archimate/i.test(x)) && await inFrame("return !Array.from(document.querySelectorAll('.geSidebarContainer button, .geSidebarContainer a')).some(b => /More Shapes/i.test(b.textContent) && b.style.display !== 'none');"),
    "never draw.io's ArchiMate libraries, never More Shapes");
  const titles = await inFrame("return Array.from(document.querySelectorAll('.geSidebarContainer .geTitle')).map(t => t.textContent.trim()).filter(Boolean);");
  check(titles.indexOf('Junctions') >= 0 && titles.indexOf('Junctions') < titles.findIndex(t => /General/.test(t)), 'the decoration palettes come after ours', titles);
  check(await inFrame("const pl = ui.sidebar.palettes['general']; return !!pl && pl[1].firstChild.style.display === 'none';"), 'and are collapsed at first');
  const relCount = await inFrame("const pl = ui.sidebar.palettes['eax-relationships']; return pl ? pl[1].querySelectorAll('a').length : 0;");
  check(relCount === 6, 'one line per relationship type the metamodel uses, in the stencil', relCount);
  check(JSON.stringify((await last('eax-setup-done'))?.groups) === JSON.stringify(['Strategy', 'Common', 'Application', 'Relationships', 'Junctions', 'General', 'Misc', 'Basic']),
    'setup says the stencil groups: the domains, Relationships, Junctions, then the decoration palettes (D409, D414)', (await last('eax-setup-done'))?.groups);
  const domOrder = await inFrame("return Array.from(document.querySelectorAll('.geSidebarContainer .geTitle')).map(t => t.textContent.trim()).filter(Boolean);");
  check(JSON.stringify(domOrder.filter(t => ['Strategy', 'Common', 'Application', 'Relationships', 'Junctions'].includes(t))) === JSON.stringify(['Strategy', 'Common', 'Application', 'Relationships', 'Junctions']),
    'the palettes are in ArchiMate order on screen (D412)', domOrder);
  const relOrder = await inFrame("const pl = ui.sidebar.palettes['eax-relationships']; return Array.from(pl[1].querySelectorAll('a')).map(a => a.getAttribute('title') || a.textContent.trim());");
  check(JSON.stringify(relOrder) === JSON.stringify(['Composition', 'Aggregation', 'Assignment', 'Realization', 'Serving', 'Association']),
    'relationships structural, dependency, dynamic, other', relOrder);
  const vis = (id) => inFrame(`const pl = ui.sidebar.palettes['${id}']; return pl ? pl.map(e => e.style.display !== 'none') : null;`);
  await send({ eax: 'palettes', show: { Strategy: false, Junctions: false } }); await wait(200);
  check((await vis('eax-Strategy')).every(x => !x) && (await vis('eax-junctions')).every(x => !x) && (await vis('eax-Common')).every(x => x),
    'hiding a domain and the junctions hides those groups only');
  check(JSON.stringify((await last('eax-palettes'))?.hidden) === JSON.stringify(['Strategy', 'Junctions']), 'the plugin says which groups are hidden');
  await send(SETUP); await wait(800);
  check((await vis('eax-Strategy')).every(x => !x), 'a hidden group stays hidden when the stencil is built again');
  await p.screenshot({ path: SHOTS + '/stencil-groups-hidden.png' });
  await send({ eax: 'palettes', show: { General: false } }); await wait(200);
  check((await vis('general')).every(x => !x), 'a decoration palette is hidden like any group');
  await send({ eax: 'palettes', show: { Strategy: true, Junctions: true, General: true } }); await wait(200);
  check((await vis('eax-Strategy')).every(x => x) && (await vis('eax-junctions')).every(x => x), 'shown again');
  check(!(await inFrame("return m.getRoot().getChildAt ? new XMLSerializer().serializeToString(new mxCodec().encode(m)).includes('palettes') : false;")),
    'nothing of it is saved in the view');

  console.log('2. placing realised entities');
  await send({ eax: 'place', entity: { id: 'e-app', name: 'Claims Platform', type: 'ApplicationComponent' }, at: { x: 40, y: 40 } });
  await send({ eax: 'place', entity: { id: 'e-proc', name: 'Register Claim', type: 'Process' }, at: { x: 340, y: 40 }, relationships: [{ id: 'r-1', type: 'Assignment', source: 'e-app', target: 'e-proc', name: 'performs' }] });
  await send({ eax: 'place', entity: { id: 'e-cap', name: 'Claims Management', type: 'Capability' }, at: { x: 340, y: 260 } });
  await send({ eax: 'place', entity: { id: 'e-svc', name: 'Claims Service', type: 'Service' }, at: { x: 640, y: 40 } });
  await wait(500);
  check((await events('eax-placed')).length === 4, '4 placed');
  check(await inFrame("return !!R('r-1') && a(R('r-1'),'ea_uncommitted') !== '1';"), 'the relationship the model has is drawn (committed, solid)');
  check(await inFrame("return a(R('r-1'),'label')==='performs' && /labelBackgroundColor=#ffffff/.test(m.getStyle(R('r-1')));"), "a relationship's name is kept as the line's label (D412)");
  // the label shows name, type and values (D565)
  const shown = await inFrame("return g.convertValueToString(R('r-1'));");
  check(/<b>performs<\/b>/.test(shown) && /\(<\/?i>?|\(Assignment\)|<i>\(/.test(shown) && /Assignment|Serving|Realization|Association|Composition|Aggregation/.test(shown),
    'the line shows its name in bold and its type in italics', shown);
  check(await inFrame("return ui.eaxLineLabel('Nightly', 'Flow', {Frequency: 'Daily'}, false);") === 'Nightly (Flow) [Frequency:Daily]', 'label format: name (Type) [key:value]');
  check(await inFrame("return ui.eaxLineLabel('', 'Flow', {}, false);") === '(Flow)', 'no name: (Type); no values: no brackets');
  check(await inFrame("return ui.eaxLineLabel('a', 'Flow', {A: 1, B: 2, C: 3, D: 4, E: 5}, false);") === 'a (Flow) [A:1 B:2 C:3 +2]', 'more than 3 values: the first 3 and +n');
  check(!/<script/.test(await inFrame("return ui.eaxLineLabel('<script>', 'Flow', {k: '<b>'}, true);")), 'the label is escaped');
  check(await inFrame("return g.isCellEditable(R('r-1'));"), 'a bound line may be renamed in place');
  check(await inFrame("return g.getEditingValue(R('r-1')) === 'performs';"), 'editing starts from the name alone, never the type');
  // renaming in place: the type stays, the host is asked to commit it
  await inFrame("m.setValue(R('r-1'), (function () { const v = R('r-1').value.cloneNode(true); v.setAttribute('label', 'runs'); return v; })());"); await wait(300);
  const ren = await last('eax-rel-rename');
  check(ren && ren.relationship === 'r-1' && ren.name === 'runs', 'renaming a line posts eax-rel-rename', ren);
  check(await inFrame("return a(R('r-1'),'ea_rel') !== null && /\\(/.test(g.convertValueToString(R('r-1'))) && a(R('r-1'),'label') === 'runs';"),
    'the line keeps its type after the rename');
  await send({ eax: 'rel-values', values: { 'r-1': { Frequency: 'Daily', 'Data volume': '2 GB' } } }); await wait(200);
  check(/Frequency:Daily/.test(await inFrame("return g.convertValueToString(R('r-1'));")), 'rel-values shows key:value on the line');
  await send({ eax: 'line-labels', attrs: false }); await wait(200);
  check(!/Frequency/.test(await inFrame("return g.convertValueToString(R('r-1'));")), 'Line labels: name and type hides the values');
  await send({ eax: 'line-labels', attrs: true }); await wait(100);
  await send({ eax: 'rel-name', id: 'r-1', name: 'performs' }); await wait(200);
  check(await inFrame("return a(R('r-1'),'label') === 'performs';"), 'rel-name puts the model\'s name back');
  check(await inFrame("return /image=data:image\\/png,/.test(m.getStyle(F('e-app')));"), "the entity's own icon shows (box form)");
  check(await inFrame("return /fillColor=#B0D0D9/.test(m.getStyle(F('e-app')));"), 'type colour kept with an icon');

  console.log('3. lines drawn by a person');
  await inFrame(`
    const P = g.getDefaultParent(), fire = (e) => g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e));
    m.beginUpdate(); try {
      const ph = g.insertVertex(P, 'ph1', (() => { const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label','Capability'); o.setAttribute('ea_type','Capability'); o.setAttribute('ea_placeholder','1'); return o; })(), 700, 300, 120, 60, 'dashed=1;');
      fire(g.insertEdge(P, 'x1', '', F('e-app'), F('e-cap')));
      fire(g.insertEdge(P, 'x2', '', F('e-proc'), ph));
      fire(g.insertEdge(P, 'x3', '', F('e-cap'), F('e-app')));
    } finally { m.endUpdate(); }`);
  await wait(800);
  const refused = (await events('eax-refused')).map(e => e.reason);
  check(refused.some(r => /placeholder/.test(r)), 'a line to a placeholder is refused', refused);
  check(refused.some(r => /allows no relationship from Capability to Application Component/.test(r)), 'a line no rule allows is refused');
  check(await inFrame("return cells().some(c => m.isEdge(c) && a(c,'ea_rel')==='Association' && a(c,'ea_uncommitted')==='1');"), 'an allowed line becomes an uncommitted relationship');
  check(await inFrame("return !m.getCell('x2') && !m.getCell('x3');"), 'refused lines are taken away');

  console.log('4. a line from the stencil (a chosen relationship type)');
  await inFrame(`
    const mk = (t) => { const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label',''); o.setAttribute('ea_rel_type', t); return o; };
    const e1 = g.insertEdge(g.getDefaultParent(), 'l1', mk('Realization'), null, null, '');
    const e2 = g.insertEdge(g.getDefaultParent(), 'l2', mk('Serving'), null, null, '');
    m.setTerminal(e1, F('e-proc'), true); m.setTerminal(e1, F('e-svc'), false);
    m.setTerminal(e2, F('e-app'), true); m.setTerminal(e2, F('e-cap'), false);`);
  await wait(800);
  check(await inFrame("return a(m.getCell('l1'),'ea_rel')==='Realization';"), 'a Realization line between Process and Service becomes that relationship');
  check(!(await inFrame("return !!m.getCell('l2');")) && (await events('eax-refused')).some(e => /does not allow Serving/.test(e.reason)), 'a Serving line no rule allows is refused with the reason');

  console.log('5. Add a relationship...');
  await send({ eax: 'add-relationship', entity: 'e-app' }); await wait(300);
  const ask = await last('eax-add-relationship');
  check(ask && ask.candidates.length >= 3 && ask.candidates.every(c => c.entity !== 'e-app'), 'asks with the other realised objects as candidates', ask);
  const cells = await inFrame("return {app: F('e-app').id, proc: F('e-proc').id};");
  await send({ eax: 'rel-create', source: cells.app, target: cells.proc, type: 'Assignment', id: 'r-add', name: 'Handles' }); await wait(300);
  check(await inFrame("return !!R('r-add') && a(R('r-add'),'ea_uncommitted')==='1';"), 'rel-create draws it, uncommitted (dashed)');
  check(await inFrame("return a(R('r-add'),'label')==='Handles';"), 'rel-create shows the name on the line');
  await send({ eax: 'rel-create', source: cells.proc, target: cells.app, type: 'Assignment', id: 'r-noname' }); await wait(300);
  check(await inFrame("return !R('r-noname') || !a(R('r-noname'),'label');"), 'no name, no label');
  console.log('5b. stencil size (D412)');
  const th = () => inFrame("return ui.sidebar.thumbWidth;");
  check(await th() === 84, 'the stencil is medium by default (about twice the old size)', await th());
  await send({ eax: 'stencil-size', size: 'large' }); await wait(400);
  check((await last('eax-stencil-size'))?.size === 'large' && await th() === 120, 'Large rebuilds the palettes bigger', await last('eax-stencil-size'));
  check(await inFrame("return document.querySelectorAll('.geSidebar a.geItem').length > 0;"), 'the palettes are there after the rebuild');
  await send({ eax: 'stencil-size', size: 'small' }); await wait(400);
  check(await th() === 42, 'Small', await th());
  await send({ eax: 'stencil-size', size: 'medium' }); await wait(400);

  console.log('6. locked to layout');
  await inFrame(`const c = F('e-app'); g.setCellStyles('fillColor', '#FF00FF', [c]); g.setCellStyles('fontSize', '16', [c]); m.setValue(c, 'Renamed on the canvas');`);
  await wait(400);
  check(await inFrame("return /fillColor=#B0D0D9/.test(m.getStyle(F('e-app'))) && !/FF00FF/.test(m.getStyle(F('e-app')));"), 'a colour change is put back');
  check(await inFrame("return /fontSize=16/.test(m.getStyle(F('e-app')));"), 'a font change stays (layout)');
  check(await inFrame("return a(F('e-app'),'label')==='Claims Platform' && a(F('e-app'),'ea_id')==='e-app';"), 'a renamed object is put back');
  check(await inFrame("return !g.isCellEditable(F('e-app')) ;"), 'no in-place editing of an EA object');
  await inFrame("m.setTerminal(R('r-1'), F('e-cap'), false);"); await wait(300);
  check(await inFrame("return R('r-1').target === F('e-proc');"), "a relationship's end is put back");
  await inFrame("g.setSelectionCell(F('e-app')); ui.actions.get('editData').funct();"); await wait(200);
  check((await events('eax-refused')).some(e => /only their layout/.test(e.reason)), 'Edit Data is refused on an EA object');

  console.log('7. box or shape');
  await inFrame("ui.eax.setForm(F('e-proc'), 'shape');"); await wait(200);
  check(await inFrame("const s = m.getStyle(F('e-proc')); return a(F('e-proc'),'ea_form')==='shape' && /mxgraph.archimate3.process/.test(s) && /fillColor=#E4DED2/.test(s);"), 'shown as shape, colour kept');
  await inFrame("ui.eax.setForm(F('e-proc'), 'box');"); await wait(200);
  check(await inFrame("return !a(F('e-proc'),'ea_form') && /appType=proc/.test(m.getStyle(F('e-proc')));"), 'back to box');

  console.log('8. junctions');
  await p.evaluate(() => { window.answers.prefer = 'Realization'; });
  await inFrame(`
    const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label',''); o.setAttribute('ea_junction_kind','and');
    g.importCells([(() => { const c = new mxCell(o, new mxGeometry(520, 180, 14, 14), 'ellipse;'); c.vertex = true; c.id = 'J1'; return c; })()], 0, 0, g.getDefaultParent());`);
  await wait(600);
  check((await last('eax-junction-new'))?.kind === 'and', 'a dropped junction is reported');
  const jid = await inFrame("const j = cells().find(c => a(c,'ea_junction_kind')==='and'); return j ? a(j,'ea_junction') : null;");
  check(!!jid, 'and bound to the model', jid);
  await inFrame(`
    const j = cells().find(c => a(c,'ea_junction_kind')==='and'), P = g.getDefaultParent(), fire = (e) => g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e));
    fire(g.insertEdge(P, 'j1', '', F('e-proc'), j));`);
  await wait(500);
  await inFrame(`
    const j = cells().find(c => a(c,'ea_junction_kind')==='and'), P = g.getDefaultParent(), fire = (e) => g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e));
    fire(g.insertEdge(P, 'j2', '', j, F('e-cap')));`);
  await wait(500);
  await inFrame(`
    const j = cells().find(c => a(c,'ea_junction_kind')==='and'), P = g.getDefaultParent(), fire = (e) => g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e));
    fire(g.insertEdge(P, 'j3', '', j, F('e-app')));`);
  await wait(500);
  const jr = await inFrame("return ['j1','j2','j3'].map(id => m.getCell(id) ? a(m.getCell(id),'ea_rel') : 'gone');");
  check(jr[0] === 'Realization' && jr[1] === 'Realization', 'lines through the junction share one type, checked as if direct', jr);
  check(jr[2] === 'gone', 'a line through the junction not allowed as if direct is refused', jr);
  const asked = (await events('eax-relationship')).filter(e => e.junction);
  check(asked.length === 2 && asked[1].through[0] === 'e-proc', 'the host is told the junction and the objects through it', asked);

  console.log('9. nesting must match a relationship');
  const before = await inFrame("const c = F('e-cap'); return {x: c.geometry.x, y: c.geometry.y};");
  await inFrame("const c = F('e-cap'), p = F('e-app'); m.beginUpdate(); try { m.add(p, c); const gg = c.geometry.clone(); gg.x = 5; gg.y = 5; m.setGeometry(c, gg); } finally { m.endUpdate(); }");
  await wait(400);
  const nest = await last('eax-nest');
  check(nest && nest.entity === 'e-cap' && nest.parent === 'e-app', 'nesting is reported to the host', nest);
  await send({ eax: 'nest-refused', cell: nest.cell, reason: 'no relationship' }); await wait(300);
  check(await inFrame("const c = F('e-cap'); return m.getParent(c) === g.getDefaultParent() && c.geometry.x === arg.x && c.geometry.y === arg.y;", before), 'refused: moved back where it was');
  await inFrame("const c = F('e-svc'), p = F('e-proc'); m.beginUpdate(); try { m.add(p, c); const gg = c.geometry.clone(); gg.x = 10; gg.y = 10; m.setGeometry(c, gg); } finally { m.endUpdate(); }");
  await wait(400);
  await send({ eax: 'nest-ok', cell: (await last('eax-nest')).cell }); await wait(300);
  check(await inFrame("const e = m.getCell('l1'); return a(e,'ea_nested')==='1' && !m.isVisible(e) && !ui.eax.hidden().some(h => h.id === a(e,'ea_rel_id'));"), 'accepted: the nested line is not drawn (and not in the hidden list)');

  console.log('9b. decoration (D414)');
  await inFrame("const pl = ui.sidebar.palettes['general']; pl[0].click();"); await wait(600);
  const decorItems = await inFrame("const pl = ui.sidebar.palettes['general']; return pl[1].querySelectorAll('a.geItem').length;");
  check(decorItems > 10, 'the General palette opens with its shapes', decorItems);
  // click the General palette's items until one draws a line (an arrow): it must come marked ea_decor
  const items = fr.locator('.geSidebarContainer a.geItem');
  const total = await items.count();
  let fromPalette = [], arrowAt = -1;
  const firstGeneral = await inFrame("const all = Array.from(document.querySelectorAll('.geSidebarContainer a.geItem')); return all.indexOf(ui.sidebar.palettes['general'][1].querySelector('a.geItem'));");
  for (let i = firstGeneral; i >= 0 && i < total && i < firstGeneral + 60; i++) {
    const beforeIds = await inFrame("g.clearSelection(); return Object.keys(m.cells);");
    await items.nth(i).click(); await wait(150);
    const added = await inFrame("return cells().filter(c => !arg.includes(c.id)).map(c => ({ id: c.id, edge: !!c.edge, decor: a(c,'ea_decor'), rel: a(c,'ea_rel') }));", beforeIds);
    if (added.some(x => x.edge)) { fromPalette = added.filter(x => x.edge); arrowAt = i; break; }
    await inFrame("g.removeCells(arg.map(x => m.getCell(x.id)).filter(Boolean));", added);
  }
  check(arrowAt >= 0 && fromPalette.length > 0 && fromPalette.every(x => x.decor === '1' && !x.rel), "the General palette's arrow comes marked ea_decor", { arrowAt, fromPalette });
  await inFrame(`
    const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label',''); o.setAttribute('ea_decor','1');
    const P = g.getDefaultParent(); let e; m.beginUpdate(); try { e = g.insertEdge(P, 'd1', o, F('e-app'), F('e-proc'), 'endArrow=classic;html=1;'); } finally { m.endUpdate(); }
    g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e));
    const n = g.insertVertex(P, 'note1', 'A comment', 60, 420, 120, 50, 'shape=note;whiteSpace=wrap;html=1;');
    const e2 = g.insertEdge(P, 'd2', '', n, F('e-app'), '');
    g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', e2));
    g.setCellStyles('fillColor', '#FFF2CC', [n]);`);
  await wait(800);
  check(await inFrame("const e = m.getCell('d1'); return !!e && !a(e,'ea_rel') && a(e,'ea_decor')==='1';"), 'a decoration arrow between two EA objects stays a drawing, never a relationship');
  check(!(await events('eax-relationship')).some(e => e.cell === 'd1' || e.cell === 'd2'), 'and EA Explorer is not asked about it');
  check(await inFrame("const e = m.getCell('d2'); return !!e && a(e,'ea_decor')==='1';"), 'a line from a note to an object is decoration too');
  check(await inFrame("return /fillColor=#FFF2CC/.test(m.getStyle(m.getCell('note1')));"), 'a note is freely styled (no lock)');
  const sb4 = await inFrame("return document.querySelectorAll('.geSidebarContainer .geItem').length;");
  check(sb4 > 0, 'the stencil is still there');

  console.log('9c. a placeholder shown as another type (D413)');
  await inFrame("const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label','Service'); o.setAttribute('ea_type','Service'); o.setAttribute('ea_placeholder','1'); g.insertVertex(g.getDefaultParent(), 'ph9', o, 900, 600, 120, 60, 'dashed=1;');");
  await send({ eax: 'placeholder-type', cell: 'ph9', type: 'Process' }); await wait(300);
  check(await inFrame("const c = m.getCell('ph9'); return a(c,'ea_type')==='Process' && a(c,'label')==='Process' && /appType=proc/.test(m.getStyle(c)) && /dashed=1/.test(m.getStyle(c));"), 'its type and look change, still a placeholder');
  check((await last('eax-selected'))?.type === 'Process', 'the panel is told the new type');
  await inFrame("g.removeCells([m.getCell('ph9')]);");

  console.log('10. deleting a line asks; hide and show (D413)');
  await inFrame("g.removeCells([R('r-1')]);"); await wait(300);
  const ld = await last('eax-line-deleted');
  check(ld && ld.relationship.id === 'r-1' && ld.relationship.rel === 'Assignment' && ld.relationship.name === 'performs', 'deleting a line asks EA Explorer', ld);
  check(await inFrame("return !ui.eax.hidden().some(h => h.id === 'r-1');"), 'not hidden until answered');
  await send({ eax: 'line-restore', id: 'r-1' }); await wait(300);
  check(await inFrame("return !!R('r-1') && a(R('r-1'),'label')==='performs';"), 'Cancel: the line is drawn again');
  await inFrame("g.removeCells([R('r-1')]);"); await wait(300);
  await send({ eax: 'line-hide', id: 'r-1' }); await wait(300);
  check(await inFrame("return !R('r-1') && ui.eax.hidden().some(h => h.id === 'r-1');"), 'Hide in this view: in the hidden list');
  await inFrame("ui.eax.showHidden(F('e-proc'));"); await wait(300);
  check(await inFrame("return !!R('r-1') && !ui.eax.hidden().some(h => h.id === 'r-1');"), 'Show hidden relationships brings it back');
  await inFrame("g.removeCells([F('e-cap')], true);"); await wait(300);
  check(await inFrame("return !F('e-cap') && !ui.eax.hidden().some(h => /r-new/.test(h.id));"), "deleting an object does not hide its lines");

  await inFrame("g.removeCells([R('r-add')]);"); await wait(300);
  await send({ eax: 'line-removed', id: 'r-add' }); await wait(300);
  check(await inFrame("return !R('r-add') && !ui.eax.hidden().some(h => h.id === 'r-add');"), 'Delete from the model: the line goes, not hidden');
  await send({ eax: 'rel-create', source: cells.app, target: cells.proc, type: 'Assignment', id: 'r-add', name: 'Handles' }); await wait(300);

  console.log('11. resync');
  await send({ eax: 'resync', entities: { 'e-app': { name: 'Claims Platform v2', type: 'ApplicationComponent' }, 'e-proc': { name: 'Register Claim', type: 'Process' } },
    deleted: ['e-svc'], relationships: [{ id: 'r-9', type: 'Association', source: 'e-app', target: 'e-proc', pending: false },
      { id: 'r-add', type: 'Assignment', source: 'e-app', target: 'e-proc', pending: false }], deletedRelationships: ['r-1'] });
  await wait(500);
  const rs = await last('eax-resynced');
  check(rs && rs.renamed === 1 && rs.added === 1 && rs.deleted === 2, 'resynced: one renamed, one new relationship drawn, two deletions marked', rs);
  check(rs && rs.committed === 1, 'and one pending line now committed (for the note on opening, D413)', rs);
  check(await inFrame("return a(F('e-app'),'label')==='Claims Platform v2';"), 'names brought up to date');
  check(await inFrame("return a(F('e-svc'),'ea_deleted')==='1' && /strokeColor=#C62828/.test(m.getStyle(F('e-svc')));"), 'a deleted entity is marked, not removed');
  check(await inFrame("return a(R('r-1'),'ea_deleted')==='1';"), 'a deleted relationship is marked');
  check(await inFrame("return a(R('r-add'),'ea_uncommitted')!=='1' && !/1565C0/.test(m.getStyle(R('r-add')));"), 'a committed relationship turns solid');

  console.log('12. heat map (on screen only)');
  await send({ eax: 'heat', colours: { 'e-app': 'D7301F' }, legend: [{ label: 'High', colour: 'D7301F' }] }); await wait(300);
  check(await inFrame("return g.getCellStyle(F('e-app')).fillColor === '#D7301F' && /fillColor=#B0D0D9/.test(m.getStyle(F('e-app')));"), 'painted on screen; the stored colour unchanged');
  check(await inFrame("return g.getCellStyle(F('e-proc')).fillColor === '#F2F2F2';"), 'objects without a value go pale grey');
  await send({ eax: 'heat-off' }); await wait(200);
  check(await inFrame("return g.getCellStyle(F('e-app')).fillColor === '#B0D0D9';"), 'heat map off');

  console.log('13. icons');
  await send({ eax: 'icons', icons: { 'e-app': null } }); await wait(200);
  check(await inFrame("return !/image=/.test(m.getStyle(F('e-app'))) && /appType=comp/.test(m.getStyle(F('e-app')));"), "an icon removed: the type's glyph is back");

  console.log('14. placeholders and changes');
  await send({ eax: 'placeholders' }); await wait(300);
  const phs = await last('eax-placeholders');
  check(phs && phs.list.length === 1 && phs.list[0].type === 'Capability', 'placeholders listed', phs);
  check(((await last('eax-changed')) || {}).placeholders === 1, 'eax-changed reports the drawing changed, with the placeholders');

  console.log('15. dropped from the search panel onto a placeholder');
  const at = await inFrame("const s = g.view.getState(m.getCell('ph1')); const r = g.container.getBoundingClientRect(); return {x: r.left + s.getCenterX() - g.container.scrollLeft, y: r.top + s.getCenterY() - g.container.scrollTop};");
  await send({ eax: 'place-at-pointer', entity: { id: 'e-fd', name: 'Fraud Detection', type: 'Capability' }, clientX: at.x, clientY: at.y }); await wait(300);
  check(await inFrame("return a(m.getCell('ph1'),'ea_id')==='e-fd' && a(m.getCell('ph1'),'ea_placeholder') !== '1';"), 'the placeholder is realised');
  await send({ eax: 'place-at-pointer', entity: { id: 'e-new', name: 'New Thing', type: 'Service' }, clientX: at.x - 300, clientY: at.y + 150 }); await wait(300);
  check(await inFrame("return !!F('e-new');"), 'elsewhere: placed where it was dropped');

  console.log('15b. the properties panel: what is selected, and a placeholder realised from it (D411)');
  await inFrame("const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label','Capability'); o.setAttribute('ea_type','Capability'); o.setAttribute('ea_placeholder','1'); g.insertVertex(g.getDefaultParent(), 'ph2', o, 900, 420, 120, 60, 'dashed=1;'); g.setSelectionCell(m.getCell('ph2'));"); await wait(200);
  const selPh = await last('eax-selected');
  check(selPh && selPh.cell === 'ph2' && selPh.placeholder === true && selPh.type === 'Capability' && !selPh.entity, 'a placeholder selected: the panel is told its type', selPh);
  await send({ eax: 'bind', cell: 'ph2', entity: { id: 'e-cap2', name: 'Claims Triage', type: 'Capability' },
    relationships: [{ id: 'r-pc2', type: 'Realization', source: 'e-proc', target: 'e-cap2', pending: false }] }); await wait(300);
  check(await inFrame("const c = m.getCell('ph2'); return a(c,'ea_id')==='e-cap2' && a(c,'ea_placeholder') !== '1' && !!R('r-pc2');"), 'realised from the panel: bound, its relationship to an object on the view drawn');
  check(await inFrame("const st = m.getStyle(m.getCell('ph2')); return !/dashed=1|fontStyle=2|opacity=70/.test(st);"), "the placeholder's dashed, italic look goes once realised");
  const selB = await last('eax-selected');
  check(selB && selB.entity === 'e-cap2' && selB.placeholder === false, 'then the bound object is selected', selB);
  await send({ eax: 'bind', cell: 'ph2', entity: { id: 'e-cap3', name: 'Claims Routing', type: 'Capability' }, relationships: [] }); await wait(300);
  check(await inFrame("return a(m.getCell('ph2'),'ea_id')==='e-cap3' && !R('r-pc2');"), "change instance: the old entity's lines go");
  await inFrame("const e = cells().find(c => c.edge && a(c,'ea_rel_id')); if (e) g.setSelectionCell(e);"); await wait(200);
  const selL = await last('eax-selected');
  check(selL && selL.relationship && selL.relType && selL.source && selL.target, 'a line selected: its type and both ends', selL);

  console.log('15c. the working space (D420)');
  check(await inFrame("return !ui.isFormatPanelVisible() && ui.formatWidth === 0;"), "draw.io's Format panel is not shown");
  await inFrame("ui.actions.get('format').funct(); ui.toggleFormatPanel(true);"); await wait(200);
  check(await inFrame("const a2 = ui.actions.get('format'); return ui.formatWidth === 0 && a2.visible === false && !a2.isEnabled() && (!ui.toggleFormatElement || ui.toggleFormatElement.style.display === 'none');"),
    'and cannot be opened again (the action, View > Format, its button)');
  await send({ eax: 'stencil-panel', open: false }); await wait(200);
  check(await inFrame("return ui.hsplitPosition === 0;"), 'the stencil folds away (unpinned)');
  await send({ eax: 'stencil-panel', open: true, width: 260 }); await wait(500);
  check(await inFrame("return ui.hsplitPosition === 260;"), 'and opens at the width kept for the person');
  await inFrame("ui.hsplitPosition = 300; ui.refresh();"); await wait(700);
  check((await last('eax-stencil-width'))?.width === 300, 'dragging its edge says the new width', await last('eax-stencil-width'));
  await inFrame("const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('label','Service'); o.setAttribute('ea_type','Service'); o.setAttribute('ea_placeholder','1'); const v = new mxCell(o, new mxGeometry(40, 600, 120, 60), 'dashed=1;'); v.vertex = true; g.importCells([v], 0, 0, g.getDefaultParent());"); await wait(300);
  const drop = await last('eax-dropped');
  check(drop && drop.type === 'Service' && !!drop.cell, 'a placeholder dropped from the stencil: EA Explorer is asked what it is', drop);
  await inFrame("const o = mxUtils.createXmlDocument().createElement('object'); o.setAttribute('ea_junction_kind','and'); const v = new mxCell(o, new mxGeometry(10, 700, 14, 14), ''); v.vertex = true; g.importCells([v], 0, 0, g.getDefaultParent());"); await wait(300);
  check((await last('eax-dropped')).cell === drop.cell, 'a junction is not asked about');
  // the Relationships tab: e-proc's related entity placed next to it, with the line
  const nApp = await inFrame("return cells().filter(c => c.vertex && a(c,'ea_id')).length;");
  await send({ eax: 'add-related', near: 'e-proc', entity: { id: 'e-svc9', name: 'Claim Status Service', type: 'Service' },
    relationship: { id: 'r-ps9', type: 'Realization', source: 'e-proc', target: 'e-svc9', name: '', pending: false }, relationships: [] }); await wait(400);
  const ra = await last('eax-related-added');
  check(ra && ra.cell && ra.line && !ra.already && await inFrame("const r = R('r-ps9'); return !!F('e-svc9') && !!r && a(r.source,'ea_id')==='e-proc' && a(r.target,'ea_id')==='e-svc9';"),
    'Relationships tab: the related entity placed with the relationship line', ra);
  check(await inFrame("const b = (c) => { const g2 = c.geometry; return [g2.x, g2.y, g2.width, g2.height]; }; const n = F('e-svc9'); const [x,y,w,h] = b(n); return cells().filter(c => c.vertex && c !== n && c.parent === n.parent && m.isVisible(c)).every(o => { const [ox,oy,ow,oh] = b(o); return x >= ox + ow || x + w <= ox || y >= oy + oh || y + h <= oy; });"),
    'placed where nothing else is (tidy placement)');
  check(nApp + 1 === await inFrame("return cells().filter(c => c.vertex && a(c,'ea_id')).length;"), 'one object more');
  await send({ eax: 'add-related', near: 'e-proc', entity: { id: 'e-svc9', name: 'Claim Status Service', type: 'Service' },
    relationship: { id: 'r-ps9', type: 'Realization', source: 'e-proc', target: 'e-svc9' }, relationships: [] }); await wait(300);
  check((await last('eax-related-added')).already === true && await inFrame("return g.getSelectionCell() === R('r-ps9');"), 'both on the view already: the line is selected');
  await inFrame("g.removeCells([R('r-ps9')], false);"); await wait(300);
  await send({ eax: 'line-hide', id: 'r-ps9' }); await wait(200);
  await send({ eax: 'add-related', near: 'e-proc', entity: { id: 'e-svc9', name: 'Claim Status Service', type: 'Service' },
    relationship: { id: 'r-ps9', type: 'Realization', source: 'e-proc', target: 'e-svc9' }, relationships: [] }); await wait(300);
  check(await inFrame("return !!R('r-ps9') && !ui.eax.hidden().some(h => h.id === 'r-ps9');"), 'the entity on the view, its line hidden: the line is drawn again and leaves the hidden list');
  // the Allowed relationships tab: a placeholder joined by a waiting line; bound, EA Explorer is asked to make the relationship
  await send({ eax: 'add-allowed', near: 'e-proc', type: 'Service', types: ['Service', 'Capability'], rel: 'Realization', outgoing: true }); await wait(400);
  const ad = await last('eax-dropped');
  check(ad && ad.via === 'allowed' && ad.rel === 'Realization' && ad.types.length === 2 && ad.line, 'Allowed relationships: a placeholder of the other type, and the pop-up asked for', ad);
  check(await inFrame("const e = m.getCell(arg[0]), ph = m.getCell(arg[1]); return a(e,'ea_waiting')==='1' && a(e,'ea_rel_type')==='Realization' && a(e.source,'ea_id')==='e-proc' && e.target === ph && a(ph,'ea_placeholder')==='1';", [ad.line, ad.cell]),
    'joined to the selected object by a line waiting for it');
  await inFrame("g.connectionHandler.fireEvent(new mxEventObject(mxEvent.CONNECT, 'cell', m.getCell(arg)));", ad.line); await wait(300);
  check(await inFrame("return !!m.getCell(arg);", ad.line), 'the waiting line is not refused');
  await send({ eax: 'bind', cell: ad.cell, entity: { id: 'e-svc10', name: 'Claim Payment Service', type: 'Service' }, relationships: [] }); await wait(300);
  const wl = await last('eax-waiting-line');
  check(wl && wl.cell === ad.line && wl.source === 'e-proc' && wl.target === 'e-svc10' && wl.type === 'Realization', 'bound: EA Explorer is asked to make the relationship', wl);
  await send({ eax: 'rel', cell: ad.line, type: 'Realization', id: 'r-ps10', name: '', pending: false }); await wait(300);
  check(await inFrame("const e = R('r-ps10'); return !!e && a(e,'ea_waiting') !== '1' && !/8A96A3/.test(m.getStyle(e));"), 'made: an ordinary relationship line');
  await send({ eax: 'add-allowed', near: 'e-proc', type: 'Capability', rel: 'Realization', outgoing: true }); await wait(300);
  const ad2 = await last('eax-dropped');
  await send({ eax: 'waiting-cancel', cell: ad2.line }); await wait(200);
  check(await inFrame("return !m.getCell(arg[0]) && !!m.getCell(arg[1]);", [ad2.line, ad2.cell]), 'not made: the line goes, the placeholder stays');
  await send({ eax: 'add-allowed', near: 'e-svc10', type: 'Process', rel: 'Realization', outgoing: false }); await wait(300);
  const ad3 = await last('eax-dropped');
  const nV = await inFrame("return cells().filter(c => c.vertex && a(c,'ea_id')).length;");
  await send({ eax: 'bind', cell: ad3.cell, entity: { id: 'e-proc', name: 'Register Claim', type: 'Process' }, relationships: [] }); await wait(300);
  const wl3 = await last('eax-waiting-line');
  check(!(await inFrame("return !!m.getCell(arg);", ad3.cell)) && nV === await inFrame("return cells().filter(c => c.vertex && a(c,'ea_id')).length;")
    && wl3.cell === ad3.line && wl3.source === 'e-proc' && wl3.target === 'e-svc10', 'bound to an entity already on the view: no second copy, the line joins the one there', wl3);
  await send({ eax: 'waiting-cancel', cell: ad3.line }); await wait(200);
  await p.screenshot({ path: SHOTS + '/working-space.png' });

  console.log('15d. labels, the same entity twice, undo and redo (owner, 10 Nov 2026, D460)');
  check(await inFrame("const v = F('e-proc'); const t = g.convertValueToString(v); return t.indexOf('<b>Register Claim</b>') === 0 && /: <i>Process<\\/i>/.test(t) && /font-size:0.85em/.test(t) && a(v,'label') === 'Register Claim';"),
    'an entity shows "<b>name</b> : <i>Entity Type</i>" (the type a size smaller); the file keeps the name alone', await inFrame("return g.convertValueToString(F('e-proc'));"));
  await send({ eax: 'place', entity: { id: 'e-odd', name: '<script>x</script> & B', type: 'Service' }, at: { x: 1100, y: 40 }, relationships: [] }); await wait(300);
  check(await inFrame("const t = g.convertValueToString(F('e-odd')); return t.indexOf('<b>&lt;script&gt;x&lt;/script&gt; &amp; B</b>') === 0 && !/<script>/.test(t);"),
    'names are escaped: "<script>" and "&" show as text', await inFrame("return g.convertValueToString(F('e-odd'));"));
  check(await inFrame("const v = F('e-odd'); return g.getEditingValue(v) === '&lt;script&gt;x&lt;/script&gt; &amp; B' && g.getEditingValue(F('e-proc')) === 'Register Claim' && a(v,'label') === '<script>x</script> & B';"),
    'editing starts from the plain name (no bold, no type), and the saved name stays plain');
  check(await inFrame("const x = new XMLSerializer().serializeToString(F('e-proc').value); return /label=\"Register Claim\"/.test(x) && !/<b>|&lt;b&gt;/.test(x);"), 'the saved file: our attributes hold the plain name, no markup');
  check(await inFrame("const p2 = cells().find(c => c.vertex && a(c,'ea_placeholder')==='1' && !a(c,'ea_id')); const t = !!p2 && g.convertValueToString(p2); return !!p2 && t.indexOf('(unbound) ') === 0 && (g.isHtmlLabel(p2) ? /: <i>/.test(t) : / : /.test(t)) && !/<b>/.test(t);"),
    'a placeholder shows "(unbound) : <i>Entity Type</i>"');
  check(await inFrame("const e = R('r-ps10'); const t = g.convertValueToString(e); return t.replace(/<[^>]+>/g, '') === '(Realization)';"), 'a relationship with no name shows "(Type)" on the line (D565)');
  await send({ eax: 'resync', entities: {}, relationships: [{ id: 'r-ps10', type: 'Realization', source: 'e-proc', target: 'e-svc10', name: 'pays', pending: false }] }); await wait(300);
  check(await inFrame("return g.convertValueToString(R('r-ps10')).replace(/<[^>]+>/g, '') === 'pays (Realization)';"), 'a named one shows its name and keeps its type (D565)');
  // the same entity twice: the Relationships tab at the second copy draws the line there, not a new relationship
  await send({ eax: 'place', entity: { id: 'e-proc', name: 'Register Claim', type: 'Process' }, at: { x: 900, y: 600 }, relationships: [] }); await wait(300);
  const second = (await last('eax-placed')).cell;
  await send({ eax: 'add-related', cell: second, near: 'e-proc', entity: { id: 'e-svc10', name: 'Claim Payment Service', type: 'Service' },
    relationship: { id: 'r-ps10', type: 'Realization', source: 'e-proc', target: 'e-svc10', name: 'pays' }, relationships: [] }); await wait(300);
  const ra2 = await last('eax-related-added');
  check(!ra2.already && await inFrame("const l = cells().filter(c => c.edge && a(c,'ea_rel_id')==='r-ps10'); return l.length === 2 && l.some(e => e.source === m.getCell(arg));", second),
    'the second copy: the existing relationship drawn at it (two lines, one relationship)', ra2);
  await send({ eax: 'add-related', cell: second, near: 'e-proc', entity: { id: 'e-svc10', name: 'Claim Payment Service', type: 'Service' },
    relationship: { id: 'r-ps10', type: 'Realization', source: 'e-proc', target: 'e-svc10' }, relationships: [] }); await wait(300);
  check((await last('eax-related-added')).already === true, 'asked again: the line at that copy is selected');
  // a line drawn at the second copy, answered with the existing relationship: bound, nothing new
  const drawn = await inFrame("const e = g.insertEdge(g.getDefaultParent(), null, '', m.getCell(arg), F('e-cap3')); return e.id;", second); await wait(300);
  const askD = await last('eax-relationship');
  check(askD && askD.cell === drawn && askD.source === 'e-proc' && askD.target === 'e-cap3', 'a line at the second copy is asked about by entity, not by shape', askD);
  await send({ eax: 'rel', cell: drawn, type: 'Realization', id: 'r-pc3', name: '', pending: false }); await wait(300);
  check(await inFrame("return a(m.getCell(arg),'ea_rel_id') === 'r-pc3';", drawn), 'answered with the existing relationship: the line shows it');
  // undo and redo
  const vx = await inFrame("const v = m.getCell(arg); const x = v.geometry.x; g.moveCells([v], 40, 0); return [x, v.geometry.x];", second);
  await inFrame("ui.actions.get('undo').funct();"); await wait(200);
  check(vx[1] === vx[0] + 40 && await inFrame("return m.getCell(arg[0]).geometry.x === arg[1];", [second, vx[0]]), 'Ctrl+Z (undo) puts a moved object back');
  await send({ eax: 'redo' }); await wait(200);
  check(await inFrame("return m.getCell(arg[0]).geometry.x === arg[1];", [second, vx[0] + 40]), 'redo, also when the keys are pressed in EA Explorer');
  await send({ eax: 'undo' }); await wait(200);
  const histBefore = await inFrame("return ui.editor.undoManager.history.length;");
  await send({ eax: 'resync', entities: {}, relationships: [] }); await send({ eax: 'icons', icons: {} }); await wait(300);
  check(histBefore === await inFrame("return ui.editor.undoManager.history.length;"), 'what the plugin does for EA Explorer (resync, icons) is not something to undo');
  // a line whose relationship is committed: undo takes it off the view only; redo brings it back, bound
  const delAsked = (await events('eax-line-deleted')).length;
  await inFrame("ui.actions.get('undo').funct();"); await wait(400);    // the line drawn at the second copy
  const un = await last('eax-undo-note');
  check(!(await inFrame("return !!m.getCell(arg);", drawn)) && un && /Still in the model/.test(un.text) && delAsked === (await events('eax-line-deleted')).length,
    'undoing a committed line: off the view only, with a note; never the delete question', un);
  await inFrame("ui.actions.get('redo').funct();"); await wait(400);
  check(await inFrame("const e = m.getCell(arg); return !!e && a(e,'ea_rel_id') === 'r-pc3' && !ui.eax.hidden().some(h => h.id === 'r-pc3');", drawn),
    'redo: the line is back, bound to its relationship');
  // a line deleted from the model never comes back by undo
  await inFrame("g.removeCells([m.getCell(arg)], false);", drawn); await wait(300);
  await send({ eax: 'line-removed', id: 'r-pc3' }); await wait(200);
  await inFrame("ui.actions.get('undo').funct();"); await wait(400);
  check(!(await inFrame("return cells().some(c => c.edge && a(c,'ea_rel_id') === 'r-pc3');")), 'a relationship deleted from the model: undo does not bring its line back');
  await p.screenshot({ path: SHOTS + '/labels-undo.png' });

  console.log('16. exports and saving');
  await send({ action: 'export', format: 'png' }); await wait(2500);
  const png = (await events('export')).find(e => /^data:image\/png/.test(e.data || ''));
  check(!!png, 'PNG export (draw.io embed export)');
  await send({ action: 'export', format: 'svg' }); await wait(1500);
  check((await events('export')).some(e => /^data:image\/svg/.test(e.data || '')), 'SVG export');
  await send({ eax: 'heat', colours: { 'e-app': 'D7301F' } }); await wait(200);
  await inFrame("ui.actions.get('save').funct();"); await wait(800);
  const xml = (await last('save'))?.xml || '';
  check(/ea_id="e-app"/.test(xml) && /ea_junction=/.test(xml) && /ea_hidden=/.test(xml) && /ea_nested="1"/.test(xml) && /ea_form|ea_rel="Realization"/.test(xml), 'the saved file carries bindings, junction, hidden list, nesting');
  check(!/D7301F/i.test(xml), 'the heat map is not saved');
  await send({ eax: 'heat-off' });
  console.log('   style e-app:', await inFrame("return m.getStyle(F('e-app')) + ' / deleted=' + a(F('e-app'),'ea_deleted');"));
  await p.screenshot({ path: SHOTS + '/tests-final.png' });

  console.log('16b. File > Export as > .drawio file (D585)');
  await send(Object.assign({}, SETUP, { title: 'Claims landscape: today' })); await wait(800);
  const exportItems = await inFrame(`
    const menu = new mxPopupMenu(function (mn, cell, evt) { ui.menus.get('exportAs').funct(mn, null); });
    menu.div.className += ' geMenubarMenu'; menu.smartSeparators = true; menu.showDisabled = true;
    menu.popup(420, 90, null, null); window.__eaxMenu = menu;
    return Array.from(menu.div.querySelectorAll('td.mxPopupMenuItem')).map(t => t.textContent.trim()).filter(Boolean);`);
  check(/\.drawio file/.test(exportItems[0] || '') && exportItems.some(t => /^PNG/.test(t)) && exportItems.some(t => /^SVG/.test(t)) && exportItems.some(t => /^PDF/.test(t)),
    'Export as offers .drawio file first, and keeps PNG, SVG and PDF', exportItems);
  await p.screenshot({ path: SHOTS + '/export-as-menu.png' });
  await inFrame("window.__eaxMenu.hideMenu(); window.__eaxMenu.destroy();");
  const dl = p.waitForEvent('download', { timeout: 5000 }).catch(() => null);
  await inFrame("ui.actions.get('eaxExportDrawio').funct();");
  const got = await dl;
  check(!!got && got.suggestedFilename() === 'Claims landscape- today.drawio', 'the file is named after the view (unsafe characters replaced)', got && got.suggestedFilename());
  let body = '';
  if (got) { const fp = await got.path(); body = fp ? require('fs').readFileSync(fp, 'utf8') : ''; }
  check(/^<mxfile/.test(body) && /<mxGraphModel/.test(body) && /ea_id="e-app"/.test(body), 'an uncompressed .drawio of the current diagram, bindings and all', body.slice(0, 120));
  await send({ eax: 'heat', colours: { 'e-app': 'D7301F' } }); await wait(200);
  check(!/D7301F/i.test(await inFrame("return ui.eax.drawioFileXml();")), 'a heat map is on screen only: never in the exported file');
  await send({ eax: 'heat-off' });
  check((await last('eax-exported-drawio'))?.name === 'Claims landscape- today.drawio', 'EA Explorer is told what was exported');
  // a picture opened to look at (D585): its colours and, when asked, its own labels are kept
  const PIC = '<mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/><object id="k1" label="Kept" ea_id="e-kept" ea_type="Capability">' +
    '<mxCell style="rounded=1;whiteSpace=wrap;html=1;fillColor=#123456;" vertex="1" parent="1"><mxGeometry x="40" y="40" width="120" height="60" as="geometry"/></mxCell></object></root></mxGraphModel>';
  await send({ action: 'load', xml: PIC, autosave: 0, title: 'A picture' }); await wait(800);
  await send(Object.assign({}, SETUP, { keepLook: true, plainLabels: true, readOnly: true })); await wait(800);
  check(/fillColor=#123456/.test(await inFrame("return m.getStyle(m.getCell('k1'));")), 'keepLook: the colours it was made with stay');
  check(await inFrame("return g.convertValueToString(m.getCell('k1')) === 'Kept';"), 'plainLabels: the label as made, no ": Type"');
  await send(SETUP); await wait(800);
  check(!/fillColor=#123456/.test(await inFrame("return m.getStyle(m.getCell('k1'));")) && /: <i>Capability/.test(await inFrame("return g.convertValueToString(m.getCell('k1'));")),
    'a drawn view still restyles and shows "name : Type"');

  console.log('17. read only');
  await send(Object.assign({}, SETUP, { readOnly: true })); await wait(800);
  check(await inFrame("return Object.keys(ui.sidebar.palettes).length === 0 && !g.isCellsMovable() && !g.isConnectable();"), 'read only: no stencil, no moving, no lines');
  check(await inFrame("const ac = ui.actions.get('eaxExportDrawio'); return !!ac && ac.isEnabled();"), 'read only: .drawio file is still offered');

  console.log(errs.length ? 'errors:\n' + errs.join('\n') : 'no page errors');
  console.log(`\n${pass} passed, ${fail} failed`);
  await b.close();
  process.exit(fail ? 1 : 0);
})();
