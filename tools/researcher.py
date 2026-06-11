# tools/researcher.py

import requests
import os
import json
from bs4 import BeautifulSoup
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
    api_key=os.getenv("GROQ_API_KEY"),
)

HEADERS = {
    # Pretend to be a real browser — many sites block default Python requests
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36"
}


def search_web(query: str, num_results: int = 3) -> list[str]:
    """
    Search DuckDuckGo (no API key needed) and return
    a list of result snippets for the query.

    DuckDuckGo's HTML search page is the simplest free
    search option — no rate limits for moderate use.
    """
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        response = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        # DuckDuckGo wraps each result in a <div class="result__body">
        for result in soup.find_all("div", class_="result__body")[:num_results]:
            snippet = result.find("a", class_="result__snippet")
            title   = result.find("a", class_="result__a")
            if snippet and title:
                results.append(f"{title.get_text()} — {snippet.get_text()}")

        return results if results else ["No results found."]
    except Exception as e:
        return [f"Search failed: {str(e)}"]


def fetch_page_text(url: str, max_chars: int = 3000) -> str:
    """
    Fetch a webpage and extract its readable text content.
    Strips all HTML tags, navigation, footers, and scripts.
    Truncates to max_chars to stay within LLM context limits.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(response.text, "html.parser")

        # Remove noise elements that add no readable content
        for tag in soup(["script", "style", "nav", "footer",
                          "header", "aside", "form"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)
        # Collapse multiple spaces into one
        text = " ".join(text.split())
        return text[:max_chars]
    except Exception as e:
        return f"Could not fetch page: {str(e)}"


def research_person(name: str, company: str, domain: str) -> dict:
    """
    Research a specific person and their company using web search.
    Returns a structured profile dict.

    Strategy:
    1. Search for the person + company combination
    2. Search for recent company news
    3. Feed all results to the LLM to synthesize a structured profile
    """
    print(f"  [researcher] Researching {name} at {company}...")

    # ── Search 1: Person profile ──────────────────────────────────
    person_results = search_web(f"{name} {company} LinkedIn role background")
    person_text = "\n".join(person_results)

    # ── Search 2: Company context ─────────────────────────────────
    company_results = search_web(f"{company} company news funding 2024 2025")
    company_text = "\n".join(company_results)

    # ── Search 3: Company website about page ─────────────────────
    about_text = ""
    if domain:
        about_url = f"https://{domain}/about"
        about_text = fetch_page_text(about_url, max_chars=1500)
        if "Could not fetch" in about_text:
            # Try without /about
            about_text = fetch_page_text(f"https://{domain}", max_chars=1500)

    # ── LLM synthesis ─────────────────────────────────────────────
    # Feed all raw search results to the LLM and ask it to extract
    # only what matters for a sales prep brief
    prompt = f"""You are a sales intelligence analyst preparing a brief before a sales call.

Extract key information about this person and company from the search results below.

PERSON: {name}
COMPANY: {company}

SEARCH RESULTS ABOUT THE PERSON:
{person_text}

SEARCH RESULTS ABOUT THE COMPANY:
{company_text}

COMPANY WEBSITE TEXT:
{about_text[:1000] if about_text else "Not available"}

Return a JSON object with exactly these fields:
{{
  "name": "{name}",
  "company": "{company}",
  "role": "their job title (or 'Unknown' if not found)",
  "background": "1-2 sentences about their career background",
  "company_description": "1-2 sentences about what the company does",
  "company_size": "employee count or funding stage if known, else 'Unknown'",
  "recent_news": "1-2 sentences about recent company news if any, else 'No recent news found'",
  "likely_pain_points": ["pain point 1", "pain point 2", "pain point 3"],
  "conversation_starter": "one personalized question to open the call based on what you found"
}}

Return ONLY the JSON object. No explanation, no markdown, no backticks."""

    response = llm.invoke(prompt)
    raw = response.content.strip()

    # Clean up in case the LLM adds markdown fences despite instructions
    raw = raw.replace("```json", "").replace("```", "").strip()

    try:
        profile = json.loads(raw)
        print(f"  [researcher] Profile built for {name}: {profile.get('role','?')} at {company}")
        return profile
    except json.JSONDecodeError:
        # If JSON parsing fails, return a graceful fallback
        print(f"  [researcher] JSON parse failed for {name} — using fallback")
        return {
            "name":                 name,
            "company":              company,
            "role":                 "Unknown",
            "background":           "Could not retrieve background.",
            "company_description":  "Could not retrieve company info.",
            "company_size":         "Unknown",
            "recent_news":          "No recent news found.",
            "likely_pain_points":   ["meeting efficiency", "CRM hygiene", "coaching at scale"],
            "conversation_starter": f"What are the biggest challenges your team at {company} is facing right now?",
        }


def research_company(company: str, domain: str) -> dict:
    """
    Research the company as a whole — separate from individual attendees.
    Looks for funding, growth signals, tech stack, and strategic priorities.
    """
    print(f"  [researcher] Researching company: {company}...")

    results = search_web(f"{company} company profile funding employees 2025")
    results_text = "\n".join(results)

    prompt = f"""You are a sales intelligence analyst. Extract key company information.

COMPANY: {company}
DOMAIN: {domain}

SEARCH RESULTS:
{results_text}

Return a JSON object with exactly these fields:
{{
  "name": "{company}",
  "industry": "their industry",
  "stage": "startup/growth/enterprise or funding stage if known",
  "size": "approximate employee count or range",
  "headquarters": "city, country if known",
  "recent_news": "most relevant recent news for a sales context",
  "strategic_priorities": ["priority 1", "priority 2"],
  "tech_stack_hints": ["tool 1", "tool 2"]
}}

Return ONLY the JSON object. No explanation, no markdown, no backticks."""

    response = llm.invoke(prompt)
    raw = response.content.strip().replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "name":                 company,
            "industry":             "Unknown",
            "stage":                "Unknown",
            "size":                 "Unknown",
            "headquarters":         "Unknown",
            "recent_news":          "No recent news found.",
            "strategic_priorities": [],
            "tech_stack_hints":     [],
        }