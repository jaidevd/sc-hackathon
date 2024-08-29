import os
import json
from gramex import cache
from requests import post
import numpy as np
import pandas as pd

secrets = cache.open(".secrets.yaml", "config", rel=True)
op = os.path


url = "https://llmfoundry.straive.com/openai/v1/chat/completions"
headers = {"Authorization": f"Bearer {secrets.LLMFOUNDRY_TOKEN}:schack"}
DOCTYPES = ['Writ Petition', 'Transfer Petition', 'Special Leave Petition']


IDENTIFY_DOC = f"""The user message contains the text content of the first page of a document.
Identify the type of document based on it. The valid types are {DOCTYPES}.
Respond with one of the valid strings."""
ANNEXURE_PAGES = """The user message contains a JSON encoded representation of multiple tables from a document. Note that tables may span multiple pages. Find the table of contents that lists annexures and their page numbers. Based on this, identify whether the table contains the page numbers of annexures.
Respond with a decodeable JSON string, with no markdown decoration. It should contain two keys:
`toc_pages` which is an array of page numbers, and `annexures_page_nos_present` which is a boolean."""


def _chat(payload, loads=True):
    payload["model"] = "gpt-4o-mini"
    resp = post(url, headers=headers, json=payload)
    resp.raise_for_status()
    result = resp.json()["choices"][0]["message"]["content"]
    if not loads:
        return result
    return json.loads(result)


def get_doctype(result):
    page = result.pages[0]
    start = page.spans[0].offset
    end = start + page.spans[0].length
    content = result.content[start:end]
    payload = {
        "messages": [
            {"role": "system", "content": IDENTIFY_DOC},
            {"role": "user", "content": content},
        ]
    }
    return _chat(payload, False)


def get_annexures_index(tables):
    tables = [t for t in tables if any('annexure' in cell.content.lower() for cell in t.cells)]
    payload = {
        "messages": [
            {"role": "system", "content": ANNEXURE_PAGES},
            {"role": "user", "content": json.dumps([t.to_dict() for t in tables])},
        ]
    }
    return _chat(payload, False)


def bad_quality_pages(result, threshold=0.9):
    conf = [(page.page_number, np.mean([w.confidence for w in page.words])) for page in result.pages]
    df = pd.DataFrame(conf, columns=["page", "confidence"])
    return df[df['confidence'] < threshold]['page'].sort_values().values
