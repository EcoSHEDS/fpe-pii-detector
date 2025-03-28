#!/usr/bin/env python3
"""
Test runner for FPE PII Detector tests.
Run this script to execute all tests in the tests directory.
"""

import unittest
import sys
import os
import logging

# Add the parent directory to the path so we can import the fpe_pii_detector package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Disable logs during tests
logging.disable(logging.CRITICAL)

if __name__ == "__main__":
    # Discover and run all tests
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover("tests", pattern="test_*.py")

    # Run tests
    test_runner = unittest.TextTestRunner(verbosity=2)
    result = test_runner.run(test_suite)

    # Return non-zero exit code if any tests failed
    sys.exit(not result.wasSuccessful())
