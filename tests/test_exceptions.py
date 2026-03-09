"""Tests for dlightclient exceptions."""

import unittest
from dlightclient.exceptions import (
    DLightError,
    DLightConnectionError,
    DLightTimeoutError,
    DLightCommandError,
    DLightResponseError,
)


class TestExceptions(unittest.TestCase):
    """Test the exception hierarchy."""

    def test_dlight_error(self):
        """Test DLightError instantiation and hierarchy."""
        error = DLightError("test error")
        self.assertIsInstance(error, Exception)
        self.assertEqual(str(error), "test error")

    def test_connection_error(self):
        """Test DLightConnectionError instantiation and hierarchy."""
        error = DLightConnectionError("connection error")
        self.assertIsInstance(error, DLightError)
        self.assertEqual(str(error), "connection error")

    def test_timeout_error(self):
        """Test DLightTimeoutError instantiation and hierarchy."""
        error = DLightTimeoutError("timeout error")
        self.assertIsInstance(error, DLightConnectionError)
        self.assertIsInstance(error, DLightError)
        self.assertEqual(str(error), "timeout error")

    def test_command_error(self):
        """Test DLightCommandError instantiation and hierarchy."""
        error = DLightCommandError("command error")
        self.assertIsInstance(error, DLightError)
        self.assertEqual(str(error), "command error")

    def test_response_error(self):
        """Test DLightResponseError instantiation and hierarchy."""
        error = DLightResponseError("response error")
        self.assertIsInstance(error, DLightError)
        self.assertEqual(str(error), "response error")
