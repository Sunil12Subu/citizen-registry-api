"""Fill the development database with synthetic citizens for demos.

Usage:
    uv run python scripts/seed_data.py              # 100 citizens
    uv run python scripts/seed_data.py --count 500

Everything goes through the normal service layer, so seeded records are hashed, masked
and audited exactly like records created through the API.

Privacy notes:
- Names are generic, emails use example.com (a domain reserved for examples), and
  mobile numbers are left empty: a random 10-digit number could belong to a real person.
- Aadhaar numbers are random digits that only pass the format checksum. They are hashed
  on save and never printed.
"""

import argparse
import random
import sys
from datetime import date, timedelta

from citizen_registry_api.config import get_settings
from citizen_registry_api.db import SessionLocal
from citizen_registry_api.errors import ConflictError
from citizen_registry_api.schemas import CitizenCreate
from citizen_registry_api.security import verhoeff_check_digit
from citizen_registry_api.services.citizens import create_citizen

FIRST_NAMES = [
    "Priya",
    "Arun",
    "Kavya",
    "Karthik",
    "Divya",
    "Suresh",
    "Meena",
    "Vignesh",
    "Lakshmi",
    "Rajesh",
    "Anitha",
    "Senthil",
    "Deepa",
    "Murugan",
    "Revathi",
    "Bala",
]
LAST_NAMES = [
    "Raman",
    "Kumar",
    "Subramaniam",
    "Krishnan",
    "Natarajan",
    "Venkatesh",
    "Sundaram",
    "Rajendran",
    "Ganesan",
    "Pandian",
    "Selvam",
    "Iyer",
]
DISTRICTS = [
    "Chennai",
    "Coimbatore",
    "Madurai",
    "Tiruchirappalli",
    "Salem",
    "Tirunelveli",
    "Erode",
    "Vellore",
    "Thanjavur",
    "Thoothukudi",
    "Kanchipuram",
    "Dindigul",
]

# random (not secrets) is fine here: this is demo data, not security-sensitive values.
# A fixed seed makes every run produce the same data, which helps when demoing.
rng = random.Random(2026)  # noqa: S311


def synthetic_aadhaar() -> str:
    first11 = str(rng.randint(2, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(10))
    return first11 + verhoeff_check_digit(first11)


def synthetic_citizen(index: int) -> CitizenCreate:
    first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
    birth = date(1950, 1, 1) + timedelta(days=rng.randint(0, 365 * 55))
    return CitizenCreate(
        full_name=f"{first} {last}",
        date_of_birth=birth,
        district=rng.choice(DISTRICTS),
        email=f"{first.lower()}.{last.lower()}.{index}@example.com",
        aadhaar=synthetic_aadhaar(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--count", type=int, default=100, help="how many citizens to create")
    args = parser.parse_args()

    settings = get_settings()
    if settings.app_env == "production":
        print("Refusing to seed: APP_ENV is 'production'.")
        return 1

    secret = settings.id_hash_secret.get_secret_value()
    created = skipped = 0
    with SessionLocal() as session:
        for i in range(args.count):
            try:
                create_citizen(session, synthetic_citizen(i), actor="seed-script", secret=secret)
                created += 1
            except ConflictError:
                skipped += 1  # same synthetic Aadhaar already in the database (e.g. a re-run)

    print(f"Created {created} citizens, skipped {skipped} duplicates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
