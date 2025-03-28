import os
import boto3
import json
import logging
import pandas as pd
from sqlalchemy import (
    create_engine,
    text,
    Table,
    MetaData,
    Column,
    Integer,
    Float,
    JSON,
)
from .utils import convert_fpe_detections_to_db_format

logger = logging.getLogger("fpe-pii-detector")


def get_db_credentials_from_secret(secret_name="FPE_DB_SECRET"):
    """
    Retrieve database credentials from AWS Secrets Manager.

    Args:
        secret_name (str): Name of the AWS Secrets Manager secret containing database credentials.
            Default is 'FPE_DB_SECRET'.

    Returns:
        dict: Dictionary containing database connection parameters:
            - host (str): Database host address
            - port (int): Database port number (default: 5432)
            - dbname (str): Database name (default: 'postgres')
            - user (str): Database username
            - password (str): Database password

    Raises:
        Exception: If unable to retrieve the secret or if the secret format is invalid.
    """
    try:
        logger.info(
            f"Fetching database credentials from secret (secret_name={secret_name})"
        )
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_name)
        value = json.loads(response["SecretString"])
        return {
            "host": value["host"],
            "port": value.get("port", 5432),
            "dbname": value.get("dbname", "postgres"),
            "user": value["username"],
            "password": value["password"],
        }
    except Exception as e:
        logger.error(
            f"Failed to retrieve database credentials from secret (secret_name={secret_name}): {str(e)}"
        )
        raise


def get_db_credentials_from_env():
    """
    Retrieve database credentials from environment variables.

    Looks for the following environment variables:
        - FPE_DB_HOST: Database host address
        - FPE_DB_PORT: Database port number (default: 5432)
        - FPE_DB_NAME: Database name (default: 'postgres')
        - FPE_DB_USER: Database username
        - FPE_DB_PASSWORD: Database password

    Returns:
        dict: Dictionary containing database connection parameters.

    Raises:
        Exception: If environment variables cannot be accessed.
    """
    try:
        logger.debug("Extracting database configuration from environment variables")
        config = {
            "host": os.getenv("FPE_DB_HOST"),
            "port": os.getenv("FPE_DB_PORT", 5432),
            "dbname": os.getenv("FPE_DB_NAME", "postgres"),
            "user": os.getenv("FPE_DB_USER"),
            "password": os.getenv("FPE_DB_PASSWORD"),
        }
        return config
    except Exception as e:
        logger.error(f"Failed to get database credentials from environment: {str(e)}")
        raise


def get_db_credentials():
    """
    Retrieve database credentials from either AWS Secrets Manager or environment variables.

    First checks for the FPE_DB_SECRET environment variable, and if present, uses AWS Secrets Manager.
    Otherwise, falls back to using direct environment variables for connection parameters.

    Returns:
        dict: Dictionary containing database connection parameters.

    Raises:
        Exception: If required credentials are missing or if retrieval fails.
    """
    try:
        if os.getenv("FPE_DB_SECRET"):
            config = get_db_credentials_from_secret("FPE_DB_SECRET")
        else:
            config = get_db_credentials_from_env()
        if not config["host"] or not config["user"] or not config["dbname"]:
            raise Exception(
                "Failed to get database configuration, must supply either FPE_DB_SECRET or FPE_DB_HOST, FPE_DB_PORT, FPE_DB_NAME, FPE_DB_USER, FPE_DB_PASSWORD"
            )
        return config
    except Exception as e:
        logger.error(f"Failed to get database credentials: {str(e)}")
        raise


def db_connect(config):
    """
    Create a SQLAlchemy database engine from configuration parameters.

    Args:
        config (dict): Dictionary containing database connection parameters:
            - host (str): Database host address
            - port (int): Database port number
            - dbname (str): Database name
            - user (str): Database username
            - password (str): Database password

    Returns:
        sqlalchemy.engine.Engine: Database engine object for executing SQL.

    Raises:
        Exception: If connection fails.
    """
    try:
        connstring = f'postgresql://{config["user"]}:{config["password"]}@{config["host"]}:{config["port"]}/{config["dbname"]}'
        return create_engine(connstring)
    except Exception as e:
        logger.error(f"Failed to create database connection: {str(e)}")
        raise


def fetch_imageset_images(engine, imageset_id, max_images=None):
    """
    Retrieve images associated with a specific imageset from the database.

    Args:
        engine (sqlalchemy.engine.Engine): Database engine object.
        imageset_id (int): ID of the imageset to fetch images for.
        max_images (int, optional): Maximum number of images to retrieve.
            If provided, adds a LIMIT clause to the SQL query.

    Returns:
        pandas.DataFrame: DataFrame containing image records for the specified imageset.
            Returns an empty DataFrame if no images are found.

    Raises:
        Exception: If database query fails.
    """
    try:
        query = "SELECT * FROM images WHERE imageset_id=:imageset_id"
        if max_images:
            query += f" LIMIT :max_images"
        query = text(query)
        df = pd.read_sql(
            query, engine, params={"imageset_id": imageset_id, "max_images": max_images}
        )
        if df.empty:
            logger.warning(f"No images found for imageset (imageset_id={imageset_id})")
        return df
    except Exception as e:
        logger.error(
            f"Database error fetching images for imageset (imageset_id={imageset_id}): {str(e)}"
        )
        raise


def fetch_imageset(engine, imageset_id):
    """
    Retrieve a specific imageset from the database.

    Args:
        engine (sqlalchemy.engine.Engine): Database engine object.
        imageset_id (int): ID of the imageset to fetch.

    Returns:
        dict: Dictionary containing imageset attributes, or None if not found.

    Raises:
        Exception: If database query fails.
    """
    try:
        query = text("SELECT * FROM imagesets WHERE id=:imageset_id")
        df = pd.read_sql(query, engine, params={"imageset_id": imageset_id})
        if df.empty:
            logger.warning(f"No imageset found with (imageset_id={imageset_id})")
            return None
        return df.iloc[0].to_dict()
    except Exception as e:
        logger.error(
            f"Database error fetching imageset (imageset_id={imageset_id}): {str(e)}"
        )
        raise


def update_imageset_pii_status(engine, imageset_id, status):
    """
    Update the PII processing status of an imageset.

    Args:
        engine (sqlalchemy.engine.Engine): Database engine object.
        imageset_id (int): ID of the imageset to update.
        status (str): New status value for the imageset.
            Typical values: 'PROCESSING', 'DONE', 'FAILED'

    Returns:
        bool: True if the update was successful.

    Raises:
        Exception: If database update fails.
    """
    try:
        query = text("UPDATE imagesets SET pii_status=:status WHERE id=:imageset_id")
        with engine.connect() as conn:
            conn.execute(query, {"status": status, "imageset_id": imageset_id})
            conn.commit()
        logger.debug(f"Updated imageset status to {status} (imageset_id={imageset_id})")
        return True
    except Exception as e:
        logger.error(
            f"Failed to update status for imageset (imageset_id={imageset_id}): {str(e)}"
        )
        raise


def save_results_to_database(engine, results):
    """
    Save PII detection results to the database.

    Creates a temporary table with results and then updates the images table
    with PII detection values using a SQL join operation.

    Args:
        engine (sqlalchemy.engine.Engine): Database engine object.
        results (list): List of dictionaries containing PII detection results.
            Each dictionary must contain:
            - 'image_id': ID of the image
            - Detection confidence values and bounding boxes

    Raises:
        Exception: If database operations fail.
    """
    try:
        rows = []
        for result in results:
            row = convert_fpe_detections_to_db_format(result)
            row["image_id"] = result["image_id"]
            rows.append(row)

        with engine.connect() as conn:
            metadata = MetaData()
            table = Table(
                "pii_results",
                metadata,
                Column("image_id", Integer, primary_key=True),
                Column("pii_animal", Float),
                Column("pii_person", Float),
                Column("pii_vehicle", Float),
                Column("pii_detections", JSON),
                prefixes=["TEMPORARY"],
            )
            metadata.create_all(conn)
            conn.execute(table.insert(), rows)

            update_query = text(
                """
                UPDATE images
                SET pii_animal = pii_results.pii_animal,
                    pii_person = pii_results.pii_person,
                    pii_vehicle = pii_results.pii_vehicle,
                    pii_detections = pii_results.pii_detections
                FROM pii_results
                WHERE images.id = pii_results.image_id;
            """
            )
            conn.execute(update_query)
            conn.commit()
    except Exception as e:
        logger.error(f"Failed to save results to database: {str(e)}")
        raise
