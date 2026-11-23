"""
Optional API smoke test for the Airbnb red-teaming experiment.

This script checks whether the project's configured Anthropic and
OpenAI models can successfully process a small API request.

It uses the API adapter functions defined in model_clients.py,
which are also used by the main experiment.

The test verifies that:
- The configured API credentials allow requests to be made.
- The selected model identifiers are accessible.
- Both APIs can return responses that are parsed as valid JSON.
- The response metadata includes the model identifier.

This is a smoke test rather than a comprehensive API validation.
It does not evaluate summarization quality, claim-judging accuracy,
or the complete evidence-grounding workflow.

IMPORTANT:
Running this script makes two real, PAID API requests:
one to Anthropic and one to OpenAI.

Although the requests are intentionally small, they may incur
API charges. Importing this script does not run the tests.
"""

from __future__ import annotations

# Import the API adapter functions used throughout the experiment.
#
# claude_json() sends a request to the configured Claude model.
# openai_json() sends a request to the configured OpenAI judge model.
#
# Both functions:
# - Check whether the relevant API key is configured.
# - Send the request using the provider's API.
# - Parse the response as JSON.
# - Return the parsed result, raw response, request ID,
#   and token usage metadata.
#
# The model identifiers and credentials are configured through
# model_clients.py and the project's environment variables.
from model_clients import claude_json, openai_json

# Execute the smoke test only when this file is run directly.
#
# This prevents the API requests from being triggered automatically
# if another Python module imports this script.
if __name__ == "__main__":

    # Inform the user that the script is about to send
    # two real API requests that may incur charges.
    #
    # This message is informational; it does not ask for
    # confirmation before proceeding.
    print("Sending two small PAID API requests to verify model access...")

    # Test the configured Anthropic model.
    #
    # claude_json() accepts:
    # 1. System instructions defining the model's task.
    # 2. A user-message payload containing the request.
    # 3. An optional maximum output-token limit.
    #
    # The system instruction asks for valid JSON, while the
    # user message requests a simple JSON object:
    #
    # {"ok": true}
    #
    # max_tokens=120 keeps the output allowance small because
    # the expected response is only a short JSON object.
    #
    # The function returns four values:
    # - Parsed JSON response.
    # - Raw response text.
    # - API request ID.
    # - Usage metadata.
    #
    # Only the parsed response and metadata are needed here.
    # The two underscores discard the other returned values.
    #
    # This is the first paid API request.
    claude, _, _, meta = claude_json(
        "Return only valid JSON.", 'Reply with {"ok": true}', max_tokens=120
    )

    # Display the parsed Claude response and the model
    # identifier reported by the API.
    #
    # A successful response should resemble:
    # Anthropic: {'ok': True} model: <configured model>
    #
    # Python displays JSON true as True after parsing.
    #
    # The model identifier helps confirm which model
    # actually processed the request.
    #
    # Note that the script prints the response but does not
    # explicitly assert that the "ok" field equals True.
    print("Anthropic:", claude, "model:", meta["model_returned"])

    # Test the configured OpenAI judge model.
    #
    # This follows the same basic approach as the Claude test:
    # request a small JSON object and verify that the API
    # adapter can parse the returned response.
    #
    # max_output_tokens=180 limits the output-token allowance.
    # The limit is slightly larger than Claude's allowance
    # because some OpenAI models may use reasoning tokens
    # in addition to visible output tokens.
    #
    # As before, the raw response and request ID are not
    # needed for this basic connectivity test.
    #
    # This is the second paid API request.
    judge, _, _, meta = openai_json(
        "Return only valid JSON.", 'Reply with {"ok": true}', max_output_tokens=180
    )

    # Display the parsed OpenAI response and the model
    # identifier returned by the API.
    #
    # A successful response should resemble:
    # OpenAI: {'ok': True} model: <configured model>
    #
    # If both requests finish without exceptions, the
    # configured models have demonstrated basic API access
    # and JSON response parsing.
    print("OpenAI:", judge, "model:", meta["model_returned"])
