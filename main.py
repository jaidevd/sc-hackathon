import os
import re
import glob
import hashlib
import json

import gramex
from gramex.config import secrets
import pandas as pd
from azure.ai.formrecognizer import DocumentAnalysisClient, AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from tqdm import tqdm
from tornado.gen import coroutine

op = os.path


def checksum(file_path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def ocr(
    path,
    model="prebuilt-document",
    endpoint=None,
    api_key=None,
    cache_dir="data/cache/",
) -> AnalyzeResult:
    cs = checksum(path)
    if not op.isdir(cache_dir):
        os.makedirs(cache_dir, exist_ok=True)

    if op.isfile(op.join(cache_dir, f"{cs}.{model}.json")):
        with open(op.join(cache_dir, f"{cs}.{model}.json"), "r") as f:
            return AnalyzeResult.from_dict(json.load(f))

    # Initialize the client
    document_analysis_client = DocumentAnalysisClient(
        endpoint=endpoint, credential=AzureKeyCredential(api_key)
    )

    # Open the PDF file in binary mode
    with open(path, "rb") as pdf_file:
        poller = document_analysis_client.begin_analyze_document(model, pdf_file)
        result = poller.result()
    with open(op.join(cache_dir, f"{cs}.{model}.json"), "w") as f:
        json.dump(result.to_dict(), f)
    return result


def save(filename, body, **kwargs):
    path = op.join("data", "upload", filename)
    with open(path, "wb") as fout:
        fout.write(body)
    return path


"""
2.6 Non-mentioning of page numbers of annexures in the list of dates/ petition.
2.8 Incorrect mentioning of description of annexures in Index
3.2 Page No…………. not clear/legible/small font/dim/missing.
3.3 Page Nos. �…..contain underlines/highlights/blanks/torn condition.
5.5 Blanks in the affidavit
8.1 Improper execution of Vakalatnama/Memo of Appearance
17.1 Non-mentioning of the number of days of delay
24.2 Non-inclusion of complete listing proforma filled in, signed in the paper-books
"""


def annexure_index(tables):
    bad = []
    for i, t in enumerate(tables):
        clookup = pd.DataFrame(
            [(c.row_index, c.column_index) for c in t.cells],
            columns=['row', 'col']
        )
        for j, c in enumerate(t.cells):
            if c.content.startswith('Annexure'):
                raise ValueError('Needs more work.')
                col_next = clookup.loc[j, 'col'] + 1
                row = clookup[clookup['row'] == c.row_index]
                cell_next = row[row['col'] == col_next]
                if not re.match(r"\d+(-\d+)?", t.cells[cell_next.index[0]].content):
                    bad.append({
                        "table": i,
                        "row": c.row_index,
                        "col": c.column_index,
                        "bbox": c.bounding_regions[0].to_dict()
                    })
    return bad


def polygon2bbox(kvp):
    kbr = kvp['key']['bounding_regions'][0]['polygon']
    vbr = kvp['value']['bounding_regions'][0]['polygon']
    bb = pd.DataFrame.from_records(kbr + vbr)
    (xmin, ymin), (xmax, ymax) = bb.min(axis=0).values, bb.max(axis=0).values
    return {"x": xmin, "y": ymin, "width": xmax - xmin, "height": ymax - ymin}


def normalize_bboxes(df, pages):
    bbox = pd.DataFrame.from_records(df['bbox'].tolist(), index=df.index)
    bbox['page'] = df['page']
    page_sizes = pd.DataFrame(
        [(p.page_number, p.width, p.height) for p in pages],
        columns=['page', 'width', 'height']
    ).set_index('page', verify_integrity=True)
    bbox = bbox.join(page_sizes, on='page', rsuffix='_')
    bbox['x'] = bbox['x'] / bbox['width_']
    bbox['y'] = bbox['y'] / bbox['height_']
    bbox['width'] = bbox['width'] / bbox['width_']
    bbox['height'] = bbox['height'] / bbox['height_']
    df[['x', 'y', 'width', 'height']] = bbox[['x', 'y', 'width', 'height']]
    return df.drop(['bbox'], axis=1)


def get_kvps(result, threshold=0.85, n_pages=20):
    kvps = [kvp for kvp in result.key_value_pairs if kvp.confidence >= threshold and kvp.value]
    kvps = pd.DataFrame.from_records([{
        "key": kvp.key.content,
        "value": kvp.value.content if kvp.value else "",
        "page": kvp.key.bounding_regions[0].page_number,
        "bbox": polygon2bbox(kvp.to_dict()),
        "confidence": kvp.confidence
    } for kvp in kvps])
    kvps = kvps[kvps['value'] != ':unselected:']
    kvps = kvps[kvps['value'] != 'N/A']
    kvps.loc[kvps['value'] == ":selected:", "value"] = "Yes"
    to_keep = pd.concat(
        [kvps['key'].str.lower(), kvps['value'].str.lower()], axis=1).drop_duplicates().index
    kvps = kvps.loc[to_keep]
    # Drop short, common keys like "no.", "of", etc.
    kvps = kvps[~kvps['key'].str.contains(r"^no\.$", case=False)]
    kvps = kvps[~kvps['key'].str.contains(r"^on\.$", case=False)]
    kvps = kvps[~kvps['key'].str.contains(r"^of$", case=False)]
    if n_pages:
        kvps = kvps[kvps['page'] <= n_pages]
    kvps = kvps.sort_values(["page", "confidence"], ascending=[True, False])
    return normalize_bboxes(kvps, result.pages)


@coroutine
def extract(handler):
    file = handler.request.files["file"][0]
    path = save(**file)
    result = yield gramex.service.threadpool.submit(ocr, path, endpoint=secrets["AZURE_OCR_URL"], api_key=secrets["AZURE_OCR_KEY"])
    return {'url': path, 'kvps': get_kvps(result)}


if __name__ == "__main__":
    from gramex import cache
    secrets_ = cache.open('.secrets.yaml', 'config')
    for file in tqdm(glob.glob("data/files/*.pdf")):
        result = ocr(file, endpoint=secrets_.AZURE_OCR_URL, api_key=secrets_.AZURE_OCR_KEY)
        kvps = []
        for kvp in result.key_value_pairs:
            if kvp.confidence >= 0.9:
                kvps.append((kvp.key.content, kvp.value.content if kvp.value else kvp.value))
        outpath = op.join("data/kvps", op.basename(file) + ".json")
        with open(outpath, "w") as f:
            json.dump(kvps, f, indent=2)
