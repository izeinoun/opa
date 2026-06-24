"""
verify_env.py — Check all required environment variables and connectivity.

Usage:
    cd server
    python verify_env.py
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = "  PASS" if ok else "  FAIL"
    line = f"{status}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


async def check_db() -> bool:
    try:
        from app.config import settings
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text

        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception as e:
        _check("DATABASE_URL (connect)", False, str(e))
        return False


def check_aws() -> bool:
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity", "--output", "text", "--query", "Account"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            account = result.stdout.strip()
            return _check("AWS credentials (sts get-caller-identity)", True, f"account={account}")
        else:
            return _check("AWS credentials (sts get-caller-identity)", False, result.stderr.strip())
    except FileNotFoundError:
        return _check("AWS credentials", False, "aws CLI not found")
    except subprocess.TimeoutExpired:
        return _check("AWS credentials", False, "timeout")


async def main() -> int:
    from dotenv import load_dotenv
    load_dotenv()

    print("\n" + "=" * 60)
    print("  OPA Environment Verification")
    print("=" * 60)

    results: list[bool] = []

    # DATABASE_URL
    db_ok = await check_db()
    results.append(_check("DATABASE_URL (connect)", db_ok))

    # ANTHROPIC_API_KEY
    key = os.getenv("ANTHROPIC_API_KEY", "")
    results.append(_check("ANTHROPIC_API_KEY", bool(key), "set" if key else "NOT SET"))

    # AWS credentials
    results.append(check_aws())

    # LANGFUSE
    lf_pub = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    lf_sec = os.getenv("LANGFUSE_SECRET_KEY", "")
    results.append(_check("LANGFUSE_PUBLIC_KEY", bool(lf_pub), "set" if lf_pub else "NOT SET"))
    results.append(_check("LANGFUSE_SECRET_KEY", bool(lf_sec), "set" if lf_sec else "NOT SET"))

    # HIGH_DOLLAR_THRESHOLD (optional; defaults to 2000 in config)
    thr_raw = os.getenv("HIGH_DOLLAR_THRESHOLD", "")
    if thr_raw:
        try:
            thr_val = float(thr_raw)
            results.append(_check("HIGH_DOLLAR_THRESHOLD", thr_val > 0, f"${thr_val:,.0f}"))
        except ValueError:
            results.append(_check("HIGH_DOLLAR_THRESHOLD", False, f"not a number: {thr_raw!r}"))
    else:
        results.append(_check("HIGH_DOLLAR_THRESHOLD", True, "unset → default $2,000"))

    # ML_MODELS_DIR
    ml_dir = os.getenv("ML_MODELS_DIR", "./ml_models")
    try:
        Path(ml_dir).mkdir(parents=True, exist_ok=True)
        results.append(_check("ML_MODELS_DIR", True, ml_dir))
    except Exception as e:
        results.append(_check("ML_MODELS_DIR", False, str(e)))

    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"  {passed}/{total} checks passed")
    print("=" * 60 + "\n")

    critical_failed = not results[0]  # DB is critical
    return 1 if critical_failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
