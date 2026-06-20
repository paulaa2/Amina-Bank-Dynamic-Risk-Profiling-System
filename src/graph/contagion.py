"""Directed, weighted topological risk contagion.

Risk propagates asymmetrically along corporate-control edges: a sanctioned or
adverse director (or majority owner) contaminates the company they control, but
a subsidiary does not contaminate its parent. This directionality is what lets
the engine detect "ownership / beneficial-owner" KYC drift without flagging
every loosely associated entity.

Edge control weights mirror the technical specification::

    DIRECTS, OWNS_MAJORITY (>= 25%) -> W = 1.0  (full contagion)
    LOCATED_AT, OWNS_MINORITY (< 25%) -> W = 0.1 (attenuated)
"""

from __future__ import annotations

import networkx as nx

CONTROL_RELATIONS = {"DIRECTS", "OWNS_MAJORITY"}


class ComplianceDirectedGraph:
    """Wraps a :class:`networkx.DiGraph` of the client's control structure."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    def add_node(
        self,
        node_id: str,
        label: str,
        node_type: str,
        intrinsic_risk: float = 0.0,
    ) -> None:
        """Insert or update a node in the control graph."""
        self.graph.add_node(
            node_id, label=label, type=node_type, intrinsic_risk=intrinsic_risk
        )

    def add_edge(
        self,
        source: str,
        target: str,
        rel_type: str,
        control_weight: float = 1.0,
    ) -> None:
        """Add a directed control edge ``source -> target``."""
        self.graph.add_edge(source, target, type=rel_type, weight=control_weight)

    def set_intrinsic_risk(self, node_id: str, risk: float) -> None:
        """Update the intrinsic risk of an existing node."""
        if node_id in self.graph.nodes:
            self.graph.nodes[node_id]["intrinsic_risk"] = float(risk)

    def propagate_directed_contagion(
        self, beta: float = 0.5, activation_threshold: float = 0.5
    ) -> dict[str, float]:
        """Propagate risk one hop downstream along control edges.

        A node only emits contagion when its intrinsic risk exceeds
        ``activation_threshold``. The transferred risk is
        ``intrinsic_risk * beta * edge_weight`` and is capped at 1.0 per node.
        """
        contagion: dict[str, float] = {node: 0.0 for node in self.graph.nodes}

        for u in self.graph.nodes:
            u_risk = self.graph.nodes[u].get("intrinsic_risk", 0.0)
            if u_risk <= activation_threshold:
                continue
            for v in self.graph.successors(u):
                edge = self.graph.get_edge_data(u, v) or {}
                rel_type = edge.get("type", "UNKNOWN")
                edge_weight = 1.0 if rel_type in CONTROL_RELATIONS else 0.1
                impact = u_risk * beta * edge_weight
                contagion[v] = min(1.0, contagion[v] + impact)

        return contagion

    def exposure_of(self, node_id: str, beta: float = 0.5) -> float:
        """Convenience accessor for a single node's contagion exposure."""
        return self.propagate_directed_contagion(beta=beta).get(node_id, 0.0)

    def top_risk_contributors(self, target: str, beta: float = 0.5) -> list[dict]:
        """List upstream nodes contributing risk to ``target``, descending.

        Used for explainability: it answers "which director / owner is driving
        the company's exposure?".
        """
        contributors: list[dict] = []
        for u in self.graph.predecessors(target):
            u_risk = self.graph.nodes[u].get("intrinsic_risk", 0.0)
            if u_risk <= 0.0:
                continue
            edge = self.graph.get_edge_data(u, target) or {}
            rel_type = edge.get("type", "UNKNOWN")
            edge_weight = 1.0 if rel_type in CONTROL_RELATIONS else 0.1
            contributors.append(
                {
                    "node_id": u,
                    "label": self.graph.nodes[u].get("label", u),
                    "type": self.graph.nodes[u].get("type", "UNKNOWN"),
                    "rel_type": rel_type,
                    "intrinsic_risk": u_risk,
                    "contributed": min(1.0, u_risk * beta * edge_weight),
                }
            )
        contributors.sort(key=lambda c: c["contributed"], reverse=True)
        return contributors

    def check_ownership_cycles(self, target: str, max_len: int = 5) -> bool:
        """Detect short circular-ownership loops involving ``target``.

        Circular ownership is a classic layering / opacity signal.
        """
        for cycle in nx.simple_cycles(self.graph):
            if target in cycle and len(cycle) <= max_len:
                return True
        return False
