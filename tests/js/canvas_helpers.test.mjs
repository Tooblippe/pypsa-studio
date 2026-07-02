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
    readCanvasPart("geometry.jsx"),
    readCanvasPart("regions.jsx"),
    edgeHelpers,
    `Object.assign(globalThis, {
      activePalettePayload,
      applyBusSideConstraintsToLayout,
      clampContextMenuPosition,
      componentToBuilderKind,
      connectorTerminalSides,
      displayNameForNode,
      edgePathIntersectsRect,
      normalizeSelectionRect,
      flowBoundsFromLocalRect,
      hasNegativeGeneratorSign,
      iconContactPercent,
      isAttachableComponent,
      isCanvasVisible,
      localNodeRect,
      localPointFromMouseEvent,
      localRectFromFlowBounds,
      parseComponentPayload,
      rectsIntersect,
      normalizeRegionColor,
      resizeRegionBounds,
      flowRectForRegion,
      flowRectsIntersect,
      safeHandleId,
      shouldRotateIconForBusSide,
      symbolMetaForComponent,
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

test("geometry helpers handle wrapper offsets and clamping", () => {
  const wrapper = {
    getBoundingClientRect: () => ({ left: 10, top: 20, width: 200, height: 160 }),
  };
  const reactFlow = {
    screenToFlowPosition: ({ x, y }) => ({ x: x / 2, y: y / 2 }),
    flowToScreenPosition: ({ x, y }) => ({ x: x * 2, y: y * 2 }),
  };

  assert.deepEqual(
    plain(helpers.localPointFromMouseEvent({ clientX: 25, clientY: 50 }, wrapper)),
    { x: 15, y: 30 },
  );
  assert.deepEqual(
    plain(helpers.clampContextMenuPosition({ x: 190, y: 150 }, wrapper)),
    { x: 12, y: 48 },
  );
  assert.deepEqual(
    plain(
      helpers.flowBoundsFromLocalRect(
        { x: 0, y: 0, right: 20, bottom: 40 },
        reactFlow,
        wrapper,
      ),
    ),
    { x: 5, y: 10, width: 10, height: 20 },
  );
  assert.deepEqual(
    plain(
      helpers.localRectFromFlowBounds(
        { x: 5, y: 10, width: 10, height: 20 },
        reactFlow,
        wrapper,
      ),
    ),
    { x: 0, y: 0, width: 20, height: 40 },
  );
  assert.deepEqual(
    plain(
      helpers.localNodeRect(
        {
          position: { x: 5, y: 10 },
          style: { width: "30", height: "40" },
        },
        reactFlow,
        wrapper,
      ),
    ),
    { x: 0, y: 0, right: 30, bottom: 40 },
  );
});

test("component metadata helpers cover defaults and malformed payloads", () => {
  assert.equal(helpers.componentToBuilderKind("Storage_Units"), "storage_unit");
  assert.deepEqual(plain(helpers.symbolMetaForComponent("unknown")), {
    width: 56,
    height: 56,
  });
  assert.equal(helpers.iconContactPercent("loads", "left"), 0);
  assert.deepEqual(plain(helpers.connectorTerminalSides("stores")), ["left"]);
  assert.equal(helpers.isAttachableComponent("lines"), false);
  assert.equal(helpers.shouldRotateIconForBusSide("generators", "right"), true);
  assert.equal(
    helpers.hasNegativeGeneratorSign({
      component: "generators",
      attrs: { sign: -1 },
    }),
    true,
  );
  assert.deepEqual(plain(helpers.parseComponentPayload('{"component":"buses"}')), {
    component: "buses",
  });
  assert.deepEqual(plain(helpers.parseComponentPayload("{bad json")), {
    component: "",
  });
  assert.equal(helpers.activePalettePayload(), "");
  assert.equal(
    helpers.displayNameForNode({ id: "node_1", pypsa_name: "Bus" }),
    "node_1",
  );
  assert.equal(helpers.isCanvasVisible({ layout: { visible: false } }), false);
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
    {
      id: "bus_1",
      component: "buses",
      position: { x: 100, y: 100 },
      attrs: { name: "bus_a" },
    },
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

test("buildBusConnectionRouting orders handles and preserves component side", () => {
  const nodes = [
    { id: "bus_1", component: "buses", position: { x: 100, y: 100 }, attrs: { name: "bus_a" } },
    {
      id: "gen_1",
      component: "generators",
      position: { x: 40, y: 20 },
      layout: { bus_side: "left" },
      attrs: { bus: "bus_a" },
    },
    {
      id: "load_1",
      component: "loads",
      position: { x: 220, y: 220 },
      layout: { bus_side: "right" },
      attrs: { bus: "bus_a" },
    },
    {
      id: "load_2",
      component: "loads",
      position: { x: 220, y: 160 },
      layout: { bus_side: "right" },
      attrs: { bus: "bus_a" },
    },
  ];
  const edges = [
    {
      id: "attach:load_1:bus_1",
      source: "bus_1",
      target: "load_1",
      sourceHandle: "right-source",
      targetHandle: "left-target",
    },
    {
      id: "attach:load_2:bus_1",
      source: "bus_1",
      target: "load_2",
      sourceHandle: "right-source",
      targetHandle: "left-target",
    },
    {
      id: "attach:gen_1:bus_1",
      source: "gen_1",
      target: "bus_1",
      sourceHandle: "right-source",
      targetHandle: "left-target",
    },
  ];

  const routed = helpers.buildBusConnectionRouting(nodes, edges);

  assert.equal(routed.edges[0].sourceHandle, "right-source-attach_load_1_bus_1");
  assert.equal(routed.edges[2].sourceHandle, "right-source");
  const offsetsByHandleId = Object.fromEntries(
    routed.handlesByBusId.bus_1.map((handle) => [handle.id, handle.offsetPx]),
  );
  assert.equal(offsetsByHandleId["right-source-attach_load_2_bus_1"], 24);
  assert.equal(offsetsByHandleId["right-source-attach_load_1_bus_1"], 48);

  const constrained = helpers.applyBusSideConstraintsToLayout(
    [{ id: "gen_1", x: 250, y: 20 }],
    nodes,
  );
  assert.equal(constrained[0].x, 25);
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

test("edgePathIntersectsRect samples branch SVG paths only", () => {
  const pathElement = {
    ownerSVGElement: {
      createSVGPoint: () => ({
        x: 0,
        y: 0,
        matrixTransform() {
          return { x: this.x, y: this.y };
        },
      }),
      getScreenCTM: () => ({}),
    },
    getTotalLength: () => 100,
    getPointAtLength: (length) => ({ x: length, y: 10 }),
  };
  const wrapper = {
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
    querySelectorAll: () => [
      {
        getAttribute: () => "branch:line_1",
        querySelector: () => pathElement,
      },
    ],
    querySelector: () => null,
  };

  assert.equal(
    helpers.edgePathIntersectsRect(
      wrapper,
      { id: "branch:line_1", component: "lines" },
      { x: 45, y: 5, right: 55, bottom: 15 },
    ),
    true,
  );
  assert.equal(
    helpers.edgePathIntersectsRect(
      wrapper,
      { id: "attach:load_1:bus_1", component: "loads" },
      { x: 45, y: 5, right: 55, bottom: 15 },
    ),
    false,
  );
});
