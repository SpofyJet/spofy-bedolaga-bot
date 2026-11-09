import pytest


pytestmark = pytest.mark.postgres


class PanelBoundary(BaseException):
    pass
