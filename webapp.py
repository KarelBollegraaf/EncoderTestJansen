# webapp.py
import os
import json
import sqlite3
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

DB_PATH = os.getenv("DB_PATH", "/data/encoder.db")

app = FastAPI()

def _connect():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Encoder Data</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 16px; }
    table { border-collapse: collapse; width: 100%; font-size: 12px; }
    th, td { border: 1px solid #ddd; padding: 6px; vertical-align: top; }
    th { position: sticky; top: 0; background: #f7f7f7; }
    .row { display: flex; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
    input { padding: 6px; }
  </style>
</head>
<body>
  <h2>Latest Encoder Samples</h2>
  <div class="row">
    <label>Limit <input id="limit" type="number" value="200" min="1" max="5000"/></label>
    <label>Bale # <input id="bale" type="number" placeholder="optional"/></label>
    <button onclick="load()">Refresh</button>
    <span id="status"></span>
  </div>

  <table>
    <thead>
      <tr>
        <th>timestamp</th>
        <th>data_valid</th>
        <th>BaleNumber_s</th>
        <th>BaleNumber_i</th>
        <th>sBaleReady</th>
        <th>iRamGoesForward</th>
        <th>EncoderDisRaw</th>
        <th>Rounds</th>
        <th>Distance</th>
        <th>sRamdistance</th>
        <th>StrokeLength</th>
        <th>qBaleNumber</th>
        <th>qBale_Length</th>
        <th>qStrokeLength</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>

<script>
async function load() {
  const limit = document.getElementById("limit").value || 200;
  const bale = document.getElementById("bale").value;
  let url = `/api/samples?limit=${limit}`;
  if (bale !== "") url += `&bale=${bale}`;

  document.getElementById("status").textContent = "loading...";
  const res = await fetch(url);
  const rows = await res.json();

  const tb = document.getElementById("tbody");
  tb.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.ts}</td>
      <td>${r.data_valid ? "YES" : "NO"}</td>
      <td>${r.bale_s ?? ""}</td>
      <td>${r.bale_i ?? ""}</td>
      <td>${r.bale_ready ? "True" : "False"}</td>
      <td>${r.ram_forward ? "True" : "False"}</td>
      <td>${r.encoder_raw ?? ""}</td>
      <td>${r.rounds ?? ""}</td>
      <td>${r.distance ?? ""}</td>
      <td>${r.ram_distance ?? ""}</td>
      <td>${JSON.stringify(r.stroke)}</td>
      <td>${r.q_bale_number ?? ""}</td>
      <td>${r.q_bale_length ?? ""}</td>
      <td>${JSON.stringify(r.q_stroke)}</td>
    `;
    tb.appendChild(tr);
  }
  document.getElementById("status").textContent = `${rows.length} rows`;
}
load();
setInterval(load, 2000);
</script>
</body>
</html>
"""

@app.get("/api/samples")
def samples(
    limit: int = Query(200, ge=1, le=5000),
    bale: int | None = Query(None, description="Filter by bale_s or bale_i equals this"),
):
    con = _connect()
    try:
        if bale is None:
            cur = con.execute("""
                SELECT * FROM encoder_samples
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
        else:
            cur = con.execute("""
                SELECT * FROM encoder_samples
                WHERE bale_s = ? OR bale_i = ?
                ORDER BY id DESC
                LIMIT ?
            """, (bale, bale, limit))

        out = []
        for row in cur.fetchall():
            d = dict(row)
            d["stroke"] = json.loads(d["stroke_json"]) if d.get("stroke_json") else []
            d["q_stroke"] = json.loads(d["q_stroke_json"]) if d.get("q_stroke_json") else []
            d.pop("stroke_json", None)
            d.pop("q_stroke_json", None)
            out.append(d)
        return JSONResponse(out)
    finally:
        con.close()
