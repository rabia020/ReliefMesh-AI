"""Central place for reading settings from environment variables.

Every other file imports settings from here, so secrets never
get hard-coded in the source code.
"""

import os

from dotenv import load_dotenv

# Reads the .env file (if it exists) into environment variables.
load_dotenv()

APP_NAME = "ReliefMesh AI"
APP_VERSION = "0.1.0"

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DATABASE_PATH = os.getenv("DATABASE_PATH", "data/reliefmesh.db")

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

SAFETY_DISCLAIMER = (
    "ReliefMesh AI is a decision-support prototype using SIMULATED data. "
    "It does not replace emergency services, doctors, rescue professionals, "
    "or government authorities."
)