"""Configuration for the scheduler service."""

import os

from dotenv import load_dotenv

from aci.common.utils import check_and_get_env_variable, construct_db_url

load_dotenv()

# Database configuration (reuse CLI config pattern)
DB_SCHEME = check_and_get_env_variable("CLI_DB_SCHEME")
DB_USER = check_and_get_env_variable("CLI_DB_USER")
DB_PASSWORD = check_and_get_env_variable("CLI_DB_PASSWORD")
DB_HOST = check_and_get_env_variable("CLI_DB_HOST")
DB_PORT = check_and_get_env_variable("CLI_DB_PORT")
DB_NAME = check_and_get_env_variable("CLI_DB_NAME")
DB_FULL_URL = construct_db_url(DB_SCHEME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)

# OpenAI configuration for LLM validation
OPENAI_API_KEY = check_and_get_env_variable("CLI_OPENAI_API_KEY")

# Schema fix scheduler configuration
# Cron schedule for processing pending fixes (default: every hour at minute 0)
SCHEMA_FIX_CRON_SCHEDULE = os.getenv("SCHEDULER_SCHEMA_FIX_CRON", "0 * * * *")

# Whether to automatically apply high-confidence fixes
SCHEMA_FIX_AUTO_APPLY = os.getenv("SCHEDULER_SCHEMA_FIX_AUTO_APPLY", "true").lower() == "true"

# Maximum number of fixes to process per run
SCHEMA_FIX_BATCH_SIZE = int(os.getenv("SCHEDULER_SCHEMA_FIX_BATCH_SIZE", "50"))

# Minimum occurrence count before processing a fix
SCHEMA_FIX_MIN_OCCURRENCES = int(os.getenv("SCHEDULER_SCHEMA_FIX_MIN_OCCURRENCES", "1"))
