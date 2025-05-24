// Get the backend URL based on the environment
const baseURL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? "http://localhost:8000"
    : "/api"; // When deployed on Vercel, the API is available at /api

// State management
let selectedLeads = new Map();
let processedLeads = new Set(); // Track processed lead emails

// Loading spinner functions
function showLoading() {
    const spinner = document.createElement('div');
    spinner.className = 'spinner-overlay';
    spinner.innerHTML = '<div class="spinner"></div>';
    document.body.appendChild(spinner);
}

function hideLoading() {
    const spinner = document.querySelector('.spinner-overlay');
    if (spinner) {
        spinner.remove();
    }
}

function isLeadProcessed(email) {
    return processedLeads.has(email);
}

function markLeadAsProcessed(lead) {
    if (lead.email) {
        processedLeads.add(lead.email);
    }
}

function getPhoneNumbers(contactInfo) {
    if (!contactInfo) return [];
    
    console.log('Processing contact info for phone numbers:', contactInfo);
    
    const phones = [];
    
    // First try sanitized phones as they are most reliable
    if (contactInfo.sanitized_phone) {
        console.log('Found sanitized phone:', contactInfo.sanitized_phone);
        phones.push(contactInfo.sanitized_phone);
    }
    if (contactInfo.sanitized_mobile_phone) {
        console.log('Found sanitized mobile:', contactInfo.sanitized_mobile_phone);
        phones.push(contactInfo.sanitized_mobile_phone);
    }
    if (contactInfo.enriched_sanitized_phone) {
        console.log('Found enriched sanitized phone:', contactInfo.enriched_sanitized_phone);
        phones.push(contactInfo.enriched_sanitized_phone);
    }
    if (contactInfo.enriched_sanitized_mobile_phone) {
        console.log('Found enriched sanitized mobile:', contactInfo.enriched_sanitized_mobile_phone);
        phones.push(contactInfo.enriched_sanitized_mobile_phone);
    }
    if (contactInfo.revealed_sanitized_phone) {
        console.log('Found revealed sanitized phone:', contactInfo.revealed_sanitized_phone);
        phones.push(contactInfo.revealed_sanitized_phone);
    }
    if (contactInfo.revealed_sanitized_mobile_phone) {
        console.log('Found revealed sanitized mobile:', contactInfo.revealed_sanitized_mobile_phone);
        phones.push(contactInfo.revealed_sanitized_mobile_phone);
    }
    
    // Then try other phone fields
    if (contactInfo.direct_phone) {
        console.log('Found direct phone:', contactInfo.direct_phone);
        phones.push(contactInfo.direct_phone);
    }
    if (contactInfo.mobile_phone) {
        console.log('Found mobile phone:', contactInfo.mobile_phone);
        phones.push(contactInfo.mobile_phone);
    }
    if (contactInfo.revealed_direct_phone) {
        console.log('Found revealed direct phone:', contactInfo.revealed_direct_phone);
        phones.push(contactInfo.revealed_direct_phone);
    }
    if (contactInfo.revealed_mobile_phone) {
        console.log('Found revealed mobile phone:', contactInfo.revealed_mobile_phone);
        phones.push(contactInfo.revealed_mobile_phone);
    }
    
    // Add phone numbers from arrays
    if (contactInfo.phone_numbers && contactInfo.phone_numbers.length) {
        console.log('Found phone numbers array:', contactInfo.phone_numbers);
        phones.push(...contactInfo.phone_numbers);
    }
    if (contactInfo.revealed_phone_numbers && contactInfo.revealed_phone_numbers.length) {
        console.log('Found revealed phone numbers array:', contactInfo.revealed_phone_numbers);
        phones.push(...contactInfo.revealed_phone_numbers);
    }
    
    // Remove duplicates and nulls
    const uniquePhones = [...new Set(phones.filter(p => p))];
    console.log('Final unique phone numbers:', uniquePhones);
    return uniquePhones;
}

function createLinkedInLink(url, text) {
    if (!url) return '';
    return `
        <a href="${url}" target="_blank" rel="noopener noreferrer" class="linkedin-link">
            <svg class="linkedin-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#0077b5">
                <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/>
            </svg>
            ${text}
        </a>
    `;
}

function createLeadCard(lead, contactInfo = null, showActions = true) {
    console.log('Creating lead card with contact info:', contactInfo);
    const phones = contactInfo ? getPhoneNumbers(contactInfo) : [];
    console.log('Processed phone numbers for card:', phones);
    
    return `
        <div class="lead-card">
            <div class="lead-info">
                <div class="person-section">
                    <h3 class="lead-title">${lead.firstname} ${lead.lastname}</h3>
                    <p class="lead-detail"><strong>Company:</strong> ${lead.company}</p>
                    ${lead.job_title ? `<p class="lead-detail"><strong>Role:</strong> ${lead.job_title}</p>` : ''}
                    <p class="lead-detail"><strong>Email:</strong> ${lead.email || 'N/A'}</p>
                    ${phones.length > 0 ? `
                        <div class="contact-info">
                            <strong>Phone Numbers:</strong><br>
                            ${phones.map(phone => `<span class="phone-number">${phone}</span>`).join('<br>')}
                        </div>
                    ` : '<p class="lead-detail">No phone numbers available</p>'}
                    ${lead.description ? `<p class="lead-description">${lead.description}</p>` : ''}
                    ${lead.linkedin_url ? createLinkedInLink(lead.linkedin_url, 'View Profile on LinkedIn') : ''}
                </div>
                
                ${lead.company ? `
                    <div class="company-section">
                        <h4 class="section-title">Company Information</h4>
                        <p class="lead-detail"><strong>Name:</strong> ${lead.company}</p>
                        ${lead.company_description ? `
                            <p class="company-description">${lead.company_description}</p>
                        ` : ''}
                        ${lead.company_linkedin_url ? createLinkedInLink(lead.company_linkedin_url, 'View Company on LinkedIn') : ''}
                    </div>
                ` : ''}
            </div>
            ${showActions ? `
                <div class="lead-actions">
                    <button onclick='addToSelected(${JSON.stringify(lead)})'>Select</button>
                </div>
            ` : ''}
        </div>
    `;
}

function updateSelectedLeadsUI() {
    const container = document.querySelector('.selected-leads-list');
    const selectedLeadsCard = document.getElementById('selectedLeads');
    
    if (selectedLeads.size === 0) {
        selectedLeadsCard.style.display = 'none';
        return;
    }
    
    selectedLeadsCard.style.display = 'block';
    container.innerHTML = Array.from(selectedLeads.values())
        .map(lead => createLeadCard(lead, null, false))
        .join('');
}

function addToSelected(lead) {
    if (isLeadProcessed(lead.email)) {
        alert("This lead has already been processed.");
        return;
    }
    selectedLeads.set(lead.email, lead);
    updateSelectedLeadsUI();
}

function removeLead(email) {
    selectedLeads.delete(email);
    updateSelectedLeadsUI();
}

// Create Lead Form
document.getElementById("createLeadForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    
    const data = {
        firstname: form.firstname.value,
        lastname: form.lastname.value,
        email: form.email.value,
        phone: form.phone.value,
        company: form.company.value,
        message: form.message.value || ""
    };

    if (isLeadProcessed(data.email)) {
        alert("This lead has already been processed.");
        return;
    }

    try {
        submitButton.disabled = true;
        showLoading();
        
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
                <h3 class="lead-title">✅ Lead Created</h3>
                <p class="lead-detail"><strong>Email:</strong> ${result.email}</p>
                <p class="lead-detail"><strong>Score:</strong> ${result.score}</p>
            </div>
        `;
        markLeadAsProcessed(data);
        form.reset();
    } catch (error) {
        console.error("Error:", error);
        alert("Failed to create lead.");
    } finally {
        submitButton.disabled = false;
        hideLoading();
    }
});

// Find Leads Form
document.getElementById("findLeadsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submitButton = form.querySelector('button[type="submit"]');
    
    const data = {
        job_title: form.job_title.value,
        organization_name: form.organization_name.value,
        location: form.location.value,
        industry_tag: form.industry_tag.value,
        exclude_emails: Array.from(processedLeads)
    };

    try {
        submitButton.disabled = true;
        showLoading();
        
        const response = await fetch(`${baseURL}/find-leads`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data)
        });

        const result = await response.json();
        
        if (result.results.length === 0) {
            document.getElementById("results").innerHTML = `
                <div class="card">
                    <h3>No new leads found</h3>
                    <p>All matching leads have already been processed. Try different search criteria.</p>
                </div>
            `;
            return;
        }
        
        const html = result.results
            .map(res => createLeadCard(res.lead, res.apollo_contact_info))
            .join("");

        document.getElementById("results").innerHTML = html;
    } catch (error) {
        console.error("Error:", error);
        alert("Failed to fetch leads.");
    } finally {
        submitButton.disabled = false;
        hideLoading();
    }
});

// Process Selected Leads
document.getElementById("processSelectedLeads").addEventListener("click", async () => {
    if (selectedLeads.size === 0) {
        alert("Please select leads to process first.");
        return;
    }

    const sendImmediately = document.getElementById("sendImmediately").checked;
    const leads = Array.from(selectedLeads.values());
    const button = document.getElementById("processSelectedLeads");

    try {
        button.disabled = true;
        showLoading();
        
        const response = await fetch(`${baseURL}/process-leads`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify({
                leads: leads,
                send_immediately: sendImmediately
            })
        });

        const result = await response.json();
        
        // Mark processed leads
        result.results.forEach(res => {
            if (!res.error && res.lead.email) {
                markLeadAsProcessed(res.lead);
            }
        });
        
        // Display processing results
        const html = result.results.map((res) => {
            const card = createLeadCard(res.lead, res.apollo_contact_info, false);
            return card.replace('</div></div>', `
                    ${res.error ? 
                        `<p class="error">Error: ${res.error}</p>` :
                        `<p class="lead-detail"><strong>Score:</strong> ${res.score}</p>
                         <p class="lead-detail"><strong>Email Status:</strong> 
                            <span class="status-badge ${res.email_sent ? 'success' : 'pending'}">
                                ${res.email_sent ? 'Sent' : 'Generated'}
                            </span>
                         </p>`
                    }
                </div>
            </div>`);
        }).join("");

        document.getElementById("results").innerHTML = html;
        
        // Clear selected leads after processing
        selectedLeads.clear();
        updateSelectedLeadsUI();
    } catch (error) {
        console.error("Error:", error);
        alert("Failed to process leads.");
    } finally {
        button.disabled = false;
        hideLoading();
    }
});
