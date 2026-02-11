from contourwall_emulator import ContourWallEmulator
import argparse
import time
import random
import sys

try:
	import cv2 as cv
except ImportError:  # Allow running without cv2 input support.
	cv = None
try:
	import mediapipe as mp
except ImportError:
	mp = None

from game_input import PhysicalMotionController, normalize_key
from score_display import draw_score


class PoseController:
	def __init__(self, camera_index=0, show_window=False):
		self.show_window = show_window
		if cv is None or mp is None or not hasattr(mp, "solutions"):
			raise RuntimeError("MediaPipe Pose is unavailable.")
		if sys.platform.startswith("win"):
			self.cap = cv.VideoCapture(camera_index, cv.CAP_DSHOW)
		else:
			self.cap = cv.VideoCapture(camera_index)
		if not self.cap.isOpened():
			raise RuntimeError("Camera failed to open.")
		self.cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
		self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
		self.pose = mp.solutions.pose.Pose(
			static_image_mode=False,
			model_complexity=1,
			min_detection_confidence=0.3,
			min_tracking_confidence=0.3,
		)

	def read_key(self):
		if not self.show_window or cv is None:
			return -1
		return normalize_key(cv.waitKey(1))

	def read_target_col(self, cols):
		ret, frame = self.cap.read()
		if not ret:
			return None
		frame = cv.flip(frame, 1)
		rgb = cv.cvtColor(frame, cv.COLOR_BGR2RGB)
		results = self.pose.process(rgb)
		if self.show_window:
			cv.imshow("Camera", frame)
		if not results.pose_landmarks:
			return None

		lm = results.pose_landmarks.landmark
		xs = [
			lm[mp.solutions.pose.PoseLandmark.LEFT_SHOULDER].x,
			lm[mp.solutions.pose.PoseLandmark.RIGHT_SHOULDER].x,
			lm[mp.solutions.pose.PoseLandmark.LEFT_HIP].x,
			lm[mp.solutions.pose.PoseLandmark.RIGHT_HIP].x,
		]
		avg_x = sum(xs) / len(xs)
		return int(max(0, min(cols - 1, round(avg_x * (cols - 1)))))

	def close(self):
		if self.cap is not None:
			self.cap.release()
		if self.pose is not None:
			self.pose.close()
		if self.show_window and cv is not None:
			cv.destroyAllWindows()


def read_key():
	if cv is None:
		return -1
	return cv.waitKey(1) & 0xFF


def hole_runner(motion_controller=None):
	rows, cols = cw.pixels.shape[:2]
	player_row = rows - 2
	player_col = cols // 2
	player_col_float = float(player_col)
	player_color = (0, 255, 255)

	hole_width = max(2, cols // 6)
	line_row = 0
	hole_start = random.randint(0, cols - hole_width)

	line_interval = 0.08
	last_line = time.time()
	last_tick = time.time()
	last_move_time = 0.0
	last_move_key = None
	move_repeat_delay = 0.12
	move_repeat_interval = 0.05

	score = 0
	if motion_controller is None:
		print("Hole runner controls: A/D or Left/Right arrows. Press Q to quit.")
	else:
		print("Hole runner camera mode: move left/right. Press Q to quit.")

	while True:
		now = time.time()
		if now - last_tick < 0.02:
			time.sleep(0.002)
			continue
		last_tick = now

		key = read_key() if motion_controller is None else normalize_key(motion_controller.read_key())
		if key in (ord('q'), 27):
			break

		if motion_controller is None:
			move_key = None
			if key in (ord('a'), 81):
				move_key = 'left'
			elif key in (ord('d'), 83):
				move_key = 'right'

			if move_key is not None:
				if move_key != last_move_key:
					last_move_key = move_key
					last_move_time = now
					if move_key == 'left':
						player_col = max(0, player_col - 1)
					else:
						player_col = min(cols - 1, player_col + 1)
				else:
					elapsed = now - last_move_time
					if elapsed >= move_repeat_delay or elapsed >= move_repeat_interval:
						if move_key == 'left':
							player_col = max(0, player_col - 1)
							last_move_time = now
						else:
							player_col = min(cols - 1, player_col + 1)
							last_move_time = now
			else:
				last_move_key = None
		else:
			physical_col = motion_controller.read_target_col(cols)
			if physical_col is not None:
				target = float(max(0, min(cols - 1, physical_col)))
				player_col_float = (0.8 * player_col_float) + (0.2 * target)
				player_col = int(max(0, min(cols - 1, round(player_col_float))))

		if now - last_line >= line_interval:
			last_line = now
			line_row += 1

			if line_row >= player_row:
				if hole_start <= player_col < hole_start + hole_width:
					score += 1
					line_interval = max(0.02, line_interval - 0.005)  # Speed up slightly
					line_row = 0
					hole_start = random.randint(0, cols - hole_width)
				else:
					break

		cw.pixels[:] = 0, 0, 0
		
		# Draw score at top left
		draw_score(cw.pixels, score, start_row=0, position='center')
		
		if 0 <= line_row < rows:
			cw.pixels[line_row, :] = 255, 255, 255
			cw.pixels[line_row, hole_start:hole_start + hole_width] = 0, 0, 0

		cw.pixels[player_row, player_col] = player_color
		cw.show()

	print(f"Game over. Score: {score}")


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description="Hole runner for ContourWallEmulator.")
	parser.add_argument(
		"--physical",
		action="store_true",
		help="Use webcam motion as player input.",
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

	cw = ContourWallEmulator()
	cw.new()

	motion_controller = None
	if args.physical:
		try:
			motion_controller = PoseController(
				camera_index=args.camera_index,
				show_window=args.show_camera,
			)
		except RuntimeError as exc:
			print(f"[INPUT WARN] {exc}")
			print("[INPUT WARN] Falling back to motion input.")
			try:
				motion_controller = PhysicalMotionController(
					camera_index=args.camera_index,
					show_window=args.show_camera,
				)
			except RuntimeError as inner_exc:
				print(f"[INPUT WARN] {inner_exc}")
				print("[INPUT WARN] Falling back to keyboard input.")

	try:
		hole_runner(motion_controller=motion_controller)
	finally:
		if motion_controller is not None:
			motion_controller.close()
		time.sleep(1)
		cw.pixels[:] = 0, 0, 0
		cw.show()
