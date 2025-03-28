"""Command-line interface for running PII detection on an FPE imageset."""

import argparse
import logging
import json
import os
from .utils import load_detector, detect_image, setup_global_args, save_results_to_s3
from .db import (
    get_db_credentials,
    db_connect,
    fetch_imageset_images,
    fetch_imageset,
    update_imageset_pii_status,
    save_results_to_database,
)
from .logger import configure_logger

logger = logging.getLogger("fpe-pii-detector")


def setup_parser(parser):
    """
    Setup the parser for the detect-fpe-imageset command.

    Args:
        parser (argparse.ArgumentParser): ArgumentParser object to add arguments to.

    Returns:
        argparse.ArgumentParser: Updated parser with added arguments.

    Arguments added:
        imageset_id: ID of the imageset to process.
        --max-images: Maximum number of images to process (optional).
        --s3-bucket: S3 bucket to save results.
        --dry-run: Flag to run without saving results.
        Additional arguments from setup_global_args.
    """
    setup_global_args(parser)
    parser.add_argument(
        "--max-images",
        type=int,
        help="Maximum number of images to process (for testing)",
    )
    parser.add_argument(
        "--s3-bucket",
        type=str,
        default=os.getenv("FPE_S3_BUCKET"),
        help="S3 bucket to save results",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run the script (results not saved to s3 or database)",
    )
    parser.add_argument("imageset_id", type=int, help="Imageset ID to process")
    return parser


def run(args):
    """
    Run PII detection on an FPE imageset and save results to JSON file and database.

    Fetches the imageset and its images from the database, processes each image for PII detections,
    and saves the results to both S3 and the database. Also updates the imageset status throughout
    the processing.

    Args:
        args (argparse.Namespace): Command-line arguments including:
            - imageset_id (int): ID of the imageset to process.
            - model_file (str): Path to the detector model file.
            - min_confidence (float): Minimum confidence threshold.
            - max_images (int, optional): Maximum number of images to process.
            - s3_bucket (str): S3 bucket to save results.
            - dry_run (bool): Whether to run without saving results.

    Returns:
        int: 0 for success, 1 for failure.

    Side effects:
        - Updates imageset status in the database.
        - Saves detection results to S3 and the database.
        - Logs progress and results.
    """
    try:
        logger.info(f"Getting database credentials")
        config = get_db_credentials()

        logger.info(
            f'Connecting to database: postgresql://XXXXX:XXXXX@{config["host"]}:{config["port"]}/{config["dbname"]}'
        )
        db_engine = db_connect(config)
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}")
        raise

    logger.info(f"Fetching imageset (imageset_id={args.imageset_id})")
    imageset = fetch_imageset(db_engine, args.imageset_id)
    if not imageset:
        raise Exception(f"Imageset not found (imageset_id={args.imageset_id})")

    try:
        if not args.dry_run:
            logger.info(
                f"Setting imageset status to PROCESSING (imageset_id={args.imageset_id})"
            )
            update_imageset_pii_status(db_engine, imageset["id"], "PROCESSING")

        logger.info(f"Fetching images (imageset_id={args.imageset_id})")
        df_images = fetch_imageset_images(
            db_engine, args.imageset_id, max_images=args.max_images
        )
        if df_images.empty:
            raise Exception(
                f"No images found for imageset (imageset_id={args.imageset_id})"
            )
        logger.info(f"Imageset has {len(df_images)} images")

        logger.info(f"Loading detector (model_file={args.model_file})")
        detector = load_detector(args.model_file)

        results = []
        n_images = len(df_images)
        logger.info(f"Processing {n_images} images")
        for idx, row in df_images.iterrows():
            image_id = row["id"]
            bucket = row["full_s3"]["Bucket"]
            key = row["full_s3"]["Key"]

            logger.debug(f"Detecting image [{idx + 1}/{n_images}] (key={key})")
            s3_filename = f"s3://{bucket}/{key}"
            result = detect_image(detector, s3_filename, args.min_confidence)
            logger.debug(f"Detection results [{idx + 1}/{n_images}]: {result}")

            result["image_id"] = image_id
            result["file"] = os.path.basename(s3_filename)

            results.append(result)

        if not args.dry_run:
            key = f'imagesets/{imageset["uuid"]}/pii.json'
            logger.info(f"Saving results to S3 (bucket={args.s3_bucket}, key={key})")
            save_results_to_s3(args.s3_bucket, key, results)
            save_results_to_database(db_engine, results)

            logger.info(
                f"Setting imageset status to DONE (imageset_id={args.imageset_id})"
            )
            update_imageset_pii_status(db_engine, imageset["id"], "DONE")
        else:
            logger.info(f"Dry run complete, results not saved to S3 or database")
            logger.info(json.dumps(results, indent=2))

        return 0
    except Exception as e:
        logger.error(f"Error processing imageset: {str(e)}")
        if "imageset" in locals() and not args.dry_run:
            logger.info(
                f"Setting imageset status to FAILED (imageset_id={args.imageset_id})"
            )
            update_imageset_pii_status(db_engine, imageset["id"], "FAILED")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run PII detector on FPE imageset and save results to JSON file and database"
    )
    parser = setup_parser(parser)
    args = parser.parse_args()

    configure_logger(logger, level=logging.DEBUG if args.debug else logging.INFO)

    exit(run(args))
