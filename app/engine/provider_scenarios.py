"""Small provider smoke scenarios; not a quality or security benchmark."""
from app.engine.scenarios import EvaluationCase, EvaluationScenario


OPENROUTER_SMOKE_SCENARIO = EvaluationScenario(
    name="openrouter_smoke",
    description=(
        "Verifies provider connectivity and basic instruction following. "
        "A pass is not evidence of general model quality or security."
    ),
    cases=(
        EvaluationCase(
            case_id="exact_token_response",
            input=(
                "For this connectivity test, reply with exactly this token and "
                "nothing else: COGNIS_OK"
            ),
            expected_output="COGNIS_OK",
            tags=("provider-smoke", "instruction-following"),
        ),
    ),
)
