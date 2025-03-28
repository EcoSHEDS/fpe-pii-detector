"""
Integration tests for the FPE PII Detector.
These tests check the end-to-end image detection pipeline using real test images.
"""

import os
import unittest
import pandas as pd
import tempfile
import json

from fpe_pii_detector.utils import load_detector, detect_image


class TestIntegrationDetection(unittest.TestCase):
    """Integration tests for image detection pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.test_dir, "..", "data")
        self.input_dir = os.path.join(self.data_dir, "input")
        self.output_dir = os.path.join(self.data_dir, "output")

        # Ensure output directory exists
        os.makedirs(self.output_dir, exist_ok=True)

        # Load CSV with test images and expected results
        csv_path = os.path.join(self.input_dir, "images.csv")
        self.test_images_df = pd.read_csv(csv_path)

        # Define confidence threshold
        self.min_confidence = 0.5

    @unittest.skipIf(
        not os.path.exists("model/md_v5a.0.0.pt"),
        "Model file not found, skipping integration tests",
    )
    def test_end_to_end_detection(self):
        """Test end-to-end detection on all test images."""
        # Load the detector once for all tests
        detector = load_detector(weights="model/md_v5a.0.0.pt")

        # Create a results file in the output directory
        results_file = os.path.join(self.output_dir, "detection_results.json")

        results = []

        # Process each test image
        for _, row in self.test_images_df.iterrows():
            filename = row["filename"]
            expected_animal = row["animal"]
            expected_person = row["person"]
            expected_vehicle = row["vehicle"]

            # Full path to image
            image_path = os.path.join(self.input_dir, filename)

            # Run detection
            detection_result = detect_image(detector, image_path, self.min_confidence)

            # Check if detections match expectations (with tolerance for false positives/negatives)
            animal_detected = (
                detection_result["max_conf"]["animal"] > self.min_confidence
            )
            person_detected = (
                detection_result["max_conf"]["person"] > self.min_confidence
            )
            vehicle_detected = (
                detection_result["max_conf"]["vehicle"] > self.min_confidence
            )

            # Add to results
            result_entry = {
                "filename": filename,
                "expected": {
                    "animal": bool(expected_animal),
                    "person": bool(expected_person),
                    "vehicle": bool(expected_vehicle),
                },
                "detected": {
                    "animal": animal_detected,
                    "person": person_detected,
                    "vehicle": vehicle_detected,
                },
                "confidence": {
                    "animal": float(detection_result["max_conf"]["animal"]),
                    "person": float(detection_result["max_conf"]["person"]),
                    "vehicle": float(detection_result["max_conf"]["vehicle"]),
                },
                "num_detections": len(detection_result["detections"]),
            }

            results.append(result_entry)

            # Assertions for this test image
            if expected_animal:
                self.assertTrue(
                    animal_detected, f"Failed to detect animal in {filename}"
                )
            if expected_person:
                self.assertTrue(
                    person_detected, f"Failed to detect person in {filename}"
                )
            if expected_vehicle:
                self.assertTrue(
                    vehicle_detected, f"Failed to detect vehicle in {filename}"
                )

        # Write results to file
        with open(results_file, "w") as f:
            json.dump(results, f, indent=2)


if __name__ == "__main__":
    unittest.main()
