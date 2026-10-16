import face_recognition
import os
import pickle
import sys

def train_face_encodings():
    """Reads facial images from dataset folder and saves encodings into pickle files per person."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(base_dir, "dataset")
    output_folder = os.path.join(base_dir, "feature_db")

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    print("[INFO] Starting modular face encoding process...")

    if not os.path.exists(dataset_path):
        print(f"[ERROR] Dataset path not found: {dataset_path}")
        sys.exit(1)

    for person_name in os.listdir(dataset_path):
        person_folder = os.path.join(dataset_path, person_name)

        if not os.path.isdir(person_folder):
            continue

        pickle_filename = os.path.join(output_folder, f"{person_name}.pickle")

        if os.path.exists(pickle_filename):
            print(f"  [SKIP] Encoding for '{person_name}' already exists. Skipping.")
            continue

        print(f"  [PROCESS] Generating encodings for: {person_name}...")

        known_encodings = []
        known_names = []

        for image_name in os.listdir(person_folder):
            if not image_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                continue

            image_path = os.path.join(person_folder, image_name)
            try:
                image = face_recognition.load_image_file(image_path)
                encodings = face_recognition.face_encodings(image)

                if len(encodings) > 0:
                    known_encodings.append(encodings[0])
                    known_names.append(person_name)
                else:
                    print(f"    [FAIL] No face detected in: {image_name}")
            except Exception as e:
                print(f"    [ERROR] {image_name}: {e}")

        if known_encodings:
            data = {"encodings": known_encodings, "names": known_names}
            with open(pickle_filename, "wb") as f:
                f.write(pickle.dumps(data))
            print(f"  [SUCCESS] Saved to {person_name}.pickle ({len(known_encodings)} faces)")
        else:
            print(f"  [WARNING] Failed to generate data for {person_name} (0 faces detected)")

    print("\n[INFO] Process complete. Check 'feature_db' folder.")


if __name__ == "__main__":
    train_face_encodings()