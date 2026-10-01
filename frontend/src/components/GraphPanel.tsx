import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import type { GraphPayload } from "../types";

const colorByType: Record<string, string> = {
  USER: "#4fd1c5",
  DEVICE: "#60a5fa",
  CARD: "#f6ad55",
  BANK_ACCOUNT: "#c084fc",
  UPI_ID: "#c084fc",
  IP: "#94a3b8",
  MERCHANT: "#fb7185",
};

export function GraphPanel({ graph }: { graph: GraphPayload }) {
  const container = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    if (!container.current) return;
    const cy = cytoscape({
      container: container.current,
      elements: [...graph.nodes, ...graph.edges],
      style: [
        {
          selector: "node",
          style: {
            "background-color": (element) => colorByType[element.data("entity_type") as string] ?? "#64748b",
            label: "data(id)",
            color: "#cbd5e1",
            "font-size": 8,
            "text-valign": "bottom",
            "text-margin-y": 6,
            width: 24,
            height: 24,
            "border-width": 2,
            "border-color": "#111827",
          },
        },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#334155",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.72,
          },
        },
        { selector: ":selected", style: { "border-color": "#ffffff", "border-width": 3, "line-color": "#4fd1c5" } },
        { selector: ".faded", style: { opacity: 0.12 } },
      ],
      layout: { name: "cose", animate: false, fit: true, padding: 24, randomize: false },
      minZoom: 0.25,
      maxZoom: 2.5,
    });
    cy.on("tap", "node, edge", (event) => {
      const element = event.target;
      setSelected(element.data() as Record<string, unknown>);
      cy.elements().addClass("faded");
      element.closedNeighborhood().removeClass("faded");
    });
    cy.on("tap", (event) => {
      if (event.target === cy) {
        cy.elements().removeClass("faded");
        setSelected(null);
      }
    });
    return () => cy.destroy();
  }, [graph]);

  return (
    <section className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div><p className="eyebrow">Relationship graph</p><p className="mt-1 text-xs text-slate-500">Click a node to isolate its neighborhood</p></div>
        <span className="rounded-full border border-slate-700 px-2 py-1 text-[10px] text-slate-500">{graph.nodes.length} nodes · {graph.edges.length} edges</span>
      </div>
      <div className="grid lg:grid-cols-[1fr_220px]">
        <div ref={container} className="h-[430px] bg-ink/50" aria-label="Interactive ring graph" />
        <aside className="h-[430px] overflow-auto border-l border-slate-800 p-4">
          <p className="eyebrow">Selection details</p>
          {selected ? (
            <dl className="mt-4 space-y-3 text-xs">
              {Object.entries(selected).filter(([, value]) => typeof value !== "object").map(([key, value]) => (
                <div key={key}><dt className="text-slate-600">{key}</dt><dd className="mt-1 break-all text-slate-300">{String(value)}</dd></div>
              ))}
            </dl>
          ) : <p className="mt-4 text-xs leading-5 text-slate-600">Select an entity or relationship to inspect graph-backed attributes.</p>}
        </aside>
      </div>
    </section>
  );
}
