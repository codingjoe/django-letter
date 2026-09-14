"""HTML emails via Django templates."""

from . import _version
from .message import TemplateEmail

__version__ = _version.version
VERSION = _version.version_tuple

__all__ = ["VERSION", "TemplateEmail", "__version__"]
