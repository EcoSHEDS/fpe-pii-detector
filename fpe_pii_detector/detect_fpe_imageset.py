"""Command-line interface for running PII detection on an FPE imageset."""

import argparse
import logging
import json
import os
import multiprocessing
import futureproof
import concurrent.futures
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
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of worker processes for parallel processing. Set to 0 or omit for sequential processing.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of images to process in each batch (default: 100)",
    )
    parser.add_argument("imageset_id", type=int, help="Imageset ID to process")
    return parser


def process_image(detector, row, min_confidence, idx=None, total=None):
    """
    Process a single image for PII detection.

    Args:
        detector: The PII detector model
        row: Database row with image information
        min_confidence: Minimum confidence threshold
        idx: Index of the image (for logging)
        total: Total number of images (for logging)

    Returns:
        dict: Detection results for the image
    """
    image_id = row["id"]
    bucket = row["full_s3"]["Bucket"]
    key = row["full_s3"]["Key"]

    s3_filename = f"s3://{bucket}/{key}"
    result = detect_image(detector, s3_filename, min_confidence)

    result["image_id"] = image_id
    result["file"] = os.path.basename(s3_filename)

    return result


def process_images_in_sequence(detector, df_images, min_confidence):
    results = []
    n_images = len(df_images)
    for idx, row in df_images.iterrows():
        logger.info(
            f"Processing image [{idx + 1}/{n_images}] (id={row['id']}, key={row['full_s3']['Key']})"
        )
        result = process_image(detector, row, min_confidence)
        results.append(result)
    return results


def process_images_in_parallel(detector, df_images, min_confidence, workers, batch_size):
    """
    Process images in parallel using batch processing.

    Args:
        detector: The loaded PII detector model
        df_images: DataFrame containing images to process
        min_confidence: Minimum confidence threshold for detections
        workers: Number of worker processes to use
        batch_size: Number of images to process in each batch

    Returns:
        list: Results from processing all images
    """
    n_images = len(df_images)
    results = []
    total_completed = 0

    # Process images in batches
    for batch_start in range(0, n_images, batch_size):
        batch_end = min(batch_start + batch_size, n_images)
        batch_images = df_images.iloc[batch_start:batch_end]
        batch_count = len(batch_images)

        logger.info(
            f"Processing batch {batch_start//batch_size + 1}/{(n_images + batch_size - 1)//batch_size} ({batch_count} images)"
        )

        # Create a pool with specified number of workers
        with futureproof.ThreadPoolExecutor(
            max_workers=workers,
            monitor_interval=5,  # Check for completed tasks every 5 seconds
        ) as executor:
            futures = []

            # Submit batch jobs to the executor
            for idx, row in batch_images.iterrows():
                global_idx = batch_start + (idx - batch_images.index[0])
                logger.debug(
                    f"Submitting image [{global_idx + 1}/{n_images}] (id={row['id']}, key={row['full_s3']['Key']})"
                )
                futures.append(
                    executor.submit(
                        process_image,
                        detector,
                        row,
                        min_confidence,
                        global_idx,
                        n_images,
                    )
                )

            # Process batch results as they complete
            completed = 0
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    completed += 1
                    total_completed += 1
                    logger.debug(
                        f"Completed image [{total_completed}/{n_images}] (id={result['image_id']}): {result}"
                    )
                    results.append(result)
                except Exception as e:
                    completed += 1
                    total_completed += 1
                    logger.error(
                        f"Error processing image [{total_completed}/{n_images}]: {str(e)}"
                    )

        logger.info(
            f"Completed batch {batch_start//batch_size + 1}/{(n_images + batch_size - 1)//batch_size} ({completed}/{batch_count} images)"
        )

    return results


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
            - workers (int): Number of worker processes to use.

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
        logger.info(
            f"Retrieved {len(df_images)} images for imageset (imageset_id={args.imageset_id})"
        )

        logger.info(f"Loading detector (model_file={args.model_file})")
        detector = load_detector(args.model_file)

        n_images = len(df_images)

        # Choose between parallel or sequential processing
        if args.workers is None or args.workers <= 0:
            logger.info(f"Processing {n_images} images sequentially")
            results = process_images_in_sequence(detector, df_images, args.min_confidence)
        else:
            workers = min(args.workers, n_images)
            batch_size = min(args.batch_size, n_images)
            logger.info(
                f"Processing {n_images} images using {workers} worker processes in batches of {batch_size}"
            )
            results = process_images_in_parallel(
                detector, df_images, args.min_confidence, workers, batch_size
            )

        if not args.dry_run:
            key = f'imagesets/{imageset["uuid"]}/pii.json'
            logger.info(f"Saving results to S3 (bucket={args.s3_bucket}, key={key})")
            save_results_to_s3(args.s3_bucket, key, results)

            logger.info(
                f"Saving results to database (imageset_id={args.imageset_id}, n_images={len(results)})"
            )
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
