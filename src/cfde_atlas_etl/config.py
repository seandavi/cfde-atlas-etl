"""Runtime configuration. Reads from environment (and .env in dev)."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()


class Settings(BaseModel):
    database_url: str = Field(..., description="Postgres connection string")
    icc_eval_core_ref: str = Field("main", description="icc-eval-core git ref to pull from")
    icc_eval_core_base_url: str = Field(
        "https://raw.githubusercontent.com/nih-cfde/icc-eval-core",
        description="Raw GitHub base URL for icc-eval-core",
    )

    @property
    def icc_eval_core_output_url(self) -> str:
        """Resolved base URL for /data/output/*.json files at the configured ref."""
        return f"{self.icc_eval_core_base_url}/{self.icc_eval_core_ref}/data/output"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        icc_eval_core_ref=os.environ.get("ICC_EVAL_CORE_REF", "main"),
        icc_eval_core_base_url=os.environ.get(
            "ICC_EVAL_CORE_BASE_URL",
            "https://raw.githubusercontent.com/nih-cfde/icc-eval-core",
        ),
    )
