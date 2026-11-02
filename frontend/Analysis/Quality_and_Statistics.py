"""Analysis > Quality & Statistics group."""
GROUP = {
    "label": "Quality & Statistics",
    "tools": [
        dict(id="layer-statistics", label="Layer Statistic & Properties", icon="stats", kind="action",
             action="show_stats", tip="Layer Statistics & Properties"),

        dict(id="histogram", label="Histogram", icon="stats", kind="panel",
             tip="Histogram",
             fields=[
                 dict(type="layer", label="Raster layer"),
                 dict(type="slider", label="Bins", min=10, max=100, value=30),
                 dict(type="check", label="Logarithmic counts", value=False),
             ]),
        dict(id="nodata-check", label="NoData Check", icon="check", kind="panel",
             tip="NoData Check",
             fields=[
                 dict(type="layer", label="Raster layer"),
                 dict(type="text", label="NoData value", value="-9999"),
             ]),

        dict(id="outlier-check", label="Outlier Check", icon="eye", kind="panel",
             tip="Outlier Check",
             fields=[
                 dict(type="layer", label="Raster layer"),
                 dict(type="slider", label="Sensitivity", min=1, max=10, value=5),
             ]),
    ],
}
