from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langsmith import Client

client = Client()


def upload_prompt(prompt_identifier: str, obj: Any | None):
    prompt = ChatPromptTemplate(obj)
    client.push_prompt('metis', object=prompt)
