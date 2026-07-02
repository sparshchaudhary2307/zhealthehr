import unittest
import numpy as np
from collections import deque
from world import World, MOVES, FREE, WALL
from navigator import Navigator

class TestNavigatorEdgeCases(unittest.TestCase):
    def setUp(self):
        # Create a basic 10x10 mock world layout
        self.shape = (10, 10)
        self.start = (1, 1)
        self.goal = (8, 8)
        self.nav = Navigator(self.shape, self.start, self.goal)

    def mock_lidar_scan(self, pose, visible_free, visible_walls):
        # Generate a mock observation scan
        # We'll just construct what Navigator.act expects: obs["pose"], obs["goal"], obs["scan"]
        # In navigator.py, scan_to_cells is imported from world.
        # Let's mock a scan that results in the given free and occupied cells when scan_to_cells is called.
        # But wait! Instead of generating actual raw scans, we can simply mock scan_to_cells in the test.
        pass

    def test_unknown_goal_hybrid_pathfinding(self):
        """Test if the navigator successfully plans path through unknown cells when no clean known-free path exists."""
        self.nav.known[(1, 1)] = FREE
        self.nav.known[(2, 2)] = WALL # obstacle
        
        # Target goal is at (8,8). No known free path exists.
        # The hybrid planner should route through unknown cells (since they are not marked WALL).
        path = self.nav.get_path((1, 1), [(8, 8)], allow_unknown=True)
        self.assertIsNotNone(path)
        self.assertEqual(path[0], (1, 1))
        self.assertEqual(path[-1], (8, 8))
        # Ensure it does not route through the known wall at (2,2)
        self.assertNotIn((2, 2), path)

    def test_known_wall_blocking_bfs(self):
        """Test that the pathfinder never routes through a known WALL."""
        # Walled off completely. (2,2) is surrounded by WALL.
        self.nav.known[(1, 2)] = WALL
        self.nav.known[(3, 2)] = WALL
        self.nav.known[(2, 1)] = WALL
        self.nav.known[(2, 3)] = WALL
        # Diagonals as well if 4-connectivity is used (MOVES is 4-connected, but let's check)
        
        path = self.nav.get_path((2, 2), [(8, 8)], allow_unknown=True)
        self.assertIsNone(path, "Path should be None as the node is fully walled off.")

    def test_out_of_bounds_protection(self):
        """Test that pathfinding doesn't search outside the shape boundaries."""
        # Top-left cell (0,0)
        self.nav.known[(0, 0)] = FREE
        path = self.nav.get_path((0, 0), [(-1, 0)], allow_unknown=True)
        self.assertIsNone(path, "Should not return a path out of bounds.")

    def test_act_fallback(self):
        """Test that act() always returns a valid action even in complex configurations."""
        # Create a mock obs
        # scan values that cast out
        angles = np.linspace(0, 2*np.pi, 60, endpoint=False).tolist()
        scan = {
            "angles": angles,
            "ranges": [1.0] * 60,
            "hit": [True] * 60,
            "max_range": 6.0
        }
        obs = {
            "pose": (1, 1),
            "goal": (8, 8),
            "scan": scan
        }
        
        action = self.nav.act(obs)
        self.assertIn(action, MOVES)

if __name__ == '__main__':
    unittest.main()
