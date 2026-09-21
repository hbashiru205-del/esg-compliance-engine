"""Plain-text version of the answers, plus a copy-to-clipboard button."""
import html
import json


def plain_text(pairs, start: int = 1) -> str:
    blocks = []
    for n, p in enumerate(pairs, start):
        block = f"Q{n}. {p['question']}\n\n{p['answer'].strip()}"
        if p.get("citations"):
            block += "\n\nSources: " + "; ".join(p["citations"])
        blocks.append(block)
    return "\n\n---\n\n".join(blocks)


_STYLE = ("width:100%;padding:.45rem .75rem;border-radius:8px;"
          "cursor:pointer;border:1px solid rgba(250,250,250,.25);"
          "background:#262730;color:#fafafa;"
          "font:14px 'Source Sans Pro',sans-serif")


def copy_button_html(text: str, label: str) -> str:
    payload = json.dumps(text).replace("</", "<\\/")
    return f"""<style>body{{margin:0}}</style>
<button id="b" style="{_STYLE}">{html.escape(label)}</button>
<script>
const T = {payload}, L = {json.dumps(label)};
const b = document.getElementById("b");
function legacy() {{
  const t = document.createElement("textarea");
  t.value = T; t.style.position = "fixed"; t.style.opacity = "0";
  document.body.appendChild(t); t.focus(); t.select();
  let ok = false;
  try {{ ok = document.execCommand("copy"); }} catch (e) {{}}
  document.body.removeChild(t);
  return ok;
}}
b.onclick = async () => {{
  let ok = false;
  try {{ await navigator.clipboard.writeText(T); ok = true; }}
  catch (e) {{ ok = legacy(); }}
  b.textContent = ok ? "\\u2713 Copied" : "Copy blocked - use the plain text box";
  setTimeout(() => {{ b.textContent = L; }}, 2200);
}};
</script>"""
