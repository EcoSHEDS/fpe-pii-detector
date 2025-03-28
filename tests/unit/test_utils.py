import os
import unittest
import numpy as np
from unittest.mock import patch, MagicMock
import json

from fpe_pii_detector.utils import (
    load_detector,
    convert_md_detections_to_fpe_format,
    convert_fpe_detections_to_db_format,
    read_image,
    read_image_from_file,
    read_image_from_s3,
    detect_image,
)


class TestUtils(unittest.TestCase):
    """Test cases for the utils module."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.test_dir, "..", "data")
        self.input_dir = os.path.join(self.data_dir, "input")

        # Define paths to test images
        self.animal_image = os.path.join(self.input_dir, "animal", "RCNX0613.JPG")
        self.person_image = os.path.join(
            self.input_dir, "person", "West Brook 0__2023-02-22__12-00-57(8).JPG"
        )
        self.vehicle_image = os.path.join(
            self.input_dir, "vehicle", "Sanderson Brook__2022-03-20__12-17-24(1).JPG"
        )
        self.none_image = os.path.join(
            self.input_dir, "none", "West Brook Lower__2021-09-18__11-00-13(1).JPG"
        )

        # Check if test images exist
        self.assertTrue(
            os.path.exists(self.animal_image),
            f"Test animal image not found: {self.animal_image}",
        )
        self.assertTrue(
            os.path.exists(self.person_image),
            f"Test person image not found: {self.person_image}",
        )
        self.assertTrue(
            os.path.exists(self.vehicle_image),
            f"Test vehicle image not found: {self.vehicle_image}",
        )
        self.assertTrue(
            os.path.exists(self.none_image),
            f"Test none image not found: {self.none_image}",
        )

    @patch("fpe_pii_detector.utils.detection")
    def test_load_detector(self, mock_detection):
        """Test loading the detector."""
        # Setup mock
        mock_detector = MagicMock()
        mock_detection.MegaDetectorV5.return_value = mock_detector

        # Call function
        detector = load_detector(weights="test_model.pt")

        # Verify
        mock_detection.MegaDetectorV5.assert_called_once_with(
            weights="test_model.pt", device="cpu", pretrained=True, version="a"
        )
        self.assertEqual(detector, mock_detector)

    def test_read_image_from_file(self):
        """Test reading an image from a file."""
        # Read a test image
        image = read_image_from_file(self.none_image)

        # Verify
        self.assertIsInstance(image, np.ndarray)
        self.assertEqual(len(image.shape), 3)  # Should be 3D (height, width, channels)
        self.assertEqual(image.shape[2], 3)  # Should have 3 channels (RGB)

    @patch("fpe_pii_detector.utils.s3")
    def test_read_image_from_s3(self, mock_s3):
        """Test reading an image from S3."""
        from io import BytesIO
        import PIL.Image

        # Create a mock image
        test_image = PIL.Image.new("RGB", (100, 100), color="red")
        image_bytes = BytesIO()
        test_image.save(image_bytes, format="JPEG")
        image_bytes.seek(0)

        # Setup mock
        mock_response = {"Body": MagicMock()}
        mock_response["Body"].read.return_value = image_bytes.getvalue()
        mock_s3.get_object.return_value = mock_response

        # Call function
        image = read_image_from_s3("test-bucket", "test-key")

        # Verify
        mock_s3.get_object.assert_called_once_with(Bucket="test-bucket", Key="test-key")
        self.assertIsInstance(image, np.ndarray)
        self.assertEqual(image.shape, (100, 100, 3))

    def test_read_image_local(self):
        """Test reading a local image with read_image function."""
        # Read a test image
        image = read_image(self.none_image)

        # Verify
        self.assertIsInstance(image, np.ndarray)
        self.assertEqual(len(image.shape), 3)

    @patch("fpe_pii_detector.utils.read_image_from_s3")
    def test_read_image_s3(self, mock_read_s3):
        """Test reading an S3 image with read_image function."""
        # Setup mock
        mock_read_s3.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        # Call function
        image = read_image("s3://test-bucket/test-key")

        # Verify
        mock_read_s3.assert_called_once_with("test-bucket", "test-key")
        self.assertIsInstance(image, np.ndarray)
        self.assertEqual(image.shape, (100, 100, 3))

    def test_convert_md_detections_to_fpe_format(self):
        """Test conversion from MegaDetector to FPE format."""

        # Create mock MegaDetector output
        class Detections:
            def __init__(self, class_id, confidence, xyxy):
                self.class_id = class_id
                self.confidence = confidence
                self.xyxy = xyxy

        mock_detections = {
            "detections": Detections(
                class_id=np.array([0, 1]),  # animal, person
                confidence=np.array([0.85, 0.95]),
                xyxy=np.array([[10, 20, 30, 40], [50, 60, 70, 80]]),
            )
        }

        # Call function
        result = convert_md_detections_to_fpe_format(mock_detections)

        # Verify
        self.assertIn("detections", result)
        self.assertIn("max_conf", result)

        self.assertEqual(len(result["detections"]), 2)
        self.assertEqual(result["detections"][0]["category"], 0)  # animal
        self.assertEqual(result["detections"][0]["conf"], 0.85)
        self.assertEqual(result["detections"][0]["bbox"], [10, 20, 30, 40])

        self.assertEqual(result["detections"][1]["category"], 1)  # person
        self.assertEqual(result["detections"][1]["conf"], 0.95)
        self.assertEqual(result["detections"][1]["bbox"], [50, 60, 70, 80])

        self.assertEqual(result["max_conf"]["animal"], 0.85)
        self.assertEqual(result["max_conf"]["person"], 0.95)
        self.assertEqual(result["max_conf"]["vehicle"], 0)

    def test_convert_fpe_detections_to_db_format(self):
        """Test conversion from FPE format to database format."""
        # Create mock FPE format
        fpe_format = {
            "detections": [
                {"category": 0, "conf": 0.85, "bbox": [10, 20, 30, 40]},
                {"category": 1, "conf": 0.95, "bbox": [50, 60, 70, 80]},
            ],
            "max_conf": {"animal": 0.85, "person": 0.95, "vehicle": 0},
        }

        # Call function
        result = convert_fpe_detections_to_db_format(fpe_format)

        # Verify
        self.assertEqual(result["pii_animal"], 0.85)
        self.assertEqual(result["pii_person"], 0.95)
        self.assertEqual(result["pii_vehicle"], 0)
        self.assertEqual(result["pii_detections"], fpe_format["detections"])

    @patch("fpe_pii_detector.utils.read_image")
    def test_detect_image(self, mock_read_image):
        """Test the detect_image function."""
        # Setup mocks
        mock_read_image.return_value = np.zeros((100, 100, 3), dtype=np.uint8)

        mock_detector = MagicMock()

        class Detections:
            def __init__(self):
                self.class_id = np.array([1])  # person
                self.confidence = np.array([0.9])
                self.xyxy = np.array([[10, 20, 30, 40]])

        mock_detector.single_image_detection.return_value = {"detections": Detections()}

        # Call function
        result = detect_image(mock_detector, "test_image.jpg", 0.5)

        # Verify
        mock_read_image.assert_called_once_with("test_image.jpg")
        mock_detector.single_image_detection.assert_called_once()

        self.assertIn("detections", result)
        self.assertIn("max_conf", result)
        self.assertEqual(result["max_conf"]["person"], 0.9)

    @unittest.skipIf(not os.path.exists("model/md_v5a.0.0.pt"), "Model file not found")
    def test_integration_detect_animal(self):
        """Integration test for detecting animal in an image."""
        # Load the actual model
        detector = load_detector(weights="model/md_v5a.0.0.pt")

        # Detect in an image with an animal
        result = detect_image(detector, self.animal_image, 0.5)

        # Verify animal detection
        self.assertGreater(result["max_conf"]["animal"], 0.5)

    @unittest.skipIf(not os.path.exists("model/md_v5a.0.0.pt"), "Model file not found")
    def test_integration_detect_person(self):
        """Integration test for detecting person in an image."""
        # Load the actual model
        detector = load_detector(weights="model/md_v5a.0.0.pt")

        # Detect in an image with a person
        result = detect_image(detector, self.person_image, 0.5)

        # Verify person detection
        self.assertGreater(result["max_conf"]["person"], 0.5)

    @unittest.skipIf(not os.path.exists("model/md_v5a.0.0.pt"), "Model file not found")
    def test_integration_detect_vehicle(self):
        """Integration test for detecting vehicle in an image."""
        # Load the actual model
        detector = load_detector(weights="model/md_v5a.0.0.pt")

        # Detect in an image with a vehicle
        result = detect_image(detector, self.vehicle_image, 0.5)

        # Verify vehicle detection
        self.assertGreater(result["max_conf"]["vehicle"], 0.5)


if __name__ == "__main__":
    unittest.main()
