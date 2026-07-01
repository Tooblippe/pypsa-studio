import React, {
  useCallback as useCallbackReactFlowCanvas,
  useEffect as useEffectReactFlowCanvas,
  useMemo as useMemoReactFlowCanvas,
  useRef as useRefReactFlowCanvas,
  useState as useStateReactFlowCanvas,
} from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlowProvider,
  applyNodeChanges,
  getSmoothStepPath,
  useReactFlow,
  useUpdateNodeInternals,
} from "reactflow";
import ReactFlow from "reactflow";
import "reactflow/dist/style.css";

export function ReactFlowCanvas(props) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
