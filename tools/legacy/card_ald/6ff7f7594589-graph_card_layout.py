"""Deterministic NetworkX planning for the seven-row ALD character grid.

NetworkX supplies connectivity, feedback components and topological layers.
ALD-specific ordering keeps sibling gates together, places input terminations
under their gate and moves a shared input driver near its first consumer.
Wire geometry remains the responsibility of the orthogonal grid router.
"""
from collections import defaultdict
from statistics import mean


def _networkx():
    try:
        import networkx
    except ImportError as exc:
        raise RuntimeError('Graph layout needs NetworkX. Install tools/card_ald/requirements.txt with this Python interpreter.') from exc
    return networkx


def primary(node):
    parts = str(node.get('function', '')).lstrip('✲').split()
    return parts[0] if parts else '�'


def height(node):
    return max(7, len(node.get('_inputs', [])) + 2, len(node.get('_outputs', [])) + 2)


def inputs(node):
    return {p.get('pin') or p.get('ref') for p in node.get('_inputs', [])
            if p.get('pin') or p.get('ref')}


def inversion_count(graph, ranks, positions):
    """Ordering estimate only; the router reports actual grid crossings."""
    segments = defaultdict(list)
    for source, target in graph.edges:
        if ranks[source] < ranks[target]:
            segments[ranks[source], ranks[target]].append((positions[source], positions[target]))
    return sum((a[0]-b[0]) * (a[1]-b[1]) < 0 for edges in segments.values()
               for i,a in enumerate(edges) for b in edges[i+1:])


def plan(model):
    nx = _networkx()
    nodes = model['portions']
    graph = nx.DiGraph()
    graph.add_nodes_from(sorted(nodes))
    for edge in model['edges']:
        source, target = edge['source'], edge['target']
        if source == target:
            continue
        weight = max(1, len(edge.get('evidence', [])))
        if graph.has_edge(source, target):
            graph[source][target]['weight'] += weight
        else:
            graph.add_edge(source, target, weight=weight)
    original_components = [sorted(c) for c in nx.strongly_connected_components(graph) if len(c) > 1]
    # The complete electrical graph is retained. Only the placement DAG omits
    # feedback arcs, preferably a one-input output stage feeding a many-input
    # gate, rather than breaking the forward gate-to-collector path.
    dag = graph.copy()
    feedback = []
    while not nx.is_directed_acyclic_graph(dag):
        components = sorted((sorted(c) for c in nx.strongly_connected_components(dag) if len(c)>1),key=lambda c:c[0])
        component = set(components[0])
        candidates = []
        for source, target in dag.subgraph(component).edges:
            s, t = nodes[source], nodes[target]
            si, ti = len(s.get('_inputs', [])), len(t.get('_inputs', []))
            physically_driven = any(p.get('pin') for p in s.get('_outputs', []))
            feedback_score = (100 if physically_driven and si <= 1 and ti >= 2 else 0)
            feedback_score += (30 if ti > si else -30 if si > ti else 0)
            feedback_score += 10 if source > target else 0
            candidates.append((-feedback_score, dag[source][target]['weight'], source, target))
        _, _, source, target = min(candidates)
        dag.remove_edge(source, target)
        feedback.append((source, target))
    ranks = {p:0 for p in nodes}
    for generation in nx.topological_generations(dag):
        for p in sorted(generation):
            ranks[p] = max((ranks[q]+1 for q in dag.predecessors(p)), default=0)
    siblings = []
    for target in sorted(nodes):
        sources = sorted(p for p in dag.predecessors(target)
                         if primary(nodes[p]) in ['A','OR'] and len(nodes[p].get('_inputs',[])) >= 2)
        if len(sources) >= 2 and not any(nx.has_path(dag,a,b) or nx.has_path(dag,b,a)
                                        for i,a in enumerate(sources) for b in sources[i+1:]):
            siblings.append(sources)
    # A gate with no shared clock still stays beside the other inputs of its
    # collector. Repropagate depths after aligning those sibling sources.
    shifted_siblings = set()
    for _ in range(len(nodes)+1):
        changed = False
        for family in siblings:
            rank = max(ranks[p] for p in family)
            for p in family:
                if ranks[p] != rank:
                    ranks[p] = rank
                    shifted_siblings.add(p)
                    changed = True
        for p in nx.topological_sort(dag):
            required = max((ranks[q]+1 for q in dag.predecessors(p)), default=0)
            if required > ranks[p]:
                ranks[p] = required
                changed = True
        if not changed:
            break
    else:
        raise ValueError('Sibling grouping could not stabilize its dependency layers')
    anchors = {}
    for p in sorted(nodes):
        if primary(nodes[p]) != 'R' or nodes[p].get('_outputs'):
            continue
        shared = inputs(nodes[p])
        candidates = [(len(shared & inputs(nodes[q])), q) for q in nodes
                      if q != p and primary(nodes[q]) != 'R' and shared & inputs(nodes[q])]
        if candidates:
            _, anchor = min(candidates, key=lambda item:(-item[0],ranks[item[1]],item[1]))
            anchors[p] = anchor
            ranks[p] = ranks[anchor]
    union = nx.utils.UnionFind(nodes)
    for family in siblings:
        for p in family[1:]:
            union.union(family[0],p)
    for p, anchor in anchors.items():
        union.union(p,anchor)
    output_siblings = []
    for source in sorted(nodes):
        followers = sorted(p for p in dag.successors(source)
                           if primary(nodes[p]) in ['A','OR','AR']
                           and len(nodes[p].get('_inputs',[])) == 1)
        by_rank = defaultdict(list)
        for p in followers:by_rank[ranks[p]].append(p)
        for family in by_rank.values():
            if len(family)>1:
                output_siblings.append(family)
                for p in family[1:]:union.union(family[0],p)
    units = defaultdict(list)
    for p in sorted(nodes):
        units[union[p]].append(p)
    units = {min(members):members for members in units.values()}
    member_unit = {p:u for u,members in units.items() for p in members}
    layers = defaultdict(list)
    for u,members in sorted(units.items()):
        assert len({ranks[p] for p in members}) == 1
        layers[ranks[members[0]]].append(u)
    unit_orders = {rank:list(values) for rank,values in layers.items()}
    initial_positions = {p:i for rank,values in unit_orders.items() for i,u in enumerate(values) for p in units[u]}
    before = inversion_count(dag,ranks,initial_positions)
    best_orders = {rank:list(values) for rank,values in unit_orders.items()}
    best_score = before
    # Alternating barycentric sweeps reduce inter-layer inversions while each
    # sibling/termination unit remains contiguous.
    for sweep in range(12):
        down = sweep % 2 == 0
        sequence = sorted(unit_orders,reverse=not down)
        positions = {p:i for rank,values in unit_orders.items() for i,u in enumerate(values) for p in units[u]}
        for rank in sequence:
            scores = {}
            for old_index,u in enumerate(unit_orders[rank]):
                neighbor_positions = [positions[q] for p in units[u]
                                      for q in (dag.predecessors(p) if down else dag.successors(p))
                                      if member_unit[q] != u]
                scores[u] = (mean(neighbor_positions) if neighbor_positions else old_index,old_index,u)
            unit_orders[rank].sort(key=lambda u:scores[u])
            for index,u in enumerate(unit_orders[rank]):
                for p in units[u]:positions[p]=index
        score = inversion_count(dag,ranks,positions)
        if score <= best_score:
            best_score = score
            best_orders = {rank:list(values) for rank,values in unit_orders.items()}
    orders = {}
    for rank,values in best_orders.items():
        ordered = []
        for u in values:
            members = units[u]
            gates = [p for p in members if p not in anchors]
            # Port evidence order is stable and keeps terminators directly
            # under the gate; equivalent-input reordering happens at routing.
            for p in sorted(gates):
                ordered.append(p)
                ordered.extend(sorted(q for q in members if anchors.get(q)==p))
        orders[rank] = ordered
    tops = {}
    for rank,values in orders.items():
        row = 14
        for p in values:
            tops[p] = row
            row += ((height(nodes[p])+6)//7)*7
    offsets, starts, spans = {}, {}, {}
    for u,members in units.items():
        start = min(tops[p] for p in members)
        starts[u] = start
        for p in members:offsets[p]=tops[p]-start
        spans[u] = max(offsets[p]+((height(nodes[p])+6)//7)*7 for p in members)
    def vertical_cost():
        return sum(abs(tops[s]-tops[t]) for s,t in dag.edges)
    initial_vertical_cost = vertical_cost()
    best_tops, best_vertical_cost = dict(tops), initial_vertical_cost
    # Align collectors to the centre of their input group and buffers to the
    # collector, rather than stacking every layer independently at row14.
    # Whole sibling units move together, preserving exact R/gate adjacency.
    for sweep in range(8):
        down = sweep % 2 == 0
        for rank in sorted(best_orders,reverse=not down):
            cursor = 14
            for u in best_orders[rank]:
                demands = [tops[q]-offsets[p] for p in units[u]
                           for q in (dag.predecessors(p) if down else dag.successors(p))
                           if member_unit[q] != u]
                desired = round(mean(demands)/7)*7 if demands else starts[u]
                start = max(cursor,desired,14)
                starts[u] = start
                for p in units[u]:tops[p]=start+offsets[p]
                cursor = start+spans[u]
        cost = vertical_cost()
        if cost <= best_vertical_cost:
            best_tops,best_vertical_cost = dict(tops),cost
    tops = best_tops
    deferred = []
    for p in sorted(nodes,key=lambda p:(ranks[p],p)):
        if dag.in_degree(p) or not dag.out_degree(p) or len(units[member_unit[p]]) != 1:
            continue
        targets = list(dag.successors(p))
        desired = max(14, min(tops[q] for q in targets)-7)
        peers = [q for q in nodes if q != p and ranks[q] == ranks[p]]
        def free(row):
            return all(row+height(nodes[p]) <= tops[q] or tops[q]+height(nodes[q]) <= row for q in peers)
        limit = max(tops.values(),default=14) + 14
        available = [row for row in range(14,limit+1,7) if free(row)]
        if available:
            selected = min(available,key=lambda row:(abs(row-desired),row))
            if selected != tops[p]:
                deferred.append({'portion':p,'from':tops[p],'to':selected,'first_consumers':sorted(targets)})
                tops[p] = selected
    fanout = defaultdict(set)
    for p,node in nodes.items():
        for pin in node.get('_inputs',[]):
            if pin.get('pin'):fanout[pin['pin']].add(p)
    global_inputs = sum(len(consumers - set(anchors))>1 for consumers in fanout.values())
    first_bank_x = max(18,12+2*global_inputs)
    right_margin = max(18,12+2*len(feedback))
    centrality = nx.betweenness_centrality(dag,normalized=True)
    return {'algorithm':'networkx-layered-ald-v1','networkx_version':nx.__version__,
            'ranks':ranks,'order':{str(rank):values for rank,values in orders.items()},'tops':tops,
            'bank_interval':36,'first_bank_x':first_bank_x,'right_margin':right_margin,
            'node_priority':centrality,'routing_strategy':'centrality-first',
            'crossing_penalty':18,'bend_penalty':4,
            'metrics':{'graph_nodes':len(nodes),'graph_edges':graph.number_of_edges(),
                       'feedback_components':original_components,'feedback_edges':feedback,
                       'sibling_groups':siblings,'aligned_siblings':sorted(shifted_siblings),
                       'output_sibling_groups':output_siblings,
                       'termination_anchors':anchors,'deferred_input_drivers':deferred,
                       'estimated_order_crossings_before':before,'estimated_order_crossings_after':best_score,
                       'vertical_edge_span_before':initial_vertical_cost,'vertical_edge_span_after':best_vertical_cost}}
