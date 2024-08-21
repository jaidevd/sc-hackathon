import os
import glob
import hashlib
import json

from azure.ai.formrecognizer import DocumentAnalysisClient, AnalyzeResult
from azure.core.credentials import AzureKeyCredential
from tqdm import tqdm

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


if __name__ == "__main__":
    from gramex import cache
    secrets = cache.open('.secrets.yaml', 'config')
    for file in tqdm(glob.glob("data/files/*.pdf")):
        result = ocr(file, endpoint=secrets.AZURE_OCR_URL, api_key=secrets.AZURE_OCR_KEY)
        kvps = []
        for kvp in result.key_value_pairs:
            if kvp.confidence >= 0.9:
                kvps.append((kvp.key.content, kvp.value.content if kvp.value else kvp.value))
        outpath = op.join("data/kvps", op.basename(file) + ".json")
        with open(outpath, "w") as f:
            json.dump(kvps, f, indent=2)
