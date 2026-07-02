import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "..", "..");
const canvasDir = path.join(root, "pypsa_studio", "components", "react_flow_canvas");

function readCanvasPart(fileName) {
  return fs.readFileSync(path.join(canvasDir, fileName), "utf8");
}

function loadHelpers() {
  const edgeHelpers = readCanvasPart("edge_rendering.jsx").split(
    "function SchematicStepEdge",
  )[0];
  const source = [
    "const Position = { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' };",
    readCanvasPart("constants.jsx"),
    readCanvasPart("component_meta.jsx"),
    readCanvasPart("bus_routing.jsx"),
    readCanvasPart("selection.jsx"),
    readCanvasPart("regions.jsx"),
    edgeHelpers,
    `Object.assign(globalThis, {
      normalizeSelectionRect,
      rectsIntersect,
      normalizeRegionColor,
      resizeRegionBounds,
      flowRectForRegion,
      flowRectsIntersect,
      safeHandleId,
      busSymbolLengthForHandles,
      sideForBusConnection,
      buildBusConnectionRouting,
      edgeOffsetFromData,
      shouldRenderEdgeSymbol
    });`,
  ].join("\n\n");
  const context = {};
  vm.createContext(context);
  vm.runInContext(source, context);
  return context;
}

const helpers = loadHelpers();

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("normalizeSelectionRect handles reverse drags", () => {
  assert.deepEqual(
    plain(helpers.normalizeSelectionRect({ x: 40, y: 30 }, { x: 10, y: 5 })),
    { x: 10, y: 5, width: 30, height: 25, right: 40, bottom: 30 },
  );
});

test("rectsIntersect detects overlap and separation", () => {
  assert.equal(
    helpers.rectsIntersect(
      { x: 0, y: 0, right: 10, bottom: 10 },
      { x: 5, y: 5, right: 15, bottom: 15 },
    ),
    true,
  );
  assert.equal(
    helpers.rectsIntersect(
      { x: 0, y: 0, right: 10, bottom: 10 },
      { x: 11, y: 0, right: 20, bottom: 10 },
    ),
    false,
  );
});

test("normalizeRegionColor accepts known colors and falls back", () => {
  assert.equal(helpers.normalizeRegionColor(" #16A34A "), "#16a34a");
  assert.equal(helpers.normalizeRegionColor("not-a-color"), "#2563eb");
});

test("resizeRegionBounds clamps west and north handles", () => {
  assert.deepEqual(
    plain(
      helpers.resizeRegionBounds(
        { x: 10, y: 20, width: 100, height: 80 },
        "nw",
        { x: 200, y: 200 },
      ),
    ),
    { x: 94, y: 84, width: 16, height: 16 },
  );
});

test("flowRectsIntersect works with region rectangles", () => {
  const region = helpers.flowRectForRegion({ x: 10, y: 10, width: 20, height: 20 });

  assert.equal(
    helpers.flowRectsIntersect(region, { x: 29, y: 29, right: 40, bottom: 40 }),
    true,
  );
  assert.equal(
    helpers.flowRectsIntersect(region, { x: 31, y: 10, right: 40, bottom: 20 }),
    false,
  );
});

test("safeHandleId sanitizes edge identifiers", () => {
  assert.equal(helpers.safeHandleId("branch:line 1"), "branch_line_1");
  assert.equal(helpers.safeHandleId(""), "edge");
});

test("busSymbolLengthForHandles grows with side count", () => {
  assert.equal(helpers.busSymbolLengthForHandles([]), 72);
  assert.equal(
    helpers.busSymbolLengthForHandles([
      { side: "left" },
      { side: "left" },
      { side: "left" },
      { side: "left" },
    ]),
    92,
  );
});

test("sideForBusConnection handles vertical and horizontal buses", () => {
  const verticalBus = { component: "buses", position: { x: 100, y: 100 } };
  const horizontalBus = {
    component: "buses",
    position: { x: 100, y: 100 },
    layout: { bus_orientation: "horizontal" },
  };

  assert.equal(
    helpers.sideForBusConnection(verticalBus, {
      component: "loads",
      position: { x: 250, y: 100 },
    }),
    "right",
  );
  assert.equal(
    helpers.sideForBusConnection(horizontalBus, {
      component: "loads",
      position: { x: 100, y: 250 },
    }),
    "bottom",
  );
});

test("buildBusConnectionRouting creates stable bus handles", () => {
  const nodes = [
    { id: "bus_1", component: "buses", position: { x: 100, y: 100 }, attrs: { name: "bus_a" } },
    {
      id: "gen_1",
      component: "generators",
      position: { x: 0, y: 100 },
      attrs: { bus: "bus_a" },
    },
  ];
  const edges = [
    {
      id: "attach:gen_1:bus_1",
      source: "gen_1",
      target: "bus_1",
      sourceHandle: "right-source",
      targetHandle: "left-target",
    },
  ];

  const routed = helpers.buildBusConnectionRouting(nodes, edges);

  assert.equal(routed.edges[0].sourceHandle, "right-source");
  assert.equal(routed.edges[0].targetHandle, "left-target-attach_gen_1_bus_1");
  assert.equal(routed.handlesByBusId.bus_1[0].offsetPx, 36);
});

test("edge helper functions read serialized edge data", () => {
  assert.deepEqual(
    plain(helpers.edgeOffsetFromData({ edgeOffset: { x: "3", y: 4 } })),
    {
      x: 3,
      y: 4,
    },
  );
  assert.equal(helpers.shouldRenderEdgeSymbol("transformers"), true);
  assert.equal(helpers.shouldRenderEdgeSymbol("loads"), false);
});
