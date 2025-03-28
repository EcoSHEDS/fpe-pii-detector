import os
from PytorchWildlife.models import detection
import json
import numpy as np
import PIL
import logging
import boto3
from io import StringIO, BytesIO

s3 = boto3.client("s3")

logger = logging.getLogger("fpe-pii-detector")

CLASS_NAMES = {0: "animal", 1: "person", 2: "vehicle"}
DEFAULT_CONF_THRESHOLD = 0.1


def setup_global_args(parser):
    """
    Set up common command-line arguments used across detector scripts.

    Args:
        parser (argparse.ArgumentParser): ArgumentParser object to add arguments to.

    Returns:
        argparse.ArgumentParser: Updated parser with added arguments.

    Arguments added:
        --model-file: Path to the MegaDetector model file.
        --min-confidence: Minimum confidence threshold for detections.
        --debug: Flag to enable debug logging.
    """
    parser.add_argument(
        "--model-file",
        type=str,
        default="model/md_v5a.0.0.pt",
        help="Path to the model file",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.1,
        help="Minimum confidence threshold between 0 and 1 (default=0.1)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def load_detector(weights=None, device="cpu", pretrained=True, version="a"):
    """
    Load the MegaDetectorV5 model.

    Args:
        weights (str, optional): Path to the weights file.
            If None, will use the default MegaDetector weights.
        device (str, optional): Device to load the model on (e.g., "cpu" or "cuda").
            Default is "cpu".
        pretrained (bool, optional): Whether to load the pretrained model.
            Default is True.
        version (str, optional): Version of the MegaDetectorV5 model to load.
            Default is "a".

    Returns:
        PytorchWildlife.models.detection.MegaDetectorV5: The loaded MegaDetector model.

    Raises:
        Exception: If the model cannot be loaded.
    """
    try:
        detection_model = detection.MegaDetectorV5(
            weights=weights, device=device, pretrained=pretrained, version=version
        )
        return detection_model
    except Exception as e:
        logger.error(f"Failed to load detector model: {str(e)}")
        raise


def convert_md_detections_to_fpe_format(md_detections):
    """
    Convert MegaDetector v5 detections to FPE format.

    Args:
        md_detections (dict): MegaDetector v5 detections from single_image_detection().
            Expected to contain a 'detections' key with class_id, confidence, and xyxy attributes.

    Returns:
        dict: Dictionary in the FPE PII format containing:
            - 'detections': List of detection objects, each with category, confidence, and bbox.
            - 'max_conf': Dictionary with maximum confidence scores for each category.

    Raises:
        Exception: If conversion fails due to unexpected format in md_detections.
    """
    try:
        detections = []
        n_detections = len(md_detections["detections"].class_id)
        max_conf = {"animal": 0, "person": 0, "vehicle": 0}
        for i in range(n_detections):
            detection = {
                "category": int(md_detections["detections"].class_id[i]),
                "conf": float(md_detections["detections"].confidence[i]),
                "bbox": md_detections["detections"].xyxy[i].astype(int).tolist(),
            }
            detections.append(detection)
            category = detection["category"]
            category_label = CLASS_NAMES[category]
            max_conf[category_label] = max(max_conf[category_label], detection["conf"])

        return {"detections": detections, "max_conf": max_conf}
    except Exception as e:
        logger.error(
            f"Failed to convert MegaDetector detections to FPE format: {str(e)}"
        )
        raise


def convert_fpe_detections_to_db_format(detections):
    """
    Convert FPE detections to database storage format.

    Args:
        detections (dict): FPE detections from convert_md_detections_to_fpe_format().
            Expected to contain 'max_conf' and 'detections' keys.

    Returns:
        dict: Dictionary with database field mappings:
            - pii_animal (float): Maximum confidence for animal detections.
            - pii_person (float): Maximum confidence for person detections.
            - pii_vehicle (float): Maximum confidence for vehicle detections.
            - pii_detections (JSON): Original detections in JSON-compatible format.

    Raises:
        Exception: If conversion fails due to unexpected format in detections.
    """
    try:
        return {
            "pii_animal": detections["max_conf"]["animal"],
            "pii_person": detections["max_conf"]["person"],
            "pii_vehicle": detections["max_conf"]["vehicle"],
            "pii_detections": detections["detections"],
        }
    except Exception as e:
        logger.error(f"Failed to convert FPE detections to database format: {str(e)}")
        raise


def read_image_from_file(filename):
    """
    Read an image from a local file path.

    Args:
        filename (str): Local path to the image file.

    Returns:
        numpy.ndarray: Image as a numpy array in RGB format.

    Raises:
        Exception: If the image cannot be read or processed.
    """
    try:
        image = PIL.Image.open(filename)
        return np.array(image.convert("RGB"))
    except Exception as e:
        logger.error(f"Failed to read image from file (filename={filename}): {str(e)}")
        raise


def read_image_from_s3(bucket_name, key):
    """
    Read an image from an AWS S3 bucket.

    Args:
        bucket_name (str): Name of the S3 bucket.
        key (str): Object key (path) within the bucket.

    Returns:
        numpy.ndarray: Image as a numpy array in RGB format.

    Raises:
        Exception: If the S3 object cannot be read or processed as an image.
    """
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        body = BytesIO(response["Body"].read())
        image = PIL.Image.open(body)
        return np.array(image.convert("RGB"))
    except Exception as e:
        logger.error(
            f"Failed to read image from S3 (bucket={bucket_name}, key={key}): {str(e)}"
        )
        raise


def read_image(filename):
    """
    Read an image from either a local file path or an S3 URI.

    Args:
        filename (str): Path to the image, either a local file path or an S3 URI.
            S3 URIs should be in the format 's3://bucket-name/path/to/image.jpg'.

    Returns:
        numpy.ndarray: Image as a numpy array in RGB format.

    Raises:
        Exception: If the image cannot be read or processed.
    """
    if filename.startswith("s3://"):
        bucket_name, key = filename[5:].split("/", 1)
        return read_image_from_s3(bucket_name, key)
    else:
        return read_image_from_file(filename)


def detect_image(detector, filename, min_confidence):
    """
    Detect PII (persons, vehicles, animals) in an image.

    Args:
        detector (PytorchWildlife.models.detection.MegaDetectorV5): Loaded detector model.
        filename (str): Path to the image, either a local file path or an S3 URI.
        min_confidence (float): Minimum confidence threshold for detections (0.0 to 1.0).

    Returns:
        dict: Dictionary in FPE PII format containing detections and confidence scores.

    Raises:
        Exception: If detection fails for any reason.
    """
    try:
        image = read_image(filename)
        md_results = detector.single_image_detection(
            image, det_conf_thres=min_confidence
        )
        return convert_md_detections_to_fpe_format(md_results)
    except Exception as e:
        logger.error(f"Failed to detect PII in image (filename={filename}): {str(e)}")
        raise


def save_results_to_s3(bucket, key, data):
    """
    Save detection results to an AWS S3 bucket as a JSON file.

    Args:
        bucket (str): Name of the S3 bucket.
        key (str): Object key (path) within the bucket.
        data (dict or list): Python object to save as JSON.

    Returns:
        dict: Response from S3 put_object operation.

    Raises:
        Exception: If saving to S3 fails.
    """
    try:
        body = StringIO(json.dumps(data))
        return s3.put_object(Bucket=bucket, Key=key, Body=body.getvalue())
    except Exception as e:
        logger.error(
            f"Failed to save results to S3 (bucket={bucket}, key={key}): {str(e)}"
        )
        raise
