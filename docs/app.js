async function load() {
  const res = await fetch("./report.json?cb=" + Date.now());
  const data = await res.json();

  document.getElementById("meta").textContent = "Last run: " + data.generated_at;

  const pill = (t) => `<span class="pill">${t}</span>`;

  const render = (item) => {
    const r = (item.reasons || []).map(pill).join(" ");
    const links = item.links || {};
    const c = item.contact || {};
    const email = c.primary_email || "";
    const form = c.contact_form_url || "";

    const contactLine = email
      ? `Email: <b>${email}</b>`
      : form
        ? `Contact form: <a target="_blank" href="${form}">open</a>`
        : `<span class="pill">No contact found</span>`;

    return `
      <div class="card">
        <div class="row">
          <span class="brand">${item.brand}</span>
          ${pill("Score: " + item.score)}
          ${item.has_contact ? pill("Contact: yes") : pill("Contact: no")}
        </div>

        <div class="row" style="margin-top:8px;">${r}</div>

        <div class="divider"></div>

        <div><b>Pitch:</b> ${item.pitch}</div>
        <div class="contact" style="margin-top:6px;">${contactLine}</div>

        <div class="contact" style="margin-top:8px;">
          ${links.homepage ? `<a target="_blank" href="${links.homepage}">Homepage</a>` : ""}
          ${links.product ? ` | <a target="_blank" href="${links.product}">Product</a>` : ""}
          ${links.careers ? ` | <a target="_blank" href="${links.careers}">Careers</a>` : ""}
          ${links.press ? ` | <a target="_blank" href="${links.press}">Press</a>` : ""}
        </div>

        <details>
          <summary>Outreach drafts</summary>

          <div style="margin-top:10px;"><b>DM</b></div>
          <textarea readonly>${item.outreach.dm || ""}</textarea>

          <div style="margin-top:10px;"><b>Email subject</b>: ${item.outreach.email_subject || ""}</div>
          <div style="margin-top:8px;"><b>Email</b></div>
          <textarea readonly>${item.outreach.email_body || ""}</textarea>
        </details>
      </div>
    `;
  };

  document.getElementById("top").innerHTML = (data.top5 || []).map(render).join("");
  document.getElementById("all").innerHTML = (data.all || []).map(render).join("");
}

load();
