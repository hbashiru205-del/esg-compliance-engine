import html

_CAP = 700

def make_excerpt_records(chunks):
    return [{"source": c.get("source", "Unknown"),
             "index": c.get("index", "?"),
             "text": c.get("text", "")} for c in chunks]

def render_excerpts(st, excerpts):
    if not excerpts:
        return
    with st.expander(f"\U0001f4c4 Show retrieved excerpts ({len(excerpts)})"):
        for e in excerpts:
            text = e["text"]
            shown = text[:_CAP] + ("…" if len(text) > _CAP else "")
            st.markdown(
                f"**[Source: {html.escape(str(e['source']))}, "
                f"Chunk #{html.escape(str(e['index']))}]**")
            st.markdown(f"> {html.escape(shown).replace(chr(10), '  ' + chr(10) + '> ')}")
            st.markdown("---")
