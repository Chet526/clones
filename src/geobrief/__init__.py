"""GeoBrief LE — local-first investigator location evidence processor.

Phase 1 prototype: turn messy CSV/XLSX location records into a cleaned,
validated, hashed data set with a map, a cleaned spreadsheet, and a JSON
processing summary.
"""

from .assistant import Assistant, AssistantConfig, build_context
from .pipeline import ProcessingResult, process_dataframe, process_file
from .subscription import PLANS, Feature, Plan, current_plan, plan_allows

__all__ = [
    "process_file",
    "process_dataframe",
    "ProcessingResult",
    "Assistant",
    "AssistantConfig",
    "build_context",
    "Plan",
    "PLANS",
    "Feature",
    "current_plan",
    "plan_allows",
    "__version__",
]

__version__ = "0.1.0"
