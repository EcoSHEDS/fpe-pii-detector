"""Command-line interface for running PII detection on a single image."""

import argparse
import logging
from .utils import (
    load_detector,
    detect_image,
    setup_global_args,
)
from .logger import configure_logger

logger = logging.getLogger("fpe-pii-detector")


def setup_parser(parser):
    """
    Setup the parser for the detect-image command.

    Args:
        parser (argparse.ArgumentParser): ArgumentParser object to add arguments to.

    Returns:
        argparse.ArgumentParser: Updated parser with added arguments.

    Arguments added:
        filename: Local path or S3 URI for the image to process.
        Additional arguments from setup_global_args.
    """
    setup_global_args(parser)
    parser.add_argument("filename", type=str, help="Local path or S3 URI for the image")
    return parser


def run(args):
    """
    Run the PII detection on a single image.

    Loads the detector model, processes the specified image, and outputs the results.

    Args:
        args (argparse.Namespace): Command-line arguments including:
            - model_file (str): Path to the model file.
            - filename (str): Path to the image file.
            - min_confidence (float): Minimum confidence threshold.

    Returns:
        int: 0 for success, 1 for failure.

    Side effects:
        Logs detection results and any errors.
    """
    try:
        logger.debug(f"Loading detector (model_file={args.model_file})")
        detector = load_detector(args.model_file)

        logger.info(f"Detecting PII in image (filename={args.filename})")
        fpe_results = detect_image(detector, args.filename, args.min_confidence)
        logger.info(f"Results: {fpe_results}")
        return 0
    except Exception as e:
        logger.error(f"Error detecting PII: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect PII on a single image")
    parser = setup_parser(parser)
    args = parser.parse_args()

    configure_logger(logger, level=logging.DEBUG if args.debug else logging.INFO)

    exit(run(args))
