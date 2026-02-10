from __future__ import annotations

import sys
from dataclasses import dataclass

import cv2 as cv
import numpy as np

LEFT_KEYS = {81}
RIGHT_KEYS = {83}
UP_KEYS = {82}
DOWN_KEYS = {84}


def normalize_key(key: int) -> int:
    if key is None:
        return -1
    return int(key) & 0xFF


@dataclass
class PhysicalMotionController:
    camera_index: int = 0
    show_window: bool = False

    def __post_init__(self) -> None:
        if sys.platform.startswith("win"):
            self.cap = cv.VideoCapture(self.camera_index, cv.CAP_DSHOW)
        else:
            self.cap = cv.VideoCapture(self.camera_index)
        if not self.cap.isOpened():
            raise RuntimeError("Camera failed to open.")
        self.cap.set(cv.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv.CAP_PROP_FRAME_HEIGHT, 480)
        self.prev_gray: np.ndarray | None = None
        self.last_key = -1

    def read_key(self) -> int:
        if self.show_window:
            return normalize_key(cv.waitKey(1))
        return -1

    def read_target_col(self, cols: int) -> int | None:
        ret, frame = self.cap.read()
        if not ret:
            return None
        frame = cv.flip(frame, 1)
        gray = cv.cvtColor(frame, cv.COLOR_BGR2GRAY)
        gray = cv.GaussianBlur(gray, (7, 7), 0)

        if self.prev_gray is None:
            self.prev_gray = gray
            if self.show_window:
                cv.imshow("Motion", frame)
            return None

        diff = cv.absdiff(self.prev_gray, gray)
        _, thresh = cv.threshold(diff, 25, 255, cv.THRESH_BINARY)
        thresh = cv.dilate(thresh, None, iterations=2)
        self.prev_gray = gray

        contours, _ = cv.findContours(thresh, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE)
        if not contours:
            if self.show_window:
                cv.imshow("Motion", frame)
            return None

        largest = max(contours, key=cv.contourArea)
        if cv.contourArea(largest) < 500:
            if self.show_window:
                cv.imshow("Motion", frame)
            return None

        moments = cv.moments(largest)
        if moments["m00"] == 0:
            if self.show_window:
                cv.imshow("Motion", frame)
            return None

        cx = int(moments["m10"] / moments["m00"])
        if self.show_window:
            cv.circle(frame, (cx, frame.shape[0] // 2), 12, (0, 255, 255), 2)
            cv.imshow("Motion", frame)
        return int(np.clip(round(cx / max(1, frame.shape[1] - 1) * (cols - 1)), 0, cols - 1))

    def close(self) -> None:
        if self.cap is not None:
            self.cap.release()
        if self.show_window:
            cv.destroyAllWindows()
