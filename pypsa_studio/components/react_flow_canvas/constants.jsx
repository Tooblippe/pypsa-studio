const BUILDER_SYMBOL_META = {
  bus: { width: 24, height: 72 },
  generator: { width: 44, height: 44 },
  load: { width: 42, height: 48 },
  storage_unit: { width: 44, height: 52 },
  store: { width: 50, height: 52 },
  line: { width: 52, height: 28 },
  link: { width: 52, height: 28 },
};

const BUS_LABEL_HEIGHT = 20;

const BUS_MIN_HEIGHT_PX = 72;

const BUS_CONNECTION_SPACING_PX = 24;

const BUS_CONNECTION_PADDING_PX = 10;

const EDGE_LABEL_VERTICAL_THRESHOLD_PX = 8;

const EDGE_SYMBOL_SIZE_PX = 24;

const BUS_COMPONENT_HORIZONTAL_OFFSET_PX = 75;

const DEFAULT_REGION_COLOR = "#2563eb";

const REGION_COLOR_OPTIONS = [
  { color: "#2563eb", label: "Blue" },
  { color: "#16a34a", label: "Green" },
  { color: "#d97706", label: "Amber" },
  { color: "#dc2626", label: "Red" },
  { color: "#7c3aed", label: "Violet" },
  { color: "#0891b2", label: "Cyan" },
  { color: "#4b5563", label: "Gray" },
];

const VOLTAGE_COLOR_OPTIONS =  [
  { color: "#090909", label: "Blue" },
  { color: "#16a34a", label: "Green" },
  { color: "#d97706", label: "Amber" },
  { color: "#dc2626", label: "Red" },
  { color: "#7c3aed", label: "Violet" },
  { color: "#0891b2", label: "Cyan" },
  { color: "#4b5563", label: "Gray" },
];
