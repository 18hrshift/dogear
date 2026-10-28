from pathlib import Path

import pytest

import dogear
from dogear.config import default_config, load_config
from dogear.errors import ConfigError


def write(tmp_path, text):
    path = tmp_path / "dogear.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_no_file_means_defaults():
    assert load_config(None) == default_config()


def test_user_values_override_defaults(tmp_path):
    config = load_config(write(tmp_path, "[pdf]\npage_split_size = 5\n[ocr]\nlanguage = 'fra'\n"))
    assert config["pdf"]["page_split_size"] == 5
    assert config["ocr"]["language"] == "fra"
    assert config["ocr"]["dpi"] == default_config()["ocr"]["dpi"]


def test_word_tables_merge_instead_of_replacing(tmp_path):
    config = load_config(
        write(tmp_path, '[speech.abbreviations]\n"approx." = "about"\n"w/" = "with"\n')
    )
    table = config["speech"]["abbreviations"]
    assert table["approx."] == "about"
    assert table["w/"] == "with"
    assert table["etc."] == "et cetera"


def test_pair_tables_merge_instead_of_replacing(tmp_path):
    config = load_config(
        write(
            tmp_path, '[speech.units]\n"km" = ["klick", "klicks"]\n"nmi" = ["league", "leagues"]\n'
        )
    )
    units = config["speech"]["units"]
    assert units["km"] == ["klick", "klicks"]
    assert units["nmi"] == ["league", "leagues"]
    assert units["mph"] == ["mile per hour", "miles per hour"]


def test_default_word_tables_are_valid(tmp_path):
    # Feeding the defaults back in as a user file runs every table through validation.
    defaults = (Path(dogear.__file__).parent / "defaults.toml").read_text(encoding="utf-8")
    assert load_config(write(tmp_path, defaults)) == default_config()


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ("[pdff]\nx = 1\n", "Unknown setting 'pdff'"),
        ("[pdf]\npage_split = 5\n", "Unknown setting 'pdf.page_split'"),
        ("[pdf]\npage_split_size = '5'\n", "must be int"),
        ("[pdf]\npage_split_size = true\n", "must be int"),
        ("[pdf]\nchapter_detection = 'pattern'\n", "must be list"),
        ("[pdf]\nchapter_detection = [1, 2]\n", "Every item in 'pdf.chapter_detection'"),
        ("pdf = 3\n", "must be a table"),
        ('[speech.abbreviations]\n"x." = 1\n', "must be text"),
        ('[speech.time_suffixes]\n"pm" = ["p", "m"]\n', "must be text"),
        ('[speech.units]\n"km" = "kilometer"\n', "must be two texts"),
        ('[speech.units]\n"km" = ["kilometer"]\n', "must be two texts"),
        ('[speech.units]\n"km" = ["a", "b", "c"]\n', "must be two texts"),
        ('[speech.currency]\n"$" = ["dollar", 2]\n', "must be two texts"),
        ('[speech.currency_cents]\n"$" = {one = "cent"}\n', "must be two texts"),
        ('[speech.units]\n"" = ["x", "y"]\n', "empty key"),
        ('[speech.abbreviations]\n"" = "x"\n', "empty key"),
        ("[speech]\nroman_numeral_keywords = 'Chapter'\n", "must be list"),
        ("[speech]\nroman_numeral_keywords = [1]\n", "Every item in"),
        ("[pdf\n", "not valid TOML"),
    ],
)
def test_bad_settings_fail_at_the_door(tmp_path, toml, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, toml))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")


def test_defaults_are_not_shared_between_loads(tmp_path):
    first = load_config(None)
    first["pdf"]["page_split_size"] = 999
    assert load_config(None)["pdf"]["page_split_size"] != 999


def test_pronunciation_files_are_a_list_of_paths(tmp_path):
    config = load_config(write(tmp_path, "[pronunciation]\nfiles = ['~/a.toml', 'b.toml']\n"))
    assert config["pronunciation"]["files"] == ["~/a.toml", "b.toml"]
    assert default_config()["pronunciation"]["files"] == []


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ("[pronunciation]\nfiles = 'words.toml'\n", "must be list"),
        ("[pronunciation]\nfiles = [1]\n", "Every item in 'pronunciation.files' must be str"),
        ("[pronunciation]\nfile = []\n", "Unknown setting 'pronunciation.file'"),
    ],
)
def test_bad_pronunciation_settings_fail_at_the_door(tmp_path, toml, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, toml))
