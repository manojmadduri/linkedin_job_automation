from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
import time
import re
import smtplib
import json
import os
import random
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import openai
import logging
import uuid
import hashlib

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('linkedin_automation.log'),
        logging.StreamHandler()
    ]
)

class LinkedInPostAutomation:
    def __init__(self):
        self.driver = None
        self.email = None
        self.password = None
        self.openai_client = None
        self.responded_posts = set()
        self.history_file = 'response_history.json'
        self.load_response_history()
        self.max_retries = 3
        self.wait_time = 10

    def wait_and_find_element(self, by, value, timeout=10):
        """Wait for element to be present and return it"""
        try:
            element = WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, value))
            )
            return element
        except TimeoutException:
            logging.error(f"Timeout waiting for element: {value}")
            return None

    def safe_click(self, element):
        """Safely click an element with retry logic"""
        for _ in range(self.max_retries):
            try:
                self.driver.execute_script("arguments[0].scrollIntoView(true);", element)
                time.sleep(1)
                element.click()
                return True
            except Exception as e:
                logging.warning(f"Click failed, retrying... Error: {str(e)}")
                time.sleep(2)
        return False

    def load_response_history(self):
        """Load previously responded posts from history file"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
                    self.responded_posts = set(history.get('responded_posts', []))
                    logging.info(f"Loaded {len(self.responded_posts)} previous responses")
        except Exception as e:
            logging.error(f"Error loading response history: {str(e)}")

    def save_response_history(self):
        """Save responded posts to history file"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump({
                    'responded_posts': list(self.responded_posts),
                    'last_updated': datetime.now().isoformat()
                }, f)
            logging.info("Response history saved successfully")
        except Exception as e:
            logging.error(f"Error saving response history: {str(e)}")

    def setup_driver(self):
        """Initialize the Chrome WebDriver"""
        logging.info("Setting up Chrome WebDriver...")
        try:
            chrome_options = Options()
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--start-maximized")
            chrome_options.add_argument("--disable-notifications")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            logging.info("Chrome WebDriver setup successful!")
        except Exception as e:
            logging.error(f"Error setting up Chrome WebDriver: {str(e)}")
            raise

    def setup_openai(self, api_key):
        """Initialize OpenAI client"""
        try:
            openai.api_key = api_key
            self.openai_client = openai
            logging.info("OpenAI client initialized successfully")
        except Exception as e:
            logging.error(f"Error initializing OpenAI client: {str(e)}")
            raise

    def login_to_linkedin(self, email, password):
        """Login to LinkedIn with retry logic"""
        logging.info("Attempting to log in to LinkedIn...")
        try:
            self.driver.get("https://www.linkedin.com/login")
            
            email_field = self.wait_and_find_element(By.ID, "username")
            if not email_field:
                raise Exception("Email field not found")
            email_field.send_keys(email)
            
            password_field = self.wait_and_find_element(By.ID, "password")
            if not password_field:
                raise Exception("Password field not found")
            password_field.send_keys(password)
            password_field.send_keys(Keys.RETURN)
            
            # Wait for login to complete
            time.sleep(3)
            
            # Verify login success
            if "feed" in self.driver.current_url or "mynetwork" in self.driver.current_url:
                logging.info("Successfully logged in to LinkedIn")
                return True
            
        except Exception as e:
            logging.error(f"Login failed: {str(e)}")
            raise

    def process_post(self, post):
        """Process a single post"""
        try:
            # Extract post content
            content_elements = post.find_elements(By.CSS_SELECTOR, ".feed-shared-update-v2__description-wrapper, .feed-shared-text, .update-components-text, .feed-shared-update-v2__commentary, .update-components-text span[dir='ltr'], .feed-shared-text__text-view, .feed-shared-update-v2__update-content-wrapper")
            
            if not content_elements:
                logging.debug("No content found in post")
                return False
            
            content = ""
            for element in content_elements:
                try:
                    content += element.text + " "
                except:
                    pass
            
            content = content.strip()
            if not content:
                logging.debug("Empty content in post")
                return False
            
            # Get post author
            author_elements = post.find_elements(By.CSS_SELECTOR, ".feed-shared-actor__name, .update-components-actor__name, .feed-shared-actor__title, .update-components-actor__meta a, .feed-shared-actor__meta a, .update-components-actor__meta-link")
            author = ""
            for element in author_elements:
                try:
                    author += element.text + " "
                except:
                    pass
            
            author = author.strip()
            if not author:
                author = "LinkedIn User"
            
            # Extract job description
            job_description = ""
            job_desc_elements = post.find_elements(By.CSS_SELECTOR, ".feed-shared-update-v2__description, .feed-shared-text__text-view, .update-components-text, .feed-shared-inline-show-more-text")
            for element in job_desc_elements:
                try:
                    if element.text and element.text not in content:
                        job_description += element.text + " "
                except:
                    pass
            
            job_description = job_description.strip()
            
            # Get post identifier to avoid duplicates
            post_id = self.get_post_identifier(post)
            if post_id in self.responded_posts:
                logging.info(f"Already responded to post: {post_id}")
                return False
            
            # Extract emails
            emails = self.extract_emails(content + " " + job_description)
            if not emails:
                logging.debug("No emails found in post")
                return False
            
            # Check if this is a candidate post (not a job posting)
            combined_text = (content + " " + job_description).lower()
            candidate_indicators = [
                'open to work',
                'seeking opportunities',
                'job seeker',
                'seeking a role',
                'seeking a position'
            ]
            
            for indicator in candidate_indicators:
                if indicator in combined_text:
                    logging.info(f"Skipping candidate post (detected term: {indicator})")
                    print(f"\nSkipping candidate post (detected term: {indicator})")
                    return False
            
            # Check if job is in the US
            is_us_job = False
            us_terms = ['united states', ' usa', 'u.s.', 'u.s.a', 'america', 'american', 'remote us', 'us remote', 
                       'california', 'new york', 'texas', 'florida', 'illinois', 'pennsylvania', 'ohio', 'georgia', 
                       'north carolina', 'michigan', 'new jersey', 'virginia', 'washington', 'arizona', 'massachusetts', 
                       'tennessee', 'indiana', 'missouri', 'maryland', 'wisconsin', 'minnesota', 'colorado', 'alabama', 
                       'south carolina', 'louisiana', 'kentucky', 'oregon', 'oklahoma', 'connecticut', 'utah', 'iowa', 
                       'nevada', 'arkansas', 'mississippi', 'kansas', 'new mexico', 'nebraska', 'west virginia', 
                       'idaho', 'hawaii', 'new hampshire', 'maine', 'montana', 'rhode island', 'delaware', 
                       'south dakota', 'north dakota', 'alaska', 'vermont', 'wyoming', 'dc', 'washington dc',
                       'chicago', 'new york city', 'nyc', 'los angeles', 'la', 'san francisco', 'sf', 'seattle', 
                       'boston', 'austin', 'dallas', 'houston', 'atlanta', 'miami', 'philadelphia', 'phoenix', 
                       'denver', 'san diego', 'san jose', 'nashville', 'portland', 'charlotte', 'raleigh']
            
            # Non-US locations to explicitly exclude
            non_us_terms = ['india', 'hyderabad', 'bangalore', 'mumbai', 'delhi', 'chennai', 'kolkata', 'pune', 
                           'ahmedabad', 'jaipur', 'surat', 'kanpur', 'nagpur', 'lucknow', 'indore', 'bhopal',
                           'united kingdom', 'uk', 'london', 'manchester', 'birmingham', 'liverpool', 'glasgow',
                           'canada', 'toronto', 'montreal', 'vancouver', 'ottawa', 'calgary', 'edmonton',
                           'australia', 'sydney', 'melbourne', 'brisbane', 'perth', 'adelaide',
                           'germany', 'berlin', 'munich', 'hamburg', 'frankfurt', 'cologne',
                           'france', 'paris', 'lyon', 'marseille', 'toulouse', 'nice',
                           'spain', 'madrid', 'barcelona', 'valencia', 'seville',
                           'italy', 'rome', 'milan', 'naples', 'turin', 'palermo',
                           'japan', 'tokyo', 'osaka', 'kyoto', 'yokohama', 'nagoya',
                           'china', 'beijing', 'shanghai', 'guangzhou', 'shenzhen',
                           'brazil', 'sao paulo', 'rio de janeiro', 'brasilia',
                           'mexico', 'mexico city', 'guadalajara', 'monterrey',
                           'singapore', 'hong kong', 'dubai', 'abu dhabi', 'doha', 'qatar',
                           'ireland', 'dublin', 'cork', 'galway',
                           'netherlands', 'amsterdam', 'rotterdam', 'the hague',
                           'sweden', 'stockholm', 'gothenburg', 'malmo',
                           'switzerland', 'zurich', 'geneva', 'bern',
                           'poland', 'warsaw', 'krakow', 'lodz',
                           'south africa', 'johannesburg', 'cape town', 'durban',
                           'new zealand', 'auckland', 'wellington', 'christchurch',
                           'argentina', 'buenos aires', 'cordoba', 'rosario',
                           'chile', 'santiago', 'valparaiso', 'concepcion',
                           'colombia', 'bogota', 'medellin', 'cali',
                           'israel', 'tel aviv', 'jerusalem', 'haifa',
                           'philippines', 'manila', 'quezon city', 'davao',
                           'vietnam', 'ho chi minh city', 'hanoi', 'da nang',
                           'thailand', 'bangkok', 'chiang mai', 'phuket',
                           'malaysia', 'kuala lumpur', 'penang', 'johor bahru',
                           'indonesia', 'jakarta', 'surabaya', 'bandung',
                           'pakistan', 'karachi', 'lahore', 'islamabad',
                           'bangladesh', 'dhaka', 'chittagong', 'khulna',
                           'sri lanka', 'colombo', 'kandy', 'galle',
                           'nepal', 'kathmandu', 'pokhara', 'lalitpur',
                           'remote global', 'worldwide remote', 'global remote', 'international remote']
            
            combined_text = (content + " " + job_description).lower()
            
            # First check if it contains any non-US terms
            for term in non_us_terms:
                if term.lower() in combined_text:
                    logging.info(f"Skipping non-US job based on term: {term}")
                    print(f"\nSkipping non-US job (detected term: {term})")
                    return False
            
            # Only check for US terms if no non-US terms were found
            for term in us_terms:
                if term.lower() in combined_text:
                    is_us_job = True
                    logging.info(f"Detected US job based on term: {term}")
                    break
                
            # Also check for US zip code pattern
            if re.search(r'\b\d{5}(?:-\d{4})?\b', combined_text):
                is_us_job = True
                logging.info("Detected US job based on zip code pattern")
            
            # Check if this is a contract/C2C position
            contract_terms = ['contract', 'c2c', 'corp-to-corp', 'corp to corp', 'corporation to corporation', 
                             'contractor', 'consulting', 'consultant', '1099', 'independent contractor', 'f2f']
            
            non_contract_terms = ['w2 only', 'no c2c', 'no corp-to-corp', 'no 1099', 'permanent only', 'full time only', 'no contractors']
            
            # First check if it explicitly states no contract
            for term in non_contract_terms:
                if term.lower() in combined_text:
                    logging.info(f"Skipping non-contract position (detected term: {term})")
                    print(f"\nSkipping non-contract position (detected term: {term})")
                    return False
            
            # Then check if it mentions contract terms
            is_contract_position = False
            for term in contract_terms:
                if term.lower() in combined_text:
                    is_contract_position = True
                    logging.info(f"Detected contract position based on term: {term}")
                    break
            
            if not is_contract_position:
                logging.info("Contract status not explicitly mentioned, assuming potential contract opportunity")
                print("\nContract status not explicitly mentioned, assuming potential contract opportunity")
                is_contract_position = True
            
            # Check if we've already emailed this person today
            email_domain = emails[0].split('@')[1]
            today = datetime.now().strftime('%Y-%m-%d')
            
            # Load email history
            email_history = {}
            try:
                if os.path.exists('email_history.json'):
                    with open('email_history.json', 'r') as f:
                        email_history = json.load(f)
            except Exception as e:
                logging.warning(f"Could not load email history: {str(e)}")
            
            # Check if we've emailed this domain today
            if email_domain in email_history and email_history[email_domain].get('date') == today:
                logging.info(f"Already emailed domain {email_domain} today")
                print(f"\nSkipping - already emailed domain {email_domain} today")
                return False
            
            # Load config to check auto-send setting
            try:
                with open('config.json', 'r') as f:
                    config = json.load(f)
                auto_send_us_jobs = config.get('auto_send_us_jobs', True)
            except:
                auto_send_us_jobs = True
            
            if is_us_job:
                print("\nDetected US job opening - automatically responding")
            else:
                # If not explicitly a US job but also not explicitly non-US, we'll still process it
                # but log that we're not sure about the location
                logging.info("Job location not clearly identified as US, but no non-US terms found")
                print("\nJob location not clearly identified, but processing anyway")
            
            # Prepare post data
            post_data = {
                'author': author,
                'content': content,
                'job_description': job_description,
                'emails': emails,
                'is_us_job': is_us_job,
                'is_contract': is_contract_position
            }
            
            # Draft and send email
            result = self.draft_and_send_email(post_data, self.email, self.password)
            
            if result:
                # Add to responded posts
                self.responded_posts.add(post_id)
                self.save_response_history()
                
                # Update email history
                email_history[email_domain] = {
                    'date': today,
                    'email': emails[0],
                    'post_id': post_id
                }
                
                # Save email history
                try:
                    with open('email_history.json', 'w') as f:
                        json.dump(email_history, f)
                except Exception as e:
                    logging.warning(f"Could not save email history: {str(e)}")
                
                return True
            
            return False
            
        except Exception as e:
            logging.error(f"Error processing post: {str(e)}")
            return False

    def get_post_identifier(self, post):
        """Generate a unique identifier for a post to avoid duplicates"""
        try:
            # Try to get post ID from data-id attribute
            post_id = post.get_attribute('data-id')
            if post_id:
                return post_id
            
            # Try to get post URL
            post_links = post.find_elements(By.CSS_SELECTOR, "a.app-aware-link")
            for link in post_links:
                href = link.get_attribute('href')
                if href and '/posts/' in href:
                    return href
            
            # If no ID or URL, use author name + first 50 chars of content
            author_elements = post.find_elements(By.CSS_SELECTOR, ".feed-shared-actor__name, .update-components-actor__name")
            author = ""
            for element in author_elements:
                try:
                    author += element.text + " "
                except:
                    pass
            
            content_elements = post.find_elements(By.CSS_SELECTOR, ".feed-shared-update-v2__description-wrapper, .feed-shared-text")
            content = ""
            for element in content_elements:
                try:
                    content += element.text + " "
                except:
                    pass
            
            # Create a hash of author + content
            identifier = hashlib.md5((author + content[:100]).encode()).hexdigest()
            return identifier
        except Exception as e:
            logging.error(f"Error generating post identifier: {str(e)}")
            # Fallback to a random ID
            import random
            return f"post_{random.randint(1000, 9999)}"

    def extract_emails(self, text):
        """Extract all emails from text using regex"""
        if not text:
            return []
        
        # Clean the text first
        # Replace common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        
        # Common email patterns
        patterns = [
            r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # Standard email
            r'[a-zA-Z0-9._%+-]+\s*@\s*[a-zA-Z0-9.-]+\s*\.\s*[a-zA-Z]{2,}',  # Email with spaces
            r'[a-zA-Z0-9._%+-]+\s*\[at\]\s*[a-zA-Z0-9.-]+\s*\[dot\]\s*[a-zA-Z]{2,}',  # [at] and [dot]
            r'[a-zA-Z0-9._%+-]+\s*\[at\]\s*[a-zA-Z0-9.-]+\s*\(dot\)\s*[a-zA-Z]{2,}',  # [at] and (dot)
            r'[a-zA-Z0-9._%+-]+\s*\[at\]\s*[a-zA-Z0-9.-]+\s*\[\.\]\s*[a-zA-Z]{2,}',  # [at] and [.]
            r'[a-zA-Z0-9._%+-]+\s*@\s*[a-zA-Z0-9.-]+\s*dot\s*[a-zA-Z]{2,}',  # @ and dot
            r'[a-zA-Z0-9._%+-]+\s*\[\.\]\s*[a-zA-Z0-9.-]+\s*\[\.\]\s*[a-zA-Z]{2,}',  # [.] for @ and dot
            r'email:?\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # email: prefix
            r'e-?mail:?\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # e-mail: prefix
            r'contact:?\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # contact: prefix
            r'send\s+(?:your\s+)?(?:resume|cv)(?:\s+to)?:?\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',  # send resume to: prefix
            r'apply(?:\s+to)?:?\s*[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'  # apply to: prefix
        ]
        
        emails = []
        text = text.replace('\n', ' ')  # Replace newlines with spaces
        
        # First, try to find emails with context
        context_patterns = [
            r'email\s*(?:address|id)?[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'e-?mail\s*(?:address|id)?[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'send\s+(?:your\s+)?(?:resume|cv)(?:\s+to)?[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'apply(?:\s+to)?[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'contact[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'reach\s+(?:out|me)(?:\s+at)?[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            r'(?:my|our)\s+email[\s:]*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'
        ]
        
        for pattern in context_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                if match and '@' in match:
                    emails.append(match.strip())
        
        # Then try the regular patterns
        for pattern in patterns:
            found = re.findall(pattern, text, re.IGNORECASE)
            if found:
                # Clean up the found emails
                for email in found:
                    # Extract just the email if there's a prefix like "email:"
                    if ':' in email:
                        parts = email.split(':', 1)
                        if len(parts) > 1 and '@' in parts[1]:
                            email = parts[1].strip()
                    
                    # Replace common obfuscations
                    email = re.sub(r'\s*\[at\]\s*', '@', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s*\(at\)\s*', '@', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s+at\s+', '@', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s+AT\s+', '@', email, flags=re.IGNORECASE)
                    
                    email = re.sub(r'\s*\[dot\]\s*', '.', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s*\(dot\)\s*', '.', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s+dot\s+', '.', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s+DOT\s+', '.', email, flags=re.IGNORECASE)
                    email = re.sub(r'\s*\[\.\]\s*', '.', email, flags=re.IGNORECASE)
                    
                    # Remove spaces
                    email = ''.join(email.split())
                    
                    # Validate the email has proper format after cleaning
                    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                        emails.append(email)
        
        # Remove duplicates while preserving order
        unique_emails = []
        for email in emails:
            if email not in unique_emails:
                unique_emails.append(email)
        
        return unique_emails

    def save_page_source(self, filename_prefix="page_source"):
        """Save the current page source to a file for debugging"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{filename_prefix}_{timestamp}.html"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logging.info(f"Saved page source to {filename}")
            return filename
        except Exception as e:
            logging.error(f"Error saving page source: {str(e)}")
            return None

    def search_and_process_posts(self, search_term, max_posts=50):
        """Search for posts and process them"""
        try:
            # Navigate to LinkedIn search page
            self.driver.get("https://www.linkedin.com/feed/")
            time.sleep(3)
            
            # Find and click on the search box
            search_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//input[contains(@class, 'search-global-typeahead__input')]"))
            )
            search_box.click()
            search_box.send_keys(search_term)
            search_box.send_keys(Keys.RETURN)
            time.sleep(5)
            
            # Click on the Posts tab - try multiple approaches
            posts_tab_clicked = False
            
            # First approach: Direct CSS selectors
            posts_tab_selectors = [
                "button.search-reusables__filter-pill-button[aria-label='Posts']",
                "button[data-control-name='search_filter_posts']",
                ".search-reusables__filter-trigger-and-dropdown[aria-label='Posts']",
                ".artdeco-pill.artdeco-pill--slate.artdeco-pill--choice.artdeco-pill--2.search-reusables__filter-pill-button[aria-label='Posts']"
            ]
            
            for selector in posts_tab_selectors:
                try:
                    posts_tabs = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    for tab in posts_tabs:
                        if tab.is_displayed() and "posts" in tab.text.lower():
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", tab)
                            posts_tab_clicked = True
                            logging.info(f"Clicked Posts tab with selector: {selector}")
                            time.sleep(5)
                            break
                    if posts_tab_clicked:
                        break
                except Exception as e:
                    logging.debug(f"Failed to click Posts tab with selector {selector}: {str(e)}")
            
            # Second approach: Try XPath if CSS selectors didn't work
            if not posts_tab_clicked:
                posts_tab_xpaths = [
                    "//button[contains(text(), 'Posts')]",
                    "//button[contains(@aria-label, 'Posts')]",
                    "//span[contains(text(), 'Posts')]/parent::button",
                    "//div[contains(@class, 'search-reusables')]//*[contains(text(), 'Posts')]"
                ]
                
                for xpath in posts_tab_xpaths:
                    try:
                        posts_elements = self.driver.find_elements(By.XPATH, xpath)
                        for element in posts_elements:
                            if element.is_displayed():
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", element)
                                posts_tab_clicked = True
                                logging.info(f"Clicked Posts tab with XPath: {xpath}")
                                time.sleep(5)
                                break
                        if posts_tab_clicked:
                            break
                    except Exception as e:
                        logging.debug(f"Failed to click Posts tab with XPath {xpath}: {str(e)}")
            
            # Third approach: Try to find all tabs and click on the one that says "Posts"
            if not posts_tab_clicked:
                try:
                    # Try to find all filter tabs
                    all_tabs = self.driver.find_elements(By.CSS_SELECTOR, ".search-reusables__filter-pill-button, .artdeco-pill--choice, [data-control-name*='filter'], .search-reusables__primary-filter button")
                    
                    for tab in all_tabs:
                        try:
                            if tab.is_displayed() and ("posts" in tab.text.lower() or (tab.get_attribute("aria-label") and "posts" in tab.get_attribute("aria-label").lower())):
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tab)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", tab)
                                posts_tab_clicked = True
                                logging.info("Clicked Posts tab from general tab collection")
                                time.sleep(5)
                                break
                        except Exception as e:
                            continue
                except Exception as e:
                    logging.debug(f"Failed to find Posts tab in general tab collection: {str(e)}")
            
            # Fourth approach: Try clicking on the filter dropdown and selecting Posts
            if not posts_tab_clicked:
                try:
                    # Try to find and click on the filter dropdown
                    filter_dropdown_selectors = [
                        "button.search-reusables__filter-trigger-and-dropdown",
                        "button[aria-label='Sort by']",
                        "button.artdeco-dropdown__trigger--is-dropdown-trigger",
                        "button.search-reusables__sort-dropdown-trigger",
                        "button.search-reusables__sort-filter",
                        ".search-reusables__primary-filter button[data-control-name='sort_dropdown']"
                    ]
                    
                    dropdown_clicked = False
                    for selector in filter_dropdown_selectors:
                        try:
                            dropdowns = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for dropdown in dropdowns:
                                if dropdown.is_displayed() and ("sort" in dropdown.text.lower() or "sort" in dropdown.get_attribute("aria-label").lower() if dropdown.get_attribute("aria-label") else False):
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", dropdown)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", dropdown)
                                    dropdown_clicked = True
                                    logging.info(f"Clicked filter dropdown with selector: {selector}")
                                    time.sleep(2)
                                    break
                            if dropdown_clicked:
                                break
                        except Exception as e:
                            logging.debug(f"Failed to click filter dropdown with selector {selector}: {str(e)}")
                    
                    # If dropdown clicked, try to find and click Posts option
                    if dropdown_clicked:
                        posts_option_selectors = [
                            ".artdeco-dropdown__content li button:contains('Posts')",
                            ".search-reusables__dropdown-list li button:contains('Posts')",
                            ".artdeco-dropdown__item:contains('Posts')"
                        ]
                        
                        for selector in posts_option_selectors:
                            try:
                                options = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                for option in options:
                                    if option.is_displayed() and "posts" in option.text.lower():
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", option)
                                        time.sleep(1)
                                        self.driver.execute_script("arguments[0].click();", option)
                                        posts_tab_clicked = True
                                        logging.info(f"Selected Posts option from dropdown with selector: {selector}")
                                        time.sleep(3)
                                        break
                                if posts_tab_clicked:
                                    break
                            except Exception as e:
                                logging.debug(f"Failed to click Posts option with selector {selector}: {str(e)}")
                except Exception as e:
                    logging.debug(f"Failed to use filter dropdown approach: {str(e)}")
            
            # Save a screenshot to debug
            self.driver.save_screenshot("after_search_before_posts_tab.png")
            logging.info("Saved screenshot before Posts tab click attempt")
            
            if not posts_tab_clicked:
                logging.warning("Could not click on Posts tab using any method. Taking a screenshot and saving page source for debugging.")
                self.save_page_source("failed_posts_tab_click.html")
            
            # Verify we're on the Posts results page and take a screenshot
            try:
                # Wait for posts to load
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".search-results__list, .reusable-search__result-container"))
                )
                logging.info("Posts results loaded successfully")
                
                # Save a screenshot after attempting to click on Posts tab
                screenshot_path = "after_posts_tab_click.png"
                self.driver.save_screenshot(screenshot_path)
                logging.info(f"Saved screenshot after Posts tab click to {screenshot_path}")
            except:
                logging.warning("Could not verify posts results loaded, continuing anyway")
            
            # Try to sort by recent posts
            try:
                # Click on sort dropdown
                sort_dropdown_selectors = [
                    "button.search-reusables__filter-trigger-and-dropdown",
                    "button[aria-label='Sort by']",
                    "button.artdeco-dropdown__trigger--is-dropdown-trigger",
                    "button.search-reusables__sort-dropdown-trigger",
                    "button.search-reusables__sort-filter",
                    ".search-reusables__primary-filter button[data-control-name='sort_dropdown']"
                ]
                
                sort_dropdown_found = False
                for selector in sort_dropdown_selectors:
                    try:
                        sort_buttons = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        for sort_button in sort_buttons:
                            if sort_button.is_displayed() and ("sort" in sort_button.text.lower() or "sort" in sort_button.get_attribute("aria-label").lower() if sort_button.get_attribute("aria-label") else False):
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sort_button)
                                time.sleep(1)
                                self.driver.execute_script("arguments[0].click();", sort_button)
                                sort_dropdown_found = True
                                logging.info(f"Clicked sort dropdown with selector: {selector}")
                                time.sleep(2)
                                break
                        if sort_dropdown_found:
                            break
                    except Exception as e:
                        logging.debug(f"Failed to click sort dropdown with selector {selector}: {str(e)}")
                
                if not sort_dropdown_found:
                    # Try XPath approach
                    sort_xpath_selectors = [
                        "//button[contains(text(), 'Sort by')]",
                        "//button[contains(@aria-label, 'Sort')]",
                        "//span[contains(text(), 'Sort')]/parent::button",
                        "//div[contains(@class, 'search-reusables')]//*[contains(text(), 'Sort')]"
                    ]
                    
                    for xpath in sort_xpath_selectors:
                        try:
                            sort_elements = self.driver.find_elements(By.XPATH, xpath)
                            for sort_element in sort_elements:
                                if sort_element.is_displayed():
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sort_element)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", sort_element)
                                    sort_dropdown_found = True
                                    logging.info(f"Clicked sort dropdown with XPath: {xpath}")
                                    time.sleep(2)
                                    break
                            if sort_dropdown_found:
                                break
                        except Exception as e:
                            logging.debug(f"Failed to click sort dropdown with XPath {xpath}: {str(e)}")
                
                # Click on "Recent" option
                if sort_dropdown_found:
                    recent_option_selectors = [
                        "button[aria-label='Recent']",
                        "button[aria-label='Sort by Recent']",
                        "button.search-reusables__sort-filter-subfilter[data-control-name='recent_sort']",
                        ".artdeco-dropdown__content button:nth-child(2)",
                        ".search-reusables__sort-filter-dropdown button:nth-child(2)",
                        "li.search-reusables__primary-filter button"
                    ]
                    
                    recent_option_found = False
                    for selector in recent_option_selectors:
                        try:
                            recent_options = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for option in recent_options:
                                if option.is_displayed() and "recent" in option.text.lower():
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", option)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", option)
                                    recent_option_found = True
                                    logging.info(f"Selected 'Recent' sort option with selector: {selector}")
                                    time.sleep(3)
                                    break
                            if recent_option_found:
                                break
                        except Exception as e:
                            logging.debug(f"Failed to click 'Recent' option with selector {selector}: {str(e)}")
                    
                    if not recent_option_found:
                        # Try XPath approach for Recent option
                        recent_xpath_selectors = [
                            "//button[contains(text(), 'Recent')]",
                            "//button[contains(@aria-label, 'Recent')]",
                            "//span[contains(text(), 'Recent')]/parent::button",
                            "//div[contains(@class, 'dropdown__content')]//*[contains(text(), 'Recent')]"
                        ]
                        
                        for xpath in recent_xpath_selectors:
                            try:
                                recent_elements = self.driver.find_elements(By.XPATH, xpath)
                                for element in recent_elements:
                                    if element.is_displayed():
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                        time.sleep(1)
                                        self.driver.execute_script("arguments[0].click();", element)
                                        recent_option_found = True
                                        logging.info(f"Selected 'Recent' sort option with XPath: {xpath}")
                                        time.sleep(3)
                                        break
                                if recent_option_found:
                                    break
                            except Exception as e:
                                logging.debug(f"Failed to click 'Recent' option with XPath {xpath}: {str(e)}")
                
                # Now try to filter for Past 24 hours
                try:
                    # Click on date posted filter
                    date_filter_selectors = [
                        "button[aria-label='Date posted filter']",
                        "button.search-reusables__filter-trigger-and-dropdown[aria-label='Date posted filter']",
                        ".search-reusables__filter-trigger-and-dropdown button[aria-controls*='date']",
                        ".artdeco-dropdown__trigger[aria-label*='Date']",
                        "button[data-control-name='filter_timePosted']"
                    ]
                    
                    date_filter_found = False
                    for selector in date_filter_selectors:
                        try:
                            date_filters = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for date_filter in date_filters:
                                if date_filter.is_displayed() and ("date" in date_filter.text.lower() or "date" in date_filter.get_attribute("aria-label").lower() if date_filter.get_attribute("aria-label") else False):
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", date_filter)
                                    time.sleep(1)
                                    self.driver.execute_script("arguments[0].click();", date_filter)
                                    date_filter_found = True
                                    logging.info(f"Clicked date filter dropdown with selector: {selector}")
                                    time.sleep(2)
                                    break
                            if date_filter_found:
                                break
                        except Exception as e:
                            logging.debug(f"Failed to click date filter with selector {selector}: {str(e)}")
                    
                    if not date_filter_found:
                        # Try XPath approach for date filter
                        date_xpath_selectors = [
                            "//button[contains(text(), 'Date posted')]",
                            "//button[contains(@aria-label, 'Date')]",
                            "//span[contains(text(), 'Date')]/parent::button",
                            "//div[contains(@class, 'search-reusables')]//*[contains(text(), 'Date')]"
                        ]
                        
                        for xpath in date_xpath_selectors:
                            try:
                                date_elements = self.driver.find_elements(By.XPATH, xpath)
                                for element in date_elements:
                                    if element.is_displayed():
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                        time.sleep(1)
                                        self.driver.execute_script("arguments[0].click();", element)
                                        date_filter_found = True
                                        logging.info(f"Clicked date filter dropdown with XPath: {xpath}")
                                        time.sleep(2)
                                        break
                                if date_filter_found:
                                    break
                            except Exception as e:
                                logging.debug(f"Failed to click date filter with XPath {xpath}: {str(e)}")
                    
                    # Click on "Past 24 hours" option
                    if date_filter_found:
                        past24_selectors = [
                            "button[aria-label='Past 24 hours']",
                            "button.search-reusables__filter-value-item[data-control-name='timePosted_past-24']",
                            ".artdeco-dropdown__content li:first-child button",
                            ".search-reusables__dropdown-list li:first-child button",
                            "button[data-control-name='filter_timePosted_24h']"
                        ]
                        
                        past24_found = False
                        for selector in past24_selectors:
                            try:
                                past24_options = self.driver.find_elements(By.CSS_SELECTOR, selector)
                                for option in past24_options:
                                    if option.is_displayed() and ("24" in option.text.lower() or "day" in option.text.lower()):
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", option)
                                        time.sleep(1)
                                        self.driver.execute_script("arguments[0].click();", option)
                                        past24_found = True
                                        logging.info(f"Selected 'Past 24 hours' option with selector: {selector}")
                                        time.sleep(3)
                                        break
                                if past24_found:
                                    break
                            except Exception as e:
                                logging.debug(f"Failed to click 'Past 24 hours' option with selector {selector}: {str(e)}")
                        
                        if not past24_found:
                            # Try XPath approach for Past 24 hours option
                            past24_xpath_selectors = [
                                "//button[contains(text(), 'Past 24')]",
                                "//button[contains(text(), '24 hours')]",
                                "//button[contains(@aria-label, 'Past 24')]",
                                "//span[contains(text(), 'Past 24')]/parent::button",
                                "//div[contains(@class, 'dropdown__content')]//*[contains(text(), 'Past 24')]"
                            ]
                            
                            for xpath in past24_xpath_selectors:
                                try:
                                    past24_elements = self.driver.find_elements(By.XPATH, xpath)
                                    for element in past24_elements:
                                        if element.is_displayed():
                                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                            time.sleep(1)
                                            self.driver.execute_script("arguments[0].click();", element)
                                            past24_found = True
                                            logging.info(f"Selected 'Past 24 hours' option with XPath: {xpath}")
                                            time.sleep(3)
                                            break
                                    if past24_found:
                                        break
                                except Exception as e:
                                    logging.debug(f"Failed to click 'Past 24 hours' option with XPath {xpath}: {str(e)}")
                except Exception as e:
                    logging.warning(f"Failed to filter for Past 24 hours: {str(e)}")
            except Exception as e:
                logging.warning(f"Failed to sort by recent posts: {str(e)}")
            
            posts_processed = 0
            max_scrolls = 100
            scroll_count = 0
            
            processed_post_ids = set()
            
            print("\nStarting continuous search mode - press Ctrl+C to stop")
            
            while scroll_count < max_scrolls:
                # Get all visible posts
                try:
                    # Try different post selectors
                    post_selectors = [
                        ".feed-shared-update-v2",
                        ".search-result__occluded-item",
                        ".search-results__list-item",
                        ".ember-view.occludable-update",
                        ".search-content__result",
                        "li.reusable-search__result-container",
                        "div.feed-shared-update-v2__content",
                        "div[data-urn]",
                        "div.relative.ember-view"
                    ]
                    
                    posts = []
                    for selector in post_selectors:
                        found_posts = self.driver.find_elements(By.CSS_SELECTOR, selector)
                        if found_posts:
                            posts = found_posts
                            logging.info(f"Found {len(posts)} posts with selector: {selector}")
                            break
                    
                    if not posts:
                        logging.warning("No posts found. Trying to scroll...")
                    else:
                        logging.info(f"Processing {len(posts)} posts")
                        
                        # Process each post
                        for post in posts:
                            try:
                                post_id = self.get_post_identifier(post)
                                if post_id and post_id not in processed_post_ids:
                                    processed_post_ids.add(post_id)
                                    if self.process_post(post):
                                        print("\nSuccessfully processed post!")
                                        posts_processed += 1
                                        self.save_response_history()
                            except StaleElementReferenceException:
                                logging.warning("Encountered stale element, skipping post")
                                continue
                
                    # Scroll to load more
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    logging.info(f"Scrolled to load more posts (scroll {scroll_count + 1}/{max_scrolls})")
                    time.sleep(3)
                    scroll_count += 1
                    
                except Exception as e:
                    logging.error(f"Error processing posts: {str(e)}")
                    scroll_count += 1
                    continue

            if posts_processed == 0:
                print("\nNo posts with emails were found. Try adjusting the search terms or scrolling more.")

            print(f"\nCompleted search with {posts_processed} posts processed. Restarting search...")
            time.sleep(10)  # Wait a bit before restarting
            self.search_and_process_posts(search_term, max_posts)

        except KeyboardInterrupt:
            print("\nSearch stopped by user")
            return
        except Exception as e:
            logging.error(f"Error in search and process: {str(e)}")
            time.sleep(30)  # Wait longer on error
            self.search_and_process_posts(search_term, max_posts)

    def generate_email_content(self, post_details):
        """Generate email content using ChatGPT"""
        if not self.openai_client:
            raise Exception("OpenAI client not initialized")

        # Load config to get user details
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            user_email = config.get('gmail_email', '')
            # Add phone number to config if it doesn't exist
            user_phone = config.get('user_phone', 'Your Phone Number')
            user_name = config.get('user_name', 'Your Full Name')
        except Exception as e:
            logging.warning(f"Could not load user details from config: {str(e)}")
            user_email = self.email
            user_phone = "Your Phone Number"
            user_name = "Your Full Name"

        # Load resume content if available
        resume_content = ""
        resume_paths = ['resume.txt', 'resume.md', 'resume.docx', 'resume.pdf']
        
        for path in resume_paths:
            if os.path.exists(path):
                try:
                    if path.endswith('.txt') or path.endswith('.md'):
                        with open(path, 'r', encoding='utf-8') as f:
                            resume_content = f.read()
                            logging.info(f"Loaded resume from {path}")
                            break
                    # For other formats, just note that we found it but can't read it directly
                    else:
                        resume_content = f"Resume found at {path} but content cannot be read directly."
                        logging.info(f"Found resume at {path} but content cannot be read directly")
                        break
                except Exception as e:
                    logging.warning(f"Could not read resume from {path}: {str(e)}")

        # Determine if this is a contract/C2C position
        position_type = "Contract/C2C" if post_details.get('is_contract', False) else "Full-time"

        prompt = f"""
        Write a professional email response to a Java Developer {position_type} opportunity.
        
        Post Author: {post_details['author']}
        Post Content: {post_details['content']}
        Job Description: {post_details.get('job_description', 'Not provided')}
        
        My Resume Information:
        {resume_content if resume_content else "Not provided, please use general Java developer experience"}
        
        Requirements:
        1. Personalize based on the post content and job description
        2. Keep it concise but professional
        3. Express genuine interest in the opportunity
        4. Highlight relevant Java development experience that matches the requirements mentioned in the job description
        5. Emphasize that I am available for {position_type} roles
        6. End with a call to action
        7. Reference specific skills and requirements mentioned
        8. Include company name and location if mentioned
        9. Include my contact information at the end: Phone: {user_phone}, Email: {user_email}
        10. Sign the email with my name: {user_name}
        
        Format:
        Subject: [Your subject line]
        
        [Your email body]
        
        [Include my contact information and name at the end]
        """

        try:
            response = self.openai_client.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a professional job seeker writing an email response to a LinkedIn post for a contract/C2C position."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=500
            )

            email_content = response.choices[0].message['content'].strip()
            
            return email_content

        except Exception as e:
            logging.error(f"Error generating email content: {str(e)}")
            return None

    def draft_and_send_email(self, post_data, sender_email, sender_password):
        """Draft and send an email response"""
        try:
            # Generate email content
            email_content = self.generate_email_content(post_data)
            if not email_content:
                return False
            
            # Parse the email content
            lines = email_content.strip().split('\n')
            subject_line = next((line for line in lines if line.startswith('Subject:')), None)
            if subject_line:
                subject = subject_line.replace('Subject:', '').strip()
            else:
                subject = f"Regarding your Java Developer opportunity"
            
            # Extract the body (everything after the subject line)
            start_idx = 0
            for i, line in enumerate(lines):
                if line.startswith('Subject:'):
                    start_idx = i + 1
                    break
            
            body = '\n'.join(lines[start_idx:]).strip()
            
            # Show the draft
            print("\nGenerated Email:")
            print(f"To: {post_data['emails'][0]}")
            print(f"Subject: {subject}")
            print(f"\nBody:\n{body}")
            
            # Auto-send email without confirmation
            print("\nAutomatically sending email...")
            
            # Connect to Gmail SMTP server
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, sender_password)
            
            # Create email message
            msg = MIMEMultipart()
            msg['From'] = sender_email
            msg['To'] = post_data['emails'][0]
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # Send email
            server.send_message(msg)
            server.quit()

            logging.info(f"Email sent successfully to {post_data['emails'][0]}")
            print(f"\nEmail sent successfully to {post_data['emails'][0]}")
            return True

        except Exception as e:
            logging.error(f"Error sending email: {str(e)}")
            print(f"\nError sending email: {str(e)}")
            return False

    def close(self):
        """Close the browser"""
        if self.driver:
            self.driver.quit()

def load_config():
    """Load credentials from config file"""
    config_file = 'config.json'
    if not os.path.exists(config_file):
        default_config = {
            "linkedin_email": "",
            "linkedin_password": "",
            "gmail_email": "",
            "gmail_app_password": "",
            "openai_api_key": ""
        }
        with open(config_file, 'w') as f:
            json.dump(default_config, f, indent=4)
        print(f"Please fill in your credentials in {config_file}")
        return None
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    if any(not value for value in config.values()):
        print(f"Please fill in all credentials in {config_file}")
        return None
    
    return config

def main():
    # Load configuration
    config = load_config()
    if not config:
        return
    
    # Initialize the automation
    bot = LinkedInPostAutomation()
    
    try:
        # Store email credentials
        bot.email = config['gmail_email']
        bot.password = config['gmail_app_password']
        
        # Setup OpenAI
        bot.setup_openai(config['openai_api_key'])
        
        # Setup and login
        bot.setup_driver()
        bot.login_to_linkedin(config['linkedin_email'], config['linkedin_password'])
        
        # Search and process posts
        bot.search_and_process_posts("java developer")
        
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        print(f"An error occurred: {str(e)}")
    
    finally:
        bot.close()

if __name__ == "__main__":
    main()
