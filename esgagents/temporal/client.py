from __future__ import annotations

from temporalio.client import Client

from .models import TemporalSettings


async def create_temporal_client(
    settings: TemporalSettings,
    *,
    lazy: bool = False,
) -> Client:
    return await Client.connect(
        settings.address,
        namespace=settings.namespace,
        api_key=settings.api_key or None,
        tls=settings.tls,
        lazy=lazy,
    )
