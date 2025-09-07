import re

from neurogabber.backend.adapters import llm


def test_tool_names_are_underscored_and_valid():
    pattern = re.compile(r"^[a-zA-Z0-9_-]+$")
    names = [t["function"]["name"] for t in llm.TOOLS]
    # Ensure all names match the allowed pattern
    for name in names:
        assert pattern.match(name), f"Invalid tool name: {name}"
    # Ensure expected set of tools exists
    assert set(names) == {
        "ng_set_view",
        "ng_set_lut",
        "ng_annotations_add",
        "data_plot_histogram",
        "data_ingest_csv_rois",
        "state_save",
        "state_load",
        "ng_state_summary",
        "ng_state_link",
        "data_info",
        "data_list_files",
        "data_sample",
        "data_ng_views_table",
        "data_preview",
        "data_describe",
        "data_select",
        "data_list_summaries",
    }
