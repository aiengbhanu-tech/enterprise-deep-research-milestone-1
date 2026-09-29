from app.core.config import Settings


def test_default_research_limits() -> None:
    settings = Settings(_env_file=None)
    assert settings.research_max_iterations == 3
    assert settings.research_default_budget_usd == 2.0
