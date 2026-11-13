// Draws the "building blocks" diagram with Rough.js (hand-drawn look).
// The same relations are also listed as text below the diagram, so the
// page stays readable without JavaScript.
(function () {
  "use strict";

  const svg = document.getElementById("blocks-diagram");
  if (!svg || typeof rough === "undefined") {
    return;
  }

  const NS = "http://www.w3.org/2000/svg";
  const rc = rough.svg(svg);
  const ink = "#1f1e1b";
  const link = "#1f5fbf";

  // Boxes: x, y, width, height, fill, title, question
  const boxes = {
    oo: { x: 30,  y: 170, w: 230, h: 84, fill: "#fde0e6", title: "OrderOrchestration", q: "How does an order run?" },
    md: { x: 640, y: 30,  w: 230, h: 84, fill: "#fff3a8", title: "MasterData",         q: "What do we stock?" },
    al: { x: 300, y: 360, w: 230, h: 84, fill: "#d9f0d3", title: "Allocation",         q: "Where do we look first?" },
    to: { x: 640, y: 300, w: 230, h: 84, fill: "#cfe0f7", title: "Topology",           q: "How is it laid out?" }
  };

  // Edges: from point, to point, label, label position
  const edges = [
    { from: [262, 190], to: [636, 80],  label: "needs items from",     lx: 440, ly: 112 },
    { from: [150, 258], to: [296, 398], label: "looks for stock via",  lx: 104, ly: 342 },
    { from: [534, 400], to: [636, 352], label: "searches areas in",    lx: 614, ly: 420 },
    { from: [262, 222], to: [636, 330], label: "target point sits in", lx: 470, ly: 246 }
  ];

  function text(x, y, value, size, weight, color, anchor) {
    const t = document.createElementNS(NS, "text");
    t.setAttribute("x", x);
    t.setAttribute("y", y);
    t.setAttribute("text-anchor", anchor || "middle");
    t.setAttribute("font-family", "Caveat, cursive");
    t.setAttribute("font-size", size);
    t.setAttribute("font-weight", weight);
    t.setAttribute("fill", color);
    t.textContent = value;
    svg.appendChild(t);
  }

  function arrow(from, to, seed) {
    svg.appendChild(rc.line(from[0], from[1], to[0], to[1], { stroke: link, strokeWidth: 2, roughness: 1.4, seed: seed }));
    // Arrow head: two short strokes back from the target point.
    const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
    const len = 16;
    [-0.45, 0.45].forEach(function (spread, i) {
      const a = angle + Math.PI + spread;
      svg.appendChild(rc.line(to[0], to[1], to[0] + len * Math.cos(a), to[1] + len * Math.sin(a),
        { stroke: link, strokeWidth: 2, roughness: 1, seed: seed + i + 1 }));
    });
  }

  edges.forEach(function (e, i) {
    arrow(e.from, e.to, 10 + i * 7);
  });

  Object.keys(boxes).forEach(function (key, i) {
    const b = boxes[key];
    svg.appendChild(rc.rectangle(b.x, b.y, b.w, b.h, {
      stroke: ink, strokeWidth: 2.4, roughness: 1.6, seed: 3 + i,
      fill: b.fill, fillStyle: "hachure", hachureGap: 7, fillWeight: 1.2
    }));
    text(b.x + b.w / 2, b.y + 36, b.title, 30, 700, ink);
    text(b.x + b.w / 2, b.y + 66, b.q, 22, 500, "#3d3b36");
  });

  edges.forEach(function (e) {
    text(e.lx, e.ly, e.label, 22, 500, link);
  });
})();
