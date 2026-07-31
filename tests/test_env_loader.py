import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add codebase directory to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
CODEBASE_DIR = ROOT_DIR / "codebase"
if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))

from env_loader import load_dotenv, load_env


class TestEnvLoader(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_load_dotenv_basic(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("# Comment line\n")
            f.write("TEST_KEY_1=value1\n")
            f.write("TEST_KEY_2=\"value2\"\n")
            f.write("TEST_KEY_3='value3'\n")
            f.write("  TEST_KEY_4  =  value4  \n")
            f.write("INVALID_LINE_NO_EQUALS\n")
            f.write("\n")
            temp_path = Path(f.name)

        try:
            load_dotenv(temp_path)
            self.assertEqual(os.environ.get("TEST_KEY_1"), "value1")
            self.assertEqual(os.environ.get("TEST_KEY_2"), "value2")
            self.assertEqual(os.environ.get("TEST_KEY_3"), "value3")
            self.assertEqual(os.environ.get("TEST_KEY_4"), "value4")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_load_dotenv_no_override_by_default(self):
        os.environ["EXISTING_KEY"] = "original_val"
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("EXISTING_KEY=new_val\n")
            temp_path = Path(f.name)

        try:
            load_dotenv(temp_path, override=False)
            self.assertEqual(os.environ.get("EXISTING_KEY"), "original_val")

            load_dotenv(temp_path, override=True)
            self.assertEqual(os.environ.get("EXISTING_KEY"), "new_val")
        finally:
            if temp_path.exists():
                temp_path.unlink()

    def test_load_dotenv_nonexistent_file(self):
        non_existent = Path("non_existent_file_path_12345.env")
        # Should not raise exception
        load_dotenv(non_existent)

    def test_load_env_external_override(self):
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            f.write("CUSTOM_ENV_VAR=from_custom_file\n")
            temp_path = Path(f.name)

        try:
            os.environ["QA_ENV_FILE"] = str(temp_path)
            load_env()
            self.assertEqual(os.environ.get("CUSTOM_ENV_VAR"), "from_custom_file")
        finally:
            if temp_path.exists():
                temp_path.unlink()


if __name__ == "__main__":
    unittest.main()
