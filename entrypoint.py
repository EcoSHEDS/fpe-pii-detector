#!/usr/bin/env python3
"""
FPE PII Detector - Command Line Interface
"""
import sys
import argparse
import logging
from fpe_pii_detector import (
    configure_logger,
    detect_image,
    detect_image_batch,
    detect_fpe_imageset,
    setup_detect_image_parser,
    setup_detect_image_batch_parser,
    setup_detect_fpe_imageset_parser,
)

logger = logging.getLogger("fpe-pii-detector")


def main():
    """Main CLI entrypoint"""
    parser = argparse.ArgumentParser(description="FPE PII Detector")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # detect-image command
    image_parser = subparsers.add_parser(
        "detect-image", help="Detect PII in a single image"
    )
    setup_detect_image_parser(image_parser)

    # detect-image-batch command
    image_batch_parser = subparsers.add_parser(
        "detect-image-batch", help="Detect PII in a batch of images"
    )
    setup_detect_image_batch_parser(image_batch_parser)

    # detect-imageset command
    imageset_parser = subparsers.add_parser(
        "detect-fpe-imageset", help="Detect PII in an FPE imageset"
    )
    setup_detect_fpe_imageset_parser(imageset_parser)

    if len(sys.argv) == 1:
        parser.print_help()
        return 1

    args = parser.parse_args()

    configure_logger(logger, level=logging.DEBUG if args.debug else logging.INFO)

    if args.command == "detect-image":
        return detect_image(args)
    elif args.command == "detect-image-batch":
        return detect_image_batch(args)
    elif args.command == "detect-fpe-imageset":
        return detect_fpe_imageset(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
