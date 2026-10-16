import csv
import math
import pickle
import socket
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import cv2
import face_recognition
import numpy as np
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================
# Network Configuration
ESP32_CAM_URL = os.getenv('ESP32_CAM_URL', 'http://192.168.1.50/capture')
ESP32_LCD_IP = os.getenv('ESP32_LCD_IP', '192.168.1.100')
ESP32_LCD_PORT = int(os.getenv('ESP32_LCD_PORT', '12345'))

# Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BASE_DIR / 'feature_db'
PROOF_FOLDER = BASE_DIR / 'proof_images'
PROOF_FOLDER.mkdir(parents=True, exist_ok=True)

# Recognition Thresholds
FACE_MATCH_THRESHOLD = 0.45

# ==============================================================================
# ANONYMIZED STUDENT DATABASE
# ==============================================================================
STUDENT_DATABASE: Dict[str, str] = {
    "John Doe": "STU001",
    "Jane Smith": "STU002",
    "Alice Johnson": "STU003",
    "Bob Williams": "STU004",
    "Charlie Brown": "STU005",
    "Diana Prince": "STU006",
    "Evan Wright": "STU007",
    "Fiona Gallagher": "STU008",
    "George Clark": "STU009",
    "Hannah Abbott": "STU010",
    "Ian Malcolm": "STU011",
}

FULL_CLASS_ROSTER = list(STUDENT_DATABASE.keys())
HALF_CLASS_ROSTER = ["John Doe", "Jane Smith", "Alice Johnson", "Bob Williams", "Charlie Brown"]

# ==============================================================================
# CLASS SCHEDULE CONFIGURATION
# ==============================================================================
CLASS_SCHEDULES: List[dict] = [
    {
        "course": "Embedded Systems + Lab",
        "filename": "Attendance_EmbeddedSystems.csv",
        "start": "11:00",
        "end": "11:30",
        "attendees": FULL_CLASS_ROSTER,
    },
    {
        "course": "Data Acquisition + Lab",
        "filename": "Attendance_DataAcquisition.csv",
        "start": "14:00",
        "end": "23:59",
        "attendees": HALF_CLASS_ROSTER,
    },
]


def compute_face_confidence(face_distance: float, threshold: float = 0.45) -> str:
    """Calculates percentage confidence from face distance metrics."""
    range_val = 1.0 - threshold
    linear_val = (1.0 - face_distance) / (range_val * 2.0)

    if face_distance > threshold:
        return f"{round(linear_val * 100, 2)}%"

    value = (linear_val + ((1.0 - linear_val) * math.pow((linear_val - 0.5) * 2, 0.2))) * 100
    return f"{round(value, 2)}%"


def get_active_schedule() -> Optional[dict]:
    """Evaluates system time against defined course schedules."""
    now = datetime.now().time()
    for schedule in CLASS_SCHEDULES:
        try:
            start_time = datetime.strptime(schedule["start"], "%H:%M").time()
            end_time = datetime.strptime(schedule["end"], "%H:%M").time()
            if start_time <= now <= end_time:
                return schedule
        except ValueError:
            print(f"[ERROR] Invalid time format in course schedule: {schedule['course']}")
    return None


class FaceRecognitionESP32:
    """Core pipeline for video capture, face recognition, and attendance logging."""

    def __init__(self) -> None:
        self.face_locations: List[Tuple[int, int, int, int]] = []
        self.face_encodings: List[np.ndarray] = []
        self.face_names: List[str] = []
        self.known_face_encodings: List[np.ndarray] = []
        self.known_face_names: List[str] = []
        self.process_current_frame = True
        self.session_attendance_cache: set = set()

        self.initialize_attendance_files()
        self.load_feature_database()

    def initialize_attendance_files(self) -> None:
        """Pre-populates CSV attendance files with headers and registered rosters."""
        print("[INFO] Verifying attendance storage files...")
        for schedule in CLASS_SCHEDULES:
            file_path = BASE_DIR / schedule["filename"]
            course_name = schedule["course"]
            attendees = schedule["attendees"]

            if not file_path.exists():
                print(f"[INIT] Creating attendance file: {file_path.name}")
                try:
                    with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        writer.writerow(["NO", "NAME", "STUDENT_ID", "COURSE", "TIMESTAMP"])
                        for index, name in enumerate(attendees, start=1):
                            student_id = STUDENT_DATABASE.get(name, "-")
                            writer.writerow([index, name, student_id, course_name, "-"])
                    print(f"[SUCCESS] Initialized {file_path.name} ({len(attendees)} enrolled)")
                except IOError as e:
                    print(f"[ERROR] Failed to write file {file_path.name}: {e}")

    def load_feature_database(self) -> None:
        """Loads serialized face encodings from the feature database directory."""
        if not DATABASE_PATH.exists():
            print(f"[ERROR] Feature database directory missing: {DATABASE_PATH}")
            sys.exit(1)

        print("[INFO] Loading facial feature encodings...")
        files_loaded = 0
        for pickle_file in DATABASE_PATH.glob("*.pickle"):
            try:
                with open(pickle_file, "rb") as f:
                    data = pickle.load(f)
                self.known_face_encodings.extend(data["encodings"])
                self.known_face_names.extend(data["names"])
                files_loaded += 1
            except (pickle.UnpicklingError, IOError) as e:
                print(f"[ERROR] Failed to unpickle {pickle_file.name}: {e}")

        if files_loaded == 0:
            print("[ERROR] Feature database is empty. Run face_encoder.py first.")
            sys.exit(1)

        print(f"[INFO] Successfully loaded {len(self.known_face_encodings)} face encodings.")

    def record_attendance(self, name: str, student_id: str, schedule: dict) -> Tuple[bool, str]:
        """Updates attendance timestamp in the corresponding CSV roster."""
        file_path = BASE_DIR / schedule["filename"]
        course_name = schedule["course"]
        session_key = f"{student_id}_{course_name}"

        if session_key in self.session_attendance_cache:
            return False, "ALREADY_RECORDED_CACHE"

        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        updated = False
        rows = []

        try:
            with open(file_path, mode="r", encoding="utf-8") as f:
                rows = list(csv.reader(f))

            for row in rows:
                if len(row) >= 5 and row[2] == student_id:
                    if row[4] in ("-", ""):
                        row[4] = timestamp_str
                        updated = True
                        print(f"[LOG] Attendance recorded for {name} ({student_id})")
                    else:
                        self.session_attendance_cache.add(session_key)
                        return False, "ALREADY_RECORDED_CSV"
                    break

            if updated:
                with open(file_path, mode="w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerows(rows)

                self.session_attendance_cache.add(session_key)
                return True, "SUCCESS"

            return False, "STUDENT_NOT_FOUND"

        except IOError as e:
            print(f"[ERROR] Attendance CSV transaction failed: {e}")
            return False, "SYSTEM_IO_ERROR"

    def transmit_to_esp32_lcd(self, detected_name: str) -> None:
        """Sends verification data payload to ESP32 LCD display over TCP Socket."""
        clean_name = detected_name.split(" (")[0]
        student_id = STUDENT_DATABASE.get(clean_name, "Unknown")
        payload = f"{clean_name}|{student_id}\n"

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
                tcp_socket.settimeout(2.0)
                tcp_socket.connect((ESP32_LCD_IP, ESP32_LCD_PORT))
                tcp_socket.sendall(payload.encode("utf-8"))
                print(f"[NET] Transmitted payload to LCD: {clean_name}")
        except (socket.timeout, socket.error) as err:
            print(f"[NET WARNING] Could not reach LCD display ({ESP32_LCD_IP}): {err}")

    def run(self) -> None:
        """Main execution loop for ESP32-CAM stream acquisition and processing."""
        print("[INFO] System online. Monitoring active class schedules...")
        print(f"[INFO] Connecting to camera endpoint: {ESP32_CAM_URL}")

        while True:
            active_schedule = get_active_schedule()

            if active_schedule is None:
                idle_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                current_time = datetime.now().strftime("%H:%M:%S")
                cv2.putText(idle_frame, "NO ACTIVE SCHEDULE", (160, 200), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                cv2.putText(idle_frame, f"System Time: {current_time}", (230, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
                cv2.imshow("ESP32-CAM Attendance System", idle_frame)

                if cv2.waitKey(1000) & 0xFF == ord("q"):
                    break
                continue

            current_course = active_schedule["course"]
            allowed_roster = active_schedule["attendees"]

            try:
                response = urllib.request.urlopen(ESP32_CAM_URL, timeout=5)
                image_array = np.array(bytearray(response.read()), dtype=np.uint8)
                frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

                if frame is None:
                    time.sleep(0.5)
                    continue

                new_verification = False
                status_display_msg = ""

                if self.process_current_frame:
                    scaled_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
                    rgb_scaled_frame = cv2.cvtColor(scaled_frame, cv2.COLOR_BGR2RGB)

                    self.face_locations = face_recognition.face_locations(rgb_scaled_frame)
                    self.face_encodings = face_recognition.face_encodings(rgb_scaled_frame, self.face_locations)
                    self.face_names = []

                    for encoding in self.face_encodings:
                        matches = face_recognition.compare_faces(
                            self.known_face_encodings, encoding, tolerance=FACE_MATCH_THRESHOLD
                        )
                        name = "Unknown"
                        confidence_str = "N/A"
                        distances = face_recognition.face_distance(self.known_face_encodings, encoding)

                        if len(distances) > 0:
                            best_index = int(np.argmin(distances))
                            if matches[best_index]:
                                matched_name = self.known_face_names[best_index]
                                if matched_name in allowed_roster:
                                    name = matched_name
                                    confidence_str = compute_face_confidence(distances[best_index], FACE_MATCH_THRESHOLD)

                        self.face_names.append(f"{name} ({confidence_str})")

                        if name != "Unknown":
                            student_id = STUDENT_DATABASE.get(name, "-")
                            success, msg = self.record_attendance(name, student_id, active_schedule)

                            if success:
                                self.transmit_to_esp32_lcd(name)
                                new_verification = True
                                status_display_msg = "SUCCESS"
                            elif "ALREADY" in msg:
                                status_display_msg = "ALREADY RECORDED"
                        else:
                            self.transmit_to_esp32_lcd("Unknown")

                self.process_current_frame = not self.process_current_frame

                # Overlay bounding boxes and metadata on output frame
                for (top, right, bottom, left), name_info in zip(self.face_locations, self.face_names):
                    top *= 2
                    right *= 2
                    bottom *= 2
                    left *= 2

                    clean_name = name_info.split(" (")[0]
                    sid = STUDENT_DATABASE.get(clean_name, "-")
                    session_key = f"{sid}_{current_course}"

                    if "Unknown" in clean_name:
                        color = (0, 0, 255)  # Red
                        status_text = "UNREGISTERED"
                    elif session_key in self.session_attendance_cache:
                        color = (255, 255, 0)  # Cyan
                        status_text = "RECORDED"
                    else:
                        color = (0, 255, 0)  # Green
                        status_text = "SUCCESS"

                    cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
                    cv2.rectangle(frame, (left, bottom - 35), (right, bottom), color, -1)
                    cv2.putText(frame, name_info, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.6, (255, 255, 255), 1)
                    cv2.putText(frame, status_text, (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

                # Header Overlay
                cv2.rectangle(frame, (0, 0), (640, 40), (0, 0, 0), -1)
                cv2.putText(frame, f"COURSE: {current_course}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                if new_verification:
                    cv2.putText(frame, "RECORD SAVED!", (200, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 3)
                    cv2.imshow("ESP32-CAM Attendance System", frame)
                    cv2.waitKey(2000)
                    continue

                if status_display_msg == "ALREADY RECORDED" and not new_verification:
                    cv2.putText(frame, "ALREADY RECORDED", (180, 400), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                cv2.imshow("ESP32-CAM Attendance System", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            except Exception as e:
                print(f"[ERROR] Capture loop iteration failed: {e}")
                time.sleep(0.5)

        cv2.destroyAllWindows()


if __name__ == "__main__":
    app = FaceRecognitionESP32()
    app.run()