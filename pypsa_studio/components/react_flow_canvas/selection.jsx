function normalizeSelectionRect(start, current) {
  const x = Math.min(start.x, current.x);
  const y = Math.min(start.y, current.y);
  const width = Math.abs(current.x - start.x);
  const height = Math.abs(current.y - start.y);
  return { x, y, width, height, right: x + width, bottom: y + height };
}

function rectsIntersect(left, right) {
  return !(
    left.right < right.x ||
    left.x > right.right ||
    left.bottom < right.y ||
    left.y > right.bottom
  );
}
