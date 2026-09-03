"""Tests for map generation and core level invariants."""

import random
import unittest

from game import COLS, GOAL_CELL, ROWS, START_CELL, generate_maze, has_path


class MazeGenerationTests(unittest.TestCase):
    def test_generated_levels_are_solvable(self) -> None:
        for level in range(1, 4):
            for seed in range(30):
                world = generate_maze(level, random.Random(seed))
                self.assertTrue(has_path(world), f"level={level}, seed={seed}")

    def test_boundaries_are_walls(self) -> None:
        world = generate_maze(3, random.Random(7))
        self.assertTrue(all(tile == 1 for tile in world[0]))
        self.assertTrue(all(tile == 1 for tile in world[-1]))
        self.assertTrue(all(row[0] == 1 and row[-1] == 1 for row in world))

    def test_start_and_goal_are_open(self) -> None:
        world = generate_maze(2, random.Random(11))
        self.assertEqual(world[START_CELL[1]][START_CELL[0]], 0)
        self.assertEqual(world[GOAL_CELL[1]][GOAL_CELL[0]], 0)
        self.assertEqual(len(world), ROWS)
        self.assertTrue(all(len(row) == COLS for row in world))


if __name__ == "__main__":
    unittest.main()
