import pytest
from core.raster.writer import write_geotiff

API = "/api/v1"

def test_layers_panel_flow(client, layer_id):
    layers = client.get(f"{API}/file/add-data/layers").json()
    assert [l["id"] for l in layers] == [layer_id] and layers[0]["kind"] == "raster"
    r = client.patch(f"{API}/file/add-data/layers/{layer_id}", json={"name": "Renamed", "opacity": 0.5})
    assert r.json()["name"] == "Renamed" and r.json()["opacity"] == 0.5
    assert client.patch(f"{API}/file/add-data/layers/{layer_id}", json={"opacity": 3}).status_code == 422
    assert client.delete(f"{API}/file/add-data/layers/{layer_id}").status_code == 200
    assert client.get(f"{API}/file/add-data/layers").json() == []


def test_add_raster_from_file_and_basemap(client, hill, tmp_path):
    path = write_geotiff(hill, tmp_path / "dem.tif")
    r = client.post(f"{API}/file/add-data/raster", json={"path": path})
    assert r.status_code == 201 and r.json()["name"] == "dem" and r.json()["width"] == 100
    assert client.post(f"{API}/file/add-data/raster", json={"path": "missing.tif"}).status_code == 404
    b = client.post(f"{API}/file/add-data/basemap", json={"name": "OSM", "url_template": "https://x/{z}/{x}/{y}.png"})
    assert b.status_code == 201 and b.json()["kind"] == "basemap"


def test_add_vector(client, tmp_path):
    f = tmp_path / "pts.geojson"
    f.write_text('{"type":"FeatureCollection","features":[]}')
    assert client.post(f"{API}/file/add-data/vector", json={"path": str(f)}).status_code == 201
    bad = tmp_path / "x.shp"
    bad.write_text("x")
    assert client.post(f"{API}/file/add-data/vector", json={"path": str(bad)}).status_code == 400


def test_project_save_and_open_round_trip(client, hill, tmp_path):
    tif = write_geotiff(hill, tmp_path / "dem.tif")
    client.post(f"{API}/file/project/new", json={"name": "Upper Indus"})
    lid = client.post(f"{API}/file/add-data/raster", json={"path": tif}).json()["id"]
    client.post(f"{API}/analysis/surface-analysis/slope", json={"layer_id": lid})          # derived, unsaved
    assert client.get(f"{API}/file/project").json()["dirty"] is True
    saved = client.post(f"{API}/file/project/save-as", json={"path": str(tmp_path / "p.json")}).json()
    assert saved["saved_layers"] == 1 and len(saved["skipped_layers"]) == 1 and saved["dirty"] is False
    client.post(f"{API}/file/project/new", json={"name": "Other"})
    assert client.get(f"{API}/file/add-data/layers").json() == []
    opened = client.post(f"{API}/file/project/open", json={"path": saved["path"]}).json()
    assert opened["name"] == "Upper Indus" and opened["layer_count"] == 1 and opened["missing_layers"] == []
    assert client.post(f"{API}/file/project/save").status_code == 200
    assert client.post(f"{API}/file/project/open", json={"path": str(tmp_path / "nope.json")}).status_code == 404


def test_export_map_image_elevations_statistics(client, layer_id, tmp_path):
    png = client.get(f"{API}/file/export/map-image/{layer_id}?ramp=viridis")
    assert png.status_code == 200 and png.content[:4] == b"\x89PNG"
    assert client.get(f"{API}/file/export/map-image/{layer_id}?ramp=nope").status_code == 400
    out = client.post(f"{API}/file/export/elevations", json={"layer_id": layer_id, "path": str(tmp_path / "o.tif")})
    assert out.status_code == 200 and (tmp_path / "o.tif").exists()
    csv = client.get(f"{API}/file/export/statistics/{layer_id}?format=csv")
    assert csv.headers["content-type"].startswith("text/csv") and "mean" in csv.text
    assert client.get(f"{API}/file/export/statistics/{layer_id}").json()["count"] == 8000


def test_raster_pixel_sample(client, layer_id, hill):
    row, col = 2, 3
    sample = client.get(
        f"{API}/file/add-data/layers/{layer_id}/pixel",
        params={"row": row, "col": col},
    )
    assert sample.status_code == 200
    result = sample.json()
    expected_x, expected_y = hill.rowcol_to_xy(row, col)
    assert result["row"] == row and result["col"] == col
    assert result["value"] == pytest.approx(float(hill.data[row, col]))
    assert result["x"] == pytest.approx(float(expected_x))
    assert result["y"] == pytest.approx(float(expected_y))
    assert result["coordinate_unit"] == "°"
    assert client.get(
        f"{API}/file/add-data/layers/{layer_id}/pixel",
        params={"row": hill.height, "col": col},
    ).status_code == 400


def test_workspace_reset_and_exit(client, layer_id):
    client.put(f"{API}/view/appearance", json={"colour_ramp": "viridis", "scale_bar": False})
    assert client.get(f"{API}/view/appearance").json()["colour_ramp"] == "viridis"
    client.post(f"{API}/file/workspace/reset")
    assert client.get(f"{API}/view/appearance").json()["colour_ramp"] == "terrain"
    assert client.post(f"{API}/file/workspace/exit").json()["unsaved_changes"] is True


def test_view_navigation_panes_display(client, layer_id):
    ext = client.get(f"{API}/view/navigate/full-extent").json()
    assert len(ext["bounds"]) == 4
    assert client.get(f"{API}/view/navigate/zoom-to-layer/{layer_id}").status_code == 200
    client.put(f"{API}/view/navigate/viewport", json={"scale": 40000})
    assert client.post(f"{API}/view/navigate/zoom-in").json()["scale"] == 20000
    assert client.post(f"{API}/view/navigate/zoom-out", json={"factor": 4}).json()["scale"] == 80000
    assert client.put(f"{API}/view/panes/statistics", json={"visible": False}).json()["statistics"] is False
    assert client.put(f"{API}/view/panes/nope", json={"visible": True}).status_code == 404
    assert client.get(f"{API}/view/appearance/colour-ramps").json()
    assert client.put(f"{API}/view/appearance", json={"colour_ramp": "nope"}).status_code == 400
    assert client.get(f"{API}/view/display/hillshade/{layer_id}").content[:4] == b"\x89PNG"
    assert client.get(f"{API}/view/display/slope/{layer_id}").content[:4] == b"\x89PNG"
    fc = client.get(f"{API}/view/display/contours/{layer_id}?interval=50").json()
    assert fc["type"] == "FeatureCollection" and fc["features"]
    grid = client.get(f"{API}/view/display/reference-grid/{layer_id}?spacing=0.005").json()
    assert grid["features"]
    note = client.post(f"{API}/view/display/annotations", json={"x": 1, "y": 2, "text": "peak"}).json()
    assert client.get(f"{API}/view/display").json()["annotations"][0]["text"] == "peak"
    assert client.delete(f"{API}/view/display/annotations/{note['id']}").status_code == 200
    assert client.put(f"{API}/view/display", json={"reference_grid": True}).json()["reference_grid"] is True
