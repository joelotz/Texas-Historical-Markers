#!/usr/bin/env python3
"""
Local browser viewer for THC SQLite databases.

The page starts blank and only loads rows after you filter by county and/or
city. Data is queried directly from SQLite so you can browse without loading
the whole table into the browser up front.
"""

from __future__ import annotations

import argparse
import html
import json
import sqlite3
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .sqlite_sync import DEFAULT_TABLE_NAME, _quote_identifier

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_SQLITE_CANDIDATES = (
    "atlas_db.sqlite",
    "../atlas_db.sqlite",
    "generated/Tarrant.sqlite",
    "../generated/Tarrant.sqlite",
)
DISPLAY_COLUMNS = (
    "ref:US-TX:thc",
    "ref:hmdb",
    "name",
    "website",
    "addr:city",
    "addr:county",
    "thc:Latitude",
    "thc:Longitude",
)


def _resolve_sqlite_path(sqlite_path: str | Path) -> str:
    return str(Path(sqlite_path).expanduser().resolve())


def resolve_default_sqlite_path(sqlite_path: str | Path | None = None) -> str:
    if sqlite_path:
        return _resolve_sqlite_path(sqlite_path)

    for candidate in DEFAULT_SQLITE_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return _resolve_sqlite_path(path)

    raise FileNotFoundError(
        "No SQLite database found. Provide --sqlite PATH "
        "(tried: atlas_db.sqlite, ../atlas_db.sqlite, generated/Tarrant.sqlite, ../generated/Tarrant.sqlite)."
    )


def _sqlite_columns(sqlite_path: str | Path, table_name: str) -> list[str]:
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute(
            f"PRAGMA table_info({_quote_identifier(table_name)})"
        ).fetchall()
    return [row[1] for row in rows]


def _available_display_columns(sqlite_path: str | Path, table_name: str) -> list[str]:
    present = set(_sqlite_columns(sqlite_path, table_name))
    return [col for col in DISPLAY_COLUMNS if col in present]


def _split_values(values: list[str] | str | None) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    cleaned: list[str] = []
    for value in values:
        if value is None:
            continue
        for part in str(value).split(","):
            text = part.strip()
            if text:
                cleaned.append(text)
    return cleaned


def _distinct_values(
    sqlite_path: str | Path,
    column_name: str,
    table_name: str = DEFAULT_TABLE_NAME,
) -> list[str]:
    table_sql = _quote_identifier(table_name)
    column_sql = _quote_identifier(column_name)
    query = (
        f"SELECT DISTINCT {column_sql} AS value "
        f"FROM {table_sql} "
        f"WHERE COALESCE(TRIM({column_sql}), '') <> '' "
        f"ORDER BY LOWER({column_sql}), {column_sql}"
    )
    with sqlite3.connect(sqlite_path) as conn:
        rows = conn.execute(query).fetchall()
    return [str(row[0]) for row in rows]


def _build_where_clause(
    county_values: list[str] | str | None,
    city_values: list[str] | str | None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []

    county_list = _split_values(county_values)
    city_list = _split_values(city_values)

    if county_list:
        clauses.append(
            "("
            + " OR ".join(['LOWER(COALESCE("addr:county", "")) = ?'] * len(county_list))
            + ")"
        )
        params.extend([value.strip().lower() for value in county_list])
    if city_list:
        clauses.append(
            "("
            + " OR ".join(['LOWER(COALESCE("addr:city", "")) = ?'] * len(city_list))
            + ")"
        )
        params.extend([value.strip().lower() for value in city_list])

    if not clauses:
        return "", params
    return "WHERE " + " AND ".join(clauses), params


def query_rows(
    sqlite_path: str | Path,
    county: list[str] | str | None = None,
    city: list[str] | str | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, object]:
    """
    Query rows for the browser viewer.

    Blank county and city values intentionally return no rows so the page
    starts empty until the user requests data.
    """
    if not county and not city:
        return {
            "rows": [],
            "total": 0,
            "columns": _available_display_columns(sqlite_path, table_name),
        }

    table_sql = _quote_identifier(table_name)
    where_sql, params = _build_where_clause(county, city)
    columns = _available_display_columns(sqlite_path, table_name)
    if not columns:
        raise ValueError(f"No display columns found in SQLite table '{table_name}'")

    order_sql = """
        ORDER BY
            COALESCE(LOWER("addr:county"), ''),
            COALESCE(LOWER("addr:city"), ''),
            COALESCE(LOWER("name"), ''),
            COALESCE("ref:US-TX:thc", '')
    """
    select_cols = ", ".join(_quote_identifier(col) for col in columns)

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        count_sql = f"SELECT COUNT(*) FROM {table_sql} {where_sql}"
        total = conn.execute(count_sql, params).fetchone()[0]

        query_sql = (
            f"SELECT {select_cols} FROM {table_sql} "
            f"{where_sql} {order_sql} LIMIT ? OFFSET ?"
        )
        rows = conn.execute(query_sql, [*params, limit, offset]).fetchall()

    payload_rows = [{col: row[col] for col in columns} for row in rows]
    return {"rows": payload_rows, "total": total, "columns": columns}


def _page_html(sqlite_name: str, table_name: str) -> str:
    safe_sqlite = html.escape(sqlite_name)
    safe_table = html.escape(table_name)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>THC SQLite Browser</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #5a647a;
      --line: #dce3ef;
      --accent: #165dff;
      --accent-soft: #e7efff;
    }}
    body {{
      margin: 0;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: linear-gradient(180deg, #eef3fb 0%, var(--bg) 35%);
      color: var(--ink);
    }}
    header {{
      padding: 20px 24px;
      background: #121826;
      color: #fff;
    }}
    main {{
      padding: 18px 24px 28px;
    }}
    .toolbar {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: end;
      margin-bottom: 14px;
    }}
    label {{
      display: flex;
      flex-direction: column;
      gap: 6px;
      font-size: 12px;
      font-weight: 700;
    }}
    input, select, button {{
      font: inherit;
      border-radius: 10px;
      border: 1px solid var(--line);
      background: var(--panel);
      padding: 10px 12px;
    }}
    input {{
      min-width: 240px;
    }}
    button {{
      cursor: pointer;
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      font-weight: 700;
    }}
    button.secondary {{
      background: var(--panel);
      color: var(--ink);
      border-color: var(--line);
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 14px;
    }}
    .pill {{
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      background: var(--accent-soft);
      color: #1a3f9f;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: var(--panel);
      box-shadow: 0 8px 24px rgba(16, 24, 40, 0.06);
    }}
    table {{
      border-collapse: collapse;
      width: max-content;
      min-width: 100%;
    }}
    thead th {{
      position: sticky;
      top: 0;
      background: #eaf0f8;
      border-bottom: 1px solid var(--line);
      text-align: left;
      padding: 10px 12px;
      font-size: 13px;
      white-space: nowrap;
    }}
    tbody td {{
      padding: 8px 12px;
      border-bottom: 1px solid #eef2f7;
      vertical-align: top;
      font-size: 13px;
      max-width: 340px;
      white-space: normal;
      word-break: break-word;
    }}
    tbody tr:nth-child(even) {{
      background: #fafcff;
    }}
    .status {{
      margin: 16px 0 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
    }}
    .hidden {{
      display: none;
    }}
    .error {{
      color: #b42318;
      font-weight: 700;
    }}
    select[multiple] {{
      min-width: 260px;
      min-height: 140px;
      padding: 8px;
    }}
    .select-note {{
      margin-top: -2px;
      font-size: 11px;
      color: var(--muted);
      font-weight: 500;
    }}
    .filter-row th {{
      position: sticky;
      top: 38px;
      z-index: 2;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
      padding: 6px 8px;
    }}
    .filter-row input {{
      min-width: 120px;
      width: 100%;
      box-sizing: border-box;
      padding: 6px 8px;
      font-size: 12px;
      border-radius: 8px;
    }}
    .filter-controls {{
      display: flex;
      flex-direction: row;
      align-items: center;
      gap: 8px;
    }}
    .blank-toggle {{
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      color: var(--muted);
      font-weight: 600;
      white-space: nowrap;
      flex: 0 0 auto;
    }}
    .blank-toggle input {{
      min-width: 0;
      width: auto;
      padding: 0;
      margin: 0;
    }}
    .sortable {{
      cursor: pointer;
      user-select: none;
    }}
    .sort-indicator {{
      color: var(--muted);
      font-size: 11px;
      margin-left: 4px;
    }}
  </style>
</head>
<body>
  <header>
    <h1 style="margin:0;font-size:22px">THC SQLite Browser</h1>
    <div style="margin-top:4px;font-size:12px;opacity:.82">SQLite: {safe_sqlite} | Table: {safe_table}</div>
  </header>
  <main>
    <form class="toolbar" id="searchForm">
      <label>
        County
        <select id="county" name="county" multiple size="8"></select>
        <div class="select-note">Hold Ctrl/Cmd to select multiple counties.</div>
      </label>
      <label>
        City
        <select id="city" name="city" multiple size="8"></select>
        <div class="select-note">Hold Ctrl/Cmd to select multiple cities.</div>
      </label>
      <label>
        Limit
        <input id="limit" name="limit" type="number" min="1" max="5000" value="2000">
      </label>
      <div style="display:flex;gap:10px;align-items:end">
        <button type="submit">Load</button>
        <button type="button" id="clearBtn" class="secondary">Clear</button>
      </div>
    </form>
    <div class="meta">
      <span class="pill" id="resultPill">No results loaded</span>
      <span class="hint">Start with county and/or city, then load rows from SQLite.</span>
    </div>
    <div id="status" class="status">The page starts blank on purpose.</div>
    <div class="table-wrap hidden" id="tableWrap">
      <table id="resultTable">
        <thead>
          <tr id="headerRow"></tr>
          <tr id="filterRow" class="filter-row"></tr>
        </thead>
        <tbody id="bodyRow"></tbody>
      </table>
    </div>
  </main>
  <script>
    const form = document.getElementById('searchForm');
    const county = document.getElementById('county');
    const city = document.getElementById('city');
    const limit = document.getElementById('limit');
    const clearBtn = document.getElementById('clearBtn');
    const statusEl = document.getElementById('status');
    const tableWrap = document.getElementById('tableWrap');
    const headerRow = document.getElementById('headerRow');
    const filterRow = document.getElementById('filterRow');
    const bodyRow = document.getElementById('bodyRow');
    const resultPill = document.getElementById('resultPill');
    let currentColumns = [];
    let currentRows = [];
    let sortState = {{ column: null, asc: true }};

    function setStatus(message, isError=false) {{
      statusEl.textContent = message;
      statusEl.classList.toggle('error', Boolean(isError));
    }}

    function normalize(value) {{
      return String(value ?? '').toLowerCase().trim();
    }}

    function isBlankLike(value) {{
      return ['','nan','none','null','na','<na>'].includes(normalize(value));
    }}

    function sortRows(rows, column) {{
      const asc = sortState.column === column ? !sortState.asc : true;
      sortState = {{ column, asc }};
      const sorted = [...rows].sort((a, b) => {{
        const left = String(a[column] ?? '').trim();
        const right = String(b[column] ?? '').trim();
        const leftNum = Number(left.replace(/,/g, ''));
        const rightNum = Number(right.replace(/,/g, ''));
        let cmp;
        if (!Number.isNaN(leftNum) && !Number.isNaN(rightNum) && left !== '' && right !== '') {{
          cmp = leftNum - rightNum;
        }} else {{
          cmp = left.localeCompare(right, undefined, {{ numeric: true, sensitivity: 'base' }});
        }}
        return asc ? cmp : -cmp;
      }});
      return sorted;
    }}

    function applyFilters() {{
      const controls = [...filterRow.querySelectorAll('[data-column]')];
      const activeFilters = new Map();
      for (const control of controls) {{
        const column = control.dataset.column;
        const mode = control.dataset.mode;
        const entry = activeFilters.get(column) || {{ text: '', blankOnly: false }};
        if (mode === 'text') {{
          entry.text = normalize(control.value);
        }} else if (mode === 'blank') {{
          entry.blankOnly = Boolean(control.checked);
        }}
        activeFilters.set(column, entry);
      }}
      let filtered = currentRows.filter(row => {{
        for (const [column, filter] of activeFilters.entries()) {{
          if (filter.blankOnly) {{
            if (!isBlankLike(row[column])) return false;
            continue;
          }}
          if (filter.text && !normalize(row[column]).includes(filter.text)) return false;
        }}
        return true;
      }});

      if (sortState.column) {{
        filtered = sortRows(filtered, sortState.column);
      }}

      renderBody(filtered);
      resultPill.textContent = `${{filtered.length}} visible row(s) / ${{currentRows.length}} loaded`;
      setStatus(filtered.length < currentRows.length
        ? `Showing ${{filtered.length}} of ${{currentRows.length}} loaded rows.`
        : `Loaded ${{currentRows.length}} row(s).`);
    }}

    function renderBody(rows) {{
      bodyRow.innerHTML = '';
      for (const row of rows) {{
        const tr = document.createElement('tr');
        for (const col of currentColumns) {{
          const td = document.createElement('td');
          td.textContent = row[col] ?? '';
          tr.appendChild(td);
        }}
        bodyRow.appendChild(tr);
      }}
    }}

    function renderTable(columns, rows) {{
      currentColumns = columns;
      currentRows = rows;
      headerRow.innerHTML = '';
      filterRow.innerHTML = '';
      bodyRow.innerHTML = '';
      for (const col of columns) {{
        const th = document.createElement('th');
        th.textContent = col;
        th.className = 'sortable';
        const indicator = document.createElement('span');
        indicator.className = 'sort-indicator';
        indicator.textContent = '';
        th.appendChild(indicator);
        th.addEventListener('click', () => {{
          const sorted = sortRows(currentRows, col);
          currentRows = sorted;
          applyFilters();
          updateSortIndicators(col);
        }});
        headerRow.appendChild(th);

        const filterTh = document.createElement('th');
        const controls = document.createElement('div');
        controls.className = 'filter-controls';
        const blankLabel = document.createElement('label');
        blankLabel.className = 'blank-toggle';
        const blank = document.createElement('input');
        blank.type = 'checkbox';
        blank.dataset.column = col;
        blank.dataset.mode = 'blank';
        blank.addEventListener('change', applyFilters);
        const blankText = document.createElement('span');
        blankText.textContent = 'Blank only';
        blankLabel.appendChild(blank);
        blankLabel.appendChild(blankText);
        controls.appendChild(blankLabel);
        const input = document.createElement('input');
        input.type = 'search';
        input.placeholder = `Filter ${{col}}`;
        input.dataset.column = col;
        input.dataset.mode = 'text';
        input.addEventListener('input', applyFilters);
        controls.appendChild(input);
        filterTh.appendChild(controls);
        filterRow.appendChild(filterTh);
      }}
      sortState = {{ column: null, asc: true }};
      renderBody(rows);
      updateSortIndicators(null);
      applyFilters();
    }}

    function updateSortIndicators(activeColumn) {{
      [...headerRow.children].forEach((th, index) => {{
        const indicator = th.querySelector('.sort-indicator');
        if (!indicator) return;
        const col = currentColumns[index];
        if (col !== activeColumn && sortState.column !== col) {{
          indicator.textContent = '';
          return;
        }}
        if (sortState.column === col) {{
          indicator.textContent = sortState.asc ? '▲' : '▼';
        }} else {{
          indicator.textContent = '';
        }}
      }});
    }}

    function selectedValues(selectEl) {{
      return [...selectEl.selectedOptions].map(option => option.value).filter(Boolean);
    }}

    async function loadOptions() {{
      const response = await fetch('/api/options');
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || 'Failed to load filter options');
      }}

      const fills = [
        [county, data.counties],
        [city, data.cities],
      ];
        for (const [selectEl, values] of fills) {{
        selectEl.innerHTML = '';
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = values.length ? `Select one or more (${{values.length}})` : 'No values available';
        placeholder.disabled = true;
        placeholder.selected = true;
        selectEl.appendChild(placeholder);
        for (const value of values) {{
          const option = document.createElement('option');
          option.value = value;
          option.textContent = value;
          selectEl.appendChild(option);
        }}
      }}
    }}

    async function loadRows() {{
      const params = new URLSearchParams();
      for (const value of selectedValues(county)) params.append('county', value);
      for (const value of selectedValues(city)) params.append('city', value);
      params.set('limit', limit.value || '2000');

      if (!params.has('county') && !params.has('city')) {{
        tableWrap.classList.add('hidden');
        resultPill.textContent = 'No results loaded';
        setStatus('Enter county and/or city, then click Load.');
        return;
      }}

      setStatus('Loading rows from SQLite...');
      const response = await fetch(`/api/search?${{params.toString()}}`);
      const data = await response.json();
      if (!response.ok) {{
        throw new Error(data.error || 'Failed to load rows');
      }}
      renderTable(data.columns, data.rows);
      tableWrap.classList.remove('hidden');
      resultPill.textContent = `${{data.total}} matching row(s)`;
      setStatus(data.rows.length < data.total
        ? `Showing ${{data.rows.length}} of ${{data.total}} matches. Increase the limit if you want more.`
        : `Loaded ${{data.total}} match(es).`);
    }}

    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      try {{
        await loadRows();
      }} catch (error) {{
        setStatus(error.message, true);
      }}
    }});

    clearBtn.addEventListener('click', () => {{
      for (const option of county.options) option.selected = false;
      for (const option of city.options) option.selected = false;
      limit.value = '2000';
      tableWrap.classList.add('hidden');
      resultPill.textContent = 'No results loaded';
      setStatus('Cleared. Enter county and/or city, then click Load.');
    }});

    loadOptions()
      .then(() => setStatus('Choose one or more counties and/or cities, then click Load.'))
      .catch(error => setStatus(error.message, true));
  </script>
</body>
</html>
"""


def _make_handler(sqlite_path: str, table_name: str):
    class ViewerHandler(BaseHTTPRequestHandler):
        def _send_json(self, payload: dict[str, object], status: int = 200) -> None:
            body = json.dumps(payload, indent=2, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, body: str) -> None:
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_html(_page_html(Path(sqlite_path).name, table_name))
                return

            if parsed.path == "/api/search":
                params = parse_qs(parsed.query)
                county = params.get("county", [])
                city = params.get("city", [])
                limit_raw = params.get("limit", ["200"])[0]
                try:
                    limit = max(1, min(5000, int(limit_raw)))
                except ValueError:
                    self._send_json({"error": "limit must be an integer"}, status=400)
                    return
                try:
                    payload = query_rows(
                        sqlite_path,
                        county=county,
                        city=city,
                        table_name=table_name,
                        limit=limit,
                    )
                except Exception as exc:  # pragma: no cover - surfaced to browser
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/options":
                try:
                    counties = _distinct_values(sqlite_path, "addr:county", table_name)
                    cities = _distinct_values(sqlite_path, "addr:city", table_name)
                except Exception as exc:  # pragma: no cover - surfaced to browser
                    self._send_json({"error": str(exc)}, status=400)
                    return
                self._send_json({"counties": counties, "cities": cities})
                return

            self.send_error(404, "Not Found")

        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

    return ViewerHandler


def serve_sqlite_browser(
    sqlite_path: str | Path | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
) -> ThreadingHTTPServer:
    sqlite_path = resolve_default_sqlite_path(sqlite_path)
    handler = _make_handler(sqlite_path, table_name)
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}/"
    print(f"✔ Serving SQLite browser for {sqlite_path}")
    print(f"✔ Open {url}")
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="thc sqlite browse",
        description="Browse THC SQLite data in a local web app",
    )
    parser.add_argument(
        "--sqlite",
        default=None,
        help="SQLite file to browse (defaults to atlas_db.sqlite if found)",
    )
    parser.add_argument("--table", default=DEFAULT_TABLE_NAME, help="SQLite table name")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--no-open", action="store_true", help="Do not auto-open the browser"
    )
    args = parser.parse_args(argv)

    server = serve_sqlite_browser(
        args.sqlite,
        table_name=args.table,
        host=args.host,
        port=args.port,
        open_browser=not args.no_open,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down browser server...")
    finally:
        server.server_close()


if __name__ == "__main__":  # pragma: no cover
    main()
