from fastapi.testclient import TestClient
from neurogabber.backend.main import app

client = TestClient(app)

CSV_CONTENT = b"id,x,y,z,size_x,size_y,size_z\n1,1,2,3,4,5,6\n2,2,3,4,5,6,7\n"

def test_upload_and_list_files():
    resp = client.post("/upload_file", files={"file": ("test.csv", CSV_CONTENT, "text/csv")})
    data = resp.json()
    assert data["ok"], data
    fid = data["file"]["file_id"]

    lst = client.post("/tools/data_list_files").json()
    assert any(f["file_id"] == fid for f in lst["files"])


def test_preview_and_describe():
    resp = client.post("/upload_file", files={"file": ("t2.csv", CSV_CONTENT, "text/csv")}).json()
    fid = resp["file"]["file_id"]
    prev = client.post("/tools/data_preview", json={"file_id": fid, "n": 1}).json()
    assert prev["rows"] and len(prev["rows"]) == 1
    desc = client.post("/tools/data_describe", json={"file_id": fid}).json()
    assert "summary" in desc
    assert desc["rows"], desc


def test_select_filter():
    resp = client.post("/upload_file", files={"file": ("t3.csv", CSV_CONTENT, "text/csv")}).json()
    fid = resp["file"]["file_id"]
    sel = client.post(
        "/tools/data_select",
        json={
            "file_id": fid,
            "columns": ["id", "x", "size_x"],
            "filters": [{"column": "id", "op": ">", "value": 1}],
            "limit": 5,
        },
    ).json()
    assert "summary" in sel, sel
    assert sel["preview_rows"], sel


def test_list_summaries():
    # Ensure at least one summary from previous tests
    resp = client.post("/tools/data_list_summaries").json()
    assert "summaries" in resp


def test_data_sample_basic_and_seed():
    resp = client.post("/upload_file", files={"file": ("sample.csv", CSV_CONTENT, "text/csv")}).json()
    fid = resp["file"]["file_id"]
    sample = client.post("/tools/data_sample", json={"file_id": fid, "n": 2}).json()
    assert sample["returned"] == 2
    assert len(sample["rows"]) == 2
    # Seeded reproducibility
    s1 = client.post("/tools/data_sample", json={"file_id": fid, "n": 2, "seed": 42}).json()
    s2 = client.post("/tools/data_sample", json={"file_id": fid, "n": 2, "seed": 42}).json()
    assert s1["rows"] == s2["rows"], "Seeded samples should match"
    # Without replacement uniqueness
    ids = [r["id"] for r in sample["rows"]]
    assert len(ids) == len(set(ids))
