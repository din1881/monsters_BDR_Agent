import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from dotenv import load_dotenv
import openai
from langchain_openai.llms import OpenAI as LangChainLLM
from langchain.agents import initialize_agent, Tool
from openai import OpenAI
from langchain.agents.agent_types import AgentType
from fastapi.middleware.cors import CORSMiddleware


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Initialize OpenAI
openai.api_key = OPENAI_API_KEY

# Initialize FastAPI
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class LeadRequest(BaseModel):
    firstname: str
    lastname: str
    email: str
    phone: str
    company: str
    message: str = ""

class ApolloSearchRequest(BaseModel):
    job_title: str
    organization_name: str = ""
    location: str = ""
    industry_tag: str = ""

# LangChain Setup
llm = LangChainLLM(temperature=0, openai_api_key=OPENAI_API_KEY)

lead_score_tool = Tool(
    name="LeadScorer",
    func=lambda x: f"Score for lead '{x}': High potential (based on title and industry match)",
    description="Scores a lead based on description and role"
)

agent = initialize_agent([lead_score_tool], llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=False)

# Utils
def generate_email(lead: LeadRequest) -> str:
    prompt = f"""
    SkillUp MENA is the pioneer of e-learning services, with our vast curated e-learning library of over 85000 courses, all offered by the world's leading training providers. Our aim is to simplify the corporate training process by offering a unique engaging learning experience, whilst marinating our partners' business needs.
    Write a personalized cold outreach email to {lead.firstname} {lead.lastname} at {lead.company}.
    Mention potential value and request a short call. Keep it under 120 words.
    """
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail="Error generating email content.")

def send_email_smtp(to_email: str, subject: str, body: str):
    msg = MIMEMultipart()
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
        logger.info(f"Email sent to {to_email}")
        return {"status": "success", "message": "Email sent successfully."}
    except Exception as e:
        logger.error(f"SMTP error: {e}")
        raise HTTPException(status_code=500, detail="Error sending email.")

def push_to_hubspot(lead: LeadRequest):
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json"
    }

    # Check if contact exists
    search_url = "https://api.hubapi.com/crm/v3/objects/contacts/search"
    search_body = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": lead.email
                    }
                ]
            }
        ]
    }

    try:
        search_resp = requests.post(search_url, json=search_body, headers=headers)
        search_resp.raise_for_status()
        results = search_resp.json().get("results", [])

        if results:
            contact_id = results[0]["id"]
            # Update existing contact
            update_url = f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}"
            update_data = {
                "properties": {
                    "firstname": lead.firstname,
                    "lastname": lead.lastname,
                    "phone": lead.phone,
                    "company": lead.company
                }
            }
            update_resp = requests.patch(update_url, json=update_data, headers=headers)
            update_resp.raise_for_status()
            logger.info(f"Contact updated in HubSpot: {lead.email} - {update_resp.json()}")
            return update_resp.json()
        else:
            # Create new contact
            create_url = "https://api.hubapi.com/crm/v3/objects/contacts"
            data = {
                "properties": {
                    "email": lead.email,
                    "firstname": lead.firstname,
                    "lastname": lead.lastname,
                    "phone": lead.phone,
                    "company": lead.company
                }
            }
            create_resp = requests.post(create_url, json=data, headers=headers)
            create_resp.raise_for_status()
            logger.info(f"Lead pushed to HubSpot: {lead.email} - {create_resp.json()}")
            return create_resp.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"HubSpot API error: {e}")
        raise HTTPException(status_code=500, detail="Error pushing lead to HubSpot.")

    
# Endpoints
@app.post("/create-lead")
async def create_lead(lead: LeadRequest):
    email_text = generate_email(lead)
    hubspot_response = push_to_hubspot(lead)
    lead_score = agent.run(f"Score this lead: {lead.firstname} {lead.lastname}, role at {lead.company}")
    
    # Send email using SMTP
    email_subject = f"Exciting Opportunity for {lead.firstname} {lead.lastname} at {lead.company}"
    send_email_smtp(lead.email, email_subject, email_text)
    
    return {"hubspot": hubspot_response, "email": email_text, "score": lead_score}

@app.post("/find-leads")
async def find_leads(query: ApolloSearchRequest):
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY
    }
    payload = {
        "per_page": 5
    }

    if query.job_title:
        payload["person_titles"] = [query.job_title]

    if query.organization_name:
        payload["organization_names"] = [query.organization_name]

    if query.location:
        payload["person_locations"] = [query.location]

    if query.industry_tag:
        payload["industry_tags"] = [query.industry_tag]

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        people = response.json().get("people", [])
        leads_created = []
        
        # Enrich each person's data to get emails
        for person in people:
            # Enrichment request
            enrich_url = "https://api.apollo.io/api/v1/people/match"
            enrich_payload = {
                "first_name": person.get("first_name", ""),
                "last_name": person.get("last_name", ""),
                "organization_name": person.get("organization", {}).get("name", ""),
                "linkedin_url": person.get("linkedin_url", ""),
                "reveal_personal_emails": True
            }
            
            enrich_response = requests.post(enrich_url, headers=headers, json=enrich_payload)
            enrich_response.raise_for_status()
            enriched_data = enrich_response.json().get("person", {})
            
            # Use enriched data if available, otherwise fall back to original data
            lead_data = LeadRequest(
                firstname=enriched_data.get("first_name", person.get("first_name", "")),
                lastname=enriched_data.get("last_name", person.get("last_name", "")),
                email=enriched_data.get("email", person.get("email", "")),
                phone=enriched_data.get("phone_number", person.get("phone", "")),
                company=enriched_data.get("organization_name", person.get("organization", {}).get("name", "")),
                message=""
            )
            
            email_text = generate_email(lead_data)
            hubspot_response = push_to_hubspot(lead_data)
            lead_score = agent.run(f"Score this lead: {lead_data.firstname} {lead_data.lastname}, role at {lead_data.company}, given that this what we do, SkillUp MENA is the pioneer of e-learning services, with our vast curated e-learning library of over 85000 courses, all offered by the world's leading training providers. Our aim is to simplify the corporate training process by offering a unique engaging learning experience, whilst marinating our partners' business needs.")
            
            # Send email using SMTP
            if lead_data.email:  # Only send if we have an email
                send_email_smtp("dina.adel@monstersgraphics.com", f"Exciting Opportunity for {lead_data.firstname} {lead_data.lastname}", email_text)
        
            leads_created.append({
                "lead": lead_data.dict(),
                "email": email_text,
                "hubspot": hubspot_response,
                "score": lead_score
            })

        return {"results": leads_created}
    except requests.exceptions.RequestException as e:
        logger.error(f"Apollo API error: {e}")
        raise HTTPException(status_code=500, detail="Error fetching leads from Apollo.")