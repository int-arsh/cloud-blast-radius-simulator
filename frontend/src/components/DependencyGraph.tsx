import React, { useMemo, useState, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize2, RotateCcw, Search, Grid, GitFork } from 'lucide-react';
import type { ResourceNode, FullAnalysisReport, NormalizedAction } from '../types';

interface DependencyGraphProps {
  report: FullAnalysisReport;
  selectedNodeAddress: string | null;
  onSelectNode: (address: string) => void;
}

interface LayoutNode {
  node: ResourceNode;
  x: number;
  y: number;
  width: number;
  height: number;
  level: number;
}

export const DependencyGraph: React.FC<DependencyGraphProps> = ({
  report,
  selectedNodeAddress,
  onSelectNode,
}) => {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 40, y: 40 });
  const [isPanning, setIsPanning] = useState(false);
  const [startPan, setStartPan] = useState({ x: 0, y: 0 });
  const [searchQuery, setSearchQuery] = useState('');
  const [layoutMode, setLayoutMode] = useState<'dag' | 'grid'>('dag');
  const [hoveredNodeAddress, setHoveredNodeAddress] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);

  // Compute blast radius sets for the active (hovered or selected) node
  const activeAddress = hoveredNodeAddress || selectedNodeAddress;

  const blastRadiusInfo = useMemo(() => {
    if (!activeAddress) return { changed: false, impactedSet: new Set<string>(), edgeSet: new Set<string>() };

    const blastEntry = report.impact_summary.resource_blast_radii.find(
      (r) => r.resource_address === activeAddress
    );

    const impactedSet = new Set<string>();
    const edgeSet = new Set<string>();

    if (blastEntry) {
      // Node is a changed resource causing impact
      blastEntry.impacted_resources.forEach((imp) => {
        impactedSet.add(imp.address);
        // Add path edges
        for (let i = 0; i < imp.shortest_path.length - 1; i++) {
          edgeSet.add(`${imp.shortest_path[i]}->${imp.shortest_path[i + 1]}`);
        }
      });
      return { changed: true, impactedSet, edgeSet };
    }

    // Check if node is an impacted dependent
    for (const r of report.impact_summary.resource_blast_radii) {
      for (const imp of r.impacted_resources) {
        if (imp.address === activeAddress) {
          impactedSet.add(r.resource_address);
          for (let i = 0; i < imp.shortest_path.length - 1; i++) {
            edgeSet.add(`${imp.shortest_path[i]}->${imp.shortest_path[i + 1]}`);
          }
        }
      }
    }

    return { changed: false, impactedSet, edgeSet };
  }, [activeAddress, report.impact_summary]);

  // Compute layout coordinates
  const layoutNodes: LayoutNode[] = useMemo(() => {
    const nodes = report.nodes || [];
    const edges = report.edges || [];

    if (nodes.length === 0) return [];

    const nodeWidth = 240;
    const nodeHeight = 76;
    const colGap = 160;
    const rowGap = 36;

    if (layoutMode === 'grid') {
      const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
      return nodes.map((node, idx) => {
        const col = idx % cols;
        const row = Math.floor(idx / cols);
        return {
          node,
          x: col * (nodeWidth + 60) + 40,
          y: row * (nodeHeight + rowGap) + 40,
          width: nodeWidth,
          height: nodeHeight,
          level: 0,
        };
      });
    }

    // Layered DAG layout based on dependency depth
    // Edge (u -> v) means u depends on v. So v is "upstream / foundational" (Level 0), u is Level 1.
    const levels = new Map<string, number>();

    // Initialize all to 0
    nodes.forEach((n) => levels.set(n.address, 0));

    // Iterative level computation
    let changed = true;
    let iterations = 0;
    while (changed && iterations < 15) {
      changed = false;
      iterations++;
      edges.forEach((e) => {
        const targetLvl = levels.get(e.target) || 0;
        const sourceLvl = levels.get(e.source) || 0;
        if (sourceLvl <= targetLvl) {
          levels.set(e.source, targetLvl + 1);
          changed = true;
        }
      });
    }

    // Group nodes by level
    const levelBuckets = new Map<number, ResourceNode[]>();
    nodes.forEach((n) => {
      const lvl = levels.get(n.address) || 0;
      if (!levelBuckets.has(lvl)) levelBuckets.set(lvl, []);
      levelBuckets.get(lvl)!.push(n);
    });

    const result: LayoutNode[] = [];
    const sortedLevels = Array.from(levelBuckets.keys()).sort((a, b) => a - b);

    sortedLevels.forEach((lvl) => {
      const bucket = levelBuckets.get(lvl)!;
      bucket.forEach((node, rowIdx) => {
        result.push({
          node,
          x: lvl * (nodeWidth + colGap) + 50,
          y: rowIdx * (nodeHeight + rowGap) + 50,
          width: nodeWidth,
          height: nodeHeight,
          level: lvl,
        });
      });
    });

    return result;
  }, [report.nodes, report.edges, layoutMode]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, LayoutNode>();
    layoutNodes.forEach((ln) => map.set(ln.node.address, ln));
    return map;
  }, [layoutNodes]);

  // Handle Zoom and Pan
  const handleMouseDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('.graph-node-group')) return;
    setIsPanning(true);
    setStartPan({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isPanning) return;
    setPan({
      x: e.clientX - startPan.x,
      y: e.clientY - startPan.y,
    });
  };

  const handleMouseUp = () => {
    setIsPanning(false);
  };

  const handleZoomIn = () => setZoom((z) => Math.min(2.5, z + 0.15));
  const handleZoomOut = () => setZoom((z) => Math.max(0.3, z - 0.15));
  const handleResetZoom = () => {
    setZoom(1);
    setPan({ x: 40, y: 40 });
  };

  const handleFitScreen = () => {
    if (layoutNodes.length === 0 || !containerRef.current) return;
    const maxX = Math.max(...layoutNodes.map((n) => n.x + n.width)) + 60;
    const maxY = Math.max(...layoutNodes.map((n) => n.y + n.height)) + 60;
    const clientWidth = containerRef.current.clientWidth;
    const clientHeight = containerRef.current.clientHeight;

    const scale = Math.min(clientWidth / maxX, clientHeight / maxY, 1.2);
    setZoom(Math.max(0.4, scale));
    setPan({ x: 30, y: 30 });
  };

  // Helper for action colors
  const getActionColor = (action?: NormalizedAction | null) => {
    switch (action) {
      case 'create':
        return '#10b981';
      case 'delete':
        return '#ef4444';
      case 'replace':
        return '#f59e0b';
      case 'update':
        return '#3b82f6';
      case 'no-op':
      default:
        return '#64748b';
    }
  };

  return (
    <div className="glass-panel graph-container" ref={containerRef}>
      {/* Toolbar */}
      <div className="graph-toolbar">
        <div className="section-title">
          <GitFork size={18} color="#6366f1" />
          <span>Interactive Infrastructure Dependency Graph</span>
          <span style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500 }}>
            ({layoutNodes.length} nodes, {(report.edges || []).length} edges)
          </span>
        </div>

        <div className="graph-controls">
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <Search size={14} color="#64748b" style={{ position: 'absolute', left: '10px' }} />
            <input
              type="text"
              placeholder="Search resource node..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="graph-search-input"
              style={{ paddingLeft: '30px' }}
            />
          </div>

          <button
            type="button"
            className="btn-icon"
            onClick={() => setLayoutMode(layoutMode === 'dag' ? 'grid' : 'dag')}
            title={`Toggle layout mode (current: ${layoutMode.toUpperCase()})`}
          >
            {layoutMode === 'dag' ? <Grid size={15} /> : <GitFork size={15} />}
          </button>

          <button type="button" className="btn-icon" onClick={handleZoomIn} title="Zoom in">
            <ZoomIn size={15} />
          </button>
          <button type="button" className="btn-icon" onClick={handleZoomOut} title="Zoom out">
            <ZoomOut size={15} />
          </button>
          <button type="button" className="btn-icon" onClick={handleFitScreen} title="Fit to screen">
            <Maximize2 size={15} />
          </button>
          <button type="button" className="btn-icon" onClick={handleResetZoom} title="Reset zoom">
            <RotateCcw size={15} />
          </button>
        </div>
      </div>

      {/* SVG Canvas */}
      <div
        className="graph-svg-wrapper"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <svg width="100%" height="100%">
          <defs>
            <marker
              id="arrow-default"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="6"
              markerHeight="6"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="rgba(255, 255, 255, 0.3)" />
            </marker>

            <marker
              id="arrow-highlighted"
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="7"
              markerHeight="7"
              orient="auto-start-reverse"
            >
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#ef4444" />
            </marker>
          </defs>

          <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
            {/* 1. Render Dependency Edges */}
            {(report.edges || []).map((edge, idx) => {
              const src = nodeMap.get(edge.source);
              const tgt = nodeMap.get(edge.target);
              if (!src || !tgt) return null;

              // Connect from right of source to left of target (or center to center)
              const startX = src.x + src.width;
              const startY = src.y + src.height / 2;
              const endX = tgt.x;
              const endY = tgt.y + tgt.height / 2;

              // Curved bezier path
              const dx = endX - startX;
              const cpOffset = Math.max(40, Math.abs(dx) * 0.45);
              const pathD = `M ${startX} ${startY} C ${startX + cpOffset} ${startY}, ${endX - cpOffset} ${endY}, ${endX} ${endY}`;

              const edgeKey = `${edge.source}->${edge.target}`;
              const isHighlighted = blastRadiusInfo.edgeSet.has(edgeKey);
              const isDimmed = activeAddress ? !isHighlighted : false;

              return (
                <path
                  key={`edge-${idx}`}
                  d={pathD}
                  className={`graph-edge ${isHighlighted ? 'highlighted-edge' : ''} ${edge.evidence_category.includes('expression') ? 'edge-dashed' : ''}`}
                  markerEnd={`url(#${isHighlighted ? 'arrow-highlighted' : 'arrow-default'})`}
                  opacity={isDimmed ? 0.15 : 1}
                />
              );
            })}

            {/* 2. Render Resource Nodes */}
            {layoutNodes.map((ln) => {
              const addr = ln.node.address;
              const action = ln.node.action || 'no-op';
              const actionColor = getActionColor(action);
              const isSelected = selectedNodeAddress === addr;
              const isRootChanged = blastRadiusInfo.changed && activeAddress === addr;
              const isImpacted = blastRadiusInfo.impactedSet.has(addr);
              const matchesSearch = searchQuery
                ? addr.toLowerCase().includes(searchQuery.toLowerCase())
                : true;

              const isDimmed = activeAddress
                ? addr !== activeAddress && !isImpacted && !blastRadiusInfo.impactedSet.has(addr)
                : !matchesSearch;

              // Check if node has blast radius count
              const blastRadiusEntry = report.impact_summary.resource_blast_radii.find(
                (r) => r.resource_address === addr
              );
              const impactedCount = blastRadiusEntry ? blastRadiusEntry.total_impacted_count : 0;

              return (
                <g
                  key={addr}
                  transform={`translate(${ln.x}, ${ln.y})`}
                  className={`graph-node-group ${isSelected ? 'selected' : ''} ${isRootChanged ? 'root-changed' : ''} ${isImpacted ? 'impacted' : ''} ${isDimmed ? 'dimmed' : ''}`}
                  onClick={() => onSelectNode(addr)}
                  onMouseEnter={() => setHoveredNodeAddress(addr)}
                  onMouseLeave={() => setHoveredNodeAddress(null)}
                >
                  {/* Card Background */}
                  <rect
                    width={ln.width}
                    height={ln.height}
                    className="graph-node-bg"
                    style={{
                      borderColor: actionColor,
                      stroke: isSelected ? '#6366f1' : isRootChanged ? actionColor : undefined,
                    }}
                  />

                  {/* Left accent bar indicating lifecycle action */}
                  <rect
                    x="0"
                    y="0"
                    width="4"
                    height={ln.height}
                    rx="2"
                    fill={actionColor}
                  />

                  {/* Action Badge & Type */}
                  <text x="14" y="24" fill={actionColor} fontSize="10" fontWeight="700" fontFamily="var(--font-mono)">
                    {action.toUpperCase()}
                  </text>

                  <text x="75" y="24" fill="#94a3b8" fontSize="10" fontFamily="var(--font-mono)">
                    {ln.node.resource_type.length > 20
                      ? `${ln.node.resource_type.slice(0, 19)}…`
                      : ln.node.resource_type}
                  </text>

                  {/* Resource Canonical Address */}
                  <text
                    x="14"
                    y="46"
                    fill="#f8fafc"
                    fontSize="12"
                    fontWeight="600"
                    fontFamily="var(--font-sans)"
                  >
                    {addr.length > 26 ? `${addr.slice(0, 25)}…` : addr}
                  </text>

                  {/* Blast Impact Count Tag */}
                  {impactedCount > 0 && (
                    <g transform="translate(14, 54)">
                      <rect width="90" height="15" rx="3" fill="rgba(239, 68, 68, 0.18)" />
                      <text x="5" y="11" fill="#ef4444" fontSize="9" fontWeight="700">
                        ⚡ {impactedCount} impacted
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      {/* Legend */}
      <div className="graph-legend">
        <div className="legend-items">
          <span style={{ fontWeight: 600, color: '#f8fafc' }}>Actions:</span>
          <div className="legend-item">
            <span className="legend-color-dot" style={{ backgroundColor: '#10b981' }} />
            <span>Create</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-dot" style={{ backgroundColor: '#ef4444' }} />
            <span>Delete</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-dot" style={{ backgroundColor: '#f59e0b' }} />
            <span>Replace</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-dot" style={{ backgroundColor: '#3b82f6' }} />
            <span>Update</span>
          </div>
          <div className="legend-item">
            <span className="legend-color-dot" style={{ backgroundColor: '#64748b' }} />
            <span>No-op</span>
          </div>
        </div>

        <div className="legend-items">
          <span style={{ fontWeight: 600, color: '#f8fafc' }}>Edges:</span>
          <span style={{ color: '#cbd5e1' }}>Solid = Depends On</span>
          <span style={{ color: '#94a3b8' }}>Dashed = Expression Ref</span>
          <span style={{ color: '#ef4444' }}>Flowing = Blast Propagation</span>
        </div>
      </div>
    </div>
  );
};
