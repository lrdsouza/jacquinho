'''Runtime settings, read once from the environment.'''

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    '''Everything the MCP servers need to know about their environment.'''

    spreadsheet_path: Path
    top_up_budget: float
    platform_fee: float
    city: str
    state: str
    ibge_locality: str
    redis_url: str
    postgres_dsn: str
    host: str
    port: int
    search_provider: str
    brave_api_key: str

    @classmethod
    def from_env(cls) -> 'Settings':
        return cls(
            spreadsheet_path=Path(
                os.environ.get('PANTRY_XLSX', '/data/despensa_dona_maria.xlsx')
            ),
            top_up_budget=float(os.environ.get('TOP_UP_BUDGET', '80')),
            platform_fee=float(os.environ.get('PLATFORM_FEE', '0.10')),
            city=os.environ.get('LOCALE_CITY', 'Sao Paulo'),
            state=os.environ.get('LOCALE_STATE', 'SP'),
            # IBGE IPCA area code. N7[3501] is metropolitan Sao Paulo; the
            # aggregate lists no localities of its own, but accepts the code.
            ibge_locality=os.environ.get('IBGE_LOCALITY', 'N7[3501]'),
            redis_url=os.environ.get('REDIS_URL', 'redis://redis:6379/0'),
            postgres_dsn=os.environ.get(
                'POSTGRES_DSN',
                'postgresql://jacquinho:jacquinho@postgres:5432/jacquinho',
            ),
            host=os.environ.get('MCP_HOST', '0.0.0.0'),
            port=int(os.environ.get('MCP_PORT', '8000')),
            search_provider=os.environ.get('SEARCH_PROVIDER', 'auto').lower(),
            brave_api_key=os.environ.get('BRAVE_API_KEY', ''),
        )
