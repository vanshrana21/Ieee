"""
backend/scripts/validate_env.py
Validate .env file exists and contains required API keys.
"""
import os
from pathlib import Path

REQUIRED_KEYS = [
    "DATABASE_URL",
    "SECRET_KEY",
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY"
]


def validate_env():
    env_path = Path(".env")
    
    if not env_path.exists():
        print("❌ CRITICAL: .env file not found!")
        print("   Copy .env.example to .env and add your API keys:")
        print("   cp .env.example .env")
        print("   nano .env  # Add your actual API keys")
        return False
    
    print(f"✓ Found .env file at: {env_path.absolute()}")
    
    # Load environment
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)
    
    # Check required keys
    missing = []
    for key in REQUIRED_KEYS:
        value = os.getenv(key)
        if not value or value.strip() == "":
            missing.append(key)
        else:
            # Mask sensitive values in output
            masked = value[:4] + "..." + value[-4:] if len(value) > 8 else "****"
            print(f"✓ {key}: {masked}")
    
    if missing:
        print(f"\n❌ MISSING REQUIRED KEYS: {missing}")
        print("   Add these to your .env file")
        return False
    
    print("\n✓✓✓ ALL ENVIRONMENT VARIABLES VALID")
    return True


if __name__ == "__main__":
    import sys
    sys.exit(0 if validate_env() else 1)
