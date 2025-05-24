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
    email: str | None = None
    phone: str | None = None
    company: str
    company_description: str | None = None
    company_linkedin_url: str | None = None
    job_title: str | None = None
    description: str | None = None
    linkedin_url: str | None = None
    message: str = ""

class ApolloSearchRequest(BaseModel):
    job_title: str
    organization_name: str = ""
    location: str = ""
    industry_tag: str = ""
    exclude_emails: list[str] = [] # List of emails to exclude from results

class EmailGenerationRequest(BaseModel):
    leads: list[LeadRequest]
    send_immediately: bool = False

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
        "per_page": 20,
        "contact_details": True,
        "reveal_phone_numbers": True,
        "enrich_company": True  # Add this to get company details
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
        
        # Log the first person's data to see the structure
        if people:
            logger.info(f"Sample person data: {people[0]}")
        
        # Enrich each person's data to get emails and phones
        for person in people:
            # Get company information
            company_info = person.get("organization", {})
            
            # Collect all phone numbers
            phone_info = {
                "phone_numbers": person.get("phone_numbers", []),
                "sanitized_phone": person.get("sanitized_phone"),
                "sanitized_mobile_phone": person.get("sanitized_mobile_phone"),
                "direct_phone": person.get("direct_phone"),
                "home_phone": person.get("home_phone"),
                "mobile_phone": person.get("mobile_phone"),
                "other_phone": person.get("other_phone"),
                "raw_phone_numbers": person.get("raw_phone_numbers", [])
            }

            # Log initial phone info
            logger.info(f"Initial phone info from person: {phone_info}")

            # Initialize revealed_data as None
            revealed_data = None

            try:
                enrich_url = "https://api.apollo.io/api/v1/people/match"
                enrich_payload = {
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "organization_name": company_info.get("name", ""),
                    "linkedin_url": person.get("linkedin_url", ""),
                    "reveal_personal_emails": True,
                    "reveal_phone_numbers": True,
                    "contact_details": True
                }
                
                enrich_response = requests.post(enrich_url, headers=headers, json=enrich_payload)
                enrich_response.raise_for_status()
                enriched_data = enrich_response.json().get("person", {})
                enriched_company = enriched_data.get("organization", {})
                
                # Log enriched data phone fields
                logger.info(f"Enriched data phone fields: {enriched_data.get('phone_numbers', [])}, sanitized: {enriched_data.get('sanitized_phone')}, mobile: {enriched_data.get('sanitized_mobile_phone')}")
                
                # Add enriched phone numbers
                if enriched_data:
                    phone_info.update({
                        "enriched_phone_numbers": enriched_data.get("phone_numbers", []),
                        "enriched_sanitized_phone": enriched_data.get("sanitized_phone"),
                        "enriched_sanitized_mobile_phone": enriched_data.get("sanitized_mobile_phone"),
                        "enriched_direct_phone": enriched_data.get("direct_phone"),
                        "enriched_mobile_phone": enriched_data.get("mobile_phone")
                    })
                    logger.info(f"Updated phone info after enrichment: {phone_info}")
                
                # Try to reveal phone numbers specifically
                if enriched_data.get("id"):
                    reveal_url = f"https://api.apollo.io/api/v1/people/{enriched_data['id']}/reveal"
                    reveal_response = requests.post(reveal_url, headers=headers, json={"reveal_phone_numbers": True})
                    if reveal_response.status_code == 200:
                        revealed_data = reveal_response.json().get("person", {})
                        # Log revealed data phone fields
                        logger.info(f"Revealed data phone fields: {revealed_data.get('phone_numbers', [])}, sanitized: {revealed_data.get('sanitized_phone')}, mobile: {revealed_data.get('sanitized_mobile_phone')}")
                        # Update phone info with revealed data
                        if revealed_data:
                            phone_info.update({
                                "revealed_phone_numbers": revealed_data.get("phone_numbers", []),
                                "revealed_sanitized_phone": revealed_data.get("sanitized_phone"),
                                "revealed_sanitized_mobile_phone": revealed_data.get("sanitized_mobile_phone"),
                                "revealed_direct_phone": revealed_data.get("direct_phone"),
                                "revealed_mobile_phone": revealed_data.get("mobile_phone")
                            })
                            logger.info(f"Final phone info after reveal: {phone_info}")
            except Exception as e:
                logger.error(f"Error enriching/revealing contact: {e}")
                enriched_data = {}
                enriched_company = {}
                revealed_data = None
            
            # Get email from enriched data
            email = enriched_data.get("email") or person.get("email")
            
            # Skip if email is in exclude list
            if email and email in query.exclude_emails:
                continue
                
            # Get job title and description
            job_title = (
                enriched_data.get("title") or 
                person.get("title") or 
                None
            )
            
            description = None
            if person.get("headline"):
                description = person["headline"]
            elif person.get("summary"):
                description = person["summary"]
            elif enriched_data.get("headline"):
                description = enriched_data["headline"]
            elif enriched_data.get("summary"):
                description = enriched_data["summary"]

            # Get company information
            company_name = enriched_company.get("name") or company_info.get("name", "")
            company_description = (
                enriched_company.get("description") or 
                company_info.get("description") or 
                None
            )
            company_linkedin_url = (
                enriched_company.get("linkedin_url") or 
                company_info.get("linkedin_url") or 
                None
            )

            # Get first and last name with fallbacks
            firstname = (
                enriched_data.get("first_name") or 
                person.get("first_name") or 
                "Unknown"
            )
            lastname = (
                enriched_data.get("last_name") or 
                person.get("last_name") or 
                "Unknown"
            )
            
            # Use enriched data if available, otherwise fall back to original data
            lead_data = LeadRequest(
                firstname=firstname,
                lastname=lastname,
                email=email,
                phone=None,  # We'll add phone separately in the response
                company=company_name or "Unknown Company",
                company_description=company_description,
                company_linkedin_url=company_linkedin_url,
                job_title=job_title,
                description=description,
                linkedin_url=enriched_data.get("linkedin_url") or person.get("linkedin_url"),
                message=""
            )
            
            # Log final phone info before sending to frontend
            logger.info(f"Final phone info being sent to frontend: {phone_info}")

            # Only add leads that have at least a company name
            if lead_data.company:
                # Create response with Apollo contact details
                lead_response = {
                    "lead": lead_data.dict(),
                    "apollo_contact_info": phone_info
                }
                
                leads_created.append(lead_response)

                # Break if we have enough unique leads
                if len(leads_created) >= 20:
                    break

        return {"results": leads_created}

    except requests.exceptions.RequestException as e:
        logger.error(f"Apollo API error: {e}")
        raise HTTPException(status_code=500, detail="Error fetching leads from Apollo.")

@app.post("/process-leads")
async def process_leads(request: EmailGenerationRequest):
    processed_leads = []
    
    for lead in request.leads:
        try:
            # Generate email
            email_text = generate_email(lead)
            
            # Score the lead
            lead_score = agent.run(
                f"Score this lead: {lead.firstname} {lead.lastname}, role at {lead.company}, "
                "given that this what we do, SkillUp MENA is the pioneer of e-learning services, "
                "with our vast curated e-learning library of over 85000 courses, all offered by "
                "the world's leading training providers."
            )
            
            # Push to HubSpot
            hubspot_response = push_to_hubspot(lead)
            
            # Send email if requested
            email_sent = False
            if request.send_immediately and lead.email:
                email_subject = f"Exciting Opportunity for {lead.firstname} {lead.lastname} at {lead.company}"
                send_email_smtp(lead.email, email_subject, email_text)
                email_sent = True
            
            processed_leads.append({
                "lead": lead.dict(),
                "email": email_text,
                "score": lead_score,
                "hubspot": hubspot_response,
                "email_sent": email_sent
            })
            
        except Exception as e:
            logger.error(f"Error processing lead {lead.email}: {e}")
            processed_leads.append({
                "lead": lead.dict(),
                "error": str(e)
            })
    
    return {"results": processed_leads}