"""
API adapters for the Airbnb review-summarization experiment.

This module provides two functions:
- claude_json(): Sends requests to Claude, which is used for
  the summarization experiments.
- openai_json(): Sends requests to an OpenAI model, which is
  used for evaluating generated summaries.

Both functions return four values:
    (parsed_json, raw_text, request_id, usage_metadata)

Keeping API interactions in one module ensures that model settings,
response parsing, and usage tracking are handled consistently
throughout the project.

Importing this module does not send any API requests. Requests are
made only when claude_json() or openai_json() is called.

However, importing the module does load environment variables
from the project's .env file.
"""

from __future__ import annotations

# Provides access to environment variables, including API keys
# and optional model configuration settings.
import os

# Used to locate the project's .env file regardless of the
# directory from which the experiment is executed.
from pathlib import Path

# Loads configuration values from a .env file into the environment.
from dotenv import load_dotenv

# Shared helper that converts a model's JSON response text
# into Python data structures.
#
# It also handles responses wrapped in Markdown code fences.
from experiment_common import parse_json_reply

# Load environment variables from the .env file in the project root.
#
# __file__ refers to model_clients.py.
# resolve() converts it to an absolute path.
# parents[1] moves up from src/ to the project root.
#
# This allows API keys and model settings to be configured outside
# the source code, avoiding the need to hardcode credentials.
#
# By default, load_dotenv() does not overwrite variables that
# are already defined in the environment.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# Model used for Claude API requests.
#
# The ANTHROPIC_MODEL environment variable can override the default.
# If it is not set, the script uses "claude-sonnet-5-5".
#
# This makes it possible to change models without editing the
# experiment code, although the selected model must be available
# through the API and support the requested parameters.
CLAUDE_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")


# Model used for the OpenAI-based claim evaluation.
#
# The judge is separate from the summarization system so that
# generated claims can be evaluated using another model.
#
# The OPENAI_JUDGE_MODEL environment variable can override
# the default model identifier.
OPENAI_JUDGE_MODEL = os.getenv("OPENAI_JUDGE_MODEL", "gpt-6.2-astra")


# Reasoning effort setting for Claude requests.
#
# The default is "medium", but it can be changed through
# the ANTHROPIC_EFFORT environment variable.
#
# The code below passes this value through output_config.
# Whether a particular effort setting is supported depends
# on the model and API configuration.
CLAUDE_EFFORT = os.getenv("ANTHROPIC_EFFORT", "medium")


def claude_json(system, payload, max_tokens=3500):
    """
    Send a request to Claude and parse its response as JSON.

    Parameters
    ----------
    system : str
        System instructions that define Claude's task and
        expected response format.

        For example, this may contain instructions for evidence
        extraction, evidence selection, or grounded generation.

    payload : str
        The user-message content sent to Claude.

        In this project, payloads are generally serialized JSON
        containing reviews, evidence, or selected claims.

    max_tokens : int, default 3500
        Maximum number of output tokens allowed for the response.

    Returns
    -------
    tuple
        parsed : Python object
            Claude's response converted from JSON.

        raw : str
            Original response text before JSON parsing.

        request_id : str
            Identifier assigned to the API response.

        metadata : dict
            Model identifier and token usage information.

    Notes
    -----
    This function makes a real API request.

    It checks for a configured API key before sending the request,
    but it does not verify the key's validity beforehand.

    The function expects Claude to return valid JSON. It does
    not independently enforce a specific JSON schema.
    """

    # Check whether an Anthropic API key is available.
    #
    # os.getenv() returns the variable's value if it exists,
    # or None if it is missing.
    #
    # This prevents an unnecessary API request when no key
    # has been configured.
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is missing. "
            "Copy .env.example to .env and configure it."
        )

    # Import the Anthropic client only when the function is called.
    #
    # This allows the module itself to be imported without
    # immediately initializing the client.
    from anthropic import Anthropic

    # Assemble the parameters for the Claude API request.
    #
    # model identifies the model to use.
    # max_tokens limits the output length.
    # system provides the task instructions.
    # messages contains the actual input to be processed.
    #
    # The payload is sent as a user message, while the
    # task-specific instructions are supplied separately.
    kwargs = dict(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": payload,
            }
        ],
    )

    # Sampling parameters such as temperature are intentionally
    # omitted from the request.
    #
    # This avoids introducing additional generation settings
    # beyond those explicitly configured for the experiment.
    #
    # However, omitting sampling parameters does not guarantee
    # that repeated requests will produce identical outputs.
    #
    # If effort is set to "none", "off", or an empty string,
    # the output_config parameter is not included.
    #
    # Otherwise, the configured effort level is passed to Claude.
    # The requested model must support this parameter.
    if CLAUDE_EFFORT.lower() not in (
        "none",
        "off",
        "",
    ):
        kwargs["output_config"] = {"effort": CLAUDE_EFFORT}

    # Send the request to Claude.
    #
    # This is the point where the API call actually occurs.
    #
    # The response may include text blocks, usage information,
    # a model identifier, a stop reason, and a request ID.
    #
    # API-level errors, such as authentication failures or
    # rate limits, are not caught here and will propagate
    # to the calling code.
    response = Anthropic().messages.create(**kwargs)

    # Extract text from the response's content blocks.
    #
    # Claude responses can contain different types of blocks.
    # Only blocks with type="text" are included.
    #
    # If multiple text blocks are present, they are joined
    # with newline characters into one response string.
    #
    # Non-text blocks are excluded from JSON parsing.
    raw = "\n".join(
        block.text
        for block in response.content
        if getattr(block, "type", None) == "text"
    )

    # Retrieve the usage object if it is available.
    #
    # getattr() avoids raising an AttributeError when the
    # expected attribute is absent.
    usage = getattr(response, "usage", None)

    # Preserve model and token usage information.
    #
    # Recording the model returned by the API helps document
    # which model actually processed the request.
    #
    # Input and output token counts can be used to estimate
    # computational usage and API costs.
    #
    # Cache-related fields record token counts associated
    # with prompt caching when the API provides them.
    #
    # Missing usage fields are stored as None.
    metadata = {
        "model_returned": getattr(response, "model", CLAUDE_MODEL),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_creation_input_tokens": getattr(
            usage, "cache_creation_input_tokens", None
        ),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
    }

    # Check whether Claude stopped because it reached the
    # maximum number of output tokens.
    #
    # A truncated response may contain incomplete JSON or
    # omit evidence that the model intended to return.
    #
    # Rather than accepting a potentially incomplete result,
    # the function raises an error.
    #
    # The message recommends reducing the extraction batch size,
    # although the token limit could also be reached during
    # another stage of the summarization pipeline.
    if response.stop_reason == "max_tokens":
        raise RuntimeError(
            "Claude reached the output-token limit before completing "
            "its response. Reduce the extraction batch size."
        )

    # Convert Claude's response text into Python data.
    #
    # parse_json_reply() removes common Markdown JSON fences
    # before calling json.loads().
    #
    # Valid JSON is required because later stages expect
    # structured evidence, claims, or summary fields.
    try:
        parsed = parse_json_reply(raw)

    # If the response cannot be parsed, raise a more informative
    # error containing metadata useful for debugging.
    #
    # The error reports:
    # - The API request ID.
    # - The reason Claude stopped generating.
    # - The length of the returned text.
    #
    # It deliberately does not print the full response.
    #
    # "from exc" preserves the original parsing error as
    # the underlying cause of the new exception.
    except ValueError as exc:
        raise RuntimeError(
            "Claude returned invalid JSON. "
            f"Request ID: {getattr(response, 'id', 'unknown')}. "
            f"Stop reason: {response.stop_reason}. "
            f"Response length: {len(raw)} characters."
        ) from exc

    # Return the parsed data together with the original response,
    # request ID, and usage metadata.
    #
    # The calling code can use the parsed result immediately
    # while retaining the other information for later auditing.
    return (parsed, raw, getattr(response, "id", ""), metadata)


def openai_json(system, payload, max_output_tokens=5000):
    """
    Send a request to an OpenAI model and parse its response as JSON.

    Parameters
    ----------
    system : str
        Instructions defining the evaluation task.

        In this project, these may include the criteria used
        to judge whether generated claims are supported by
        the supplied reviews.

    payload : str
        Content to be evaluated, generally containing
        claims and relevant review evidence.

    max_output_tokens : int, default 5000
        Maximum number of output tokens for the response.

    Returns
    -------
    tuple
        parsed : Python object
            Parsed JSON response.

        raw : str
            Original response text.

        request_id : str
            API response identifier.

        metadata : dict
            Model identifier and token usage information.

    Notes
    -----
    This function uses OpenAI's Responses API.

    It does not make requests until explicitly called.

    The function expects valid JSON but does not independently
    verify the correctness of the judge's conclusions.
    """

    # Confirm that an OpenAI API key is available.
    #
    # This only checks whether the environment variable has
    # a nonempty value. It does not validate the credential.
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing. " "Copy .env.example to .env and configure it."
        )

    # Import the OpenAI client when needed.
    #
    # Keeping the import inside the function means importing
    # model_clients.py does not initialize this client.
    from openai import OpenAI

    # Send the evaluation request using the Responses API.
    #
    # model specifies the judge model.
    # instructions contains the evaluation criteria.
    # input contains the material being evaluated.
    # max_output_tokens limits the response length.
    #
    # This is the point where the OpenAI API request occurs.
    #
    # The request does not explicitly specify a structured
    # JSON response schema, so JSON formatting depends on
    # the model following the supplied instructions.
    response = OpenAI().responses.create(
        model=OPENAI_JUDGE_MODEL,
        instructions=system,
        input=payload,
        max_output_tokens=max_output_tokens,
    )

    # Retrieve the text portion of the response.
    #
    # output_text is a convenience property that combines
    # text output from the response.
    #
    # The returned text is expected to contain valid JSON.
    raw = response.output_text

    # Retrieve usage information, if available.
    usage = getattr(response, "usage", None)

    # Record the model used and the number of tokens consumed.
    #
    # output_token_details may contain additional information
    # about output token usage, including reasoning tokens
    # when the model reports them.
    #
    # model_dump() converts the SDK's structured usage object
    # into a regular Python dictionary.
    #
    # The fallback lambda returns None if the expected
    # object or method is unavailable.
    metadata = {
        "model_returned": getattr(response, "model", OPENAI_JUDGE_MODEL),
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "output_token_details": getattr(
            getattr(usage, "output_tokens_details", None), "model_dump", lambda: None
        )(),
    }

    # Parse the judge's response as JSON.
    #
    # Unlike claude_json(), this function does not wrap
    # JSON parsing failures in a custom RuntimeError.
    #
    # If the response is malformed, the original parsing
    # exception propagates to the calling code.
    #
    # The function also does not explicitly check whether
    # the response ended because of an output-token limit.
    #
    # These differences are worth remembering when debugging
    # failures across the two API adapters.
    return (parse_json_reply(raw), raw, response.id, metadata)
