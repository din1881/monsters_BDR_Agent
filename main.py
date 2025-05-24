import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from typing import List, Optional
from dotenv import load_dotenv
import openai
from langchain_openai.llms import OpenAI as LangChainLLM
from langchain.agents import initialize_agent, Tool
from openai import OpenAI
from langchain.agents.agent_types import AgentType

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config
APOLLO_API_KEY = os.getenv("APOLLO_API_KEY")
HUBSPOT_TOKEN = os.getenv("HUBSPOT_PRIVATE_TOKEN")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Initialize OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Initialize FastAPI
app = FastAPI()

# CORS middleware
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
    email: Optional[str] = None
    phone: Optional[str] = None
    company: str
    company_description: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    job_title: Optional[str] = None
    description: Optional[str] = None
    linkedin_url: Optional[str] = None
    message: str = ""

class ApolloSearchRequest(BaseModel):
    job_title: str
    organization_name: str = ""
    location: str = ""
    industry_tag: str = ""
    exclude_emails: List[str] = []

class EmailGenerationRequest(BaseModel):
    leads: list[LeadRequest]
    send_immediately: bool = False

# LangChain Setup
llm = LangChainLLM(temperature=0, openai_api_key=os.getenv("OPENAI_API_KEY"))

lead_score_tool = Tool(
    name="LeadScorer",
    func=lambda x: f"Score for lead '{x}': High potential (based on title and industry match)",
    description="Scores a lead based on description and role"
)

agent = initialize_agent([lead_score_tool], llm, agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION, verbose=False)

# Health check endpoint
@app.get("/health")
async def health_check():
    try:
        env_vars = {
            "APOLLO_API_KEY": bool(os.getenv("APOLLO_API_KEY")),
            "HUBSPOT_PRIVATE_TOKEN": bool(os.getenv("HUBSPOT_PRIVATE_TOKEN")),
            "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
            "SMTP_HOST": bool(os.getenv("SMTP_HOST")),
            "SMTP_PORT": bool(os.getenv("SMTP_PORT")),
            "SMTP_USER": bool(os.getenv("SMTP_USER")),
            "SMTP_PASSWORD": bool(os.getenv("SMTP_PASSWORD")),
        }
        return {"status": "ok", "environment": env_vars}
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {"status": "error", "detail": str(e)}

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
    if not lead.email:
        return None
        
    headers = {
        "Authorization": f"Bearer {HUBSPOT_TOKEN}",
        "Content-Type": "application/json"
    }

    try:
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
        logger.info(f"Lead pushed to HubSpot: {lead.email}")
        return create_resp.json()

    except requests.exceptions.RequestException as e:
        logger.error(f"HubSpot API error: {e}")
        return None

@app.post("/find-leads")
async def find_leads(query: ApolloSearchRequest):
    url = "https://api.apollo.io/api/v1/mixed_people/search"
    headers = {
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "X-Api-Key": APOLLO_API_KEY
    }
    
    payload = {
        "api_key": APOLLO_API_KEY,
        "q_person_titles": [query.job_title] if query.job_title else None,
        "q_organization_name": query.organization_name if query.organization_name else None,
        "q_location_name": query.location if query.location else None,
        "q_industry": query.industry_tag if query.industry_tag else None,
        "page": 1,
        "per_page": 25,
        "reveal_personal_emails": True,
        "contact_details": True,
        "reveal_phone_numbers": True
    }

    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        people = response.json().get("people", [])
        leads_created = []
        
        for person in people:
            # Get company information
            company_info = person.get("organization", {})
            
            # Skip if email is in exclude list
            email = person.get("email")
            if not email or email in query.exclude_emails:
                continue

            # Create lead data
            lead_data = LeadRequest(
                firstname=person.get("first_name", ""),
                lastname=person.get("last_name", ""),
                email=email,
                phone=person.get("phone_number"),
                company=company_info.get("name", "Unknown Company"),
                company_description=company_info.get("description"),
                company_linkedin_url=company_info.get("linkedin_url"),
                job_title=person.get("title"),
                description=person.get("headline"),
                linkedin_url=person.get("linkedin_url")
            )
            
            # Only add leads that have at least a company name
            if lead_data.company != "Unknown Company":
                leads_created.append({
                    "lead": lead_data.dict(),
                    "apollo_contact_info": {
                        "phone_numbers": person.get("phone_numbers", []),
                        "direct_phone": person.get("direct_phone"),
                        "mobile_phone": person.get("mobile_phone")
                    }
                })

            if len(leads_created) >= 20:
                break

        return {"results": leads_created}

    except Exception as e:
        logger.error(f"Apollo API error: {e}")
        return {"results": [], "error": str(e)}

@app.post("/create-lead")
async def create_lead(lead: LeadRequest):
    try:
        # Simple email template
        email_body = f"""
Dear {lead.firstname},

I hope this email finds you well. I am reaching out from SkillUp MENA, the pioneer of e-learning services. We offer a vast curated library of over 85,000 courses from the world's leading training providers.

Given your role at {lead.company}, I believe we could provide significant value to your organization's training needs.

Would you be open to a brief call to discuss how we can support your team's development?

Best regards,
SkillUp MENA Team
        """
        
        # Send email
        if lead.email:
            email_subject = f"Exciting Opportunity for {lead.company}"
            send_email_smtp(lead.email, email_subject, email_body)
        
        # Push to HubSpot
        hubspot_response = push_to_hubspot(lead)
        
        return {
            "status": "success",
            "email": email_body,
            "hubspot": hubspot_response
        }
        
    except Exception as e:
        logger.error(f"Error processing lead: {e}")
        return {"status": "error", "detail": str(e)}

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

def generate_email(lead: LeadRequest) -> str:
    prompt = f"""
    SkillUp MENA is the pioneer of e-learning services, with our vast curated e-learning library of over 85000 courses, all offered by the world's leading training providers. Our aim is to simplify the corporate training process by offering a unique engaging learning experience, whilst marinating our partners' business needs.
    Write a personalized cold outreach email to {lead.firstname} {lead.lastname} at {lead.company}.
    Mention potential value and request a short call. Keep it under 120 words.
    """
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail="Error generating email content.") 