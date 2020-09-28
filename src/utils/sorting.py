from collections import deque


def dependency_sort(initial, dependencies):
    """
    Generic dependency sorting algorithm. Takes initial nodes, and a
    callable that returns a list of dependencies of a node given a node,
    and returns a list of the node and its dependencies from most depended
    (depends on nothing) to the node passed in (depends on everything else)
    """
    deps = list(initial)
    pending = deque(initial)
    mapping = {}
    while pending:
        current = pending.popleft()
        mapping[current] = [x for x in dependencies(current) if x is not None]
        for dep in mapping[current]:
            if dep not in pending and dep not in mapping:
                pending.append(dep)
    # Now roll through building a sorted list
    result = []
    while mapping:
        len_before = len(mapping)
        for node, deps in sorted(mapping.items()):
            if not deps or all((dep in result) for dep in deps):
                result.append(node)
                del mapping[node]
        if len(mapping) == len_before:
            raise ValueError("Circular dependency detected between: %s" % mapping.keys())
    return result
