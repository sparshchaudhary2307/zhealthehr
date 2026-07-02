# Robot LLM - Lidar-Based Navigation Writeup

This document explains the design, algorithms, and tradeoffs selected for the Mapless Lidar Navigation project.

## 1. Route Planning & Movement Logic
Instead of a simple greedy heuristic (like the Euclidean distance baseline which gets trapped easily in local minima), we implemented a graph-search-based navigation framework:
- **Dijkstra/A* Path Planner**: We plan paths from the robot's current pose using a priority-queue-based shortest path algorithm over the grid map (`self.known`).
- **Hybrid Pathfinding (Success Guarantee)**: If a clean path over known `FREE` cells does not exist (or when we are exploring unexplored terrain), the planner routes through `FREE` cells with cost `1` and `UNKNOWN` cells with cost `1000`. This allows the robot to plan paths through unknown spaces to make progress toward the target without colliding with known walls.

## 2. Exploration vs. Exploitation Balance
To maximize the combined score (`0.65 * coverage + 0.35 * SPL` with 100% success rate):
- **Frontier Detection**: The robot performs a BFS starting at its pose to locate all reachable `FREE` cells that border at least one `UNKNOWN` (unobserved) cell. These cells represent the "frontiers" of the known world.
- **Dynamic Policy Switch**:
  - **Exploration phase**: For the first part of the run (step count $\le$ 450 and known free cells $\le$ 850), the robot targets the closest reachable frontier using the path planner. This leads to efficient map expansion.
  - **Exploitation phase**: Once the thresholds are crossed or no frontiers remain, the robot immediately plans a path directly to the goal.

## 3. Performance Results
- **Success Rate**: 100% (the robot successfully reached the goal on all test environments)
- **Mean Coverage**: 84%
- **Mean SPL**: 0.31
- **Mean Collisions**: 0.0
- **Combined Score**: 0.65 (a massive improvement from the 0.18 baseline)

## 4. Fails & Future Improvements
- **SPL Limitations**: The frontier-search algorithm prioritizes scanning the environment, which naturally leads to longer exploration paths (lower SPL). If we wanted to optimize SPL further, we could use a utility function that discounts frontier rewards based on their distance away from the direct goal vector.
