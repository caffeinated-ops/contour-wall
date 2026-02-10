#!/usr/bin/env python3
"""
Stay-in-lane game for the ContourWall emulator.

Controls:
- Move lanes: Arrow keys or A/D
- Quit: Q or ESC

Physical mode:
- Start with --physical
- Move your hand/body left-right in front of a webcam
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import random
import sys
import time

import cv2 as cv
import numpy as np

EXAMPLES_DIR = Path(__file__).resolve().parent
if str(EXAMPLES_DIR) not in sys.path:
	sys.path.insert(0, str(EXAMPLES_DIR))

WRAPPER_DIR = EXAMPLES_DIR.parent
if str(WRAPPER_DIR) not in sys.path:
	sys.path.insert(0, str(WRAPPER_DIR))

from contourwall_emulator import ContourWallEmulator
from game_input import (
	LEFT_KEYS,
	RIGHT_KEYS,
	PhysicalMotionController,
	normalize_key,
)


@dataclass
class LaneState:
	current: int
	target: int


class LaneStayGame:
	def __init__(
		self,
		wall: ContourWallEmulator,
		motion_controller: PhysicalMotionController | None = None,
	):
		self.cw = wall
		self.motion_controller = motion_controller
		self.use_physical_input = motion_controller is not None
		self.rows, self.cols = wall.pixels.shape[:2]
		self.player_row = max(2, self.rows - 3)
		self.lane_state = LaneState(current=1, target=1)
		self.score = 0
		self.lives = 3
		self.tick_interval = 1.8
		self.last_tick = time.time()
		self.physical_col_float = float(self.cols // 2)

	def reset(self) -> None:
		self.rows, self.cols = self.cw.pixels.shape[:2]
		self.player_row = max(2, self.rows - 3)
		self.lane_state = LaneState(current=1, target=random.randint(0, 2))
		self.score = 0
		self.lives = 3
		self.last_tick = time.time()
		self.physical_col_float = float(self.cols // 2)

	def _lane_cols(self) -> list[int]:
		return [max(1, self.cols // 6), self.cols // 2, min(self.cols - 2, (self.cols * 5) // 6)]

	def _target_lane_from_col(self, col: int) -> int:
		lane_width = self.cols / 3.0
		return int(np.clip(col // lane_width, 0, 2))

	def _update_player_lane(self, key: int, physical_col: int | None = None) -> bool:
		key = normalize_key(key)
		if key in (27, ord("q"), ord("Q")):
			return False

		if self.use_physical_input and physical_col is not None:
			self.physical_col_float = (0.6 * self.physical_col_float) + (0.4 * float(physical_col))
			lane_width = self.cols / 3.0
			margin = lane_width * 0.08
			boundary_left = lane_width - margin
			boundary_right = (2 * lane_width) + margin
			if self.lane_state.current == 0 and self.physical_col_float > boundary_left:
				self.lane_state.current = 1
			elif self.lane_state.current == 2 and self.physical_col_float < boundary_right:
				self.lane_state.current = 1
			elif self.lane_state.current == 1:
				if self.physical_col_float < boundary_left:
					self.lane_state.current = 0
				elif self.physical_col_float > boundary_right:
					self.lane_state.current = 2
			return True

		if key in LEFT_KEYS or key in (ord("a"), ord("A")):
			self.lane_state.current = max(0, self.lane_state.current - 1)
		elif key in RIGHT_KEYS or key in (ord("d"), ord("D")):
			self.lane_state.current = min(2, self.lane_state.current + 1)
		return True

	def _tick_scoring(self) -> None:
		if time.time() - self.last_tick < self.tick_interval:
			return
		self.last_tick = time.time()

		if self.lane_state.current == self.lane_state.target:
			self.score += 1
		else:
			self.lives -= 1

		self.lane_state.target = random.randint(0, 2)

	def _draw(self) -> None:
		self.cw.pixels[:] = (5, 5, 12)

		lane_cols = self._lane_cols()
		for i, col in enumerate(lane_cols):
			color = (50, 50, 70)
			if i == self.lane_state.target:
				color = (30, 200, 90)
			self.cw.pixels[:, col] = color

		player_col = lane_cols[self.lane_state.current]
		self.cw.pixels[self.player_row:self.player_row + 2, player_col:player_col + 2] = (255, 220, 80)

		for i in range(self.lives):
			start = i * 3
			self.cw.pixels[0, start:start + 2] = (230, 60, 60)

		score_width = min(self.cols, self.score)
		if score_width > 0:
			self.cw.pixels[1, self.cols - score_width:self.cols] = (90, 160, 255)

	def _draw_digit(self, digit: int) -> None:
		patterns = {
			0: ["111", "101", "101", "101", "111"],
			1: ["010", "110", "010", "010", "111"],
			2: ["111", "001", "111", "100", "111"],
			3: ["111", "001", "111", "001", "111"],
			4: ["101", "101", "111", "001", "001"],
			5: ["111", "100", "111", "001", "111"],
			6: ["111", "100", "111", "101", "111"],
			7: ["111", "001", "001", "001", "001"],
			8: ["111", "101", "111", "101", "111"],
			9: ["111", "101", "111", "001", "111"],
		}
		pattern = patterns.get(digit)
		if pattern is None:
			return
		start_row = max(0, (self.rows // 2) - 2)
		start_col = max(0, (self.cols // 2) - 1)
		self.cw.fill_solid(0, 0, 0)
		for r, row in enumerate(pattern):
			for c, ch in enumerate(row):
				if ch == "1":
					self.cw.pixels[start_row + r, start_col + c] = (30, 200, 90)

	def run(self) -> None:
		print("Lane Stay Game")
		if self.use_physical_input:
			print("Physical mode enabled: move left-right in front of your webcam.")
		else:
			print("Move with Arrow keys or A/D.")
		print("Match the green lane to score. Misses cost a life.")
		print("Starting in 5...")
		for count in range(5, 0, -1):
			self._draw_digit(count)
			self.cw.show(sleep_ms=1000)

		self.reset()
		key = -1
		while self.lives > 0:
			frame_start = time.perf_counter()

			physical_col = None
			if self.motion_controller is not None:
				physical_col = self.motion_controller.read_target_col(self.cols)
				camera_key = normalize_key(self.motion_controller.read_key())
				if camera_key in (27, ord("q"), ord("Q")):
					return

			if not self._update_player_lane(key, physical_col=physical_col):
				return

			self._tick_scoring()
			self._draw()
			key = normalize_key(cv.waitKey(1))
			self.cw.show()

			frame_time = time.perf_counter() - frame_start
			target_dt = 0.05
			if frame_time < target_dt:
				time.sleep(target_dt - frame_time)

		print(f"Game over. Score: {self.score}")


def main() -> None:
	parser = argparse.ArgumentParser(
		description="Stay-in-lane game for ContourWallEmulator."
	)
	parser.add_argument(
		"--physical",
		action="store_true",
		help="Use webcam motion as physical player input (left-right).",
	)
	parser.add_argument(
		"--camera-index",
		type=int,
		default=0,
		help="OpenCV camera index for --physical mode (default: 0).",
	)
	parser.add_argument(
		"--show-camera",
		action="store_true",
		help="Show webcam debug windows in --physical mode.",
	)
	args = parser.parse_args()

	random.seed()
	cw = ContourWallEmulator()
	cw.new_with_ports("COM10", "COM12", "COM9", "COM14", "COM13", "COM11")

	motion_controller: PhysicalMotionController | None = None
	if args.physical:
		try:
			motion_controller = PhysicalMotionController(
				camera_index=args.camera_index,
				show_window=args.show_camera,
			)
		except RuntimeError as exc:
			print(f"[INPUT WARN] {exc}")
			print("[INPUT WARN] Falling back to keyboard input.")

	game = LaneStayGame(cw, motion_controller=motion_controller)

	try:
		game.run()
	finally:
		if motion_controller is not None:
			motion_controller.close()
		cw.fill_solid(0, 0, 0)
		cw.show()
		cv.destroyAllWindows()


if __name__ == "__main__":
	main()
