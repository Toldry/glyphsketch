"""The pinned Unicode data files, with SHA-256 checksums of the published 18.0.0 release."""

from dataclasses import dataclass
from pathlib import Path

from glyphsketch.download import download_file

UNICODE_VERSION = "18.0.0"
BASE_URL = f"https://www.unicode.org/Public/{UNICODE_VERSION}/"


@dataclass(frozen=True)
class UcdFile:
    relative_path: str
    sha256: str

    @property
    def url(self) -> str:
        return BASE_URL + self.relative_path


UNICODE_DATA = UcdFile(
    "ucd/UnicodeData.txt", "0736451de439ae7baf1425136617da495e09ee5afbe6e394374db7009ea08950"
)
BLOCKS = UcdFile(
    "ucd/Blocks.txt", "a58f8d322f3c5e254f9f97b1cbf76a454a7e02de6ac35619a5e4f27aaabfd553"
)
SCRIPTS = UcdFile(
    "ucd/Scripts.txt", "0071fd81b6aeae25f6e8bce8efec3066a6476a91b49bdb2f52dc76e817862a6a"
)
SCRIPT_EXTENSIONS = UcdFile(
    "ucd/ScriptExtensions.txt", "5c9d34a922f687726f2a8bcf57d49f905987e51f1b21b58c95a00fbe255cec23"
)
PROPERTY_VALUE_ALIASES = UcdFile(
    "ucd/PropertyValueAliases.txt",
    "06c4c8eaf7b0bf34abe73b113da1215bd784ac254d4c223600b90267caa4bbbd",
)
DERIVED_AGE = UcdFile(
    "ucd/DerivedAge.txt", "58b04334e3a31f9612694bbc3f6bff4a302b7d424565bca9c47e30aa74f8dbac"
)
PROP_LIST = UcdFile(
    "ucd/PropList.txt", "f438f532e8737bb8a2702126cdf9c4af5e357c58c7acf9d9eb2fc7c1a1d955d6"
)
EMOJI_DATA = UcdFile(
    "ucd/emoji/emoji-data.txt", "80d00f8e616a0ef27fd6b8de3b758c06383b5d917e2977709578e68baf733bf1"
)
EMOJI_VARIATION_SEQUENCES = UcdFile(
    "ucd/emoji/emoji-variation-sequences.txt",
    "ff1707564aa1f1b2fcf4ec92d609d4cb26940bc0d4dcf07f5328ad6879e84da3",
)
CONFUSABLES = UcdFile(
    "security/confusables.txt", "6ed3ee967c9dfdf6677d563c9985182fbc50a2efb7d6059cd57b2e2ce18f5b92"
)
INTENTIONAL_CONFUSABLES = UcdFile(
    "security/intentional.txt", "5b69cdfd7be6be45d51b9cf7ec799df91c1acc47c557d66c92a8d6623df78b0e"
)

ALL_FILES = (
    UNICODE_DATA,
    BLOCKS,
    SCRIPTS,
    SCRIPT_EXTENSIONS,
    PROPERTY_VALUE_ALIASES,
    DERIVED_AGE,
    PROP_LIST,
    EMOJI_DATA,
    EMOJI_VARIATION_SEQUENCES,
    CONFUSABLES,
    INTENTIONAL_CONFUSABLES,
)


def download_ucd(destination_dir: Path) -> None:
    """Fetch every pinned file into ``destination_dir``, keeping the upstream layout."""
    for ucd_file in ALL_FILES:
        download_file(ucd_file.url, destination_dir / ucd_file.relative_path, ucd_file.sha256)
