#!/usr/bin/env python3
"""
PubMed to Blogger Automation Script
This script searches for recent high-impact papers on PubMed,
generates a summary using OpenAI, and posts to Blogger.
"""

import os
import json
import datetime
import requests
import time
from xml.etree import ElementTree
import openai
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

# Constants
PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
OPENAI_MODEL = "gpt-4"

def search_pubmed(days_back=1):
    """Search PubMed for recent high-impact papers"""
    today = datetime.datetime.now()
    start_date = (today - datetime.timedelta(days=days_back)).strftime("%Y/%m/%d")
    end_date = today.strftime("%Y/%m/%d")
    
    # Search for high-impact study types
    query = (
        f'("Clinical Trial"[Publication Type] OR '
        f'"Meta-Analysis"[Publication Type] OR '
        f'"Systematic Review"[Publication Type] OR '
        f'"Randomized Controlled Trial"[Publication Type] OR '
        f'"Cohort Studies"[MeSH Terms]) AND '
        f'("{start_date}"[Date - Publication] : "{end_date}"[Date - Publication])'
    )
    
    # Perform the search
    search_url = f"{PUBMED_BASE_URL}esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": 10,
        "sort": "relevance",
        "retmode": "json"
    }
    
    response = requests.get(search_url, params=params)
    search_results = response.json()
    
    if 'esearchresult' in search_results and 'idlist' in search_results['esearchresult']:
        id_list = search_results['esearchresult']['idlist']
        if id_list:
            # Get the top paper
            return id_list[0]
    
    return None

def get_paper_details(paper_id):
    """Get detailed information about a paper from PubMed"""
    fetch_url = f"{PUBMED_BASE_URL}efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": paper_id,
        "retmode": "xml"
    }
    
    response = requests.get(fetch_url, params=params)
    
    if response.status_code != 200:
        return None
    
    # Parse XML response
    root = ElementTree.fromstring(response.content)
    
    # Extract article details
    article = root.find(".//Article")
    if article is None:
        return None
    
    # Get title
    title_element = article.find(".//ArticleTitle")
    title = title_element.text if title_element is not None else "No title available"
    
    # Get abstract
    abstract_parts = article.findall(".//AbstractText")
    abstract = " ".join([part.text for part in abstract_parts if part.text]) if abstract_parts else "No abstract available"
    
    # Get journal and date
    journal_element = article.find(".//Journal/Title")
    journal = journal_element.text if journal_element is not None else "Unknown Journal"
    
    pub_date_elements = article.findall(".//PubDate/*")
    pub_date = " ".join([e.text for e in pub_date_elements if e.text])
    
    # Get authors
    author_elements = article.findall(".//Author")
    authors = []
    for author in author_elements:
        last_name = author.find("LastName")
        fore_name = author.find("ForeName")
        if last_name is not None and fore_name is not None:
            authors.append(f"{fore_name.text} {last_name.text}")
        elif last_name is not None:
            authors.append(last_name.text)
    
    author_string = ", ".join(authors) if authors else "Unknown Authors"
    
    return {
        "id": paper_id,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "pub_date": pub_date,
        "authors": author_string,
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{paper_id}/"
    }

def generate_summary(paper_details):
    """Generate a general-audience summary using OpenAI"""
    openai.api_key = os.environ.get("OPENAI_API_KEY")
    
    prompt = f"""
    Please create a clear, engaging summary of this medical research paper for a general audience.
    Avoid technical jargon and use simple language. Format the summary in paragraphs, not bullet points.
    
    Title: {paper_details['title']}
    Authors: {paper_details['authors']}
    Journal: {paper_details['journal']}
    Publication Date: {paper_details['pub_date']}
    
    Abstract:
    {paper_details['abstract']}
    
    Your summary should:
    1. Explain why this research matters in everyday terms
    2. Describe what the researchers did
    3. Explain the key findings and what they mean
    4. Discuss potential implications for healthcare or patients
    """
    
    try:
        response = openai.ChatCompletion.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a skilled medical writer who explains complex research in simple terms."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Error generating summary: {e}")
        return None

def create_blog_post(paper_details, summary):
    """Create a formatted blog post"""
    today = datetime.datetime.now().strftime("%B %d, %Y")
    
    # Extract a shorter title for the blog post headline
    title_parts = paper_details['title'].split(':')
    short_title = title_parts[0].strip()
    if len(short_title) > 70:  # If still too long, truncate
        short_title = short_title[:67] + "..."
    
    blog_post = f"""# Today's Medical Research: {short_title}

**Date:** {today}

## {paper_details['title']}

{summary}

**Source:** [{paper_details['title']} (PMID: {paper_details['id']})]({paper_details['pubmed_url']})
"""
    return blog_post

def post_to_blogger(blog_post, paper_details):
    """Post the content to Blogger"""
    # Get credentials from environment variables
    blogger_api_key = os.environ.get("BLOGGER_API_KEY")
    blog_id = os.environ.get("BLOGGER_BLOG_ID")
    
    if not blogger_api_key or not blog_id:
        print("Missing Blogger API credentials")
        return False
    
    # Create a title for the blog post
    title_parts = paper_details['title'].split(':')
    post_title = f"Medical Research Today: {title_parts[0].strip()}"
    
    # Create the Blogger API client
    blogger = build('blogger', 'v3', developerKey=blogger_api_key)
    
    # Create the post
    body = {
        'kind': 'blogger#post',
        'title': post_title,
        'content': blog_post.replace('\n', '<br>')  # Convert newlines to HTML breaks
    }
    
    try:
        request = blogger.posts().insert(blogId=blog_id, body=body)
        response = request.execute()
        print(f"Blog post published: {response.get('url')}")
        return True
    except Exception as e:
        print(f"Error posting to Blogger: {e}")
        return False

def main():
    """Main function to run the automation"""
    # 1. Search PubMed for recent papers
    paper_id = search_pubmed(days_back=1)
    if not paper_id:
        print("No recent papers found")
        return
    
    # 2. Get paper details
    paper_details = get_paper_details(paper_id)
    if not paper_details:
        print(f"Could not retrieve details for paper ID: {paper_id}")
        return
    
    # 3. Generate summary
    summary = generate_summary(paper_details)
    if not summary:
        print("Failed to generate summary")
        return
    
    # 4. Create blog post
    blog_post = create_blog_post(paper_details, summary)
    
    # 5. Post to Blogger
    success = post_to_blogger(blog_post, paper_details)
    
    # 6. Save a local copy for reference
    with open("latest_blog_post.md", "w") as f:
        f.write(blog_post)
    
    if success:
        print("Automation completed successfully")
    else:
        print("Automation completed with errors")

if __name__ == "__main__":
    main()
