"""ATS provider registry — add a new adapter here to make it available."""

from __future__ import annotations

import aiohttp

from core.models import ATSProvider
from core.provider_base import BaseProvider
from providers.amd import AMDProvider
from providers.amazon import AmazonProvider
from providers.apple import AppleProvider
from providers.ashby import AshbyProvider
from providers.eightfold import EightfoldProvider
from providers.google import GoogleProvider
from providers.greenhouse import GreenhouseProvider
from providers.icims import ICIMSProvider
from providers.jobvite import JobviteProvider
from providers.lever import LeverProvider
from providers.oracle import OracleProvider
from providers.smartrecruiters import SmartRecruitersProvider
from providers.successfactors import SuccessFactorsProvider
from providers.taleo import TaleoProvider
from providers.uber import UberProvider
from providers.workday import WorkdayProvider

PROVIDER_CLASSES: dict[ATSProvider, type[BaseProvider]] = {
    ATSProvider.GREENHOUSE: GreenhouseProvider,
    ATSProvider.LEVER: LeverProvider,
    ATSProvider.ASHBY: AshbyProvider,
    ATSProvider.WORKDAY: WorkdayProvider,
    ATSProvider.SMARTRECRUITERS: SmartRecruitersProvider,
    ATSProvider.JOBVITE: JobviteProvider,
    ATSProvider.ICIMS: ICIMSProvider,
    ATSProvider.ORACLE: OracleProvider,
    ATSProvider.SUCCESSFACTORS: SuccessFactorsProvider,
    ATSProvider.EIGHTFOLD: EightfoldProvider,
    ATSProvider.TALEO: TaleoProvider,
    ATSProvider.GOOGLE: GoogleProvider,
    ATSProvider.AMAZON: AmazonProvider,
    ATSProvider.UBER: UberProvider,
    ATSProvider.AMD: AMDProvider,
    ATSProvider.APPLE: AppleProvider,
}


def build_providers(session: aiohttp.ClientSession) -> dict[str, BaseProvider]:
    """Instantiate all registered providers sharing one aiohttp session."""
    return {
        provider.value: cls(session) for provider, cls in PROVIDER_CLASSES.items()
    }


__all__ = ["PROVIDER_CLASSES", "build_providers"]
