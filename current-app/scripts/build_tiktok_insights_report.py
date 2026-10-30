"""Seal the verified October27 readout for The Stats and an offline HTML report.

No optional reporting runtime, browser dependency, service or API key is needed.
The completed analytical outputs are inputs; originals are never rewritten.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path, PureWindowsPath
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from stats_app.saved_insights import REPORT_KEY, SCHEMA_VERSION


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def clean(value, key=""):
    if isinstance(value, dict):
        return {k: clean(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v, key) for v in value]
    if isinstance(value, str) and PureWindowsPath(value).is_absolute():
        # Local execution locations are not portable source identities.
        return PureWindowsPath(value).name
    if value is not None and (key == "post_id" or key.endswith("_id")):
        return str(value)
    return value


def inline(text):
    pattern = re.compile(r"\*\*([^*]+)\*\*|\[([^\]]+)\]\((https?://[^\s)]+)\)|`([^`]+)`")
    result, offset = [], 0
    for match in pattern.finditer(text):
        result.append(html.escape(text[offset:match.start()]))
        if match[1] is not None:
            result.append("<strong>" + html.escape(match[1]) + "</strong>")
        elif match[2] is not None:
            result.append('<a href="' + html.escape(match[3], quote=True) + '" rel="noopener noreferrer">' + html.escape(match[2]) + "</a>")
        else:
            result.append("<code>" + html.escape(match[4]) + "</code>")
        offset = match.end()
    result.append(html.escape(text[offset:]))
    return "".join(result)


def render_markdown(text):
    """Render the deliberately small report vocabulary with escaped text only."""
    lines = text.splitlines()
    result = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                rows.append([part.strip() for part in lines[index].strip().strip("|").split("|")])
                index += 1
            header = rows[0]
            body = rows[2:] if len(rows) > 1 and all(re.fullmatch(r":?-+:?", part.replace(" ", "")) for part in rows[1]) else rows[1:]
            result.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+inline(v)+'</th>' for v in header) + '</tr></thead><tbody>')
            result.extend('<tr>' + ''.join('<td>'+inline(v)+'</td>' for v in row) + '</tr>' for row in body)
            result.append('</tbody></table></div>')
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level = len(heading[1])
            result.append(f'<h{level}>'+inline(heading[2])+f'</h{level}>')
            index += 1
            continue
        listed = re.match(r"^(?:-\s+|\d+\.\s+)(.+)$", line)
        if listed:
            ordered = bool(re.match(r"^\d+\.", line))
            tag = "ol" if ordered else "ul"
            result.append('<'+tag+'>')
            while index < len(lines):
                item = re.match(r"^(?:-\s+|\d+\.\s+)(.+)$", lines[index].strip())
                if not item:
                    break
                result.append('<li>'+inline(item[1])+'</li>')
                index += 1
            result.append('</'+tag+'>')
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(?:#|\||- |\d+\. )", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        result.append('<p>'+inline(' '.join(paragraph))+'</p>')
    return '\n'.join(result)


def render_html(report, assets, sources):
    sections = []
    image_sections = {"momentum": "monthly_trends.png", "song-choice": "song_candidates.png"}
    for section in report["sections"]:
        body = render_markdown(section["markdown"])
        if section["id"] in image_sections:
            name = image_sections[section["id"]]
            body += '<figure><img alt="'+html.escape(section['title'], quote=True)+'" src="data:image/png;base64,'+base64.b64encode(assets[name]).decode()+'"></figure>'
        refs = [{'query': q, **report['queries'][q]['source']} for q in section['queryIds']]
        body += '<details><summary>Sources and reporting scope</summary><pre>'+html.escape(json.dumps(refs, ensure_ascii=False, indent=2))+'</pre></details>'
        sections.append('<section id="'+html.escape(section['id'],quote=True)+'">'+body+'</section>')
    sections.append('<details><summary>Complete source receipts and fingerprints</summary><pre>'+html.escape(json.dumps(sources, ensure_ascii=False, indent=2))+'</pre></details>')
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>'+html.escape(report['title'])+'</title><style>body{margin:0;background:#f7f9fb;color:#17232e;font:17px/1.65 system-ui,Segoe UI,sans-serif}main{max-width:1060px;margin:auto;padding:40px 28px 80px;background:white}h1{font-size:2.35rem;line-height:1.16;margin:0 0 14px}h2{font-size:1.55rem;line-height:1.3;margin:0 0 18px}section{margin:44px 0}a{color:#006d79;text-underline-offset:3px}li{margin:10px 0}.scope{color:#52616e}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.93rem}th,td{text-align:left;vertical-align:top;padding:12px 10px;border-bottom:1px solid #dce3e8}th{background:#edf4f6}figure{margin:26px 0}img{width:100%;height:auto}details{margin-top:22px;color:#52616e;font-size:.86rem}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:18px;font-size:.8rem}nav{display:flex;gap:12px;flex-wrap:wrap;font-size:.88rem}footer{border-top:1px solid #dce3e8;padding-top:24px;color:#52616e;font-size:.88rem}@media(max-width:600px){main{padding:24px 16px}h1{font-size:1.9rem}body{font-size:16px}th,td{padding:8px}}@media print{body{background:white}main{max-width:none;padding:0}nav,details{display:none}section{break-inside:auto}figure,table{break-inside:avoid}}</style></head><body><main><header><h1>'+html.escape(report['title'])+'</h1><p class="scope">The Stats · Saved analysis prepared October 27, 2026. Each finding retains its own reporting dates. TikTok for Artists: pending.</p><nav>'+''.join('<a href="#'+html.escape(s['id'],quote=True)+'">'+html.escape(s['title'])+'</a>' for s in report['sections'])+'</nav></header>'+''.join(sections)+'<footer>Original collections remain unchanged. This fixed readout uses analysis version meta-story-backfill-20261024 and TikTok collection tiktok-20261027-studio; it does not refresh when dashboard source selection changes. No external scripts, fonts, images, accounts or report plugins are needed to read this file.</footer></main></body></html>'


def build(source: Path, output: Path):
    inputs = ["report-app/src/data.json", "cross_platform_summary.json", "tiktok/analysis_results.json",
              "spotify/analysis_receipt.json", "other_platforms/findings.json", "monthly_trends.png", "song_candidates.png"]
    input_hashes = {name: digest((source/name).read_bytes()) for name in inputs}
    if output.exists():
        manifest = read_json(output/'manifest.json')
        if manifest.get('input_sha256') == input_hashes:
            # Replay is read-only and still checks every retained asset.
            from stats_app.saved_insights import SavedInsights
            SavedInsights(output)
            return {'key':REPORT_KEY,'idempotent':True,'manifest_sha256':digest((output/'manifest.json').read_bytes())}
        raise ValueError("Refusing to replace a sealed report; build a separately named analysis version.")
    old = read_json(source/'report-app/src/data.json')
    cross = read_json(source/'cross_platform_summary.json')
    report = clean({'schema_version':SCHEMA_VERSION,'key':REPORT_KEY,'title':old['title'],
                    'prepared_date':'2026-10-27','analysis_key':'meta-story-backfill-20261024',
                    'tiktok_collection_key':'tiktok-20261027-studio','artists_status':'pending',
                    'fixed_report':True,'queries':old['queries'],'sections':old['reportSections']})
    # Delivery paths differ from the analytical workspace. Keep its original
    # draft intact and make the native readout explicit about reproduction.
    for section in report['sections']:
        section['markdown'] = section['markdown'].replace(
            'Apple reinforces that choice:176', 'Apple reinforces that choice: 176')
        if section['id'] == 'scope':
            section['markdown'] = section['markdown'].replace(
                'Reproduce the analytical outputs with analyze_cross_platform.py and the three platform analysis scripts in this folder. The companion notebook retains executed comparisons and plots.',
                'Reproduce the analytical outputs in `outputs/tiktok_cross_platform_analysis_20261027/` using `analyze_cross_platform.py`, `tiktok/analyze_tiktok.py`, `spotify/analyze_spotify.py`, and `other_platforms/analyze.py`. The executed companion notebook is `outputs/tiktok_cross_platform_analysis_20261027/analysis.ipynb`.')
    # Source lineage carries original identities/hashes while removing machine locations.
    tiktok = read_json(source/'tiktok/analysis_results.json')
    spotify = read_json(source/'spotify/analysis_receipt.json')
    other = read_json(source/'other_platforms/findings.json')
    sources = clean({'analysis_key':report['analysis_key'],'analysis_database_sha256':cross['analysis_database_sha256'],
                     'tiktok_collection_key':report['tiktok_collection_key'],'tiktok_manifest_sha256':cross['tiktok_manifest_sha256'],
                     'tiktok_tables':tiktok['sources'],'spotify_tables':spotify['source_receipts'],
                     'other_platform_tables':other['sources'],'limitations':cross['limitations']})
    assets = {name:(source/name).read_bytes() for name in ['monthly_trends.png','song_candidates.png']}
    assets['report.json'] = json_bytes(report)
    assets['sources.json'] = json_bytes(sources)
    markdown = '# '+report['title']+'\n\nPrepared October 27, 2026. This is a fixed report; each finding retains its own reporting period.\n\n'
    for section in report['sections']:
        markdown += section['markdown']+'\n\n'
        name = {'momentum':'monthly_trends.png','song-choice':'song_candidates.png'}.get(section['id'])
        if name:
            markdown += '!['+section['title']+']('+name+')\n\n'
    markdown += 'Source versions: meta-story-backfill-20261024 and tiktok-20261027-studio. Full source table hashes and limits are retained in sources.json. TikTok for Artists remains pending.\n'
    assets['report.md'] = markdown.encode('utf-8')
    assets['report.html'] = render_html(report, assets, sources).encode('utf-8')
    manifest = {'schema_version':SCHEMA_VERSION,'key':REPORT_KEY,'title':report['title'],'prepared_date':'2026-10-27',
                'analysis_key':report['analysis_key'],'tiktok_collection_key':report['tiktok_collection_key'],
                'artists_status':'pending','fixed_report':True,'shared_calendar_start':cross['shared_calendar_start'],
                'shared_calendar_end':cross['shared_calendar_end'],
                'source_fingerprints':{'analysis_database_sha256':cross['analysis_database_sha256'],'tiktok_manifest_sha256':cross['tiktok_manifest_sha256']},
                'input_sha256':input_hashes,'assets':{name:{'bytes':len(raw),'sha256':digest(raw)} for name,raw in assets.items()}}
    # Stage in a new directory; a failure never overwrites the old readout.
    output.mkdir(parents=True,exist_ok=False)
    for name,raw in assets.items():
        (output/name).write_bytes(raw)
    raw = json_bytes(manifest)
    (output/'manifest.json').write_bytes(raw)
    return {'key':REPORT_KEY,'idempotent':False,'manifest_sha256':digest(raw),'assets':len(assets),'bytes':sum(len(v) for v in assets.values())}


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=PROJECT/'outputs/tiktok_cross_platform_analysis_20261027')
    parser.add_argument('--output',type=Path,default=PROJECT/'data/reports'/REPORT_KEY)
    args = parser.parse_args()
    print(json.dumps(build(args.source,args.output),indent=2))
