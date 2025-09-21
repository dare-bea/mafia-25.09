from collections.abc import Iterable, Hashable
from typing import TypeVar
from collections import defaultdict

Node = TypeVar("Node", bound=Hashable)


def nodes_in_cycles(edges: Iterable[tuple[Node, Node]]) -> set[Node]:
    """Given an iterable of directed edges (u, v), return the set of nodes
    that belong to at least one directed cycle.

    Nodes can be any hashable type (int, str, ...).
    """
    # build adjacency and node set
    graph: dict = defaultdict(list)
    nodes: set = set()
    for u, v in edges:
        graph[u].append(v)
        nodes.add(u)
        nodes.add(v)

    index = 0
    indices: dict = {}
    lowlink: dict = {}
    stack: list[Node] = []
    onstack: set = set()
    sccs: list[list[Node]] = []

    def strongconnect(v):
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        onstack.add(v)

        for w in graph.get(v, ()):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in onstack:
                lowlink[v] = min(lowlink[v], indices[w])

        # root of SCC
        if lowlink[v] == indices[v]:
            scc = []
            while True:
                w = stack.pop()
                onstack.remove(w)
                scc.append(w)
                if w == v:
                    break
            sccs.append(scc)

    for v in nodes:
        if v not in indices:
            strongconnect(v)

    # nodes in cycles: any SCC with size>1, or size==1 with a self-loop.
    result = set()
    for scc in sccs:
        if len(scc) > 1:
            result.update(scc)
        else:
            u = scc[0]
            if u in graph and u in graph[u]:  # self-loop
                result.add(u)

    return result


if __name__ == "__main__":
    edges = [(1, 2), (2, 3), (3, 1), (3, 4), (5, 5), (6, 7)]
    print(nodes_in_cycles(edges))  # -> {1, 2, 3, 5}

    edges = [(1, 2), (2, 3), (3, 4), (4, 2)]
    print(nodes_in_cycles(edges))  # -> {2, 3, 4}

    edges = [(1, 2), (2, 3), (3, 1), (4, 5)]
    print(nodes_in_cycles(edges))  # -> {1, 2, 3}

    edges = [(1, 1), (2, 2), (3, 3)]
    print(nodes_in_cycles(edges))  # -> {1, 2, 3}

    edges = [(1, 2), (2, 1)]
    print(nodes_in_cycles(edges))  # -> {1, 2}

    edges = []
    print(nodes_in_cycles(edges))  # -> set()

    edges = [(1, 2), (2, 3), (3, 4)]
    print(nodes_in_cycles(edges))  # -> set()
