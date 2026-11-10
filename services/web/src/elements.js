// The element types of a metamodel's domain (D397, D405 junction gap): a junction is a connector type, not an element,
// so it is left out of every type list, picker, count and catalogue; the metamodel pages and the drawn-view stencil's
// Junctions group still show it.
export function elementTypes(domain) {
  return (domain?.entity_types || []).filter((t) => !t.is_connector);
}

export function isElementType(t) {
  return !!t && !t.is_connector;
}
