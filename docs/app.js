async function fetchJson(path){
  try{
    const res = await fetch(path + "?cb=" + Date.now());
    if(!res.ok) return null;
    return await res.json();
  }catch(e){
    return null;
  }
}

function pill(t){ return `<span class="pill">${t}</span>`; }

function cardCandidate(c){
  return `
    <div class="card">
      <div class="row">
        <span class="brand">${c.brand_guess || "Unknown"}</span>
        ${pill(c.matched_query || "query")}
      </div>
      <div class="divider"></div>
      <div class="small">${c.title || ""}</div>
      <div style="margin-top:8px;">
        <a href="${c.evidence_link}" target="_blank">Evidence link</a>
      </div>
    </div>
  `;
}

function cardShortlisted(b){
  const contact = b.contact || {};
  const email = contact.primary_email || "";
  const form = contact.contact_form_url || "";
  const contactLine = email ? `Email: <b>${email}</b>` : (form ? `Form: <a href="${form}" target="_blank">open</a>` : `No contact found`);

  return `
    <div class="card">
      <div class="row">
        <span class="brand">${b.brand_name}</span>
        ${pill("Score: " + (b.score ?? 0))}
        ${b.has_contact ? pill("Contact: yes") : pill("Contact: no")}
      </div>

      <div class="row" style="margin-top:8px;">
        ${(b.score_reasons || []).map(pill).join(" ")}
      </div>

      <div class="divider"></div>

      <div class="small">${contactLine}</div>
      <div class="small" style="margin-top:6px;">
        ${b.website ? `<a href="${b.website}" target="_blank">Website</a>` : ""}
        ${b.evidence_link ? ` | <a href="${b.evidence_link}" target="_blank">Evidence</a>` : ""}
      </div>

      <details>
        <summary>View evidence snippets</summary>
        <pre>${JSON.stringify(b.site?.fetched_pages || {}, null, 2)}</pre>
      </details>
    </div>
  `;
}

async function load(){
  const discovery = await fetchJson("./discovery.json");
  const report = await fetchJson("./report.json");
  const shortlist = await fetchJson("./shortlist.json");

  const meta = document.getElementById("meta");
  const ts = shortlist?.generated_at || report?.generated_at || discovery?.generated_at;
  meta.textContent = ts ? ("Last run: " + ts) : "No data yet. Run the workflow.";

  // Discovery section
  const dEl = document.getElementById("discovery");
  const candidates = discovery?.candidates || [];
  dEl.innerHTML = candidates.slice(0, 12).map(cardCandidate).join("") || `<div class="card"><div class="small">No candidates yet.</div></div>`;

  // Shortlist section
  const sEl = document.getElementById("shortlist");
  const short = shortlist?.shortlist || report?.brands?.slice(0,10) || [];
  sEl.innerHTML = short.map(cardShortlisted).join("") || `<div class="card"><div class="small">No shortlist yet.</div></div>`;
}

load();
