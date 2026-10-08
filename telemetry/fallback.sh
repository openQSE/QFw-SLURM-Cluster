#!/bin/bash
#
# The fallback for a demonstration: freeze a good window of the QFw
# dashboards so there is something to show if the live stack misbehaves.
#
# Two layers, from the same window:
#
#   snapshot  A Grafana local snapshot of each QFw dashboard, with the panel
#             data embedded, created through Grafana's API. It renders inside
#             Grafana without Prometheus or Tempo and without live jobs, and
#             the panels still answer to hover. Lives in Grafana's own volume.
#   images    A screenshot of each dashboard by headless Chrome, and an
#             offline page that shows them with the snapshot links. Needs
#             nothing running at all.
#
# A third layer costs nothing: Prometheus and Tempo keep their data for two
# weeks, so any dashboard with an absolute time range over a rehearsal shows
# that rehearsal as long as the stack is up.
#
#   ./telemetry/fallback.sh [--from WHEN] [--to WHEN] [--out DIR] [--only snapshot|images]
#
# WHEN is a Grafana time (now-30m, now, 2026-11-17T16:00:00) or an epoch in
# milliseconds; the default is the last thirty minutes. The output directory
# defaults to <QFW_CONTAINER_BASE>/qfw-fallback-<timestamp>.
#
# Environment: QFW_GRAFANA_URL (default http://localhost:<QFW_GRAFANA_PORT or 3000>),
# QFW_GRAFANA_ADMIN_PASSWORD (default qfw-demo), QFW_CHROME (the browser
# binary; found on PATH or in /Applications otherwise).
set -u

FROM="now-30m"
TO="now"
OUT=""
ONLY=""
while [ "$#" -gt 0 ]; do
	case "$1" in
		--from) FROM="$2"; shift 2 ;;
		--to) TO="$2"; shift 2 ;;
		--out) OUT="$2"; shift 2 ;;
		--only) ONLY="$2"; shift 2 ;;
		-h|--help) sed -n '2,31p' "$0"; exit 0 ;;
		*) echo "unknown option: $1" >&2; exit 2 ;;
	esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
port="${QFW_GRAFANA_PORT:-}"
if [ -z "${port}" ] && [ -f "${ENV_FILE}" ]; then
	port="$(awk -F= '$1 == "QFW_GRAFANA_PORT" { print $2 }' "${ENV_FILE}" | tail -n 1)"
fi
GRAFANA="${QFW_GRAFANA_URL:-http://localhost:${port:-3000}}"
PASSWORD="${QFW_GRAFANA_ADMIN_PASSWORD:-qfw-demo}"
if [ -z "${OUT}" ]; then
	base="$(awk -F= '$1 == "QFW_CONTAINER_BASE" { print $2 }' "${ENV_FILE}" 2>/dev/null | tail -n 1)"
	OUT="${base:-${SCRIPT_DIR}/shared-dir}/qfw-fallback-$(date +%Y%m%d-%H%M%S)"
fi
mkdir -p "${OUT}"
DASHBOARDS="qfw-jobs qfw-traces"

echo "window ${FROM} .. ${TO}, Grafana ${GRAFANA}, output ${OUT}"

# --- the snapshots -----------------------------------------------------
if [ "${ONLY}" != "images" ]; then
	python3 - "${GRAFANA}" "${PASSWORD}" "${FROM}" "${TO}" "${OUT}" ${DASHBOARDS} <<'PY'
"""
A Grafana local snapshot of each dashboard, built the way Share > Snapshot
does it in the UI. Grafana 13 stores snapshots in its v2 dashboard schema,
so the dashboard is read through the v2 API, every element's queries are
run for the window, and their frames replace the queries as the one
"snapshot" query of the Grafana data source. The time range is made
absolute, so the frozen data stays in view.
"""
import base64, datetime, json, re, sys, time, urllib.error, urllib.request

grafana, password, frm, to, out, *uids = sys.argv[1:]
auth = "Basic " + base64.b64encode(f"admin:{password}".encode()).decode()


def api(path, payload=None):
    req = urllib.request.Request(grafana + path, method="POST" if payload is not None else "GET")
    req.add_header("Authorization", auth)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(payload).encode() if payload is not None else None
    with urllib.request.urlopen(req, body, timeout=120) as r:
        return json.load(r)


UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def epoch_ms(when):
    """now, now-30m, an ISO date-time (local unless it carries a zone), or epoch milliseconds."""
    when = str(when).strip()
    if when.isdigit():
        return int(when)
    if when.startswith("now"):
        seconds = 0
        rest = when[3:]
        for sign, number, unit in re.findall(r"([+-])(\d+)([smhdw])", rest):
            seconds += (1 if sign == "+" else -1) * int(number) * UNITS[unit]
        return int((time.time() + seconds) * 1000)
    parsed = datetime.datetime.fromisoformat(when.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return int(parsed.timestamp() * 1000)


def iso_utc(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def heatmap_rows(frames):
    """
    What the Prometheus data source does in the browser for a format=heatmap
    query, which a server-side query skips: order the buckets by their upper
    bound, turn the cumulative counts into per-bucket counts, and merge them
    into one heatmap-rows frame whose fields are named by the bound. Frames
    that do not look like Prometheus buckets are returned untouched.
    """
    buckets = []
    for frame in frames:
        fields = frame.get("schema", {}).get("fields", [])
        values = frame.get("data", {}).get("values", [])
        if len(fields) != 2 or len(values) != 2:
            return frames
        bound = (fields[1].get("labels") or {}).get("le")
        if bound is None:
            return frames
        buckets.append((float(bound), bound, values[0], values[1]))
    if not buckets:
        return frames
    buckets.sort(key=lambda bucket: bucket[0])
    times = buckets[0][2]
    if any(bucket[2] != times for bucket in buckets):
        return frames
    fields = [dict(frames[0]["schema"]["fields"][0])]
    columns = [times]
    previous = None
    for _, bound, _, counts in buckets:
        # The le label is what makes the panel draw each row below its bound.
        fields.append({"name": bound, "type": "number", "labels": {"le": bound},
                       "typeInfo": {"frame": "float64", "nullable": True},
                       "config": {"displayNameFromDS": bound}})
        if previous is None:
            columns.append(list(counts))
        else:
            columns.append([None if count is None or below is None else count - below
                            for count, below in zip(counts, previous)])
        previous = counts
    meta = dict(frames[0]["schema"].get("meta") or {})
    meta["type"] = "heatmap-rows"
    return [{"schema": {"refId": frames[0]["schema"].get("refId", "A"),
                        "meta": meta, "fields": fields},
             "data": {"values": columns}}]


start_ms, end_ms = epoch_ms(frm), epoch_ms(to)
if end_ms <= start_ms:
    sys.exit(f"the window is empty: {frm} .. {to}")
created = []
for uid in uids:
    try:
        spec = api(f"/apis/dashboard.grafana.app/v2/namespaces/default/dashboards/{uid}")["spec"]
    except urllib.error.HTTPError as error:
        print(f"  {uid}: cannot read the dashboard ({error})", file=sys.stderr)
        continue
    # Every variable as "All", which is what a frozen page should show.
    variables = {}
    for variable in spec.get("variables", []):
        vspec = variable.get("spec", {})
        if vspec.get("name"):
            variables[vspec["name"]] = vspec.get("allValue") or ".*"
            vspec["current"] = {"text": ["All"], "value": ["$__all"]}

    def interpolate(text):
        for name, value in variables.items():
            text = text.replace("${" + name + "}", value).replace("$" + name, value)
        return text

    frames_total = 0
    for name, element in spec.get("elements", {}).items():
        data = element.get("spec", {}).get("data", {}).get("spec", {})
        queries = []
        heatmap = False
        for index, panel_query in enumerate(data.get("queries", [])):
            query = panel_query.get("spec", {}).get("query", {})
            request = dict(query.get("spec", {}))
            for key in ("expr", "query"):
                if isinstance(request.get(key), str):
                    request[key] = interpolate(request[key])
            request["refId"] = panel_query.get("spec", {}).get("refId") or chr(65 + index)
            request["datasource"] = {"uid": query.get("datasource", {}).get("name")}
            heatmap = heatmap or request.get("format") == "heatmap"
            request.setdefault("intervalMs", 15000)
            request.setdefault("maxDataPoints", 600)
            queries.append(request)
        if not queries:
            continue
        frames = []
        try:
            response = api("/api/ds/query", {"from": str(start_ms), "to": str(end_ms), "queries": queries})
            for ref, result in response.get("results", {}).items():
                if result.get("error"):
                    print(f"  {uid} {element['spec'].get('title')!r} {ref}: {result['error'][:100]}", file=sys.stderr)
                frames.extend(result.get("frames", []))
        except urllib.error.HTTPError as error:
            print(f"  {uid} {element['spec'].get('title')!r}: query failed ({error})", file=sys.stderr)
        if heatmap:
            frames = heatmap_rows(frames)
        data["queries"] = [{
            "kind": "PanelQuery",
            "spec": {
                "hidden": False,
                "refId": "A",
                "query": {
                    "kind": "DataQuery", "group": "grafana", "version": "v0",
                    "datasource": {"name": "grafana"},
                    "spec": {"queryType": "snapshot", "snapshot": frames},
                },
            },
        }]
        frames_total += len(frames)
    settings = spec.setdefault("timeSettings", {})
    settings["from"] = iso_utc(start_ms)
    settings["to"] = iso_utc(end_ms)
    settings["autoRefresh"] = ""
    spec["links"] = []
    dashboard = dict(spec)
    dashboard["uid"] = uid
    dashboard["snapshot"] = {"originalUrl": f"/d/{uid}"}
    window = f"{iso_utc(start_ms)[:16]}Z to {iso_utc(end_ms)[:16]}Z"
    name = f"{spec.get('title', uid)}, {window}"
    result = api("/api/snapshots", {"dashboard": dashboard, "name": name, "expires": 0})
    created.append({"uid": uid, "title": spec.get("title"), "name": name,
                    "url": result.get("url"), "key": result.get("key"),
                    "delete_key": result.get("deleteKey"), "frames": frames_total})
    print(f"  {spec.get('title')}: {frames_total} frames -> {result.get('url')}")
with open(f"{out}/snapshots.json", "w") as handle:
    json.dump({"from": frm, "to": to, "from_ms": start_ms, "to_ms": end_ms,
               "taken": time.strftime("%Y-%m-%dT%H:%M:%S"), "snapshots": created}, handle, indent=2)
PY
fi

# --- the images --------------------------------------------------------
if [ "${ONLY}" != "snapshot" ]; then
	chrome="${QFW_CHROME:-}"
	if [ -z "${chrome}" ]; then
		for candidate in google-chrome google-chrome-stable chromium chromium-browser \
				"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
				"/Applications/Chromium.app/Contents/MacOS/Chromium"; do
			if command -v "${candidate}" >/dev/null 2>&1; then
				chrome="$(command -v "${candidate}")"
				break
			elif [ -x "${candidate}" ]; then
				chrome="${candidate}"
				break
			fi
		done
	fi
	if [ -z "${chrome}" ]; then
		echo "no Chrome or Chromium found; set QFW_CHROME to take the images" >&2
	else
		img_from="${FROM}"
		img_to="${TO}"
		if [ -f "${OUT}/snapshots.json" ]; then
			# The same absolute window the snapshots froze.
			read -r img_from img_to < <(python3 -c \
				'import json,sys; d=json.load(open(sys.argv[1])); print(d["from_ms"], d["to_ms"])' \
				"${OUT}/snapshots.json")
		fi
		# A throwaway profile: anonymous, like a booth screen, and no clash
		# with a Chrome that is already running on this machine.
		profile="$(mktemp -d "${TMPDIR:-/tmp}/qfw-fallback-chrome.XXXXXX")"
		for uid in ${DASHBOARDS}; do
			url="${GRAFANA}/d/${uid}?kiosk&from=${img_from}&to=${img_to}"
			png="${OUT}/${uid}.png"
			rm -f "${png}"
			"${chrome}" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
				--user-data-dir="${profile}" \
				--window-size=1920,1600 --virtual-time-budget=20000 \
				--screenshot="${png}" "${url}" >/dev/null 2>&1 &
			pid=$!
			# Chrome writes the image once the page settles, and on a
			# Grafana page it does not always exit afterwards: wait for
			# the file, not for the process.
			waited=0
			while kill -0 "${pid}" 2>/dev/null && [ "${waited}" -lt 90 ]; do
				sleep 1
				waited=$((waited + 1))
				if [ -s "${png}" ]; then
					sleep 2
					break
				fi
			done
			{
				if kill -0 "${pid}" 2>/dev/null; then
					kill "${pid}"
					sleep 1
					kill -9 "${pid}"
				fi
				wait "${pid}"
			} 2>/dev/null
			if [ -s "${png}" ]; then
				echo "  ${uid}: ${png}"
			else
				echo "  ${uid}: no image" >&2
			fi
		done
		rm -rf "${profile}"
	fi
	python3 - "${OUT}" "${FROM}" "${TO}" "${GRAFANA}" <<'PY'
import html, json, os, sys, time
out, frm, to, grafana = sys.argv[1:]
snaps = {}
try:
    with open(os.path.join(out, "snapshots.json")) as handle:
        snaps = {s["uid"]: s for s in json.load(handle)["snapshots"]}
except OSError:
    pass
sections = []
for uid, title in (("qfw-jobs", "QFw Jobs"), ("qfw-traces", "QFw Traces")):
    link = ""
    if uid in snaps and snaps[uid].get("url"):
        url = html.escape(snaps[uid]["url"])
        link = f'<p>Live snapshot in Grafana: <a href="{url}?kiosk">{url}</a></p>'
    if os.path.exists(os.path.join(out, uid + ".png")):
        image = f'<img src="{uid}.png" alt="{html.escape(title)}">'
    else:
        image = "<p>(no image)</p>"
    sections.append(f"<section><h2>{html.escape(title)}</h2>{link}{image}</section>")
page = f"""<!doctype html>
<meta charset="utf-8">
<title>QFw dashboards, {html.escape(frm)} to {html.escape(to)}</title>
<style>
body {{ margin: 0; background: #111217; color: #ccccdc; font: 15px/1.5 system-ui, sans-serif; }}
header {{ padding: 16px 24px; }} section {{ padding: 0 24px 24px; }}
h1 {{ font-size: 20px; margin: 0 0 4px; }} h2 {{ font-size: 16px; margin: 0 0 8px; }}
img {{ width: 100%; max-width: 1920px; display: block; border: 1px solid #2c2d35; }}
a {{ color: #6e9fff; }}
</style>
<header><h1>QFw telemetry, {html.escape(frm)} to {html.escape(to)}</h1>
<p>Taken {time.strftime('%Y-%m-%d %H:%M')} from {html.escape(grafana)}.
These are the dashboards as they were; the snapshot links need that Grafana.</p></header>
{''.join(sections)}
"""
with open(os.path.join(out, "index.html"), "w") as handle:
    handle.write(page)
print(f"  page: {out}/index.html")
PY
fi
echo "done: ${OUT}"
