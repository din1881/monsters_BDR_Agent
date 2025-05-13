const baseURL = "http://localhost:8000"; // Change this if deployed

// Create Lead Form
document.getElementById("createLeadForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = {
    firstname: form.firstname.value,
    lastname: form.lastname.value,
    email: form.email.value,
    phone: form.phone.value,
    company: form.company.value,
    message: form.message.value || ""
  };

  try {
    const response = await fetch(`${baseURL}/create-lead`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data)
    });

    const result = await response.json();
    document.getElementById("results").innerHTML = `
      <div class="card">
        <h3>✅ Lead Created</h3>
        <p><strong>Email:</strong> ${result.email}</p>
        <p><strong>Score:</strong> ${result.score}</p>
      </div>
    `;
  } catch (error) {
    console.error("Error:", error);
    alert("Failed to create lead.");
  }
});

// Find Leads Form
document.getElementById("findLeadsForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const data = {
    job_title: form.job_title.value,
    organization_name: form.organization_name.value,
    location: form.location.value,
    industry_tag: form.industry_tag.value
  };

  try {
    const response = await fetch(`${baseURL}/find-leads`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data)
    });

    const result = await response.json();

    const html = result.results.map((res) => `
      <div class="card">
        <h3>${res.lead.firstname} ${res.lead.lastname}</h3>
        <p><strong>Company:</strong> ${res.lead.company}</p>
        <p><strong>Email:</strong> ${res.lead.email}</p>
        <p><strong>Score:</strong> ${res.score}</p>
        <p><strong>Email Sent:</strong><br/>${res.email}</p>
      </div>
    `).join("");

    document.getElementById("results").innerHTML = html;
  } catch (error) {
    console.error("Error:", error);
    alert("Failed to fetch leads.");
  }
});
