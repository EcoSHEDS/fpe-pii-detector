# FPE PII Detector

The FPE PII Detector is a tool that detects personally identifiable information (PII) in images. It uses [Microsoft MegaDetector](https://github.com/microsoft/CameraTraps/blob/main/megadetector.md) v5 (via PytorchWildlife) to identify persons, vehicles, and animals in images. The detector can be run on individual images, batches of images from a CSV file, or complete FPE imagesets. Results can be saved to S3 and the FPE database.

## Installation

### Prerequisites

- Python 3.8 or higher
- pip (Python package installer)

### Setup

1. Clone this repository:

```sh
git clone https://github.com/ecosheds/fpe-pii-detector.git
cd fpe-pii-detector
```

2. Install the required packages:

```sh
pip install -r requirements.txt
```

3. Download or copy the MegaDetector model file to the `model/` directory. The default expected location is `model/md_v5a.0.0.pt`.

```sh
curl -L https://zenodo.org/records/13357337/files/md_v5a.0.0.pt?download=1 -o model/md_v5a.0.0.pt
```

### Configuration

The following environment variables are needed to configure the detector for accessing the FPE database and S3 bucket:

- `FPE_DB_SECRET`: AWS Secrets Manager secret name for database credentials
- `FPE_DB_HOST`: Database host (if not using Secrets Manager)
- `FPE_DB_PORT`: Database port (default: 5432)
- `FPE_DB_NAME`: Database name (default: postgres)
- `FPE_DB_USER`: Database username
- `FPE_DB_PASSWORD`: Database password
- `FPE_S3_BUCKET`: Default S3 bucket for saving results

You can set these in a `.env` file or directly in your environment.

## Command Line Usage

The FPE PII Detector provides a unified command-line interface with several subcommands:

### Detect PII in a Single Image

```sh
python entrypoint.py detect-image [--model-file MODEL_FILE] [--min-confidence MIN_CONFIDENCE] [--debug] FILENAME
```

Examples:
```sh
# Detect PII in a local image
python entrypoint.py detect-image path/to/image.jpg

# Detect PII in an image stored in S3
python entrypoint.py detect-image s3://bucket-name/path/to/image.jpg

# Specify a different confidence threshold
python entrypoint.py detect-image --min-confidence 0.5 path/to/image.jpg
```

### Detect PII in Multiple Images from a CSV File

```sh
python entrypoint.py detect-image-batch [--model-file MODEL_FILE] [--min-confidence MIN_CONFIDENCE] [--root-dir ROOT_DIR] [--filename-column COLUMN_NAME] [--debug] CSV_FILE
```

Examples:
```sh
# Process images listed in a CSV file
python entrypoint.py detect-image-batch images.csv

# Specify a root directory for relative paths
python entrypoint.py detect-image-batch --root-dir /path/to/images images.csv

# Use a custom column name for image paths
python entrypoint.py detect-image-batch --filename-column image_path images.csv
```

### Detect PII in an FPE Imageset

```sh
python entrypoint.py detect-fpe-imageset [--model-file MODEL_FILE] [--min-confidence MIN_CONFIDENCE] [--max-images MAX_IMAGES] [--s3-bucket S3_BUCKET] [--dry-run] [--workers WORKERS] [--batch-size BATCH_SIZE] [--debug] IMAGESET_ID
```

**Parallel Processing Options:**
- `--workers`: Number of worker processes for parallel processing. Set to 0 or omit for sequential processing.
- `--batch-size`: Number of images to process in each batch when running in parallel (default: 100).

Examples:
```sh
# Process a complete imageset and save results (sequential mode)
python entrypoint.py detect-fpe-imageset 326

# Process an imageset using 4 worker processes in parallel
python entrypoint.py detect-fpe-imageset --workers 4 326

# Process an imageset using 8 worker processes with smaller batch size
python entrypoint.py detect-fpe-imageset --workers 8 --batch-size 50 326

# Perform a dry run on only the first 10 images without saving results
python entrypoint.py detect-fpe-imageset --max-images 10 --dry-run 326

# Specify a custom confidence threshold
python entrypoint.py detect-fpe-imageset --min-confidence 0.5 326
```

**Note on Parallel Processing:**
- Parallel processing significantly speeds up detection for large imagesets
- The `--workers` parameter should typically match the number of CPUs available
- For memory-intensive operations, you may need to reduce batch size

## Testing

The FPE PII Detector includes a test suite with both unit tests and integration tests. These tests verify that the detector functions correctly and produces results in the expected format.

### Test Structure

The tests are organized as follows:

- `tests/unit/` - Unit tests for individual components
- `tests/integration/` - End-to-end tests of the detection pipeline
- `tests/run_tests.py` - Script to run all tests

### Running Tests

To run all tests:

```sh
python tests/run_tests.py
```

To run a specific test file:

```sh
python -m unittest tests/unit/test_utils.py
python -m unittest tests/integration/test_detection.py
```

### Test Requirements

Most unit tests will run without additional dependencies, but the integration tests and some unit tests require:

1. The MegaDetector model file (`model/md_v5a.0.0.pt`)
2. Test images (provided in the `data/input/` directory)

Tests that require the model file will be skipped if the file is not found, with a clear message indicating the reason for skipping.

### Test Data

The test suite uses a set of labeled test images in the `data/input/` directory:

- `animal/` - Contains images with animals
- `person/` - Contains images with people
- `vehicle/` - Contains images with vehicles
- `none/` - Contains images with no PII

The `data/input/images.csv` file maps each image to its expected detection results.

### Test Output

Integration tests save their results to the `data/output/` directory:

- `detection_results.json` - Detailed results for each test image
- `performance_metrics.json` - Accuracy metrics for the detector

These files are useful for analyzing detector performance and verifying that changes to the code don't negatively impact detection accuracy.

## Docker Usage

### Building the Docker Image

```sh
# Build the Docker image
docker build -t fpe-pii-detector .

# For Apple Silicon (M1+) Macs, specify the platform
docker buildx build --platform=linux/amd64 -t fpe-pii-detector .
```

### Running with Docker

```sh
# Detect PII in a single image
# note: path is relative to the container, which is mounted from the local directory
docker run --rm -v $(pwd)/data:/data fpe-pii-detector detect-image /data/image.jpg

# Process an FPE imageset passing through AWS credentials from host user and loading environment variables from .env file
docker run --rm \
  -v ~/.aws:/root/.aws \
  -e AWS_PROFILE \
  --env-file .env \
  fpe-pii-detector detect-fpe-imageset 326

# Process an FPE imageset passing through environment variables from host
docker run --rm \
  -e AWS_ACCESS_KEY_ID \
  -e AWS_SECRET_ACCESS_KEY \
  -e AWS_SESSION_TOKEN \
  -e FPE_DB_SECRET \
  -e FPE_S3_BUCKET \
  fpe-pii-detector detect-fpe-imageset 326
```

### Parallel Processing in Docker

When using parallel processing in Docker, it's recommended to limit the container's CPU usage to match the worker count:

```sh
# Process with 4 workers (recommended for most systems)
docker run --rm \
  --cpus=4 \
  -v ~/.aws:/root/.aws \
  --env-file .env \
  fpe-pii-detector detect-fpe-imageset --workers 4 326

# Process with 8 workers and smaller batch size (for powerful systems)
docker run --rm \
  --cpus=8 \
  -v ~/.aws:/root/.aws \
  --env-file .env \
  fpe-pii-detector detect-fpe-imageset --workers 8 --batch-size 50 326
```

**Docker-Specific Considerations:**
- Use `--cpus=N` to limit container CPU usage
- Use `--memory=N` (e.g. `--memory=4g`) to limit container memory usage
- For memory-constrained environments, reduce batch size with `--batch-size`
- In AWS Batch, set resource requirements to match your worker count

### AWS ECR Deployment

To deploy the container to Amazon ECR:

1. Set environment variables:

```sh
export IMAGE_NAME=fpe-pii-detector
export AWS_ACCOUNT=<your-account-number>
export AWS_REGION=<your-region>
export AWS_REPO=${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com/${IMAGE_NAME}
```

2. Log in to Amazon ECR:

```sh
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${AWS_REPO}
```

3. Build and tag the image:

```sh
# For Intel/AMD architectures
docker build -t fpe-pii-detector .

# For Apple Silicon (M1+) Macs
docker buildx build --platform=linux/amd64 -t fpe-pii-detector .

docker tag fpe-pii-detector:latest ${AWS_REPO}:latest
```

4. Push the image:

```sh
docker push ${AWS_REPO}:latest
```

### Running Tests in Docker

The Docker image already includes the test files as shown in the Dockerfile. To run the tests in Docker:

```sh
docker run --rm --entrypoint python fpe-pii-detector /app/tests/run_tests.py
```

## AWS Batch Execution

When running in AWS Batch, the container will use the environment variables provided in the batch job definition. The entrypoint script will be executed with the command and arguments specified in the job parameters.

Example job parameters:
```json
{
  "command": ["detect-fpe-imageset", "326"]
}
```

## Development

### Code Formatting

This project uses [Black](https://github.com/psf/black) for code formatting:

```sh
# Install Black
pip install black

# Format all Python files
black .
```

## License

The code in this repository is released to the public domain under the [CC0 1.0 Universal license](https://creativecommons.org/publicdomain/zero/1.0/). See [LICENSE](LICENSE) for details.
