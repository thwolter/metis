from langchain_core.messages import AIMessage, BaseMessage

from agent.nodes import _retrieved_first_chunks


def _tool_call(name: str, args):
    return {'id': f'call-{name}', 'name': name, 'args': args, 'type': 'tool_call'}


def test_retrieved_first_chunks_accumulates_maximum():
    messages: list[BaseMessage | AIMessage] = [
        AIMessage(content='request', tool_calls=[_tool_call('first_chunks', {'k': 2, 'skip': 0})]),
        AIMessage(content='request', tool_calls=[_tool_call('first_chunks', {'k': 1, 'skip': 2})]),
    ]

    assert _retrieved_first_chunks(messages) == [0, 1, 2]


def test_retrieved_first_chunks_parses_string_arguments_and_ignores_other_tools():
    string_args = '{"k": 4, "skip": 3}'
    messages: list[BaseMessage | AIMessage] = [
        AIMessage(content='request', tool_calls=[_tool_call('first_chunks', {'k': 4, 'skip': 3})]),
        AIMessage(content='request', tool_calls=[_tool_call('retriever', {'k': 99, 'skip': 0})]),
    ]
    messages[0].tool_calls[0]['args'] = string_args  # type: ignore[missing-attribute]

    assert _retrieved_first_chunks(messages) == [3, 4, 5, 6]
