function componentToBuilderKind(component) {
  const key = String(component || "").toLowerCase();
  const map = {
    buses: "bus",
    bus: "bus",
    generators: "generator",
    generator: "generator",
    loads: "load",
    load: "load",
    storage_units: "storage_unit",
    storage_unit: "storage_unit",
    stores: "store",
    store: "store",
    lines: "line",
    line: "line",
    links: "link",
    link: "link",
    transformers: "transformer",
    transformer: "transformer",
    processes: "process",
    process: "process",
  };
  return map[key] || "";
}

function symbolMetaForComponent(component) {
  const kind = componentToBuilderKind(component);
  return BUILDER_SYMBOL_META[kind] || { width: 56, height: 56 };
}

function iconContactPercent(component, side) {
  const kind = componentToBuilderKind(component);
  const contactPoints = {
    generator: { left: 0, right: 100 },
    load: { left: 0, right: 100 },
    store: { left: 0, right: 100 },
    storage_unit: { left: 0, right: 100 },
  };
  return contactPoints[kind]?.[side] ?? (side === "left" ? 0 : 100);
}

function hasConnectorTerminal(component) {
  return connectorTerminalSides(component).length > 0;
}

function connectorTerminalSides(component) {
  const kind = componentToBuilderKind(component);
  if (kind === "generator") return ["right"];
  if (kind === "load") return ["left"];
  if (kind === "store" || kind === "storage_unit") return ["left"];
  return [];
}

function connectorTerminalStyleForComponent(component, side, topPx) {
  const kind = componentToBuilderKind(component);
  const style = { top: `${topPx}px` };
  if (kind === "generator" && side === "right") {
    style.width = "8px";
  }
  return style;
}

function isAttachableComponent(component) {
  return Boolean(
    component &&
      !["buses", "lines", "links", "transformers"].includes(component),
  );
}

/**
 * Return whether a generator should render as consuming power.
 */
function hasNegativeGeneratorSign(data) {
  return (
    String(data?.component || "").toLowerCase() === "generators" &&
    Number(data?.attrs?.sign) < 0
  );
}

/**
 * Return whether a component should be represented by an edge, not a node.
 */
function isBranchEdgeComponent(component) {
  return [
    "lines",
    "line",
    "links",
    "link",
    "processes",
    "process",
    "transformers",
    "transformer",
  ].includes(String(component || "").toLowerCase());
}

function parseComponentPayload(payload) {
  if (!payload) return { component: "" };
  if (typeof payload === "string" && payload.trim().startsWith("{")) {
    try {
      return JSON.parse(payload);
    } catch {
      return { component: "" };
    }
  }
  return { component: payload };
}

function activePalettePayload() {
  if (typeof window === "undefined") return "";
  const payload = window.__pypsaBuilderActivePayload || {
    component: window.__pypsaBuilderActiveComponent || "",
  };
  return payload.component ? JSON.stringify(payload) : "";
}

function dragPayloadFromEvent(event) {
  return (
    event.dataTransfer?.getData("application/pypsa-component") ||
    event.dataTransfer?.getData("text/plain") ||
    activePalettePayload()
  );
}

function displayNameForNode(node) {
  return String(node?.attrs?.name || node?.id || node?.pypsa_name || "");
}

function isCanvasVisible(node) {
  return node?.layout?.visible !== false;
}
