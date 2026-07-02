#This is the file you have to edit and submit in the end

import numpy as np
from collections import deque
from world import MOVES, FREE, WALL, scan_to_cells


class Navigator:
    def __init__(self, shape, start, goal):
        self.shape = shape
        self.goal = goal
        self.start = start
        self.known = {}
        self.steps_taken = 0
        self.path_to_target = []
        
    def get_path(self, start, target_cells, allow_unknown=False):
        """BFS/Dijkstra to find the shortest path from start to any cell in target_cells.
        If allow_unknown is True, we can traverse UNKNOWN cells (treating them as traversable, but prioritizing FREE).
        To implement this cleanly, we can use a simple BFS where FREE cells are expanded first, 
        or a Dijkstra/deque where we append FREE cells to the left and UNKNOWN cells to the right.
        """
        target_set = set(target_cells)
        if start in target_set:
            return [start]
            
        # We will use Dijkstra-like search with a deque (0-1 BFS style: 0 cost for FREE, 1 cost for UNKNOWN)
        # Or simpler: store (cost, path) in a priority queue.
        import heapq
        pq = [(0, [start])]
        visited = {start: 0}
        
        while pq:
            cost, path = heapq.heappop(pq)
            r, c = path[-1]
            
            if (r, c) in target_set:
                return path
                
            for move_name, (dr, dc) in MOVES.items():
                nr, nc = r + dr, c + dc
                if 0 <= nr < self.shape[0] and 0 <= nc < self.shape[1]:
                    cell_val = self.known.get((nr, nc))
                    if cell_val == WALL:
                        continue
                    
                    # Cost calculation: 1 for FREE, 1000 for UNKNOWN
                    step_cost = 1
                    if cell_val is None:
                        if not allow_unknown:
                            continue
                        step_cost = 1000
                        
                    new_cost = cost + step_cost
                    if nr_nc := (nr, nc):
                        if nr_nc not in visited or new_cost < visited[nr_nc]:
                            visited[nr_nc] = new_cost
                            heapq.heappush(pq, (new_cost, path + [nr_nc]))
        return None

    def act(self, obs):
        # 1. Update map
        free, occ = scan_to_cells(obs["pose"], obs["scan"])
        for c in occ:
            self.known[c] = WALL
        for c in free:
            self.known[c] = FREE

        self.steps_taken += 1
        pose = obs["pose"]
        goal = obs["goal"]

        # If we have a planned path and it is still valid, follow it
        if self.path_to_target and len(self.path_to_target) > 1 and self.path_to_target[0] == pose:
            next_cell = self.path_to_target[1]
            if self.known.get(next_cell) != WALL:
                self.path_to_target.pop(0)
                dr, dc = next_cell[0] - pose[0], next_cell[1] - pose[1]
                for move_name, (mdr, mdc) in MOVES.items():
                    if mdr == dr and mdc == dc:
                        return move_name

        # Plan new path
        # 2. Get shortest path to goal using ONLY known free cells
        goal_path_free_only = self.get_path(pose, [goal], allow_unknown=False)
        
        # 3. Find frontiers (FREE cells that touch at least one UNKNOWN cell)
        reachable_free = set()
        frontiers = []
        
        q = deque([pose])
        visited = {pose}
        while q:
            curr = q.popleft()
            reachable_free.add(curr)
            
            has_unobserved = False
            for dr, dc in MOVES.values():
                nr, nc = curr[0] + dr, curr[1] + dc
                if 0 <= nr < self.shape[0] and 0 <= nc < self.shape[1]:
                    if (nr, nc) not in self.known:
                        has_unobserved = True
                    elif self.known[(nr, nc)] == FREE and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        q.append((nr, nc))
            if has_unobserved:
                frontiers.append(curr)

        # Decide action based on remaining budget and known space
        # High-success priority: switch to goal early enough.
        # If we can reach the goal via known FREE space, and we've done a reasonable amount of exploration,
        # or we are running out of steps, head to goal.
        known_free_count = sum(1 for c, v in self.known.items() if v == FREE)
        
        # Determine if we should go directly to the goal
        # 1. If we are running out of steps (steps > 450)
        # 2. If we have explored a significant portion of the map (known_free_count > 850)
        # 3. If there are no frontiers left
        should_go_to_goal = False
        if self.steps_taken > 450 or known_free_count > 850 or not frontiers:
            should_go_to_goal = True

        if should_go_to_goal:
            if goal_path_free_only:
                self.path_to_target = goal_path_free_only
            else:
                # If no clean free path exists, allow pathfinding through unknown cells
                goal_path_hybrid = self.get_path(pose, [goal], allow_unknown=True)
                if goal_path_hybrid:
                    self.path_to_target = goal_path_hybrid
        else:
            # Exploration mode: target the closest frontier
            best_path = None
            best_dist = float('inf')
            
            for f in frontiers:
                path = self.get_path(pose, [f], allow_unknown=False)
                if path and len(path) < best_dist:
                    best_dist = len(path)
                    best_path = path
            
            if best_path and len(best_path) > 1:
                self.path_to_target = best_path
            elif goal_path_free_only:
                self.path_to_target = goal_path_free_only
            else:
                goal_path_hybrid = self.get_path(pose, [goal], allow_unknown=True)
                if goal_path_hybrid:
                    self.path_to_target = goal_path_hybrid

        # Determine move from planned path
        if self.path_to_target and len(self.path_to_target) > 1 and self.path_to_target[0] == pose:
            next_cell = self.path_to_target[1]
            self.path_to_target.pop(0)
            dr, dc = next_cell[0] - pose[0], next_cell[1] - pose[1]
            for name, (mdr, mdc) in MOVES.items():
                if mdr == dr and mdc == dc:
                    return name

        # Backup: just move closer to the goal
        options = []
        for name, (dr, dc) in MOVES.items():
            nr, nc = pose[0] + dr, pose[1] + dc
            if 0 <= nr < self.shape[0] and 0 <= nc < self.shape[1]:
                if self.known.get((nr, nc)) != WALL:
                    options.append((abs(nr - goal[0]) + abs(nc - goal[1]), name))
        if options:
            options.sort()
            return options[0][1]
            
        return np.random.choice(list(MOVES))




