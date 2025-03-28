"""Command-line interface for running PII detection on a batch of images."""

import argparse
import logging
import pandas as pd
import os
from .utils import load_detector, detect_image, setup_global_args
from .logger import configure_logger

logger = logging.getLogger("fpe-pii-detector")


def setup_parser(parser):
    """
    Setup the parser for the detect-image-batch command.

    Args:
        parser (argparse.ArgumentParser): ArgumentParser object to add arguments to.

    Returns:
        argparse.ArgumentParser: Updated parser with added arguments.

    Arguments added:
        filename: Path to CSV file containing image paths.
        --root-dir: Root directory for relative image paths.
        --filename-column: Name of the CSV column containing image filenames.
        Additional arguments from setup_global_args.
    """
    setup_global_args(parser)
    parser.add_argument("--root-dir", type=str, help="Path to root directory of images")
    parser.add_argument(
        "--filename-column",
        type=str,
        default="filename",
        help="Name of the column in the CSV file that contains the image filenames",
    )
    parser.add_argument(
        "filename",
        type=str,
        help='Path to CSV file containing a "filename" column with local image paths or S3 URIs',
    )
    return parser


def run(args):
    """
    Run PII detection on a batch of images specified in a CSV file.

    Reads a CSV file containing image paths, then processes each image and logs the results.

    Args:
        args (argparse.Namespace): Command-line arguments including:
            - model_file (str): Path to the model file.
            - filename (str): Path to the CSV file.
            - filename_column (str): Name of the column containing image paths.
            - root_dir (str, optional): Root directory for relative image paths.
            - min_confidence (float): Minimum confidence threshold.

    Returns:
        int: 0 for success, 1 for failure.

    Side effects:
        Logs detection results for each image and any errors.
    """
    try:
        logger.debug(f"Loading detector (model_file={args.model_file})")
        detector = load_detector(args.model_file)

        logger.info(f"Reading CSV file (filename={args.filename})")
        df = pd.read_csv(args.filename)
        logger.info(f"Processing {len(df)} images")
        for index, row in df.iterrows():
            filename = row[args.filename_column]

            logger.info(f"Detecting PII in image (filename={filename})")
            if not filename.startswith("s3://") and args.root_dir:
                filename = os.path.join(args.root_dir, filename)

            fpe_results = detect_image(detector, filename, args.min_confidence)
            logger.info(f"Results: {fpe_results}")

        return 0
    except Exception as e:
        logger.error(f"Error processing batch: {e}")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect PII on a batch of images")
    parser = setup_parser(parser)
    args = parser.parse_args()

    configure_logger(logger, level=logging.DEBUG if args.debug else logging.INFO)

    exit(run(args))
