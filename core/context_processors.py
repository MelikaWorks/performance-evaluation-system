# core/context_processors.py
# ======================================================
# Global context processor to expose constants in templates
# ======================================================

from core.constants import Settings  # ← این خط لازمه
from datetime import datetime

def global_settings(request):
    """
    Adds global constants to all templates automatically.
    Accessible in templates as {{ COMPANY_NAME }} or {{ COPYRIGHT_FOOTER }}
    """
    return {
        'COMPANY_NAME': Settings.COMPANY_NAME,
        'COPYRIGHT_FOOTER': Settings.COPYRIGHT_FOOTER,
        "CURRENT_YEAR": datetime.now().year,  # سال جاری به صورت داینامیک
        "CURRENT_PERIOD": datetime.now().strftime("%Y-%m"),  # دوره فعلی (مثلاً 2025-11)
    }
