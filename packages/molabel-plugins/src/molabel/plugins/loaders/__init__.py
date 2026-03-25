"""Built-in data loaders for MoLabel.

Each loader implements the ``DataLoaderPlugin`` protocol from
``molabel.core.plugins.protocols`` and handles a specific file format.
"""

from molabel.plugins.loaders.csv_loader import CsvLoader
from molabel.plugins.loaders.huggingface_loader import HuggingFaceLoader
from molabel.plugins.loaders.json_loader import JsonLoader
from molabel.plugins.loaders.jsonl_loader import JsonlLoader
from molabel.plugins.loaders.markdown_loader import MarkdownLoader
from molabel.plugins.loaders.parquet_loader import ParquetLoader
from molabel.plugins.loaders.yaml_loader import YamlLoader

__all__ = [
    "CsvLoader",
    "HuggingFaceLoader",
    "JsonLoader",
    "JsonlLoader",
    "MarkdownLoader",
    "ParquetLoader",
    "YamlLoader",
]
